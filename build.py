"""macro.db → public/data/*.json (화면용).  python3 build.py

monitor.json  크로스에셋 표          today.json   국면·오늘 바뀐 것·전일 미국 → 한국
timing.json   과매도 지표·신호판·과거 근거   sector.json  상대강도 비율·지역 수익률
s/<key>.json  페어 화면용 계열        catalog.json 계열 목록      glossary.json 지표 사전      status.json 신선도
"""
import json
import sys
from datetime import date, datetime

import numpy as np
import pandas as pd

import build2
import build3
import build4
import config
import store
from glossary import G

MON_GROUPS = ['주식', '변동성', '금리', '환율', '원자재', '크레딧']
RATIOS = [  # id, 이름, 분자, 분모, 읽는 법
    ('sox_spx', '반도체 ÷ S&P500', 'px:sox', 'px:spx', '오르면 반도체가 시장을 주도'),
    ('ndx_rut', '나스닥 ÷ 러셀2000', 'px:ndx', 'px:rut', '오르면 대형 기술주 쏠림, 내리면 소형주로 확산'),
    ('rsp_spy', '동일가중 ÷ 시총가중', 'px:rsp', 'px:spy', '오르면 상승이 넓게 퍼짐(폭 개선)'),
    ('xly_xlp', '경기소비 ÷ 필수소비', 'px:xly', 'px:xlp', '오르면 경기민감 선호'),
    ('sphb_splv', '고베타 ÷ 저변동', 'px:sphb', 'px:splv', '오르면 위험선호'),
    ('mtum_spy', '모멘텀 ÷ S&P500', 'px:mtum', 'px:spy', '급락하면 주도주 포지션 축소'),
    ('gvip_spy', '헤지펀드 선호주 ÷ S&P500', 'px:gvip', 'px:spy', '급락하면 헤지펀드 롱 포지션 축소'),
    ('copper_gold', '구리 ÷ 금', 'px:copper', 'px:gold', '오르면 경기 기대, 내리면 안전 선호'),
    ('eem_spy', '신흥국 ÷ 미국', 'px:eem', 'px:spy', '오르면 신흥국(한국 포함)으로 자금'),
    ('twii_spx', '대만 ÷ S&P500', 'px:twii', 'px:spx', '오르면 AI·반도체 공급망 강세'),
    ('hsi_spx', '항셍 ÷ S&P500', 'px:hsi', 'px:spx', '오르면 중국 관련(소비·소재) 강세'),
    ('kospi_spx', 'KOSPI ÷ S&P500', 'px:kospi', 'px:spx', '오르면 한국이 미국보다 강함'),
    ('kosdaq_kospi', 'KOSDAQ ÷ KOSPI', 'px:kosdaq', 'px:kospi', '오르면 중소형·성장주 선호'),
    ('hyg_ief', '하이일드 ÷ 국채', 'px:hyg', 'px:ief', '내리면 신용 위험 회피'),
]
REGIONS = ['px:kospi', 'px:kosdaq', 'px:spx', 'px:ndx', 'px:rut', 'px:sox', 'px:nikkei', 'px:twii', 'px:hsi', 'px:shcomp', 'px:stoxx', 'px:nifty']
RISK = [('px:sphb', 'px:splv'), ('px:xly', 'px:xlp'), ('px:rsp', 'px:spy'), ('px:eem', 'px:spy')]   # + VIX(역) + 60일선 위 비율
MON_SKIP = {'fred:us10y', 'fred:us30y'}      # 야후 값과 겹친다
STALE_DAYS = {'매일': 5, '주간': 12, '격주': 35, '월간': 100, '분기': 250}


def r(v, d=2):
    return None if v is None or v != v or np.isinf(v) else round(float(v), d)


def load(c):
    df = pd.read_sql('SELECT key, date, value FROM series', c)
    S = {k: g.set_index('date').value.sort_index() for k, g in df.groupby('key')}
    M = {row[0]: dict(zip(['name', 'grp', 'unit', 'source', 'freq', 'use', 'diff', 'dec', 'note', 'asof', 'fetched_at'], row[1:]))
         for row in c.execute('SELECT key,name,grp,unit,source,freq,use,diff,dec,note,asof,fetched_at FROM meta')}
    return S, M


