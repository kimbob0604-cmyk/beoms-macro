"""2단계 화면용 JSON: weight.json(비중) · flow.json(수급·포지셔닝) · sentiment.json(공탐지수) · credit.json(AI 크레딧).
build.py 가 불러 쓴다. 여기서 만든 파생 계열(한국판 공탐지수·AI 크레딧 스트레스·주식위험프리미엄)은 S·M 에 넣어 페어 화면 목록에도 나오게 한다."""
import json

import numpy as np
import pandas as pd

import config

H = {'1개월': 20, '3개월': 60, '6개월': 120, '12개월': 250}


def r(v, d=2):
    return None if v is None or v != v or np.isinf(v) else round(float(v), d)


def pct_rank(s, window=500):
    s = s.dropna().tail(window)
    return None if len(s) < 60 else float((s <= s.iloc[-1]).mean() * 100)


def roll_pct(s, window=500, minp=120):
    """날짜마다 '그날 값이 직전 window 개 중 몇 %인가' (그날까지의 값만 사용)"""
    return s.rolling(window, min_periods=minp).rank(pct=True) * 100


def tail(s, n=750, d=2):
    s = s.dropna().tail(n)
    return {'d': list(s.index), 'v': [r(v, d) for v in s]}


def last(S, k, d=2):
    return None if k not in S or not len(S[k].dropna()) else r(S[k].dropna().iloc[-1], d)


def asof(S, k):
    return None if k not in S or not len(S[k].dropna()) else S[k].dropna().index[-1]


def chg(S, k, n, pct=True):
    s = S[k].dropna()
    if len(s) <= n:
        return None
    return r((s.iloc[-1] / s.iloc[-1 - n] - 1) * 100 if pct else s.iloc[-1] - s.iloc[-1 - n], 2)


def events(idx, mask, start, gap=20):
    out, prev, pos = [], -99, {d: i for i, d in enumerate(idx)}
    for d in mask[(mask == True) & (mask.index >= start)].index:
        if pos[d] - prev >= gap:
            out.append(d)
            prev = pos[d]
    return out


def evidence(px, mask, start):
    """신호(mask) 뒤 px 의 수익률 vs 아무 날"""
    px = px.dropna()
    mask = mask.reindex(px.index)
    ev = events(px.index, mask, start)
    row = {'n': len(ev), 'dates': ev[-4:], 'since': start}
    for h, n in H.items():
        f = (px.shift(-n) / px - 1) * 100
        v, b = f.reindex(ev).dropna(), f[f.index >= start].dropna()
        row[h] = {'n': len(v), 'mean': r(v.mean(), 1) if len(v) else None, 'win': r((v > 0).mean() * 100, 0) if len(v) else None, 'base': r(b.mean(), 1), 'base_win': r((b > 0).mean() * 100, 0)}
    return row


# ── 유동성·크레딧 축 (국면) ──
def liq_score(S, at=None):
    cut = (lambda s: s if at is None else s[s.index <= at])
    parts = {
        '하이일드 스프레드 60일 변화(역)': pct_rank(cut(-S['fred:hy_oas'].diff(60))),
        'CCC 스프레드 60일 변화(역)': pct_rank(cut(-S['fred:ccc_oas'].diff(60))),
        '연준 순유동성 13주 변화': pct_rank(cut(S['fred:netliq'].diff(13)), 260),
        '금융여건 NFCI(역)': pct_rank(cut(-S['fred:nfci']), 260),
        '달러 60일 변화(역)': pct_rank(cut(-S['px:dxy'].pct_change(60))),
        '실질금리 60일 변화(역)': pct_rank(cut(-S['fred:real10y'].diff(60))),
    }
    v = [x for x in parts.values() if x is not None]
    return (r(np.mean(v), 0) if v else None), {k: r(x, 0) for k, x in parts.items()}


