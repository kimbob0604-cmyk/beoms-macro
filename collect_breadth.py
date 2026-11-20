"""한국 시장 폭 지표: 종목 일봉으로 ADR·볼밴·RSI·신고가/신저가·이평선 위 비율을 계산해 macro.db 에,
업종별 과매도 지도와 종목 목록은 public/data/kr_sector.json 에 쓴다.

종목 일봉은 두 군데서 온다. 맥(기존 대시보드 DB 가 있을 때): 그 DB 를 읽기만 한다.
혼자 돌 때(클라우드, 또는 MACRO_STANDALONE=1): macro.db 의 kr_px(seed.py 가 옮겨 두고 KRX Open API 가 매일 덧붙인다)만 쓴다 —
최근 330거래일로 계산해 마지막 70일쯤만 덮어쓴다(그 앞은 이미 계산돼 있다).

  python3 collect_breadth.py          # 최근 약 2년치만 다시 계산 (매일)
  python3 collect_breadth.py --full   # 2010년부터 전부 (처음 한 번, 1~2분)

보통주만(코드 끝자리 0), 스팩 제외. 정의는 지표 사전(glossary.py) 참고.
"""
import json
import sqlite3
import sys
from datetime import date, timedelta

import numpy as np
import pandas as pd

import config
import store

NAMES = {
    'kr:adr20': ('ADR (20일 등락비율)', '%', 1), 'kr:adr20:kospi': ('ADR 20일 — KOSPI', '%', 1), 'kr:adr20:kosdaq': ('ADR 20일 — KOSDAQ', '%', 1),
    'kr:bblow': ('볼밴 하단 이탈 종목 비율', '%', 1), 'kr:bbup': ('볼밴 상단 돌파 종목 비율', '%', 1),
    'kr:rsi30': ('RSI 30 미만 종목 비율', '%', 1), 'kr:rsi70': ('RSI 70 초과 종목 비율', '%', 1),
    'kr:nl': ('52주 신저가 종목 비율', '%', 1), 'kr:nh': ('52주 신고가 종목 비율', '%', 1),
    'kr:ma60': ('60일선 위 종목 비율', '%', 1), 'kr:ma200': ('200일선 위 종목 비율', '%', 1),
}


def load_own(c):
    """혼자 돌 때: macro.db 의 kr_px·kr_name·kr_sector 로"""
    import seed
    seed.schema(c)
    days = [r[0] for r in c.execute('SELECT DISTINCT date FROM kr_px ORDER BY date DESC LIMIT ?', (seed.ALL_DAYS,))]
    if len(days) < 280:
        raise RuntimeError('kr_px 가 비어 있다 — 맥에서 python3 seed.py 를 먼저 돌려 DB 를 올려야 한다')
    krx_topup(days[min(6, len(days) - 1)])              # 최근 며칠 중 KRX 에서 아직 못 받은 날을 채운다
    df = pd.read_sql('SELECT date, code, close, chg, mcap FROM kr_px WHERE date>=? AND (volume>0 OR volume IS NULL) AND close>0', c, params=(days[-1],))
    names = pd.read_sql('SELECT code, name, market FROM kr_name', c)
    sector = pd.read_sql('SELECT code, sector FROM kr_sector', c)
    names = names[names.market.isin(['KOSPI', 'KOSDAQ']) & names.code.str.endswith('0') & ~names.name.fillna('').str.contains('스팩')]
    df = df[df.code.isin(names.code)]
    return df, names.set_index('code'), None, sector.set_index('code').sector