def pct_rank(s, window=500):
    """마지막 값이 직전 window 개 중 몇 %에 있나 (0~100)"""
    s = s.dropna().tail(window)
    return None if len(s) < 60 else float((s <= s.iloc[-1]).mean() * 100)


def row_of(key, s, m):
    s = s.dropna()
    last, diff = s.iloc[-1], bool(m.get('diff'))

    def ch(prev):
        return None if prev is None or prev != prev else (last - prev if diff else (last / prev - 1) * 100)
    back = lambda n: s.iloc[-1 - n] if len(s) > n else None
    y = s[s.index < f'{s.index[-1][:4]}-01-01']
    d1 = s.diff() if diff else s.pct_change() * 100
    sd = d1.tail(250).std()
    w = s.tail(250)
    return {'k': key, 'name': m['name'], 'grp': m['grp'], 'use': m.get('use') or '', 'diff': diff, 'dec': m.get('dec') or 2, 'unit': m.get('unit') or '',
            'date': s.index[-1], 'last': r(last, 4), 'd1': r(ch(back(1))), 'w1': r(ch(back(5))), 'm1': r(ch(back(21))), 'ytd': r(ch(y.iloc[-1] if len(y) else None)),
            'z': r(d1.iloc[-1] / sd if sd else None), 'pos': r((last - w.min()) / (w.max() - w.min()) * 100 if w.max() > w.min() else None, 0),
            'spark': [r(v, 4) for v in s.tail(60)]}


def ratio(S, a, b):
    if b is None:
        return S[a].dropna()
    x = pd.concat([S[a], S[b]], axis=1).dropna()
    return x.iloc[:, 0] / x.iloc[:, 1]


def chg60_rank(s, sign=1, diff=False):
    """60일 변화가 최근 500일 중 몇 번째인가(백분위). sign=-1 이면 내릴수록 높은 점수"""
    c = (s.diff(60) if diff else s.pct_change(60)) * sign
    return pct_rank(c), c


def regime(S):
    def score(at=None):
        cut = (lambda s: s if at is None else s[s.index <= at])
        risk = [pct_rank(cut(ratio(S, a, b).pct_change(60))) for a, b in RISK]
        risk.append(None if (p := pct_rank(cut(S['px:vix']))) is None else 100 - p)
        risk.append(pct_rank(cut(S['kr:ma60'])))
        m = lambda v: r(np.mean([x for x in v if x is not None]), 0)
        lq, lparts = build2.liq_score(S, at)
        return m(risk), lq, [r(x, 0) for x in risk], lparts
    now = score()
    ago = S['px:spx'].index[-21]
    old = score(ago)
    d1 = S['px:spx'].index[-2]                  # 직전 거래일 — 알림의 '전날 대비' (2026-11-26 사용자: 매일 변화를 보이게)
    y = score(d1)
    cell = lambda rk, lq: ('순항' if lq >= 50 else '과열·균열') if rk >= 50 else ('눌림' if lq >= 50 else '위기')
    return {'risk': now[0], 'liq': now[1], 'cell': cell(now[0], now[1]), 'risk_prev': old[0], 'liq_prev': old[1], 'cell_prev': cell(old[0], old[1]), 'prev_date': ago,
            'risk_d1': y[0], 'liq_d1': y[1], 'cell_d1': cell(y[0], y[1]), 'd1_date': d1,
            'risk_parts': dict(zip(['고베타÷저변동', '경기소비÷필수소비', '동일가중÷시총가중', '신흥÷미국', 'VIX(역)', '60일선 위 종목 비율'], now[2])),
            'liq_parts': now[3]}


def us_to_kr(S):
    kr = S['kr:kospi'].pct_change() * 100
    out = {}
    for key, name in (('px:ndx', '나스닥'), ('px:spx', 'S&P500'), ('px:sox', '반도체지수')):
        us = S[key].pct_change() * 100
        prev = us.reindex(us.index.union(kr.index)).ffill().shift(1).reindex(kr.index)     # 한국 t일 ← 그 전 마지막 미국 장
        x = pd.concat([kr, prev], axis=1).dropna().tail(60)
        b = np.polyfit(x.iloc[:, 1], x.iloc[:, 0], 1)[0]
        out[key] = {'name': name, 'beta': r(b), 'corr': r(x.iloc[:, 0].corr(x.iloc[:, 1])), 'us_date': S[key].index[-1], 'us_chg': r(us.iloc[-1]), 'implied': r(b * us.iloc[-1])}
    k = S['kr:kospi']
    out['kospi'] = {'date': k.index[-1], 'chg': r(kr.iloc[-1]), 'after_us': k.index[-1] > S['px:ndx'].index[-1]}
    return out


