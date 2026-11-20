"""3단계 화면용 JSON: ib.json(IB 지표판) · cta.json(CTA·변동성 제어 모델) · deriv.json(파생·평단).
build.py 가 불러 쓴다. 파생 계열(위험선호 지수·글로벌 폭·패닉/유포리아식·CTA 추정 포지션 등)은 S·M 에 넣어 페어 화면 목록에도 나오게 한다.
종목 일봉·수급은 맥에서는 기존 대시보드 DB(읽기 전용), 혼자 돌 때(config.STANDALONE)는 macro.db 의 kr_px·kr_flow 에서 읽는다."""
import json
import sqlite3

import numpy as np
import pandas as pd

import config
from build2 import H, asof, chg, evidence, last, pct_rank, r, roll_pct, tail
from collect_deriv import PAIRS, US_OPT
from collect_ib import COUNTRY, SI

# 골드만 RAI 방식: 위험자산 ÷ 안전자산 쌍의 3개월 상대 성과 (이름, 분자, 분모, 부호)
RAI = [('주식 ÷ 국채', 'px:spy', 'px:ief', 1), ('하이일드 ÷ 국채', 'px:hyg', 'px:ief', 1), ('경기소비 ÷ 필수소비', 'px:xly', 'px:xlp', 1), ('산업재 ÷ 필수소비', 'px:xli', 'px:xlp', 1),
       ('기술 ÷ 유틸리티', 'px:xlk', 'px:xlu', 1), ('금융 ÷ 유틸리티', 'px:xlf', 'px:xlu', 1), ('소형 ÷ 대형', 'px:iwm', 'px:spy', 1), ('고베타 ÷ 저변동', 'px:sphb', 'px:splv', 1),
       ('신흥 ÷ 선진', 'px:eem', 'px:efa', 1), ('구리 ÷ 금', 'px:copper', 'px:gold', 1), ('호주달러/엔', 'px:audjpy', None, 1), ('달러지수 (역)', 'px:dxy', None, -1), ('VIX (역)', 'px:vix', None, -1)]
CTA = [('px:spx', 'S&P500', '주식'), ('px:ndx', '나스닥', '주식'), ('px:rut', '러셀2000', '주식'), ('kr:kospi', 'KOSPI', '주식'), ('px:nikkei', '닛케이225', '주식'), ('px:stoxx', '유로스톡스50', '주식'), ('px:hsi', '항셍', '주식'),
       ('px:zn', '미 국채 10년 선물', '채권'), ('px:dxy', '달러지수', '통화'), ('px:usdjpy', '엔/달러', '통화'), ('px:wti', 'WTI 유가', '원자재'), ('px:gold', '금', '원자재'), ('px:copper', '구리', '원자재')]
CTA_HZ, CTA_VOL = [20, 60, 125, 250], 0.15


def add(S, M, key, s, name, grp, unit, use, dec=1, diff=1, freq='매일'):
    s = s.dropna()
    if len(s):
        S[key] = s
        M[key] = {'name': name, 'grp': grp, 'unit': unit, 'source': '자체 계산', 'freq': freq, 'use': use, 'diff': diff, 'dec': dec, 'note': None, 'asof': s.index[-1], 'fetched_at': None}


def crossed(extra, S, key, level, below, text, use):
    s = S[key].dropna() if key in S else []
    if len(s) < 2:
        return
    a, b = s.iloc[-2], s.iloc[-1]
    if (a >= level > b) if below else (a <= level < b):
        extra.append({'use': use, 'text': text.format(v=r(b, 1)), 'date': s.index[-1]})


