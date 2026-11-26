"""추세추종 탭 JSON: trend.json. build.py 가 불러 쓴다.

재료(collect_trend.py): 지수 종가·거래량(tf:c·tf:v), 트렌드 템플릿·단계 비율(tf:kr·tf:us), 통과 종목 목록(blob 'trend_lists').
여기서 계산: 분산일 · IBD식 시장 상태와 팔로스루 데이 · 지수 주봉 와인스타인 단계 · 신호 뒤 수익률(과거 근거).
규칙은 대가들의 책·공개 설명을 기계적 규칙으로 옮긴 '우리 가정'이다 (IBD 는 사람이 판단한다).
"""
import json

import numpy as np
import pandas as pd

from build2 import evidence, pct_rank, r, tail
from build3 import add

IDX = [('spx', 'S&P500', 'us'), ('ndx', '나스닥', 'us'), ('kospi', 'KOSPI', 'kr'), ('kosdaq', 'KOSDAQ', 'kr')]
FTD_GAIN = {'us': 1.2, 'kr': 1.5}     # 팔로스루 데이 최소 상승률(%) — 한국 지수는 하루 변동이 커서 조금 높게
DD_DROP, DD_LIFE, DD_UNDO = -0.2, 25, 1.05
CORR_DD, CORR_DIST = 0.92, 6          # 조정 진입: 상승 구간 고점 대비 −8%, 또는 분산일 6개 이상 + 50일선 아래
PRESS = 5                             # 상승 압박: 분산일 5개 이상
STATE = {2: '상승 확인', 1: '상승 압박', 0: '조정'}


def market_state(c, v, gain):
    """IBD 방식의 시장 상태를 하루씩 따라간다. → DataFrame(dd 개수, 상태 2/1/0, 랠리 일수, 팔로스루 1/실패 −1)"""
    df = pd.concat([c.rename('c'), v.rename('v')], axis=1).dropna(subset=['c'])
    cl, vo = df.c.values, df.v.values
    ch = np.r_[np.nan, cl[1:] / cl[:-1] * 100 - 100]
    m50 = df.c.rolling(50).mean().values
    active, rows = [], []
    state, peak, low, rday, rlow, ftd_i = 2, cl[0], None, 0, None, None
    for i, x in enumerate(cl):
        volup = i > 0 and vo[i] == vo[i] and vo[i - 1] == vo[i - 1] and vo[i] > vo[i - 1] > 0
        active = [(j, cj) for j, cj in active if i - j < DD_LIFE and x < cj * DD_UNDO]
        if i > 0 and ch[i] <= DD_DROP and volup:
            active.append((i, x))
        n, ev = len(active), 0
        if state > 0:
            peak = max(peak, x)
            if rlow is not None and (i - ftd_i) <= DD_LIFE and x < rlow:          # 팔로스루 뒤 랠리 저점을 깨면 실패
                state, low, rday, rlow, ev = 0, x, 0, None, -1
            elif x <= peak * CORR_DD or (n >= CORR_DIST and m50[i] == m50[i] and x < m50[i]):
                state, low, rday, rlow = 0, x, 0, None
            else:
                state = 1 if n >= PRESS else 2
        else:
            if x < low:
                low, rday = x, 0                                                  # 새 저점 → 랠리 처음부터
            elif rday == 0:
                rday = 1 if ch[i] > 0 else 0                                      # 저점 뒤 첫 상승일 = 랠리 1일째
            else:
                rday += 1
            if rday >= 4 and ch[i] >= gain and volup:                             # 4일째 이후 큰 상승 + 거래량 증가
                state, peak, rlow, ftd_i, ev, active = 2, x, low, i, 1, []
                n = 0
        rows.append((n, state, rday if state == 0 else 0, ev))
    out = pd.DataFrame(rows, index=df.index, columns=['dd', 'state', 'rday', 'ev'])
    out.attrs['active'] = [df.index[j] for j, _ in active]          # 지금 살아 있는 분산일
    return out