def boards(S):
    """바닥·과열 신호판: 날짜별 조건 표(미래 값을 쓰지 않음)와 신호 뒤 KOSPI 수익률"""
    k = S['kr:kospi']
    k = k[(k.index >= '2010-06-01') & (k.index <= S['kr:adr20'].index[-1])]      # 폭 지표가 계산된 마지막 날까지 (당일 종목 일봉은 장 마감 뒤에 들어온다)
    idx = k.index
    q95 = lambda s: s.rolling(750, min_periods=250).quantile(0.95).shift(1)
    A = {x: S[x].reindex(idx) for x in ('kr:adr20', 'kr:bblow', 'kr:rsi30', 'kr:nl', 'kr:bbup', 'kr:rsi70', 'kr:nh')}
    ma, sd = k.rolling(20).mean(), k.rolling(20).std(ddof=0)
    pb = (k - (ma - 2 * sd)) / (4 * sd)
    usprev = lambda key: S[key].reindex(S[key].index.union(idx)).ffill().shift(1).reindex(idx)      # 한국 장 시작 전에 알 수 있는 미국 값
    vix, vix3m = usprev('px:vix'), usprev('vol:vix3m')
    thr = {x: q95(A[x]) for x in ('kr:bblow', 'kr:rsi30', 'kr:nl', 'kr:bbup', 'kr:rsi70', 'kr:nh')}
    krprev = lambda s: s.reindex(s.index.union(idx)).ffill().shift(1).reindex(idx)      # 금융투자협회 자료는 하루 늦게 나온다 → 그날 아침에 알 수 있는 전날 값
    fp5, c5 = krprev(S['kr:forced_pct'].rolling(5).mean()), krprev(S['kr:credit'].pct_change(5) * 100)
    fthr = q95(fp5)
    bottom = pd.DataFrame({
        'ADR < 75': A['kr:adr20'] < 75, '볼밴 하단 이탈 비율 상위 5%': A['kr:bblow'] >= thr['kr:bblow'], 'RSI<30 비율 상위 5%': A['kr:rsi30'] >= thr['kr:rsi30'],
        '신저가 비율 상위 5%': A['kr:nl'] >= thr['kr:nl'], 'KOSPI < 볼밴 하단': pb < 0, 'VIX > VIX 3개월 (역전)': vix > vix3m,
        '반대매매 비중 상위 5%': fp5 >= fthr, '신용잔고 5일 −3% 이하': c5 <= -3})
    hot = pd.DataFrame({
        'ADR > 120': A['kr:adr20'] > 120, '볼밴 상단 돌파 비율 상위 5%': A['kr:bbup'] >= thr['kr:bbup'], 'RSI>70 비율 상위 5%': A['kr:rsi70'] >= thr['kr:rsi70'],
        '신고가 비율 상위 5%': A['kr:nh'] >= thr['kr:nh'], 'KOSPI > 볼밴 상단': pb > 1})
    start = '2011-06-01'
    H = {'1개월': 20, '3개월': 60, '6개월': 120, '12개월': 250}
    fwd = {h: (k.shift(-n) / k - 1) * 100 for h, n in H.items()}
    base = {h: {'mean': r(f[f.index >= start].mean(), 1), 'win': r((f[f.index >= start] > 0).mean() * 100, 0)} for h, f in fwd.items()}

    def events(mask):
        """조건이 켜진 날 중, 직전 20거래일 안에 이미 잡힌 날이 없는 날만"""
        out, last = [], -99
        pos = {d: i for i, d in enumerate(idx)}
        for d in mask[mask & (mask.index >= start)].index:
            if pos[d] - last >= 20:
                out.append(d)
                last = pos[d]
        return out

    def stats(ev):
        row = {'n': len(ev), 'dates': ev[-6:]}
        for h, f in fwd.items():
            v = f.reindex(ev).dropna()
            row[h] = {'n': len(v), 'mean': r(v.mean(), 1) if len(v) else None, 'med': r(v.median(), 1) if len(v) else None, 'win': r((v > 0).mean() * 100, 0) if len(v) else None}
        return row

    def board(df, values):
        cnt = df.sum(axis=1)
        now = [{'name': c, 'on': bool(df[c].iloc[-1]), 'value': values.get(c), 'alone': stats(events(df[c].fillna(False)))} for c in df.columns]
        return {'date': idx[-1], 'count': int(cnt.iloc[-1]), 'prev': int(cnt.iloc[-2]), 'max': len(df.columns), 'conds': now,
                'by_count': [{'k': kk, **stats(events(cnt >= kk))} for kk in range(1, len(df.columns) + 1)],
                'hist': {'d': list(idx[-750:]), 'v': [int(x) for x in cnt.iloc[-750:]]}}
    last = lambda s, d=1: r(s.iloc[-1], d)
    vb = {'ADR < 75': f'{last(A["kr:adr20"])}', '볼밴 하단 이탈 비율 상위 5%': f'{last(A["kr:bblow"])}% (기준 {last(thr["kr:bblow"])}%)', 'RSI<30 비율 상위 5%': f'{last(A["kr:rsi30"])}% (기준 {last(thr["kr:rsi30"])}%)',
          '신저가 비율 상위 5%': f'{last(A["kr:nl"])}% (기준 {last(thr["kr:nl"])}%)', 'KOSPI < 볼밴 하단': f'%B {last(pb, 2)}', 'VIX > VIX 3개월 (역전)': f'{last(vix, 2)} vs {last(vix3m, 2)}',
          '반대매매 비중 상위 5%': f'{last(fp5)}% (기준 {last(fthr)}%)', '신용잔고 5일 −3% 이하': f'{last(c5)}%'}
    vh = {'ADR > 120': f'{last(A["kr:adr20"])}', '볼밴 상단 돌파 비율 상위 5%': f'{last(A["kr:bbup"])}% (기준 {last(thr["kr:bbup"])}%)', 'RSI>70 비율 상위 5%': f'{last(A["kr:rsi70"])}% (기준 {last(thr["kr:rsi70"])}%)',
          '신고가 비율 상위 5%': f'{last(A["kr:nh"])}% (기준 {last(thr["kr:nh"])}%)', 'KOSPI > 볼밴 상단': f'%B {last(pb, 2)}'}
    return {'bottom': board(bottom, vb), 'hot': board(hot, vh), 'base': base, 'since': start, 'horizons': list(H),
            'pctb': {'d': list(idx[-750:]), 'v': [r(x, 3) for x in pb.iloc[-750:]]}}