# ── IB 지표판 ──
def ib_indices(S, M):
    us = S['px:spy'].index
    on = lambda s: s.reindex(s.index.union(us)).ffill().reindex(us)
    # 1) RAI식 위험선호 지수
    zs = {}
    for name, a, b, sign in RAI:
        if a not in S or (b and b not in S):
            continue
        x = np.log(on(S[a]) / on(S[b])) if b else np.log(on(S[a]))
        mom = x.diff(63)
        zs[name] = sign * (mom - mom.rolling(756, min_periods=252).mean()) / mom.rolling(756, min_periods=252).std()
    Z = pd.concat(zs, axis=1)
    rai = Z.mean(axis=1, skipna=True)[Z.notna().sum(axis=1) >= 6]
    add(S, M, 'ib:rai', rai, '위험선호 지수 (RAI식)', 'IB 지표', 'z', '비중,흐름', dec=2)

    # 2) 글로벌 폭 (BofA 규칙): 국가 ETF 중 50일선·200일선 아래 비율
    P = pd.concat({k[5:].upper(): S[k] for k in S if k.startswith('ctry:')}, axis=1).reindex(us).ffill(limit=3)
    ok = P.rolling(200, min_periods=200).mean().notna()
    b200, b50 = (P < P.rolling(200).mean()) & ok, (P < P.rolling(50).mean()) & ok
    cnt = ok.sum(axis=1)
    both = ((b200 & b50).sum(axis=1) / cnt * 100)[cnt >= 15]
    a200 = (100 - b200.sum(axis=1) / cnt * 100)[cnt >= 15]
    add(S, M, 'ib:gb_both', both, '글로벌 폭 — 50·200일선 모두 아래인 나라 비율', 'IB 지표', '%', '타이밍')
    add(S, M, 'ib:gb_a200', a200, '글로벌 폭 — 200일선 위인 나라 비율', 'IB 지표', '%', '흐름,비중')
    lastP = P.iloc[-1]
    ctry = [{'tk': tk, 'name': COUNTRY.get(tk, tk), 'a200': bool(not b200[tk].iloc[-1]), 'a50': bool(not b50[tk].iloc[-1]), 'd200': r((lastP[tk] / P[tk].rolling(200).mean().iloc[-1] - 1) * 100, 1),
             'm1': r((lastP[tk] / P[tk].iloc[-22] - 1) * 100, 1), 'm3': r((lastP[tk] / P[tk].iloc[-64] - 1) * 100, 1)} for tk in P.columns if ok[tk].iloc[-1]]
    ctry.sort(key=lambda x: -(x['d200'] or 0))

    # 3) 패닉/유포리아식 지수 (씨티 구성요소 9개 중 무료로 되는 것). 0 = 패닉, 100 = 유포리아
    pe = {}
    rp = lambda s, w=756, m=250: roll_pct(on(s), w, m)
    if 'mkt:vol_ratio' in S:
        pe['나스닥 ÷ NYSE 거래량 (20일 평균)'] = rp(S['mkt:vol_ratio'].rolling(20).mean())
    if 'fred:margin_q' in S:
        pe['신용융자 1년 증가율 (분기)'] = rp(S['fred:margin_q'].pct_change(4))
    if 'fred:mmf_retail' in S:
        pe['소매 MMF 13주 증가율 (역)'] = 100 - rp(S['fred:mmf_retail'].pct_change(13))
    if 'si:spy' in S:
        pe['공매도 잔고 — SPY (역)'] = 100 - on(roll_pct(S['si:spy'], 72, 24))
    pe['원자재 3개월 수익률'] = rp(S['px:dbc'].pct_change(63))
    pe['휘발유 3개월 수익률'] = rp(S['px:gasoline'].pct_change(63))
    if 'sent:pc_equity' in S and len(S['sent:pc_equity']) >= 250:
        pe['풋콜 비율 (역)'] = 100 - rp(S['sent:pc_equity'].rolling(5).mean())
    E = pd.concat(pe, axis=1)
    pei = E.mean(axis=1, skipna=True)[E.notna().sum(axis=1) >= 4]
    add(S, M, 'ib:pe', pei, '패닉/유포리아식 지수', 'IB 지표', '점', '타이밍')
    lv = lambda df: {n: r(s.dropna().iloc[-1], 2 if df is Z else 0) if len(s.dropna()) else None for n, s in df.items()}
    return {'rai': lv(Z), 'pe': lv(E), 'ctry': ctry, 'n_ctry': int(cnt.iloc[-1])}