# ── 파생 계열 ──
def derive(S, M):
    def add(key, s, name, grp, unit, use, dec=1, diff=1, source='자체 계산', freq='매일'):
        s = s.dropna()
        if len(s):
            S[key] = s
            M[key] = {'name': name, 'grp': grp, 'unit': unit, 'source': source, 'freq': freq, 'use': use, 'diff': diff, 'dec': dec, 'note': None, 'asof': s.index[-1], 'fetched_at': None}
    k = S['kr:kospi']
    idx = S['kr:adr20'].index
    on = lambda s: s.reindex(s.index.union(idx)).ffill().reindex(idx)
    comp = {
        'ADR(20일)': roll_pct(S['kr:adr20']), '60일선 위 종목 비율': roll_pct(S['kr:ma60']), '신고가 − 신저가': roll_pct(S['kr:nh'] - S['kr:nl']),
        'KOSPI ÷ 125일 평균': roll_pct(on(k / k.rolling(125).mean())), 'VKOSPI(역)': 100 - roll_pct(on(S['vol:vkospi'])) if 'vol:vkospi' in S else None,
        '신용잔고 20일 변화': roll_pct(on(S['kr:credit'].pct_change(20))) if 'kr:credit' in S else None,
        '반대매매 비중(역)': 100 - roll_pct(on(S['kr:forced_pct'].rolling(5).mean())) if 'kr:forced_pct' in S else None,
        '원/달러 20일 변화(역)': 100 - roll_pct(on(S['px:usdkrw'].pct_change(20))),
    }
    comp = {n: s for n, s in comp.items() if s is not None}
    fg = pd.concat(comp, axis=1)
    krfg = fg.mean(axis=1, skipna=True)[fg.notna().sum(axis=1) >= 4]
    add('sent:krfg', krfg, '한국판 공탐지수', '심리', '점', '타이밍')
    # AI 크레딧 스트레스 (0~100, 높을수록 스트레스)
    us = S['fred:hy_oas'].index
    onu = lambda s: s.reindex(s.index.union(us)).ffill().reindex(us)
    dd = lambda key: onu((1 - S[key] / S[key].rolling(250, min_periods=60).max()) * 100) if key in S else None
    ac = {'CCC 스프레드': roll_pct(S['fred:ccc_oas']), '하이일드 스프레드': roll_pct(S['fred:hy_oas']), 'B 스프레드': roll_pct(S['fred:b_oas']),
          'BDC ETF 60일 수익률(역)': 100 - roll_pct(onu(S['px:bizd'].pct_change(60))), '레버리지론 ETF 60일 수익률(역)': 100 - roll_pct(onu(S['px:bkln'].pct_change(60))),
          '오라클 고점 대비 낙폭': roll_pct(dd('px:orcl')), '코어위브 고점 대비 낙폭': roll_pct(dd('px:crwv'), 500, 60), '네비우스 고점 대비 낙폭': roll_pct(dd('px:nbis'), 500, 60)}
    af = pd.concat(ac, axis=1)
    stress = af.mean(axis=1, skipna=True)[af.notna().sum(axis=1) >= 4]
    add('credit:ai_stress', stress, 'AI 크레딧 스트레스 지수', '크레딧', '점', '비중,섹터')
    if 'val:sp_ey' in S:
        x = pd.concat([S['val:sp_ey'], S['fred:real10y'].reindex(S['fred:real10y'].index.union(S['val:sp_ey'].index)).ffill()], axis=1).dropna()
        add('val:erp', x.iloc[:, 0] - x.iloc[:, 1], '주식위험프리미엄 (이익수익률 − 실질금리)', '밸류에이션', '%p', '비중', dec=2)
    return {'krfg': {n: r(s.dropna().iloc[-1], 0) if len(s.dropna()) else None for n, s in comp.items()}, 'stress': {n: r(s.dropna().iloc[-1], 0) if len(s.dropna()) else None for n, s in ac.items()}}