def changes(S, B, mon):
    """오늘 바뀐 것: 기준선을 넘은 지표 + 평소의 2배 넘게 움직인 지표"""
    out = []

    def cross(key, level, below, text, use):
        s = S[key].dropna()
        a, b = s.iloc[-2], s.iloc[-1]
        if (a >= level > b) if below else (a <= level < b):
            out.append({'use': use, 'text': text.format(v=r(b, 1)), 'date': s.index[-1]})
    cross('kr:adr20', 75, True, 'ADR(20일)이 75 아래로 내려왔다 ({v}) — 과매도 구간 진입', '타이밍')
    cross('kr:adr20', 75, False, 'ADR(20일)이 75 위로 올라왔다 ({v}) — 과매도 구간 탈출', '타이밍')
    cross('kr:adr20', 120, False, 'ADR(20일)이 120을 넘었다 ({v}) — 과열 구간', '타이밍')
    cross('px:vix', 30, False, 'VIX가 30을 넘었다 ({v})', '타이밍')
    cross('px:vix', 20, True, 'VIX가 20 아래로 내려왔다 ({v})', '흐름')
    cross('kr:ma60', 20, True, '60일선 위 종목이 20% 아래로 줄었다 ({v}%)', '타이밍')
    t = pd.concat([S['vol:vix9d'], S['vol:vix3m']], axis=1).dropna()
    inv = t.iloc[:, 0] > t.iloc[:, 1]
    if inv.iloc[-1] != inv.iloc[-2]:
        out.append({'use': '타이밍', 'date': t.index[-1], 'text': 'VIX 기간구조가 역전됐다 (9일 > 3개월) — 패닉 진행 신호' if inv.iloc[-1] else 'VIX 기간구조 역전이 풀렸다 — 패닉 진정 확인 신호'})
    for nm, b in (('바닥', B['bottom']), ('과열', B['hot'])):
        if b['count'] != b['prev']:
            out.append({'use': '타이밍', 'date': b['date'], 'text': f'{nm} 신호 {b["prev"]}개 → {b["count"]}개 (전체 {b["max"]}개)'})
    kw = S['px:usdkrw'].dropna()
    c20 = (kw.iloc[-1] / kw.iloc[-21] - 1) * 100
    if abs(c20) >= 3:
        out.append({'use': '흐름', 'date': kw.index[-1], 'text': f'원/달러 20일 변화 {c20:+.1f}% — 환율이 수급을 흔드는 구간'})
    movers = sorted((m for m in mon if m['z'] is not None and abs(m['z']) >= 2), key=lambda m: -abs(m['z']))[:10]
    return out, [{'k': m['k'], 'name': m['name'], 'grp': m['grp'], 'd1': m['d1'], 'diff': m['diff'], 'z': m['z'], 'date': m['date']} for m in movers]