# ── CTA·변동성 제어 모델 ──
def cta_model(S, M):
    rows, pos_all, ret_all = [], {}, {}
    for key, name, cls in CTA:
        if key not in S:
            continue
        p = S[key].dropna()
        ret = np.log(p).diff()
        sig = sum(np.sign(p / p.shift(n) - 1) for n in CTA_HZ) / len(CTA_HZ)
        vol = ret.rolling(60).std() * np.sqrt(252)
        pos = (sig * (CTA_VOL / vol).clip(upper=1) * 100).dropna()
        pos_all[key], ret_all[key] = pos, (pos.shift(1) / 100 * ret).dropna()
        px = p.iloc[-1]
        trig = [{'n': n, 'level': r(p.iloc[-n], 4), 'dist': r((p.iloc[-n] / px - 1) * 100, 1), 'on': bool(px > p.iloc[-n - 1])} for n in CTA_HZ]
        rows.append({'k': key, 'name': name, 'cls': cls, 'date': p.index[-1], 'px': r(px, 4), 'pos': r(pos.iloc[-1], 0), 'pos_w': r(pos.iloc[-1] - pos.iloc[-6], 0), 'pos_m': r(pos.iloc[-1] - pos.iloc[-22], 0),
                     'vol': r(vol.iloc[-1] * 100, 1), 'trig': trig, 'dec': M[key].get('dec') or 2})
    eq = pd.concat({k: pos_all[k] for k, _, c in CTA if c == '주식' and k in pos_all}, axis=1).sort_index().reindex(S['px:spx'].index).ffill(limit=3).mean(axis=1)
    add(S, M, 'cta:spx', pos_all['px:spx'], 'CTA 추정 포지션 — S&P500', 'IB 지표', '%', '흐름', dec=0)
    add(S, M, 'cta:kospi', pos_all['kr:kospi'], 'CTA 추정 포지션 — KOSPI', 'IB 지표', '%', '흐름', dec=0)
    add(S, M, 'cta:eq', eq, 'CTA 추정 포지션 — 주식 7개 지수 평균', 'IB 지표', '%', '흐름', dec=0)
    # 설명력: 모델 포트폴리오(자산마다 위험을 같게, 자산군 4개를 같은 비중으로) 주간 수익률 vs 실제 CTA ETF 주간 수익률
    cls_of = {k: c for k, _, c in CTA}

    def fit_of(hz):
        rets = {}
        for key in pos_all:
            p = S[key].dropna()
            ret = np.log(p).diff()
            sig = sum(np.sign(p / p.shift(n) - 1) for n in hz) / len(hz)
            rets[key] = (sig * 0.10 / (ret.rolling(60).std() * np.sqrt(252))).shift(1) * ret
        R = pd.concat(rets, axis=1).sort_index().fillna(0)
        port = sum(R[[k for k in R if cls_of[k] == g]].mean(axis=1) for g in set(cls_of.values())) / len(set(cls_of.values()))
        port.index = pd.to_datetime(port.index)
        wk = port.resample('W-FRI').sum()
        out = []
        for k, nm in (('px:dbmf', 'DBMF'), ('px:kmlm', 'KMLM'), ('px:ctaetf', 'CTA')):
            if k not in S:
                continue
            e = np.log(S[k]).diff().dropna()
            e.index = pd.to_datetime(e.index)
            x = pd.concat([wk, e.resample('W-FRI').sum()], axis=1).sort_index().dropna().tail(104)
            out.append({'name': nm, 'corr': r(x.iloc[:, 0].corr(x.iloc[:, 1]), 2), 'weeks': len(x)})
        return out
    fit, fit_long = fit_of(CTA_HZ), fit_of(CTA_HZ[2:])
    # 변동성 제어 펀드 노출 = 목표 변동성 10% ÷ max(1개월, 3개월 실현 변동성), 상한 150%
    sr = np.log(S['px:spx']).diff()
    rv = pd.concat([sr.rolling(21).std(), sr.rolling(63).std()], axis=1).max(axis=1) * np.sqrt(252) * 100
    vc = (10 / rv * 100).clip(upper=150).dropna()
    add(S, M, 'cta:volctl', vc, '변동성 제어 펀드 추정 노출 (S&P500)', 'IB 지표', '%', '흐름', dec=0)
    sp = pos_all['px:spx']
    return {'rows': rows, 'eq': {'last': r(eq.iloc[-1], 0), 'w': r(eq.iloc[-1] - eq.iloc[-6], 0), 'm': r(eq.iloc[-1] - eq.iloc[-22], 0), 'pct': r(pct_rank(eq, 750), 0), 'series': tail(eq, 500, 0)},
            'spx': {'series': tail(sp, 500, 0), 'px': tail(S['px:spx'], 500, 0)}, 'kospi': {'series': tail(pos_all['kr:kospi'], 500, 0), 'px': tail(S['kr:kospi'], 500, 0)},
            'fit': fit, 'fit_long': fit_long, 'hz': CTA_HZ, 'target': CTA_VOL * 100,
            'ev_short': evidence(S['px:spx'], sp <= -50, '2006-06-01'), 'ev_long': evidence(S['px:spx'], sp >= 99, '2006-06-01'),
            'ev_kshort': evidence(S['kr:kospi'], pos_all['kr:kospi'] <= -50, '2006-06-01'),
            'volctl': {'last': r(vc.iloc[-1], 0), 'd20': r(vc.iloc[-1] - vc.iloc[-21], 0), 'rv1': r(sr.rolling(21).std().iloc[-1] * np.sqrt(252) * 100, 1), 'rv3': r(sr.rolling(63).std().iloc[-1] * np.sqrt(252) * 100, 1),
                       'pct': r(pct_rank(vc, 750), 0), 'series': tail(vc, 500, 0), 'date': vc.index[-1]}}


# ── 종목 일봉(기존 대시보드 DB, 읽기 전용) ──
def kr_prices(codes, start):
    """{code: DataFrame(adj 수정종가, vwap 수정 VWAP, tv 거래대금 억원)}. 수정은 등락률(chg)을 거꾸로 곱해 마지막 종가에 맞춘다."""
    q = ','.join('?' * len(codes))
    if config.STANDALONE:      # 혼자 돌 때: macro.db 의 kr_px·kr_name (seed.py 가 옮겨 두고 KRX 가 매일 덧붙인다)
        c = sqlite3.connect(config.DB, timeout=60)
        df = pd.read_sql(f'SELECT date, code, close, volume, tv, chg FROM kr_px WHERE date>=? AND code IN ({q}) ORDER BY date', c, params=[start, *codes])
        names = dict(c.execute(f'SELECT code, name FROM kr_name WHERE code IN ({q})', codes))
    else:
        c = sqlite3.connect(f'file:{config.HIST_DB}?mode=ro', uri=True)
        df = pd.read_sql(f'SELECT date, code, close, volume, tv, chg FROM hp WHERE date>=? AND code IN ({q}) ORDER BY date', c, params=[start, *codes])
        names = dict(c.execute(f'SELECT code, name FROM hname WHERE code IN ({q})', codes))
    out = {}
    for code, g in df.groupby('code'):
        g = g.set_index('date')
        g = g[(g.close > 0)]
        f = (1 + g.chg.fillna(0) / 100)
        adj = g.close.iloc[-1] / f.iloc[::-1].cumprod().shift(1).fillna(1).iloc[::-1]
        raw = (g.tv * 1e8 / g.volume).where(g.volume > 0)
        out[code] = pd.DataFrame({'adj': adj, 'vwap': raw * adj / g.close, 'tv': g.tv, 'close': g.close})
    return out, names