def load(start):
    h = sqlite3.connect(f'file:{config.HIST_DB}?mode=ro', uri=True)
    df = pd.read_sql('SELECT date, code, close, chg, mcap FROM hp WHERE date>=? AND volume>0', h, params=(start,))
    names = pd.read_sql('SELECT code, name, market FROM hname', h)
    idx = pd.read_sql('SELECT code, date, close FROM hidx', h)
    last = df.date.max()
    d = sqlite3.connect(f'file:{config.DASH_DB}?mode=ro', uri=True)
    top = pd.read_sql('SELECT date, code, close, chg FROM ohlc_daily WHERE date>? AND volume>0', d, params=(last,))   # 과거 DB 에 아직 안 들어온 최근 날
    top['mcap'] = np.nan
    idx2 = pd.read_sql('SELECT code, date, close FROM index_daily WHERE code IN ("KOSPI","KOSDAQ")', d)
    sector = pd.read_sql('SELECT code, name AS sector FROM naver_sector', d)
    df = pd.concat([df, top], ignore_index=True) if len(top) else df
    own = krx_topup(df.date.max())                      # 기존 DB 에 아직 없는 날은 KRX Open API 로 직접 (전일분은 다음 날 아침 8시쯤 나온다)
    if len(own):
        df = pd.concat([df, own], ignore_index=True)
    idx = pd.concat([idx, idx2]).drop_duplicates(['code', 'date'], keep='first')
    names = names[names.market.isin(['KOSPI', 'KOSDAQ']) & names.code.str.endswith('0') & ~names.name.fillna('').str.contains('스팩')]
    df = df[df.code.isin(names.code)]
    return df, names.set_index('code'), idx, sector.set_index('code').sector


def krx_topup(last):
    """last(YYYY-MM-DD) 뒤의 평일을 KRX Open API 전 종목 일별로 받아 macro.db kr_px 에 쌓고, 그 행들을 돌려준다"""
    import time
    import requests
    import seed
    c = store.connect()
    seed.schema(c)
    k = config.key('KRX_API_KEY')
    have = {r[0] for r in c.execute('SELECT date FROM kr_px WHERE date>? GROUP BY date HAVING count(tv)>0', (last,))}      # 거래대금까지 받은 날만 '받았음' (대시보드에서 옮긴 최근 날은 거래대금이 없다 → KRX 로 다시 채운다)
    d = date.fromisoformat(last) + timedelta(days=1)
    num = lambda v: float(str(v).replace(',', '')) if v not in (None, '', '-') else None
    while k and d <= date.today():
        if d.weekday() < 5 and d.isoformat() not in have:
            rows, nm = [], []
            for ep, mkt in (('sto/stk_bydd_trd', 'KOSPI'), ('sto/ksq_bydd_trd', 'KOSDAQ')):
                try:
                    j = requests.get(f'https://data-dbg.krx.co.kr/svc/apis/{ep}', headers={'AUTH_KEY': k}, params={'basDd': d.strftime('%Y%m%d')}, timeout=30).json()
                except Exception:
                    j = {}
                for x in j.get('OutBlock_1', []):
                    cl = num(x.get('TDD_CLSPRC'))
                    if cl:
                        rows.append((d.isoformat(), x['ISU_CD'], cl, num(x.get('FLUC_RT')), (num(x.get('MKTCAP')) or 0) / 1e8, num(x.get('ACC_TRDVOL')), (num(x.get('ACC_TRDVAL')) or 0) / 1e8))
                        nm.append((x['ISU_CD'], x.get('ISU_NM') or x['ISU_CD'], mkt))
                time.sleep(0.15)
            if rows:
                c.executemany('INSERT OR REPLACE INTO kr_px (date, code, close, chg, mcap, volume, tv) VALUES (?,?,?,?,?,?,?)', rows)
                c.executemany('INSERT OR IGNORE INTO kr_name VALUES (?,?,?)', nm)      # 새로 상장한 종목의 이름 (이미 있는 이름은 그대로)
                c.commit()
        d += timedelta(days=1)
    return pd.read_sql('SELECT date, code, close, chg, mcap FROM kr_px WHERE date>? AND volume>0', c, params=(last,))


def rsi14(p):
    d = p.diff()
    up = d.clip(lower=0).ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    return (100 - 100 / (1 + up / dn)).where(p.notna())      # ewm 은 빈 날에 직전 값을 이어 붙인다 → 거래가 없는 날·상장폐지 뒤는 비운다