def main():
    c = store.connect()
    S, M = load(c)
    out = config.DATA
    (out / 's').mkdir(parents=True, exist_ok=True)
    dump = lambda name, obj: (out / name).write_text(json.dumps(obj, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    now = datetime.now().strftime('%Y-%m-%d %H:%M')

    # 크로스에셋 표
    mon = [row_of(k, S[k], M[k]) for k in S if M.get(k) and M[k]['grp'] in MON_GROUPS and k not in MON_SKIP and len(S[k].dropna()) > 30]
    from assets import A
    order = {f'px:{a[0]}': i for i, a in enumerate(A)}
    mon.sort(key=lambda m: (MON_GROUPS.index(m['grp']), order.get(m['k'], 999), m['k']))
    dump('monitor.json', {'built': now, 'groups': MON_GROUPS, 'rows': mon})

    # 타이밍
    B = boards(S)
    T = {x: {'d': list(S[x].index[-750:]), 'v': [r(v, 2) for v in S[x].iloc[-750:]]} for x in
         ('kr:kospi', 'kr:adr20', 'kr:adr20:kospi', 'kr:adr20:kosdaq', 'kr:bblow', 'kr:rsi30', 'kr:nl', 'kr:nh', 'kr:ma60', 'kr:ma200', 'px:vix', 'vol:vix9d', 'vol:vix3m', 'vol:vix6m', 'vol:vkospi') if x in S}
    vk = S.get('vol:vkospi')
    term = {k: r(S[k].iloc[-1], 2) for k in ('vol:vix9d', 'px:vix', 'vol:vix3m', 'vol:vix6m')}
    dump('timing.json', {'built': now, 'series': T, 'boards': B, 'term': term, 'term_date': S['vol:vix9d'].index[-1],
                         'vkospi': None if vk is None else {'last': r(vk.iloc[-1], 2), 'date': vk.index[-1], 'pct': r(pct_rank(vk, 750), 0), 'n': len(vk)},
                         'now': {k: r(S[k].iloc[-1], 1) for k in ('kr:adr20', 'kr:adr20:kospi', 'kr:adr20:kosdaq', 'kr:bblow', 'kr:rsi30', 'kr:nl', 'kr:nh', 'kr:ma60', 'kr:ma200')},
                         'pct': {k: r(pct_rank(S[k], 750), 0) for k in ('kr:adr20', 'kr:bblow', 'kr:rsi30', 'kr:nl', 'kr:ma60')}, 'asof': S['kr:adr20'].index[-1]})

    # 오늘
    ch, movers = changes(S, B, mon)
    R = regime(S)
    ch += build2.build(S, M, dump, now, R)          # 비중·수급·공탐지수·AI 크레딧 (파생 계열을 S·M 에 더한다)
    ch3, ib = build3.build(S, M, dump, now, c)      # IB 지표판·CTA 모델·파생·평단
    ch += ch3
    ch4, tf = build4.build(S, M, dump, now, c)      # 추세추종 (분산일·팔로스루·트렌드 템플릿·단계)
    ch += ch4
    fg = lambda k: None if k not in S else {'last': r(S[k].dropna().iloc[-1], 1), 'date': S[k].dropna().index[-1]}
    dump('today.json', {'built': now, 'regime': R, 'changes': ch, 'movers': movers, 'us2kr': us_to_kr(S), 'fg': {'cnn': fg('sent:cnn'), 'kr': fg('sent:krfg'), 'stress': fg('credit:ai_stress')}, 'ib': ib, 'trend': tf,
                        'bottom': {'count': B['bottom']['count'], 'max': B['bottom']['max'], 'on': [x['name'] for x in B['bottom']['conds'] if x['on']]},
                        'hot': {'count': B['hot']['count'], 'max': B['hot']['max'], 'on': [x['name'] for x in B['hot']['conds'] if x['on']]}})

    # 섹터·스타일
    rat = []
    for rid, name, a, b, read in RATIOS:
        s = ratio(S, a, b)
        rk, c60 = chg60_rank(s)
        rat.append({'id': rid, 'name': name, 'read': read, 'a': a, 'b': b, 'date': s.index[-1], 'c20': r((s.iloc[-1] / s.iloc[-21] - 1) * 100, 1), 'c60': r(c60.iloc[-1] * 100, 1),
                    'rank': r(rk, 0), 'd': list(s.index[-250:]), 'v': [r(v, 5) for v in s.iloc[-250:]]})
    reg = []
    for k in REGIONS:
        s = S[k].dropna()
        reg.append({'k': k, 'name': M[k]['name'], 'date': s.index[-1], **{n: r((s.iloc[-1] / s.iloc[-1 - d] - 1) * 100, 1) for n, d in (('w1', 5), ('m1', 21), ('m3', 63), ('m6', 126))}})
    dump('sector.json', {'built': now, 'ratios': rat, 'regions': reg})

    # 페어용 계열 + 목록
    cat = []
    for k, s in S.items():
        m = M.get(k)
        if not m:
            continue
        s = s.dropna()
        if len(s) < 30:
            continue
        if m['grp'] != '한국 폭':
            s = s.tail(1300)
        fk = k.replace(':', '_')
        dump(f's/{fk}.json', {'k': fk, 'name': m['name'], 'unit': m.get('unit') or '', 'd': list(s.index), 'v': [r(v, 4) for v in s]})
        cat.append({'k': fk, 'name': m['name'], 'grp': m['grp']})
    kr = out / 'kr_catalog.json'
    if kr.exists():
        cat += json.loads(kr.read_text(encoding='utf-8'))
    dump('catalog.json', cat)

    # 지표 사전 · 신선도
    dump('glossary.json', {'built': now, 'items': G,
                           'series': [{'k': k, **{f: M[k][f] for f in ('name', 'grp', 'unit', 'source', 'freq', 'use', 'asof')}} for k in sorted(M, key=lambda k: (M[k]['grp'] or '', k))]})
    today = date.today()
    stale = [{'k': k, 'name': m['name'], 'asof': m['asof']} for k, m in M.items() if m['asof'] and (today - date.fromisoformat(m['asof'])).days > STALE_DAYS.get(m.get('freq') or '매일', 5)]
    jobs = {job: {'at': at, 'ok': bool(ok), 'msg': msg} for at, job, ok, msg in c.execute('SELECT at, job, ok, msg FROM runlog ORDER BY at')}
    dump('status.json', {'built': now, 'stale': stale, 'jobs': jobs, 'n_series': len(S)})
    store.log(c, 'build', True, f'계열 {len(S)}, 모니터 {len(mon)}행, 바뀐 것 {len(ch)}건')
    print(f'build: 계열 {len(S)} · 모니터 {len(mon)}행 · 바뀐 것 {len(ch)}건 · 늦은 계열 {len(stale)} · 바닥 신호 {B["bottom"]["count"]}/{B["bottom"]["max"]}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