def half_life(x):
    x = x.dropna()
    if len(x) < 60:
        return None
    b = np.polyfit(x.shift(1).dropna().values, x.diff().dropna().values, 1)[0]
    return None if b >= 0 or b <= -1 else float(-np.log(2) / np.log(1 + b))


def pairs(S, KP, names):
    out = []
    for name, a, b, note in PAIRS:
        def px(k):
            if k.startswith('px:'):
                return S.get(k)
            return KP[k].adj if k in KP else None
        pa, pb = px(a), px(b)
        if pa is None or pb is None:
            continue
        x = pd.concat([pa, pb], axis=1).sort_index().ffill(limit=3).dropna()
        if len(x) < 40:
            continue
        lr = np.log(x.iloc[:, 0] / x.iloc[:, 1])
        w = min(250, max(40, len(lr) - 1))
        z = ((lr - lr.rolling(w, min_periods=40).mean()) / lr.rolling(w, min_periods=40).std()).dropna()
        ra, rb = np.log(x.iloc[:, 0]).diff(), np.log(x.iloc[:, 1]).diff()
        t = pd.concat([ra, rb], axis=1).dropna().tail(60)
        # 과거 근거: |z| ≥ 2 뒤 60거래일 동안 벌어진 쪽의 반대로 섰을 때의 수익 (20일 안의 반복은 한 번)
        ev, prev, pos = [], -99, {d: i for i, d in enumerate(lr.index)}
        for d in z[z.abs() >= 2].index:
            i = pos[d]
            if i - prev >= 20 and i + 60 < len(lr):
                ev.append(-np.sign(z[d]) * (lr.iloc[i + 60] - lr.iloc[i]) * 100)
                prev = i
        out.append({'name': name, 'note': note, 'a': a, 'b': b, 'date': lr.index[-1], 'n': len(lr), 'win': w, 'z': r(z.iloc[-1], 2) if len(z) else None, 'z20': r(z.iloc[-21], 2) if len(z) > 21 else None,
                    'hl': r(half_life(lr.tail(250)), 0), 'beta': r(np.polyfit(t.iloc[:, 1], t.iloc[:, 0], 1)[0], 2) if len(t) >= 30 else None, 'corr': r(t.iloc[:, 0].corr(t.iloc[:, 1]), 2) if len(t) >= 30 else None,
                    'ev': {'n': len(ev), 'mean': r(np.mean(ev), 1) if ev else None, 'win': r(np.mean([e > 0 for e in ev]) * 100, 0) if ev else None},
                    'series': {'d': list(z.index[-500:]), 'z': [r(v, 2) for v in z.iloc[-500:]], 'ratio': [r(v, 4) for v in (x.iloc[:, 0] / x.iloc[:, 1]).reindex(z.index).iloc[-500:]]}})
    return out


