"""추세추종 규칙 지표 재료 → macro.db.  계산식은 docs(대시보드 저장소 docs/macro-plan.md §12)와 화면 '추세추종' 탭에 적었다.

  python3 collect_trend.py          # 매일 (클라우드): 지수 종가·거래량, S&P500 종목 일봉 덧붙이기, 최근 두 달치 폭 계산
  python3 collect_trend.py --seed   # 맥에서 한 번: 2010년~ 전체 이력을 계산해 seed_trend.json.gz 로 저장 (저장소에 넣으면 클라우드가 빈 날짜만 채운다)

쌓는 것
  tf:c:<지수> · tf:v:<지수>       S&P500·나스닥·KOSPI·KOSDAQ 종가·거래량 (야후, 장이 덜 끝난 오늘 값은 버린다) — 분산일·팔로스루·단계는 build4.py 가 계산
  tf:kr:tt · tf:us:tt             미너비니 트렌드 템플릿 8조건(RS 포함)을 모두 통과한 종목 비율 (%)
  tf:kr:st2 · st4 · tf:us:…       와인스타인 2단계(150일선 위 + 150일선 상승)·4단계(아래 + 하락) 종목 비율 (%)
  blob 'trend_lists'              마지막 날 통과 종목 목록(한국: 시총·업종, 미국: 업종)
미국 종목은 지금의 S&P500 구성 종목이라 과거 값에는 생존 편향이 있다(빠진 종목은 없다).
"""
import gzip
import io
import json
import sys
import time
import warnings
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd

import config
import store

warnings.filterwarnings('ignore')
IDX = [('spx', '^GSPC', 'S&P500', 'us'), ('ndx', '^IXIC', '나스닥', 'us'), ('kospi', '^KS11', 'KOSPI', 'kr'), ('kosdaq', '^KQ11', 'KOSDAQ', 'kr')]
US_DAYS = 420                      # us_px 에 남겨 둘 거래일 (트렌드 템플릿은 273일이면 된다)
SEED = config.ROOT / 'seed_trend.json.gz'
KST, ET = timezone(timedelta(hours=9)), timezone(timedelta(hours=-5))
SCHEMA = """
CREATE TABLE IF NOT EXISTS us_px (date TEXT, code TEXT, close REAL, PRIMARY KEY (date, code)) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS us_name (code TEXT PRIMARY KEY, name TEXT, sector TEXT);
CREATE TABLE IF NOT EXISTS blob (key TEXT PRIMARY KEY, date TEXT, json TEXT);
"""
META = dict(grp='추세추종', source='자체 계산', freq='매일', use='흐름,타이밍', diff=1, dec=1)


def unfinished(d, mkt):
    """d(YYYY-MM-DD)가 그 시장의 오늘이고 아직 장이 안 끝났으면 True (미국 동부 16:15, 한국 15:45 — 서머타임은 무시해도 1시간 늦게 볼 뿐)"""
    now = datetime.now(ET if mkt == 'us' else KST)
    close = (16, 15) if mkt == 'us' else (15, 45)
    return d == now.strftime('%Y-%m-%d') and (now.hour, now.minute) < close


def indices(c, yf):
    full = (c.execute("SELECT count(*) FROM series WHERE key='tf:c:spx'").fetchone()[0] or 0) < 1000
    d = yf.download([t for _, t, _, _ in IDX], interval='1d', progress=False, auto_adjust=True, threads=True, **({'start': '2005-01-01'} if full else {'period': '6mo'}))
    n = 0
    for key, tk, name, mkt in IDX:
        cl, vo = d['Close'][tk].dropna(), d['Volume'][tk]
        rows = [(str(i.date()), float(v), float(vo.get(i, np.nan))) for i, v in cl.items()]
        if rows and unfinished(rows[-1][0], mkt):
            rows = rows[:-1]
        n += store.put(c, f'tf:c:{key}', [(a, b) for a, b, _ in rows], name=f'{name} 종가 (추세추종용)', unit='', **{**META, 'dec': 2, 'diff': 0, 'source': 'Yahoo Finance'})
        n += store.put(c, f'tf:v:{key}', [(a, v) for a, _, v in rows if v and v > 0], name=f'{name} 거래량', unit='', **{**META, 'dec': 0, 'diff': 0, 'source': 'Yahoo Finance'})
    c.commit()
    return n


