"""기존 대시보드 DB(읽기 전용)에서 macro.db 가 혼자 돌 때 필요한 것만 옮긴다. 맥에서만 돈다(클라우드에는 그 DB 가 없다).

  python3 seed.py     # 다시 돌려도 된다(덮어쓴다)

옮기는 것
  kr_px    전 종목 일봉(종가·등락률·시총·거래량·거래대금): 최근 330거래일은 전부, 시총 상위 400종목은 780거래일, 페어·공매도 종목은 2012년부터
  kr_name  종목 이름·시장          kr_sector  업종          kr_flow  주체별 순매수 수량(최근 150일, 평단 계산용)
그 뒤로는 KRX Open API(전 종목 일별, 다음 날 아침)와 한국투자증권 API(주체별 순매수)가 매일 덧붙인다.
"""
import sqlite3
import sys

import config
import store
from collect_deriv import PAIRS

SCHEMA = """
CREATE TABLE IF NOT EXISTS kr_px (date TEXT, code TEXT, close REAL, chg REAL, mcap REAL, volume REAL, tv REAL, PRIMARY KEY (date, code)) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS kr_name (code TEXT PRIMARY KEY, name TEXT, market TEXT);
CREATE TABLE IF NOT EXISTS kr_sector (code TEXT PRIMARY KEY, sector TEXT);
CREATE TABLE IF NOT EXISTS kr_flow (date TEXT, code TEXT, frgn REAL, org REAL, ind REAL, PRIMARY KEY (date, code)) WITHOUT ROWID;
"""
ALL_DAYS, TOP_DAYS, TOP_N = 330, 780, 400


def schema(c):
    c.executescript(SCHEMA)
    if 'tv' not in [r[1] for r in c.execute('PRAGMA table_info(kr_px)')]:
        c.execute('ALTER TABLE kr_px ADD COLUMN tv REAL')


def long_codes(c):
    """오래 두는 종목: 페어에 든 종목 + 공매도를 받는 종목"""
    codes = {x for _, a, b, _ in PAIRS for x in (a, b) if len(x) == 6}
    try:
        codes |= {r[0] for r in c.execute('SELECT DISTINCT code FROM short_daily')}
    except sqlite3.OperationalError:
        pass
    return sorted(codes)


def prune(c):
    """오래된 일봉 지우기: 전 종목은 330거래일, 시총 상위 400은 780거래일, 페어·공매도 종목은 그대로 둔다"""
    days = [r[0] for r in c.execute('SELECT DISTINCT date FROM kr_px ORDER BY date DESC LIMIT ?', (TOP_DAYS + 1,))]
    if len(days) <= ALL_DAYS:
        return 0
    keep = long_codes(c)
    top = [r[0] for r in c.execute('SELECT code FROM kr_px WHERE date=? ORDER BY mcap DESC LIMIT ?', (days[0], TOP_N))]
    q = lambda xs: ','.join('?' * len(xs))
    n = c.execute(f'DELETE FROM kr_px WHERE date<? AND code NOT IN ({q(keep + top)})', (days[ALL_DAYS - 1], *keep, *top)).rowcount
    if len(days) > TOP_DAYS:
        n += c.execute(f'DELETE FROM kr_px WHERE date<? AND code NOT IN ({q(keep)})', (days[TOP_DAYS - 1], *keep)).rowcount
    return n


def main():
    if not config.HIST_DB.exists():
        print('seed: 기존 대시보드 DB 가 없다 (맥에서만 돈다)')
        return 1
    c = store.connect()
    schema(c)
    c.execute('ATTACH DATABASE ? AS h', (f'file:{config.HIST_DB}?mode=ro',))
    c.execute('ATTACH DATABASE ? AS d', (f'file:{config.DASH_DB}?mode=ro',))
    days = [r[0] for r in c.execute('SELECT DISTINCT date FROM h.hp ORDER BY date DESC LIMIT ?', (TOP_DAYS,))]
    cut_all, cut_top, last = days[ALL_DAYS - 1], days[-1], days[0]
    keep = long_codes(c)
    top = [r[0] for r in c.execute('SELECT code FROM h.hp WHERE date=? ORDER BY mcap DESC LIMIT ?', (last, TOP_N))]
    q = lambda xs: ','.join('?' * len(xs))
    cols = 'date, code, close, chg, mcap, volume, tv'
    n = c.execute(f'INSERT OR REPLACE INTO kr_px ({cols}) SELECT {cols} FROM h.hp WHERE date>=? AND close>0', (cut_all,)).rowcount
    n += c.execute(f'INSERT OR REPLACE INTO kr_px ({cols}) SELECT {cols} FROM h.hp WHERE date>=? AND date<? AND close>0 AND code IN ({q(top)})', (cut_top, cut_all, *top)).rowcount
    n += c.execute(f"INSERT OR REPLACE INTO kr_px ({cols}) SELECT {cols} FROM h.hp WHERE date>='2012-01-01' AND date<? AND close>0 AND code IN ({q(keep)})", (cut_all, *keep)).rowcount
    # 과거 DB 에 아직 안 들어온 최근 날: 대시보드의 최근 일봉(시총·거래대금 없음). KRX 에서 이미 받은 날은 건드리지 않는다
    n += c.execute('INSERT OR IGNORE INTO kr_px (date, code, close, chg, volume) SELECT date, code, close, chg, volume FROM d.ohlc_daily WHERE date>? AND close>0', (last,)).rowcount
    c.execute('INSERT OR REPLACE INTO kr_name SELECT code, name, market FROM h.hname')
    c.execute('INSERT OR REPLACE INTO kr_sector SELECT code, name FROM d.naver_sector')
    fdays = [r[0] for r in c.execute('SELECT DISTINCT date FROM d.flow_daily ORDER BY date DESC LIMIT 150')]
    nf = c.execute('INSERT OR REPLACE INTO kr_flow SELECT date, code, frgn, org, ind FROM d.flow_daily WHERE date>=?', (fdays[-1],)).rowcount
    c.commit()
    gone = prune(c)
    c.commit()
    c.execute('DETACH DATABASE h')
    c.execute('DETACH DATABASE d')
    tot = c.execute('SELECT count(*), count(DISTINCT code), min(date), max(date) FROM kr_px').fetchone()
    store.log(c, 'seed', True, f'일봉 {n}행, 수급 {nf}행')
    print(f'seed: 일봉 {n}행 옮김(지움 {gone}) → kr_px {tot[0]}행·{tot[1]}종목·{tot[2]}~{tot[3]} · 이름 {c.execute("SELECT count(*) FROM kr_name").fetchone()[0]} · 업종 {c.execute("SELECT count(*) FROM kr_sector").fetchone()[0]} · 수급 {nf}행')
    return 0


if __name__ == '__main__':
    sys.exit(main())