def vwap_table(KP, names, codes):
    """종목별 VWAP·누적 VWAP·수급 주체별 평단 (최근 60거래일)"""
    flows = {}
    if config.STANDALONE or config.DASH_DB.exists():
        own = config.STANDALONE
        c = sqlite3.connect(config.DB, timeout=60) if own else sqlite3.connect(f'file:{config.DASH_DB}?mode=ro', uri=True)
        q = ','.join('?' * len(codes))
        start = min(g.index[-min(len(g), 61)] for g in KP.values())
        f = pd.read_sql(f'SELECT date, code, frgn, org, ind FROM {"kr_flow" if own else "flow_daily"} WHERE date>=? AND code IN ({q})', c, params=[start, *codes])
        flows = {code: g.set_index('date') for code, g in f.groupby('code')}
    rows = []
    for code in codes:
        g = KP.get(code)
        if g is None or len(g) < 80:
            continue
        g = g.tail(260)
        px, day = g.adj.iloc[-1], g.index[-1]

        def avwap(frm):
            x = g[g.index >= frm]
            x = x[x.vwap > 0]
            return None if not len(x) else float(x.tv.sum() / (x.tv / x.vwap).sum())
        hi, lo = g.adj.tail(250).idxmax(), g.adj.tail(250).idxmin()
        y0 = g.index[g.index >= f'{day[:4]}-01-01'][0]
        anchors = {'ytd': (y0, avwap(y0)), 'hi': (hi, avwap(hi)), 'lo': (lo, avwap(lo)), 'd60': (g.index[-60], avwap(g.index[-60]))}
        gap = lambda v: None if not v else r((px / v - 1) * 100, 1)
        row = {'code': code, 'name': names.get(code, code), 'date': day, 'px': r(px, 0), 'vwap': r(g.vwap.iloc[-1], 0), 'vwap_gap': gap(g.vwap.iloc[-1]),
               'anc': {k: {'from': d, 'v': r(v, 0), 'gap': gap(v)} for k, (d, v) in anchors.items()}}
        fl = flows.get(code)
        if fl is not None:
            j = fl.join(g.vwap, how='inner').tail(60)
            for who in ('frgn', 'org', 'ind'):
                q = j[who].fillna(0)
                buy, sell = q.clip(lower=0), (-q).clip(lower=0)
                bp = float((buy * j.vwap).sum() / buy.sum()) if buy.sum() > 0 else None
                sp = float((sell * j.vwap).sum() / sell.sum()) if sell.sum() > 0 else None
                row[who] = {'net': r((q * j.vwap).sum() / 1e8, 0), 'buy': r(bp, 0), 'buy_gap': gap(bp), 'sell': r(sp, 0), 'sell_gap': gap(sp)}
        # 차트용: 종가와 연초·고점일 기준 누적 VWAP
        def run(frm):
            x = g[(g.index >= frm) & (g.vwap > 0)]
            return (x.tv.cumsum() / (x.tv / x.vwap).cumsum()).reindex(g.index)
        row['series'] = {'d': list(g.index), 'px': [r(v, 0) for v in g.adj], 'ytd': [r(v, 0) for v in run(y0)], 'hi': [r(v, 0) for v in run(hi)]}
        rows.append(row)
    return rows


def shorts(c, names):
    df = pd.read_sql('SELECT date, code, close, vol, sqty, ratio, samt FROM short_daily ORDER BY date', c)
    rows = []
    for code, g in df.groupby('code'):
        if len(g) < 25:
            continue
        avg = lambda n: float(g.samt.tail(n).sum() / g.sqty.tail(n).sum()) if g.sqty.tail(n).sum() > 0 else None
        px, a20, a60 = g.close.iloc[-1], avg(20), avg(60)
        ratio = lambda n: float(g.sqty.tail(n).sum() / g.vol.tail(n).sum() * 100) if g.vol.tail(n).sum() > 0 else None
        rows.append({'code': code, 'name': names.get(code, code), 'date': g.date.iloc[-1], 'px': r(px, 0), 'r5': r(ratio(5), 2), 'r20': r(ratio(20), 2), 'r60': r(ratio(60), 2),
                     'a20': r(a20, 0), 'g20': r((px / a20 - 1) * 100, 1) if a20 else None, 'a60': r(a60, 0), 'g60': r((px / a60 - 1) * 100, 1) if a60 else None,
                     'amt20': r(g.samt.tail(20).sum() / 1e8, 0), 'spark': [r(v, 2) for v in (g.sqty.rolling(5).sum() / g.vol.rolling(5).sum() * 100).tail(60)]})
    rows.sort(key=lambda x: -(x['r5'] or 0))
    return rows