def weekly_stage(c, thr=0.005):
    """주봉 30주선 기준 와인스타인 단계. → DataFrame(주 끝 날짜: 종가, 30주선, 기울기, 단계)"""
    s = c.copy()
    s.index = pd.to_datetime(s.index)
    w = s.resample('W-FRI').last().dropna()
    last_day = s.index[-1]
    w.index = [min(d, last_day).strftime('%Y-%m-%d') for d in w.index]       # 이번 주는 마지막 거래일로
    ma = w.rolling(30).mean()
    sl = ma / ma.shift(4) - 1
    st, prev = [], 1
    for x, m, k in zip(w.values, ma.values, sl.values):
        if m != m or k != k:
            st.append(np.nan)
            continue
        if x > m and k > thr:
            s_ = 2
        elif x < m and k < -thr:
            s_ = 4
        else:
            s_ = 3 if prev in (2, 3) else 1
        st.append(s_)
        prev = s_
    return pd.DataFrame({'c': w, 'ma': ma, 'slope': sl * 100, 'stage': st})


def build(S, M, dump, now, c):
    extra, idx = [], []
    for key, name, mkt in IDX:
        ck, vk = f'tf:c:{key}', f'tf:v:{key}'
        if ck not in S:
            continue
        px = S[ck].dropna()
        ms = market_state(px, S.get(vk, pd.Series(dtype=float)), FTD_GAIN[mkt])
        add(S, M, f'tf:dd:{key}', ms.dd.astype(float), f'분산일 (25거래일) — {name}', '추세추종', '개', '흐름,타이밍', dec=0)
        add(S, M, f'tf:state:{key}', ms.state.astype(float), f'시장 상태 (IBD식: 2 상승 확인 · 1 압박 · 0 조정) — {name}', '추세추종', '', '흐름', dec=0)
        ws = weekly_stage(px)
        cur = ws.dropna().iloc[-1]
        same = ws.stage.dropna()
        weeks = int((same[::-1] != same.iloc[-1]).values.argmax()) if (same != same.iloc[-1]).any() else len(same)
        ftds = ms.index[ms.ev == 1]
        fails = set(ms.index[ms.ev == -1])
        hist = []
        for d in ftds[-6:]:
            i = px.index.get_loc(d)
            nxt = ms.index[(ms.index > d) & (ms.ev != 0)]
            hist.append({'d': d, 'chg': r((px.iloc[i] / px.iloc[i - 1] - 1) * 100, 2), 'r20': r((px.iloc[min(i + 20, len(px) - 1)] / px.iloc[i] - 1) * 100, 1) if i + 1 < len(px) else None,
                         'r60': r((px.iloc[i + 60] / px.iloc[i] - 1) * 100, 1) if i + 60 < len(px) else None, 'fail': bool(len(nxt) and nxt[0] in fails)})
        L = ms.iloc[-1]
        st_since = ms.index[(ms.state != L.state)][-1] if (ms.state != L.state).any() else ms.index[0]
        dd_dates = ms.attrs['active']
        m50 = px.rolling(50).mean()
        idx.append({'k': key, 'name': name, 'mkt': mkt, 'date': px.index[-1], 'close': r(px.iloc[-1], 2), 'state': int(L.state), 'label': STATE[int(L.state)], 'since': st_since,
                    'dd': int(L.dd), 'dd_dates': dd_dates, 'rday': int(L.rday), 'gain': FTD_GAIN[mkt],
                    'dd_peak': r((px.iloc[-1] / px.tail(63).max() - 1) * 100, 1), 'm50': r((px.iloc[-1] / m50.iloc[-1] - 1) * 100, 1),
                    'stage': int(cur.stage), 'weeks': weeks, 'ma30': r((cur.c / cur.ma - 1) * 100, 1), 'slope': r(cur.slope, 1),
                    'ftd': hist, 'ftd_n': len(ftds), 'fail_n': len(fails),
                    'series': tail(px, 500, 2), 'dd_s': tail(ms.dd.astype(float), 500, 0), 'state_s': tail(ms.state.astype(float), 500, 0),
                    'stage_s': {'d': list(ws.dropna().index[-104:]), 'v': [int(v) for v in ws.dropna().stage.tail(104)]},
                    'ev_ftd': evidence(px, ms.ev == 1, ms.index[260]), 'ev_corr': evidence(px, (ms.state == 0) & (ms.state.shift(1) > 0), ms.index[260]),
                    'ev_dd6': evidence(px, ms.dd >= 6, ms.index[260]), 'ev_st2': evidence(px, pd.Series((ws.stage == 2) & (ws.stage.shift(1) != 2), index=ws.index).reindex(px.index).fillna(False), ms.index[260])})
        if L.ev == 1:
            extra.append({'use': '타이밍', 'date': px.index[-1], 'text': f'{name} 팔로스루 데이 (+{r(px.iloc[-1] / px.iloc[-2] * 100 - 100, 2)}%, 거래량 증가) — IBD식으로 상승 확인 전환'})
        elif L.ev == -1:
            extra.append({'use': '흐름', 'date': px.index[-1], 'text': f'{name} 팔로스루 실패 — 랠리 저점을 깼다, 다시 조정'})
        elif len(ms) > 1 and ms.state.iloc[-2] > 0 and L.state == 0:
            extra.append({'use': '흐름', 'date': px.index[-1], 'text': f'{name} IBD식 시장 상태가 조정으로 바뀌었다 (분산일 {int(L.dd)}개, 63일 고점 대비 {idx[-1]["dd_peak"]}%)'})

    br = {}
    for mkt, tgt in (('kr', 'tf:c:kospi'), ('us', 'tf:c:spx')):
        k = f'tf:{mkt}:tt'
        if k not in S or tgt not in S:
            continue
        tt, st2, st4, px = S[k].dropna(), S[f'tf:{mkt}:st2'].dropna(), S[f'tf:{mkt}:st4'].dropna(), S[tgt].dropna()
        q10 = tt.expanding(500).quantile(0.10).shift(1)      # 그날까지의 값만으로 정한 하위 10% 선
        q90 = tt.expanding(500).quantile(0.90).shift(1)
        lo_turn = (tt.rolling(20).min() <= q10) & (tt >= tt.rolling(20).min() * 2) & (tt.rolling(20).min() > 0)     # 바닥권에서 20일 안에 두 배
        start = tt.index[min(500, len(tt) - 1)]
        br[mkt] = {'date': tt.index[-1], 'tt': r(tt.iloc[-1], 1), 'tt20': r(tt.iloc[-21], 1) if len(tt) > 21 else None, 'tt_pct': r(pct_rank(tt, len(tt)), 0),
                   'q10': r(q10.iloc[-1], 1), 'q90': r(q90.iloc[-1], 1), 'st2': r(st2.iloc[-1], 1), 'st4': r(st4.iloc[-1], 1), 'st2_20': r(st2.iloc[-21], 1) if len(st2) > 21 else None,
                   'since': tt.index[0], 'series': tail(tt, 1300, 1), 'st2_s': tail(st2, 1300, 1), 'st4_s': tail(st4, 1300, 1), 'px': tail(px, 1300, 1),
                   'ev_lo': evidence(px, (tt <= q10).reindex(px.index).fillna(False), start), 'ev_hi': evidence(px, (tt >= q90).reindex(px.index).fillna(False), start),
                   'ev_turn': evidence(px, lo_turn.reindex(px.index).fillna(False), start)}
    row = c.execute("SELECT json FROM blob WHERE key='trend_lists'").fetchone()
    lists = json.loads(row[0]) if row else {}
    for mkt, L in lists.items():
        sec = {}
        for x in L['rows']:
            sec[x.get('sec') or '기타'] = sec.get(x.get('sec') or '기타', 0) + 1
        L['sectors'] = sorted(sec.items(), key=lambda t: -t[1])[:12]
        if mkt == 'kr':
            L['rows'] = [x for x in L['rows'] if (x.get('mc') or 0) >= 1000][:60]
        else:
            L['rows'] = L['rows'][:60]
    dump('trend.json', {'built': now, 'idx': idx, 'breadth': br, 'lists': lists,
                        'rules': {'ftd_gain': FTD_GAIN, 'dd_drop': DD_DROP, 'dd_life': DD_LIFE, 'corr_dd': round((1 - CORR_DD) * 100), 'corr_dist': CORR_DIST, 'press': PRESS}})
    p2 = lambda o, k: (o[k]['v'][-2] if len(o[k]['v']) > 1 else None)       # 직전 값 (알림의 전날 대비)
    summary = {'idx': [{'name': x['name'], 'label': x['label'], 'dd': x['dd'], 'rday': x['rday'], 'stage': x['stage'],
                        'label_p': STATE.get(int(p2(x, 'state_s'))) if p2(x, 'state_s') is not None else None, 'dd_p': p2(x, 'dd_s'), 'stage_p': p2(x, 'stage_s')} for x in idx],
               'tt': {m: {'tt': b['tt'], 'date': b['date'], 'tt_p': b['series']['v'][-2] if len(b['series']['v']) > 1 else None} for m, b in br.items()}}
    return extra, summary