def build(S, M, dump, now, regime):
    parts = derive(S, M)
    k = S['kr:kospi']
    extra = []          # 오늘 바뀐 것에 더할 항목

    def cross(key, level, below, text, use):
        s = S[key].dropna()
        if len(s) < 2:
            return
        a, b = s.iloc[-2], s.iloc[-1]
        if (a >= level > b) if below else (a <= level < b):
            extra.append({'use': use, 'text': text.format(v=r(b, 1)), 'date': s.index[-1]})

    # ── 공탐지수 ──
    word = lambda v: None if v is None else '극단 공포' if v < 25 else '공포' if v < 45 else '중립' if v < 55 else '탐욕' if v < 75 else '극단 탐욕'
    cnn, kf = S.get('sent:cnn'), S['sent:krfg']
    dump('sentiment.json', {
        'built': now,
        'cnn': None if cnn is None else {'last': last(S, 'sent:cnn', 1), 'date': asof(S, 'sent:cnn'), 'word': word(last(S, 'sent:cnn')), 'series': tail(cnn, 400, 1),
                                         'parts': {M[x]['name'].replace('CNN 구성 — ', ''): last(S, x, 0) for x in sorted(S) if x.startswith('sent:cnn:')}},
        'kr': {'last': r(kf.iloc[-1], 1), 'date': kf.index[-1], 'word': word(kf.iloc[-1]), 'series': tail(kf, 750, 1), 'parts': parts['krfg'],
               'fear': evidence(k, kf <= 20, '2012-01-01'), 'greed': evidence(k, kf >= 80, '2012-01-01')},
        'crypto': {'last': last(S, 'sent:crypto', 0), 'date': asof(S, 'sent:crypto'), 'word': word(last(S, 'sent:crypto'))},
        'pc': {x: {'last': last(S, f'sent:{x}'), 'date': asof(S, f'sent:{x}'), 'n': len(S[f'sent:{x}'])} for x in ('pc_total', 'pc_equity', 'pc_index') if f'sent:{x}' in S}})
    cross('sent:cnn', 25, True, 'CNN 공탐지수가 25 아래로 내려왔다 ({v}) — 극단 공포', '타이밍')
    cross('sent:cnn', 25, False, 'CNN 공탐지수가 25 위로 올라왔다 ({v}) — 극단 공포 탈출', '타이밍')
    cross('sent:cnn', 75, False, 'CNN 공탐지수가 75를 넘었다 ({v}) — 극단 탐욕', '타이밍')
    cross('sent:krfg', 20, True, '한국판 공탐지수가 20 아래로 내려왔다 ({v}) — 극단 공포', '타이밍')
    cross('sent:krfg', 80, False, '한국판 공탐지수가 80을 넘었다 ({v}) — 극단 탐욕', '타이밍')

    # ── 수급·포지셔닝 ──
    cr = S['kr:credit']
    c5 = cr.pct_change(5) * 100
    fp = S['kr:forced_pct']
    dix5 = S['flow:dix'].rolling(5).mean()
    cf = []
    for key, _, kor in __import__('collect_sent').CFTC:
        lev, am = S.get(f'cftc:{key}:lev'), S.get(f'cftc:{key}:am')
        if lev is None:
            continue
        cf.append({'key': key, 'name': kor, 'date': lev.index[-1], 'lev': r(lev.iloc[-1], 1), 'lev_w': r(lev.iloc[-1] - lev.iloc[-2], 1), 'lev_pct': r(pct_rank(lev, 156), 0),
                   'am': r(am.iloc[-1], 1), 'am_w': r(am.iloc[-1] - am.iloc[-2], 1), 'am_pct': r(pct_rank(am, 156), 0), 'series': {'d': list(lev.index[-156:]), 'lev': [r(v, 1) for v in lev.iloc[-156:]], 'am': [r(v, 1) for v in am.iloc[-156:]]}})
    dump('flow.json', {
        'built': now,
        'credit': {'date': cr.index[-1], 'last': last(S, 'kr:credit'), 'kospi': last(S, 'kr:credit_kospi'), 'kosdaq': last(S, 'kr:credit_kosdaq'), 'd5': r(c5.iloc[-1], 1), 'd20': chg(S, 'kr:credit', 20), 'pct': r(pct_rank(cr, 750), 0),
                   'deposit': last(S, 'kr:deposit'), 'deposit_d20': chg(S, 'kr:deposit', 20), 'ratio': last(S, 'kr:credit_ratio', 1), 'ratio_pct': r(pct_rank(S['kr:credit_ratio'], 750), 0),
                   'forced': last(S, 'kr:forced', 0), 'forced_pct': last(S, 'kr:forced_pct', 1), 'forced_rank': r(pct_rank(fp, 750), 0), 'loan': last(S, 'kr:stock_loan'),
                   'series': {x: tail(S[f'kr:{x}'], 750) for x in ('credit', 'deposit', 'credit_ratio', 'forced_pct')}, 'kospi_s': tail(k, 750, 1),
                   'ev_drop': evidence(k, c5 <= -3, '2011-01-01'), 'ev_forced': evidence(k, fp.rolling(5).mean() >= fp.rolling(5).mean().rolling(750, min_periods=250).quantile(0.95).shift(1), '2011-06-01')},
        'china': {'date': asof(S, 'cn:margin'), 'last': last(S, 'cn:margin', 0), 'd20': chg(S, 'cn:margin', 20), 'series': tail(S['cn:margin'], 750, 0), 'sh': tail(S['px:shcomp'], 750, 1)},
        'cftc': cf,
        'dix': {'date': asof(S, 'flow:dix'), 'last': last(S, 'flow:dix', 1), 'avg5': r(dix5.iloc[-1], 1), 'pct': r(pct_rank(S['flow:dix'], 750), 0), 'gex': last(S, 'flow:gex'), 'gex_pct': r(pct_rank(S['flow:gex'], 750), 0),
                'series': tail(S['flow:dix'], 500, 1), 'avg5_s': tail(dix5, 500, 1), 'gex_s': tail(S['flow:gex'], 500, 2), 'spx': tail(S['flow:dix_spx'], 500, 0),
                'ev45': evidence(S['flow:dix_spx'], dix5 >= 45, '2011-06-01'), 'ev_gexneg': evidence(S['flow:dix_spx'], S['flow:gex'] < 0, '2011-06-01')}})
    if c5.iloc[-1] <= -3 < c5.iloc[-2]:
        extra.append({'use': '타이밍', 'date': cr.index[-1], 'text': f'신용잔고가 5일 동안 {c5.iloc[-1]:.1f}% 줄었다 — 반대매매·투매 신호'})
    cross('flow:dix', 45, False, 'DIX가 45%를 넘었다 ({v}%) — 장외에서 매수 우위', '타이밍')

    # ── 비중: 크레딧·금리·유동성·경기·밸류에이션 ──
    hy = S['fred:hy_oas']
    hy20 = (hy - hy.shift(20)) * 100
    if hy20.iloc[-1] >= 50 > hy20.iloc[-2]:
        extra.append({'use': '비중', 'date': hy.index[-1], 'text': f'하이일드 스프레드가 20일 동안 {hy20.iloc[-1]:.0f}bp 벌어졌다 — 신용 위험 경보'})
    cross('fred:t10y2y', 0, True, '미국 10년 − 2년 금리차가 0 아래로 (역전)', '비중')
    cross('credit:ai_stress', 80, False, 'AI 크레딧 스트레스 지수가 80을 넘었다 ({v})', '비중')
    row = lambda key, d=2, n=20, pct=False: {'k': key, 'name': M[key]['name'], 'unit': M[key]['unit'], 'last': last(S, key, d), 'date': asof(S, key), 'chg': chg(S, key, n, pct), 'pct': r(pct_rank(S[key], 750), 0)}
    eco = []
    for key, d, note in (('fred:gdpnow', 2, '분기 성장률 실시간 추정'), ('fred:sahm', 2, '0.5 이상이면 침체 시작 신호'), ('fred:recprob', 1, '평활 침체 확률'), ('fred:claims', 0, '늘면 고용 악화'),
                         ('fred:epu', 0, '뉴스 기반 불확실성'), ('fred:umich', 1, '소비자심리')):
        s = S[key].dropna()
        eco.append({'name': M[key]['name'], 'last': r(s.iloc[-1], d), 'prev': r(s.iloc[-2], d), 'date': s.index[-1], 'note': note, 'freq': M[key]['freq'], 'dec': d})
    dump('weight.json', {
        'built': now, 'regime': regime,
        'credit': {'rows': [row(x, 2) for x in ('fred:hy_oas', 'fred:ccc_oas', 'fred:b_oas', 'fred:bb_oas', 'fred:bbb_oas', 'fred:ig_oas')], 'hy20': r(hy20.iloc[-1], 0),
                   'series': {x: tail(S[f'fred:{x}'], 750) for x in ('hy_oas', 'ccc_oas', 'bbb_oas')}},
        'rates': {'rows': [row(x, 2) for x in ('fred:us2y', 'fred:us10y', 'fred:t10y2y', 'fred:t10y3m', 'fred:real10y', 'fred:bei10y', 'fred:tp10y')],
                  'series': {x: tail(S[f'fred:{x}'], 750) for x in ('us2y', 'us10y', 'real10y', 't10y2y')}},
        'kr': {'rows': [row(x, 3 if 'spread' not in x and 'curve' not in x else 1) for x in ('kr:ktb3y', 'kr:ktb10y', 'kr:ktb_curve', 'kr:corp_spread', 'kr:bbb_spread', 'kr:cd91')],
               'series': {x: tail(S[f'kr:{x}'], 750, 3) for x in ('ktb3y', 'ktb10y', 'corp_spread')}},
        'liq': {'netliq': last(S, 'fred:netliq', 0), 'netliq_13w': r(S['fred:netliq'].diff(13).iloc[-1], 0), 'date': asof(S, 'fred:netliq'), 'nfci': last(S, 'fred:nfci', 3), 'nfci_date': asof(S, 'fred:nfci'),
                'rrp': last(S, 'fred:rrp', 1), 'tga': r(S['fred:tga'].iloc[-1] / 1000, 0), 'walcl': r(S['fred:walcl'].iloc[-1] / 1000, 0), 'sofr_iorb': last(S, 'fred:sofr_iorb'), 'cp_spread': last(S, 'fred:cp_spread'),
                'series': {'netliq': tail(S['fred:netliq'], 300, 0), 'nfci': tail(S['fred:nfci'], 300, 3), 'ndx': tail(S['px:ndx'], 1300, 0), 'sofr_iorb': tail(S['fred:sofr_iorb'], 500), 'cp_spread': tail(S['fred:cp_spread'], 500)}},
        'eco': eco,
        'val': {'ey': last(S, 'val:sp_ey'), 'real': last(S, 'fred:real10y'), 'erp': last(S, 'val:erp'), 'cape': last(S, 'val:sp_cape'), 'pe': last(S, 'val:sp_pe'), 'date': asof(S, 'val:sp_ey'), 'n': len(S['val:erp']) if 'val:erp' in S else 0,
                'margin_q': r(S['fred:margin_q'].iloc[-1] / 1000, 0), 'margin_date': asof(S, 'fred:margin_q'), 'margin_yoy': r((S['fred:margin_q'].iloc[-1] / S['fred:margin_q'].iloc[-5] - 1) * 100, 1),
                'mmf': last(S, 'fred:mmf_retail', 0), 'mmf_date': asof(S, 'fred:mmf_retail')}})

    # ── AI 크레딧 ──
    st = S['credit:ai_stress']
    cds = {}
    try:
        for e in json.loads((config.ROOT / 'cds_input.json').read_text(encoding='utf-8'))['entries']:
            cds.setdefault(e['key'], []).append(e)
    except Exception:
        pass
    names = []
    for key, name, grp in (('orcl', '오라클', '하이퍼스케일러'), ('msft', '마이크로소프트', '하이퍼스케일러'), ('googl', '알파벳', '하이퍼스케일러'), ('amzn', '아마존', '하이퍼스케일러'), ('meta', '메타', '하이퍼스케일러'),
                           ('crwv', '코어위브', '네오클라우드'), ('nbis', '네비우스', '네오클라우드'), ('nvda', '엔비디아', '반도체')):
        s = S[f'px:{key}'].dropna()
        e = sorted(cds.get(key, []), key=lambda x: x['date'])
        names.append({'key': key, 'name': name, 'grp': grp, 'px': r(s.iloc[-1], 2), 'date': s.index[-1], 'm1': chg(S, f'px:{key}', 21), 'm3': chg(S, f'px:{key}', 63),
                      'dd': r((1 - s.iloc[-1] / s.tail(250).max()) * 100, 1), 'cds': e[-1] if e else None, 'cds_prev': e[-2] if len(e) > 1 else None, 'spark': [r(v, 2) for v in s.tail(120)]})
    dump('credit.json', {'built': now, 'stress': {'last': r(st.iloc[-1], 0), 'date': st.index[-1], 'prev20': r(st.iloc[-21], 0) if len(st) > 21 else None, 'series': tail(st, 600, 1), 'parts': parts['stress']},
                         'names': names, 'grades': [row(x, 2) for x in ('fred:ccc_oas', 'fred:b_oas', 'fred:bb_oas', 'fred:bbb_oas', 'fred:hy_oas')],
                         'series': {'ccc': tail(S['fred:ccc_oas'], 750), 'hy': tail(S['fred:hy_oas'], 750), 'bizd': tail(S['px:bizd'], 500), 'bkln': tail(S['px:bkln'], 500), 'smh': tail(S['px:smh'], 500), 'orcl': tail(S['px:orcl'], 500), 'crwv': tail(S['px:crwv'], 500)},
                         'etf': [row(x, 2, 60, True) for x in ('px:bizd', 'px:bkln', 'px:hyg')]})
    return extra