def build(S, M, dump, now, c):
    extra = []
    k, spx = S['kr:kospi'], S['px:spx']
    row = lambda key, d=2, n=20, pct=False: {'k': key, 'name': M[key]['name'], 'unit': M[key]['unit'], 'last': last(S, key, d), 'date': asof(S, key), 'chg': chg(S, key, n, pct), 'pct': r(pct_rank(S[key], 750), 0)}

    # ── IB 지표판 ──
    parts = ib_indices(S, M)
    rai, both, a200, pe = S['ib:rai'], S['ib:gb_both'], S['ib:gb_a200'], S['ib:pe']
    acwi = S['px:acwi']
    q05 = rai.expanding(750).quantile(0.05).shift(1)       # 그날까지의 값만으로 정한 '하위 5%' 선
    q95 = rai.expanding(750).quantile(0.95).shift(1)
    cta = cta_model(S, M)
    dump('ib.json', {
        'built': now,
        'rai': {'last': r(rai.iloc[-1], 2), 'date': rai.index[-1], 'prev20': r(rai.iloc[-21], 2), 'pct': r(pct_rank(rai, len(rai)), 0), 'lo': r(q05.iloc[-1], 2), 'hi': r(q95.iloc[-1], 2), 'parts': parts['rai'],
                'series': tail(rai, 750, 2), 'spx': tail(spx, 750, 0), 'ev_lo': evidence(spx, rai <= q05, '2011-01-01'), 'ev_hi': evidence(spx, rai >= q95, '2011-01-01'), 'ev_m1': evidence(spx, rai <= -1, '2009-01-01')},
        'gb': {'both': r(both.iloc[-1], 0), 'a200': r(a200.iloc[-1], 0), 'a200_prev20': r(a200.iloc[-21], 0), 'date': both.index[-1], 'n': parts['n_ctry'], 'ctry': parts['ctry'],
               'series': tail(both, 750, 0), 'a200_s': tail(a200, 750, 0), 'acwi': tail(acwi, 750, 1),
               'ev88': evidence(acwi, both >= 88, '2008-06-01'), 'ev70': evidence(acwi, both >= 70, '2008-06-01'), 'ev_spx': evidence(spx, both >= 88, '2006-01-01')},
        'pe': {'last': r(pe.iloc[-1], 0), 'date': pe.index[-1], 'prev20': r(pe.iloc[-21], 0), 'parts': parts['pe'], 'series': tail(pe, 750, 0), 'spx': tail(spx, 750, 0), 'since': pe.index[0],
               'pc_n': len(S['sent:pc_equity']) if 'sent:pc_equity' in S else 0,
               'ev_panic': evidence(spx, pe <= 20, pe.index[0]), 'ev_eu': evidence(spx, pe >= 80, pe.index[0])},
        'erp': {'last': last(S, 'val:erp'), 'ey': last(S, 'val:sp_ey'), 'real': last(S, 'fred:real10y'), 'date': asof(S, 'val:erp')},
        'gex': {'last': last(S, 'flow:gex'), 'date': asof(S, 'flow:gex')}, 'cta_eq': cta['eq']['last'], 'volctl': cta['volctl']['last'],
        'cape': last(S, 'val:sp_cape'), 'curve': last(S, 'fred:t10y2y'), 'sahm': last(S, 'fred:sahm'),
        'cftc': {'lev_pct': r(pct_rank(S['cftc:sp:lev'], 156), 0), 'am_pct': r(pct_rank(S['cftc:sp:am'], 156), 0), 'date': asof(S, 'cftc:sp:lev')} if 'cftc:sp:lev' in S else None})
    crossed(extra, S, 'ib:rai', -1, True, '위험선호 지수(RAI식)가 −1 아래로 내려왔다 ({v}) — 위험 회피가 깊은 구간', '비중')
    crossed(extra, S, 'ib:rai', 1, False, '위험선호 지수(RAI식)가 +1 위로 올라왔다 ({v}) — 위험선호가 강한 구간', '비중')
    crossed(extra, S, 'ib:gb_both', 88, False, '국가 ETF 의 {v}%가 50·200일선 모두 아래 — BofA 글로벌 폭 규칙의 매수 신호', '타이밍')
    crossed(extra, S, 'ib:pe', 20, True, '패닉/유포리아식 지수가 20 아래로 ({v}) — 패닉 구간', '타이밍')
    crossed(extra, S, 'ib:pe', 80, False, '패닉/유포리아식 지수가 80 위로 ({v}) — 유포리아 구간', '타이밍')

    # ── CTA ──
    dump('cta.json', {'built': now, **cta})
    for key, nm in (('cta:spx', 'S&P500'), ('cta:kospi', 'KOSPI')):
        crossed(extra, S, key, 0, True, f'CTA 추정 포지션({nm})이 매도로 돌았다 ({{v}}%) — 추세추종 자금의 기계적 매도 구간', '흐름')
        crossed(extra, S, key, 0, False, f'CTA 추정 포지션({nm})이 매수로 돌았다 ({{v}}%)', '흐름')

    # ── 파생·평단 ──
    D = {'built': now}
    if 'drv:k200_basis' in S:
        b, sp = S['drv:k200_basis'], S['drv:k200_spot']
        bp = (b / sp * 100).dropna()
        carry = S['drv:k200_carry'] if 'drv:k200_carry' in S else None
        cd = S['kr:cd91'].reindex(S['kr:cd91'].index.union(b.index)).ffill().reindex(b.index)
        fut = {x: S[f'drv:fut_{x}'] for x in ('frgn', 'orgn', 'prsn') if f'drv:fut_{x}' in S}
        D['basis'] = {'date': b.index[-1], 'fut': last(S, 'drv:k200_fut'), 'spot': last(S, 'drv:k200_spot'), 'basis': r(b.iloc[-1], 2), 'bp': r(bp.iloc[-1], 2), 'pct': r(pct_rank(bp, 500), 0), 'n': len(b),
                      'neg5': int((b.tail(5) < 0).sum()), 'carry': None if carry is None else r(carry.iloc[-1], 2), 'cd': r(cd.iloc[-1], 2), 'oi': last(S, 'drv:k200_fut_oi', 1), 'oi_d20': chg(S, 'drv:k200_fut_oi', 20),
                      'series': tail(bp.rolling(5).mean(), 500, 3), 'raw': tail(bp, 500, 3), 'k200': tail(sp, 500, 1),
                      'fut_flow': {x: {'last': r(s.iloc[-1], 0), 'date': s.index[-1], 'sum5': r(s.tail(5).sum(), 0), 'sum20': r(s.tail(20).sum(), 0), 'n': len(s), 'cum': tail(s.cumsum(), 250, 0)} for x, s in fut.items()},
                      'ev_back': evidence(k, (b.rolling(5).max() < 0), b.index[0])}
        crossed(extra, S, 'drv:k200_basis', 0, True, 'KOSPI200 선물이 현물보다 싸졌다 (베이시스 {v}pt, 백워데이션) — 선물 매도 압력', '흐름')
        crossed(extra, S, 'drv:k200_basis', 0, False, 'KOSPI200 선물 베이시스가 다시 플러스로 ({v}pt)', '흐름')
    if 'drv:loan_kospi' in S:
        tot = (S['drv:loan_kospi'] + S['drv:loan_kosdaq']).dropna()
        sh = (S['drv:loan_kospi_sh'] + S['drv:loan_kosdaq_sh']).dropna()
        add(S, M, 'drv:loan', tot, '대차잔고 금액 — KOSPI + KOSDAQ', '파생', '조원', '타이밍,흐름')
        add(S, M, 'drv:loan_sh', sh, '대차잔고 주수 — KOSPI + KOSDAQ', '파생', '억 주', '타이밍,흐름', dec=2)
        net = lambda m: (S[f'drv:loan_{m}_new'] - S[f'drv:loan_{m}_rdmp'])
        sh20 = sh.pct_change(20) * 100
        D['loan'] = {'date': tot.index[-1], 'amt': r(tot.iloc[-1], 1), 'kospi': last(S, 'drv:loan_kospi', 1), 'kosdaq': last(S, 'drv:loan_kosdaq', 1), 'sh': r(sh.iloc[-1], 2), 'sh_d5': r(sh.pct_change(5).iloc[-1] * 100, 1), 'sh_d20': r(sh20.iloc[-1], 1),
                     'amt_d20': r(tot.pct_change(20).iloc[-1] * 100, 1), 'pct': r(pct_rank(sh, 750), 0), 'net5': r((net('kospi') + net('kosdaq')).tail(5).sum(), 0), 'net20': r((net('kospi') + net('kosdaq')).tail(20).sum(), 0), 'n': len(sh),
                     'series': tail(sh, 750, 2), 'amt_s': tail(tot, 750, 1), 'kospi_s': tail(k, 750, 1),
                     'ev_cover': evidence(k, sh20 <= -5, sh.index[21]), 'ev_build': evidence(k, sh20 >= 5, sh.index[21])}
    if 'drv:k200_pc_vol' in S:
        pv = S['drv:k200_pc_vol']
        pv5 = pv.rolling(5).mean()
        hi = pv5.rolling(500, min_periods=120).quantile(0.95).shift(1)
        lo = pv5.rolling(500, min_periods=120).quantile(0.05).shift(1)
        oi = c.execute("SELECT json FROM blob WHERE key='k200_oi'").fetchone()
        oi = json.loads(oi[0]) if oi else None
        if oi:
            rs = oi['rows']
            sp0 = oi['spot']                                   # 현재가에서 1~10% 떨어진 행사가 중 미결제가 가장 많은 곳 (등가격 근처는 늘 많아서 뺀다)
            oi['call_wall'] = max((x for x in rs if sp0 * 1.01 <= x[0] <= sp0 * 1.10), key=lambda x: x[1], default=[None])[0]
            oi['put_wall'] = max((x for x in rs if sp0 * 0.90 <= x[0] <= sp0 * 0.99), key=lambda x: x[2], default=[None])[0]
        D['k200opt'] = {'date': pv.index[-1], 'vol': r(pv.iloc[-1], 2), 'vol5': r(pv5.iloc[-1], 2), 'vol_pct': r(pct_rank(pv5, 500), 0), 'oi': last(S, 'drv:k200_pc_oi'), 'oi_pct': r(pct_rank(S['drv:k200_pc_oi'], 500), 0),
                        'val': last(S, 'drv:k200_pc_val'), 'skew': last(S, 'drv:k200_skew', 1), 'skew_pct': r(pct_rank(S['drv:k200_skew'], 500), 0) if 'drv:k200_skew' in S else None, 'n': len(pv),
                        'series': tail(pv5, 500, 3), 'skew_s': tail(S['drv:k200_skew'].rolling(5).mean(), 500, 2) if 'drv:k200_skew' in S else None, 'k200': tail(S['drv:k200_spot'], 500, 1), 'table': oi,
                        'ev_hi': evidence(k, pv5 >= hi, pv.index[0]), 'ev_lo': evidence(k, pv5 <= lo, pv.index[0])}
    us = []
    for tk, name in US_OPT.items():
        a = f'opt:{tk.lower()}:'
        if a + 'pc_vol' in S:
            us.append({'tk': tk, 'name': name, 'date': asof(S, a + 'pc_vol'), 'pc_vol': last(S, a + 'pc_vol'), 'pc_oi': last(S, a + 'pc_oi'), 'iv': last(S, a + 'iv', 1), 'iv_prev': r(S[a + 'iv'].iloc[-2], 1) if a + 'iv' in S and len(S[a + 'iv']) > 1 else None,
                       'n': len(S[a + 'pc_vol'])})
    D['usopt'] = {'rows': us, 'cboe': {x: {'last': last(S, f'sent:{x}'), 'date': asof(S, f'sent:{x}')} for x in ('pc_total', 'pc_equity', 'pc_index') if f'sent:{x}' in S}}
    D['si'] = [{'tk': tk, 'name': name, 'date': asof(S, f'si:{tk.lower()}'), 'sh': last(S, f'si:{tk.lower()}', 1), 'chg': chg(S, f'si:{tk.lower()}', 1), 'dtc': last(S, f'si:{tk.lower()}:dtc'), 'pct': r(pct_rank(S[f'si:{tk.lower()}'], 72), 0),
                'spark': [r(v, 1) for v in S[f'si:{tk.lower()}'].tail(48)]} for tk, name in SI.items() if f'si:{tk.lower()}' in S]
    # 통화 스왑 대용: 달러선물 근월·차근월 가격 차가 말하는 금리차 − 실제 금리차
    if 'drv:usd_swap' in S:
        sw = S['drv:usd_swap'].rolling(5).mean().dropna()
        on = lambda s: s.reindex(s.index.union(sw.index)).ffill().reindex(sw.index)
        us_rate = on(S['fred:sofr']) if 'fred:sofr' in S else on(S['fred:tb3m'])
        diff = on(S['kr:cd91']) - us_rate
        basis = ((sw - diff) * 100).dropna()
        add(S, M, 'drv:swap_basis', basis, '통화 스왑 베이시스 대용 (달러선물 내재 금리차 − 실제 금리차)', '파생', 'bp', '비중', dec=0)
        D['swap'] = {'date': basis.index[-1], 'implied': r(sw.iloc[-1], 2), 'diff': r(diff.iloc[-1], 2), 'kr': r(on(S['kr:cd91']).iloc[-1], 2), 'us': r(us_rate.iloc[-1], 2), 'basis': r(basis.iloc[-1], 0), 'd20': r(basis.iloc[-1] - basis.iloc[-21], 0) if len(basis) > 21 else None,
                     'pct': r(pct_rank(basis, 500), 0), 'series': tail(basis, 500, 0), 'krw': tail(S['px:usdkrw'], 500, 1), 'n': len(basis)}
    # 롱숏 쏠림
    crowd = []
    for name, a, b, read in (('헤지펀드 선호주 ÷ S&P500', 'px:gvip', 'px:spy', '급락 = 헤지펀드가 같이 들고 있던 종목을 줄이는 중'), ('모멘텀 ÷ S&P500', 'px:mtum', 'px:spy', '급락 = 주도주 포지션 축소'),
                             ('반대베타 ETF (BTAL)', 'px:btal', None, '급등 = 고베타를 팔고 저베타를 사는 흐름(위험 축소)')):
        s = (S[a] / S[b]).dropna() if b else S[a].dropna()
        c20 = s.pct_change(20) * 100
        crowd.append({'name': name, 'read': read, 'date': s.index[-1], 'c5': r(s.pct_change(5).iloc[-1] * 100, 1), 'c20': r(c20.iloc[-1], 1), 'pct': r(pct_rank(c20, 750), 0), 'spark': [r(v, 4) for v in s.tail(120)]})
    D['crowd'] = crowd
    # 종목: 페어 z-점수 · VWAP·평단 · 공매도 평단
    codes = sorted({x for _, a, b, _ in PAIRS for x in (a, b) if len(x) == 6} | {r0[0] for r0 in c.execute('SELECT DISTINCT code FROM short_daily')})
    KP, names = kr_prices(codes, '2012-01-01')
    D['pairs'] = pairs(S, KP, names)
    top = [r0[0] for r0 in c.execute('SELECT code FROM kr_px WHERE date=(SELECT max(date) FROM kr_px) ORDER BY mcap DESC LIMIT 30')]
    D['vwap'] = vwap_table(KP, names, [x for x in top if x in KP])
    D['shorts'] = shorts(c, names)
    dump('deriv.json', D)
    if 'loan' in D and D['loan']['sh_d5'] is not None and D['loan']['sh_d5'] <= -3:
        extra.append({'use': '타이밍', 'date': D['loan']['date'], 'text': f"대차잔고 주수가 5일 동안 {D['loan']['sh_d5']}% 줄었다 — 빌린 주식을 갚는 중(숏커버)"})
    summary = {'rai': {'last': r(rai.iloc[-1], 2), 'date': rai.index[-1]}, 'pe': {'last': r(pe.iloc[-1], 0), 'date': pe.index[-1]}, 'gb': {'last': r(a200.iloc[-1], 0), 'date': a200.index[-1]},
               'cta': {'last': cta['eq']['last'], 'date': S['cta:eq'].index[-1]}}
    return extra, summary