def main():
    full = '--full' in sys.argv
    c = store.connect()
    if not c.execute("SELECT 1 FROM series WHERE key='kr:adr20' LIMIT 1").fetchone():
        full = True
    start = '2009-01-01' if full else (date.today() - timedelta(days=1100)).isoformat()     # 신저가(250일) 계산 여유
    own = config.STANDALONE
    if own:
        full = False
    df, names, idx, sector = load_own(c) if own else load(start)
    p = df.pivot(index='date', columns='code', values='close').astype('float32')
    chg = df.pivot(index='date', columns='code', values='chg').astype('float32')
    valid = p.notna()
    n = valid.sum(axis=1)
    out = {}
    for sfx, cols in (('', p.columns), (':kospi', [x for x in p.columns if names.market.get(x) == 'KOSPI']), (':kosdaq', [x for x in p.columns if names.market.get(x) == 'KOSDAQ'])):
        up, dn = (chg[cols] > 0).sum(axis=1), (chg[cols] < 0).sum(axis=1)
        out['kr:adr20' + sfx] = up.rolling(20).sum() / dn.rolling(20).sum() * 100
    ma20, sd20 = p.rolling(20).mean(), p.rolling(20).std(ddof=0)
    pctb = (p - (ma20 - 2 * sd20)) / (4 * sd20)
    out['kr:bblow'] = (p < ma20 - 2 * sd20).sum(axis=1) / n * 100
    out['kr:bbup'] = (p > ma20 + 2 * sd20).sum(axis=1) / n * 100
    rsi = rsi14(p)
    out['kr:rsi30'] = (rsi < 30).sum(axis=1) / n * 100
    out['kr:rsi70'] = (rsi > 70).sum(axis=1) / n * 100
    out['kr:nl'] = (p <= p.rolling(250, min_periods=200).min()).sum(axis=1) / n * 100
    out['kr:nh'] = (p >= p.rolling(250, min_periods=200).max()).sum(axis=1) / n * 100
    out['kr:ma60'] = (p > p.rolling(60).mean()).sum(axis=1) / n * 100
    out['kr:ma200'] = (p > p.rolling(200).mean()).sum(axis=1) / n * 100
    cut = p.index[min(260, len(p) - 1)] if not full else '2010-01-04'      # 창이 덜 찬 앞부분은 버린다
    rows = 0
    for k, s in out.items():
        s = s[s.index >= cut].replace([np.inf, -np.inf], np.nan).dropna()
        nm, unit, dec = NAMES[k]
        rows += store.put(c, k, list(zip(s.index, s.round(2))), name=nm, grp='한국 폭', unit=unit, source='종목 일봉', freq='매일', use='타이밍', diff=1, dec=dec)
    for code, key, nm in (('KOSPI', 'kr:kospi', 'KOSPI (종가)'), ('KOSDAQ', 'kr:kosdaq', 'KOSDAQ (종가)')):
        if own:      # 지수 종가는 야후 값으로 잇는다(이미 있는 날은 그대로 두고 그 뒤 날짜만)
            lastd = c.execute('SELECT max(date) FROM series WHERE key=?', (key,)).fetchone()[0] or '1900-01-01'
            new = c.execute('SELECT date, value FROM series WHERE key=? AND date>? ORDER BY date', (f'px:{code.lower()}', lastd)).fetchall()
            rows += store.put(c, key, new, name=nm, grp='한국 폭', unit='', source='Yahoo Finance', freq='매일', use='흐름', diff=0, dec=2)
            continue
        s = idx[idx.code == code].sort_values('date')
        rows += store.put(c, key, list(zip(s.date, s.close)), name=nm, grp='한국 폭', unit='', source='기존 대시보드 DB', freq='매일', use='흐름', diff=0, dec=2)
    c.commit()

    # ── 업종별 과매도 지도 + 업종 안 종목 목록 (최근일 기준) ──
    last = p.index[-1]
    mcap = df.sort_values('date').groupby('code').mcap.apply(lambda s: s.dropna().iloc[-1] if s.notna().any() else np.nan)
    sec = sector.reindex(p.columns)
    ret = {k: (p.iloc[-1] / p.shift(d).iloc[-1] - 1) * 100 for k, d in (('r5', 5), ('r20', 20), ('r60', 60))}
    up20, dn20 = (chg.tail(20) > 0).sum(), (chg.tail(20) < 0).sum()
    live = valid.iloc[-1]
    sectors = []
    for name, codes in sec[live].groupby(sec[live]).groups.items():
        codes = list(codes)
        if name in ('기타', None) or len(codes) < 5:
            continue
        w = mcap.reindex(codes).fillna(0)
        wsum = w.sum() or 1

        def wavg(s):
            s = s.reindex(codes)
            ok = s.notna()
            return round(float((s[ok] * w[ok]).sum() / (w[ok].sum() or 1)), 2)
        r, b = rsi.iloc[-1].reindex(codes), pctb.iloc[-1].reindex(codes)
        stocks = sorted(({'c': x, 'n': names.name.get(x, x), 'mc': None if pd.isna(mcap.get(x)) else round(float(mcap[x])),
                          'p': float(p.iloc[-1][x]), 'ch': None if pd.isna(chg.iloc[-1][x]) else round(float(chg.iloc[-1][x]), 2),
                          'r20': None if pd.isna(ret['r20'][x]) else round(float(ret['r20'][x]), 1),
                          'rsi': None if pd.isna(r[x]) else round(float(r[x]), 1), 'b': None if pd.isna(b[x]) else round(float(b[x]), 2)} for x in codes),
                        key=lambda s: -(s['mc'] or 0))[:40]
        sectors.append({'name': name, 'n': len(codes), 'mcap': round(float(wsum)),
                        'adr': round(float(up20.reindex(codes).sum() / max(dn20.reindex(codes).sum(), 1) * 100), 1),
                        'rsi30': round(float((r < 30).mean() * 100), 1), 'bblow': round(float((b < 0).mean() * 100), 1), 'rsi': round(float(r.median()), 1),
                        'r5': wavg(ret['r5']), 'r20': wavg(ret['r20']), 'r60': wavg(ret['r60']), 'stocks': stocks})
    config.DATA.mkdir(parents=True, exist_ok=True)
    (config.DATA / 'kr_sector.json').write_text(json.dumps({'asof': last, 'n': int(n.iloc[-1]), 'sectors': sorted(sectors, key=lambda s: s['adr'])}, ensure_ascii=False), encoding='utf-8')

    # ── 페어 화면용 한국 종목 계열 (시총 상위 400, 최근 3년) ──
    top = mcap.reindex(p.columns[live]).sort_values(ascending=False).head(400).index
    sdir = config.DATA / 's'
    sdir.mkdir(exist_ok=True)
    cat = []
    p3 = p[p.index >= (date.today() - timedelta(days=1100)).isoformat()]
    if own:      # 혼자 돌 때 p 는 330거래일뿐이라, 상위 종목의 3년치는 kr_px 에서 따로 읽는다
        q3 = pd.read_sql(f"SELECT date, code, close FROM kr_px WHERE date>=? AND close>0 AND code IN ({','.join('?' * len(top))})", c, params=[(date.today() - timedelta(days=1100)).isoformat(), *top])
        p3 = q3.pivot(index='date', columns='code', values='close')
    for x in top:
        s = p3[x].dropna()
        (sdir / f'kr_{x}.json').write_text(json.dumps({'k': f'kr_{x}', 'name': names.name.get(x, x), 'unit': '원', 'd': list(s.index), 'v': [float(v) for v in s]}, ensure_ascii=False), encoding='utf-8')
        cat.append({'k': f'kr_{x}', 'name': names.name.get(x, x), 'grp': '한국 종목', 'code': x})
    (config.DATA / 'kr_catalog.json').write_text(json.dumps(cat, ensure_ascii=False), encoding='utf-8')
    if own:
        import seed
        seed.prune(c)
        c.commit()
    store.log(c, 'breadth', True, f'{"혼자" if own else "전체" if full else "최근"} {rows}행, 기준 {last}, 종목 {int(n.iloc[-1])}, 업종 {len(sectors)}')
    print(f'breadth: {rows}행 · 기준일 {last} · 종목 {int(n.iloc[-1])} · 업종 {len(sectors)} · ADR {out["kr:adr20"].iloc[-1]:.1f}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