# ── 종목 폭: 트렌드 템플릿·단계 ──
def template(p, chunk=500):
    """p: 날짜 × 종목 종가. → (날짜별 비율 DataFrame, 마지막 날 종목별 DataFrame)"""
    p = p.sort_index().astype('float32')
    ret = lambda n: p / p.shift(n) - 1
    score = 0.4 * ret(63) + 0.2 * ret(126) + 0.2 * ret(189) + 0.2 * ret(252)      # IBD 식 RS: 최근 분기에 두 배 가중
    rs = (score.rank(axis=1, pct=True) * 99).astype('float32')
    del score
    tot = {k: 0 for k in ('n', 'tt', 'st2', 'st4')}
    lastrows = []
    for i in range(0, p.shape[1], chunk):
        q, R = p.iloc[:, i:i + chunk], rs.iloc[:, i:i + chunk]
        m50, m150, m200 = q.rolling(50).mean(), q.rolling(150).mean(), q.rolling(200).mean()
        hi, lo = q.rolling(250, min_periods=240).max(), q.rolling(250, min_periods=240).min()
        valid = m200.shift(21).notna() & R.notna() & hi.notna() & q.notna()
        ok = (q > m150) & (q > m200) & (m150 > m200) & (m200 > m200.shift(21)) & (m50 > m150) & (m50 > m200) & (q > m50) & (q >= lo * 1.3) & (q >= hi * 0.75) & (R >= 70) & valid
        up150 = m150 > m150.shift(20)
        st2, st4 = (q > m150) & up150 & valid, (q < m150) & ~up150 & valid
        tot['n'] = tot['n'] + valid.sum(axis=1)
        tot['tt'] = tot['tt'] + ok.sum(axis=1)
        tot['st2'] = tot['st2'] + st2.sum(axis=1)
        tot['st4'] = tot['st4'] + st4.sum(axis=1)
        L = pd.DataFrame({'pass': ok.iloc[-1], 'valid': valid.iloc[-1], 'rs': R.iloc[-1], 'px': q.iloc[-1],
                          'hi': (q.iloc[-1] / hi.iloc[-1] - 1) * 100, 'lo': (q.iloc[-1] / lo.iloc[-1] - 1) * 100,
                          'm50': (q.iloc[-1] / m50.iloc[-1] - 1) * 100, 'st': np.where(st2.iloc[-1], 2, np.where(st4.iloc[-1], 4, 0))})
        lastrows.append(L)
    n = tot['n'].replace(0, np.nan)
    out = pd.DataFrame({'tt': tot['tt'] / n * 100, 'st2': tot['st2'] / n * 100, 'st4': tot['st4'] / n * 100, 'n': tot['n']})
    out = out[out.n >= max(50, out.n.max() * 0.5)]             # 창이 덜 찬 앞부분은 버린다
    return out, pd.concat(lastrows)


def put_breadth(c, mkt, out, only_tail=None):
    nm = {'kr': '한국 보통주', 'us': 'S&P500 종목'}[mkt]
    o = out if only_tail is None else out.tail(only_tail)
    rows = 0
    for k, label in (('tt', f'트렌드 템플릿 통과 비율 — {nm}'), ('st2', f'와인스타인 2단계 비율 — {nm}'), ('st4', f'와인스타인 4단계 비율 — {nm}')):
        rows += store.put(c, f'tf:{mkt}:{k}', [(d, round(float(v), 2)) for d, v in o[k].items()], name=label, unit='%', **META)
    return rows


def kr_breadth(c, seed=False):
    import collect_breadth as cb
    if config.STANDALONE:
        df, names, _, sector = cb.load_own(c)
    else:
        df, names, _, sector = cb.load('2009-01-01' if seed else (datetime.now() - timedelta(days=560)).strftime('%Y-%m-%d'))
    p = df.pivot_table(index='date', columns='code', values='close', aggfunc='last')
    out, L = template(p)
    mcap = df.dropna(subset=['mcap']).sort_values('date').groupby('code').mcap.last()
    L = L[L['pass'].astype(bool)]
    lst = [{'c': x, 'n': names.name.get(x, x), 'm': names.market.get(x, ''), 'sec': sector.get(x) if x in sector.index else None,
            'mc': None if pd.isna(mcap.get(x)) else round(float(mcap[x])), 'rs': int(round(float(L.rs[x]))), 'hi': round(float(L.hi[x]), 1),
            'lo': round(float(L.lo[x]), 0), 'm50': round(float(L.m50[x]), 1)} for x in L.index]
    return out, lst, p.index[-1]


def us_list(c):
    import requests
    try:
        h = requests.get('https://en.wikipedia.org/wiki/List_of_S%26P_500_companies', headers={'User-Agent': 'Mozilla/5.0 (macro-dashboard)'}, timeout=30)
        t = pd.read_html(io.StringIO(h.text))[0]
        rows = [(str(s).replace('.', '-'), n, g) for s, n, g in zip(t['Symbol'], t['Security'], t['GICS Sector'])]
        if len(rows) > 450:
            c.execute('DELETE FROM us_name')
            c.executemany('INSERT OR REPLACE INTO us_name VALUES (?,?,?)', rows)
            c.commit()
    except Exception as e:
        print('trend: S&P500 목록을 못 받음 — 저장된 목록을 쓴다', type(e).__name__)
    return [r[0] for r in c.execute('SELECT code FROM us_name')]


def us_download(yf, codes, **kw):
    frames = []
    for i in range(0, len(codes), 100):
        part = codes[i:i + 100]
        for attempt in range(2):
            try:
                d = yf.download(part, interval='1d', progress=False, auto_adjust=True, threads=True, **kw)['Close']
                frames.append(d if hasattr(d, 'columns') else d.to_frame(part[0]))
                break
            except Exception:
                time.sleep(10)
        time.sleep(1)
    p = pd.concat(frames, axis=1) if frames else pd.DataFrame()
    p.index = [str(i.date()) for i in p.index]
    p = p.loc[:, ~p.columns.duplicated()].dropna(how='all')
    if len(p) and unfinished(p.index[-1], 'us'):
        p = p.iloc[:-1]
    return p


def us_breadth(c, yf, seed=False):
    codes = us_list(c)
    if seed:
        p = us_download(yf, codes, start='2005-01-01')
    else:
        days = c.execute('SELECT count(DISTINCT date), max(date) FROM us_px').fetchone()
        spx_last = c.execute("SELECT max(date) FROM series WHERE key='tf:c:spx'").fetchone()[0]
        if (days[0] or 0) < 300:
            new = us_download(yf, codes, period='2y')
        elif days[1] < (spx_last or ''):
            new = us_download(yf, codes, period='1mo')
        else:
            new = None
        if new is not None and len(new):
            rows = [(d, code, float(v)) for code in new.columns for d, v in new[code].dropna().items()]
            c.executemany('INSERT OR REPLACE INTO us_px VALUES (?,?,?)', rows)
            c.commit()
        p = pd.read_sql('SELECT date, code, close FROM us_px', c).pivot(index='date', columns='code', values='close')
        p = p[[x for x in p.columns if x in set(codes)]]
    if seed:      # us_px 에는 최근 것만 넣어 둔다
        tail = p.tail(US_DAYS)
        c.executemany('INSERT OR REPLACE INTO us_px VALUES (?,?,?)', [(d, code, float(v)) for code in tail.columns for d, v in tail[code].dropna().items()])
    dates = [r[0] for r in c.execute('SELECT DISTINCT date FROM us_px ORDER BY date DESC LIMIT ?', (US_DAYS + 1,))]
    if len(dates) > US_DAYS:
        c.execute('DELETE FROM us_px WHERE date<?', (dates[US_DAYS - 1],))
    c.commit()
    out, L = template(p)
    nm = {code: (n, s) for code, n, s in c.execute('SELECT code, name, sector FROM us_name')}
    L = L[L['pass'].astype(bool)]
    lst = [{'c': x, 'n': nm.get(x, (x, None))[0], 'sec': nm.get(x, (x, None))[1], 'rs': int(round(float(L.rs[x]))), 'hi': round(float(L.hi[x]), 1),
            'lo': round(float(L.lo[x]), 0), 'm50': round(float(L.m50[x]), 1)} for x in L.index]
    return out, lst, p.index[-1]


def merge_seed(c):
    """저장소의 seed_trend.json.gz(맥에서 계산한 과거 이력)로 DB 에 없는 날짜만 채운다"""
    if not SEED.exists():
        return 0
    S = json.loads(gzip.decompress(SEED.read_bytes()))
    n = 0
    for key, rows in S['series'].items():
        have = {r[0] for r in c.execute('SELECT date FROM series WHERE key=?', (key,))}
        new = [(d, v) for d, v in rows if d not in have]
        if new:
            n += store.put(c, key, new)
    c.commit()
    return n


def main():
    import yfinance as yf
    seed = '--seed' in sys.argv
    c = store.connect()
    c.executescript(SCHEMA)
    msg, ok = [], True
    try:
        msg.append(f'지수 {indices(c, yf)}행')
    except Exception as e:
        ok = False
        msg.append(f'지수 실패 {type(e).__name__}: {str(e)[:80]}')
    lists, hist = {}, {}
    for mkt, fn in (('kr', lambda: kr_breadth(c, seed)), ('us', lambda: us_breadth(c, yf, seed))):
        try:
            out, lst, last = fn()
            if seed:
                hist.update({f'tf:{mkt}:{k}': [[d, round(float(v), 2)] for d, v in out[k].items()] for k in ('tt', 'st2', 'st4')})
            rows = put_breadth(c, mkt, out, None if seed else 60)
            lst.sort(key=lambda x: -x['rs'])
            lists[mkt] = {'asof': last, 'n': int(out.n.iloc[-1]), 'pass': len(lst), 'rows': lst}
            msg.append(f'{mkt} {rows}행·통과 {len(lst)}/{int(out.n.iloc[-1])} ({last})')
        except Exception as e:
            ok = False
            msg.append(f'{mkt} 실패 {type(e).__name__}: {str(e)[:80]}')
    if lists:
        old = c.execute("SELECT json FROM blob WHERE key='trend_lists'").fetchone()
        old = json.loads(old[0]) if old else {}
        old.update(lists)
        c.execute('INSERT OR REPLACE INTO blob VALUES (?,?,?)', ('trend_lists', max(v['asof'] for v in old.values()), json.dumps(old, ensure_ascii=False)))
    if seed:
        SEED.write_bytes(gzip.compress(json.dumps({'made': datetime.now().strftime('%Y-%m-%d'), 'series': hist}, separators=(',', ':')).encode()))
        msg.append(f'seed {SEED.name} {SEED.stat().st_size // 1024}KB')
    else:
        m = merge_seed(c)
        if m:
            msg.append(f'과거 이력 {m}행 채움')
    c.commit()
    store.log(c, 'trend', ok, ' · '.join(msg))
    print('trend:', ' · '.join(msg))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
