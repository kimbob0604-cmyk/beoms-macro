"""차트북 — 야데니 'Selected Daily Markets' 의 그림 방식만 따와 공개 시세로 직접 다시 그린다. 원본 이미지는 쓰지 않는다.

따온 방식: 로그 축 · 50·200일선(점선) · 고점 대비 −10% 조정 / −20% 약세장 음영 · 미국 경기침체(NBER) 음영 ·
          범례에 '날짜 = 값' · 양쪽 눈금 · 비율(A÷B)로 상대 강도 보기 · 기준일 = 0% 경로 겹치기.
더한 것:   50·200일선 대비 거리, 최근 1년 범위 중 위치(%), 그날 일어난 일(선 돌파·1년 최고/최저·평소보다 큰 움직임·조정 진입).

  python3 chartbook.py draw [--only spx,kospi] [--light]   # _chartbook/ 에 PNG + index.json (위클리·노션용은 --light)
  python3 chartbook.py text                                # 보낼 글만 찍는다(보내지 않음)
  python3 chartbook.py send [--all] [--preview]            # 텔레그램(MACRO_TG_*)으로 지금 보낸다
  python3 chartbook.py auto                                # run_daily.py 가 부른다

보내는 때: 매일 07시(한국시간)부터 90분 안의 실행 중, 미국 새 종가가 들어온 첫 실행에 한 번(일·월요일 아침과 미국 휴장 다음 날은 건너뜀).
보내는 것: 평일 = 글(전체 차트 한 줄씩) + 그날 일이 생긴 차트만(S&P500 은 늘, 3~6장). 토·일 = 전부(위클리 차트북).
"""
import argparse
import html
import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import requests

import config

KST = ZoneInfo('Asia/Seoul')
OUT = config.ROOT / '_chartbook'
SLOT, WINDOW = 7, 90
DAYS = '월화수목금토일'
SRC = 'Yahoo Finance'
REC_FALLBACK = [('1990-07-01', '1991-03-31'), ('2001-03-01', '2001-11-30'), ('2007-12-01', '2009-06-30'), ('2020-02-01', '2020-04-30')]
SECT = [('XLK', '기술'), ('XLC', '커뮤니케이션'), ('XLY', '경기소비재'), ('XLF', '금융'), ('XLV', '헬스케어'), ('XLI', '산업재'),
        ('XLP', '필수소비재'), ('XLE', '에너지'), ('XLB', '소재'), ('XLU', '유틸리티'), ('XLRE', '부동산'), ('^GSPC', 'S&P500')]
NETSCAPE, CHATGPT = '1995-08-09', '2022-11-30'

DARK = dict(bg='#0d1117', fg='#e6edf3', muted='#8b949e', grid='#30363d', box='#161b22', main='#58a6ff', ma50='#3fb950', ma200='#ff7b72',
            corr='#388bfd', bear='#f85149', rec='#8b949e', a_sh=0.20, a_rec=0.22, c=['#58a6ff', '#ff7b72', '#3fb950', '#e3b341', '#d2a8ff'],
            up='#ff6b6b', down='#4c8dff', ref='#c9d1d9')
LIGHT = dict(bg='#ffffff', fg='#111111', muted='#555555', grid='#bdbdbd', box='#ffffff', main='#1f3fd6', ma50='#138a36', ma200='#d1242f',
             corr='#6fd0f5', bear='#f4a3a3', rec='#c4c4c4', a_sh=0.45, a_rec=0.55, c=['#1f3fd6', '#d1242f', '#138a36', '#b7791f', '#7b3fe4'],
             up='#d1242f', down='#1f5fd6', ref='#444444')


# ---------- 숫자 꼴 ----------
def fv(v, unit=''):
    if v is None or v != v:
        return '–'
    a = abs(v)
    s = f'{v:,.0f}' if a >= 1000 else f'{v:,.1f}' if a >= 100 else f'{v:.2f}' if a >= 1 else f'{v:.3f}'
    return '$' + s if unit == '$' else s + unit


def sp(v, unit='%', d=1):
    """부호 붙인 변화. 글(텔레그램)용 — 빼기는 '−'"""
    if v is None or v != v:
        return '–'
    return f'{v:+.{d}f}{unit}'.replace('-', '−')


def md(ts):
    return f'{ts.month}/{ts.day}'


# ---------- 데이터 ----------
def load(tickers):
    """{티커: 종가 Series} — 배당 조정 없는 가격(야데니 차트처럼 가격 지수끼리 비교). 한 번에 받고 빠진 것만 하나씩 다시"""
    import warnings
    import yfinance as yf
    warnings.filterwarnings('ignore')
    tk = sorted(set(tickers))
    out = {}
    try:
        d = yf.download(tk, start='1985-01-01', interval='1d', auto_adjust=False, progress=False, threads=True)['Close']
        out = {t: d[t].dropna() for t in tk if t in d and d[t].notna().any()}
    except Exception as e:
        print(f'chartbook: 한 번에 받기 실패 — {type(e).__name__}')
    for rnd in range(2):
        left = [t for t in tk if t not in out]
        if not left:
            break
        time.sleep(5 if rnd == 0 else 20)
        for t in left:
            try:
                x = yf.download(t, start='1985-01-01', interval='1d', auto_adjust=False, progress=False, threads=False)['Close'].squeeze().dropna()
                if len(x):
                    out[t] = x
            except Exception:
                pass
            time.sleep(1)
    for t, s in out.items():
        s.index = pd.to_datetime(s.index).tz_localize(None).normalize()
        out[t] = s[~s.index.duplicated(keep='last')].astype(float)
    return out


def recessions():
    """미국 경기침체(NBER, FRED USREC 월별) 구간. 열쇠가 없거나 실패하면 알려진 구간으로"""
    k = config.key('FRED_KEY')
    if k:
        try:
            r = requests.get('https://api.stlouisfed.org/fred/series/observations', timeout=30,
                             params={'series_id': 'USREC', 'api_key': k, 'file_type': 'json', 'observation_start': '1985-01-01'})
            r.raise_for_status()
            out, st, last = [], None, None
            for o in r.json()['observations']:
                on = o['value'] == '1'
                if on and st is None:
                    st = o['date']
                if not on and st:
                    out.append((st, (pd.Timestamp(last) + pd.offsets.MonthEnd(0)).strftime('%Y-%m-%d')))
                    st = None
                last = o['date']
            if st:
                out.append((st, (pd.Timestamp(last) + pd.offsets.MonthEnd(0)).strftime('%Y-%m-%d')))
            if out:
                return out
        except Exception as e:
            print(f'chartbook: USREC 못 받음 — {type(e).__name__}, 알려진 구간으로')
    return REC_FALLBACK


def ratio(P, a, b):
    return (P[a] / P[b]).dropna()


# ---------- 계산 ----------
def episodes(s, lo=0.10, up=0.20):
    """고점 대비 lo 이상 하락한 구간 [(고점일, 저점일(진행 중이면 마지막 날), 최대 낙폭, 진행 중?)].
    끝 = 고점을 되찾거나 저점에서 up 만큼 오른 때. 그 뒤로는 저점부터 다시 고점을 잡는다(2022 약세장 뒤 2023 조정처럼)."""
    v, ix, n = s.values, s.index, len(s)
    out, ip, i = [], 0, 0
    while i < n:
        if v[i] > v[ip]:
            ip = i
        elif v[i] <= v[ip] * (1 - lo):
            it, j = i, i
            while j < n:
                if v[j] < v[it]:
                    it = j
                if v[j] >= v[ip] or v[j] >= v[it] * (1 + up):
                    break
                j += 1
            ongoing = j >= n
            out.append((ix[ip], ix[-1] if ongoing else ix[it], v[it] / v[ip] - 1, ongoing))
            if ongoing:
                break
            ip = i = it
        i += 1
    return out


def fresh(s, way=1):
    """오늘이 1년(252거래일) 최고(way=1)·최저(−1)이고, 지난 10거래일 안에는 낸 적이 없을 때 — 계속 신고가를 내는 추세에서 매일 울리지 않게"""
    if len(s) < 262:
        return False
    x = s if way > 0 else -s
    top = x.rolling(252, min_periods=200).max()
    return bool(x.iloc[-1] >= top.iloc[-1] and not (x.iloc[-11:-1] >= top.iloc[-11:-1]).any())


def ep_state(s):
    e = episodes(s)
    if not e or not e[-1][3]:
        return None
    pk, _, depth, _ = e[-1]
    return {'kind': '약세장' if depth <= -0.2 else '조정', 'peak': pk, 'depth': depth * 100, 'dd': (s.iloc[-1] / s.loc[pk] - 1) * 100}


def stat(s, kind='pct'):
    """kind: pct(변화율) / bp(금리 — 차이를 bp 로). 반환: 값·변화·이평 거리·1년 위치·평소 대비 크기·일어난 일[(점수, 글)]"""
    s = s.dropna()
    d, last = s.index[-1], float(s.iloc[-1])

    def at(days):
        x = s[s.index <= d - pd.Timedelta(days=days)]
        return float(x.iloc[-1]) if len(x) else None

    def ch(o):
        if o is None:
            return None
        return (last - o) * 100 if kind == 'bp' else (last / o - 1) * 100 if o else None
    ytd_base = s[s.index < pd.Timestamp(d.year, 1, 1)]
    m50, m200 = s.rolling(50).mean(), s.rolling(200).mean()
    vs = lambda m: None if np.isnan(m.iloc[-1]) else ((last - m.iloc[-1]) * 100 if kind == 'bp' else (last / m.iloc[-1] - 1) * 100)
    y1 = s[s.index > d - pd.Timedelta(days=365)]
    pos = (last - y1.min()) / (y1.max() - y1.min()) * 100 if y1.max() > y1.min() else None
    r = s.diff() if kind == 'bp' else s.pct_change()
    sd = r.iloc[-253:-1].std()
    z = float(r.iloc[-1] / sd) if sd and sd == sd else None
    ev = []

    def crossed(x):
        """x = 선 위(+)/아래(−) 거리. 오늘 처음 넘었고, 그 전 10일 중 8일 넘게 반대편에 있었을 때만(하루 넘었다 돌아오는 잡음 거름)"""
        sg = np.sign(x.iloc[-11:].values)
        if len(sg) < 11 or np.isnan(sg).any() or sg[-1] == sg[-2]:
            return 0
        now = 1 if x.iloc[-1] >= 0 else -1
        return now if (sg[:-1] == -now).sum() >= 8 else 0
    if len(s) > 212:
        for m, name, sc in ((m200, '200일선', 10), (m50, '50일선', 6)):
            k = crossed(s - m)
            if k:
                ev.append((sc, f"{name} {'위로 올라섬' if k > 0 else '아래로 내려감'}"))
        k = crossed(m50 - m200)
        if k:
            ev.append((8, '50일선이 200일선 ' + ('위로(골든크로스)' if k > 0 else '아래로(데드크로스)')))
    if len(y1) > 200:
        if fresh(s, 1):
            ev.append((5, '1년 최고'))
        elif fresh(s, -1):
            ev.append((5, '1년 최저'))
    if z is not None and abs(z) >= 2.5:
        ev.append((3 + min(abs(z), 5), f"하루 {'상승' if z > 0 else '하락'}이 평소의 {abs(z):.1f}배"))
    return {'date': d.strftime('%Y-%m-%d'), 'last': last, 'kind': kind, 'd1': ch(float(s.iloc[-2])), 'w1': ch(at(7)),
            'ytd': ch(float(ytd_base.iloc[-1])) if len(ytd_base) else None, 'vs50': vs(m50), 'vs200': vs(m200), 'pos': pos, 'z': z, 'events': ev}


# ---------- 그림 ----------
def font():
    import matplotlib.pyplot as plt
    from matplotlib import font_manager
    want = ('Pretendard', 'NanumGothic', 'Noto Sans CJK KR', 'Apple SD Gothic Neo', 'AppleGothic')

    def find():
        for f in font_manager.findSystemFonts():
            n = Path(f).name
            if n.startswith(('Pretendard-Regular', 'Pretendard-Bold', 'NanumGothic', 'NotoSansCJK', 'AppleSDGothicNeo')):
                try:
                    font_manager.fontManager.addfont(f)
                except Exception:
                    pass
        names = {x.name for x in font_manager.fontManager.ttflist}
        return next((w for w in want if w in names), None)
    fam = find()
    if not fam and sys.platform.startswith('linux'):       # 클라우드(우분투)에는 한글 글꼴이 없다 — 그릴 때만 한 번 깐다
        subprocess.run('sudo apt-get update -qq && sudo apt-get install -y -qq fonts-nanum', shell=True, check=False, capture_output=True)
        fam = find()
    if fam:
        plt.rcParams['font.family'] = fam
    plt.rcParams['axes.unicode_minus'] = False


def canvas(T, title, sub):
    import matplotlib.pyplot as plt
    fig = plt.figure(figsize=(12.8, 7.2), dpi=125)
    fig.patch.set_facecolor(T['bg'])
    fig.text(0.055, 0.952, title, fontsize=17, fontweight='bold', color=T['fg'], va='center')
    fig.text(0.055, 0.908, sub, fontsize=11, color=T['muted'], va='center')
    return fig


def style(ax, T, right=True):
    ax.set_facecolor(T['bg'])
    for s_ in ax.spines.values():
        s_.set_color(T['muted'])
    ax.grid(True, ls=':', color=T['grid'], lw=0.8)
    ax.tick_params(colors=T['fg'], labelsize=10, right=right, labelright=right)


def foot(fig, T, note='', src=SRC):
    fig.text(0.055, 0.025, f"자료: {src} · Beom's Macro 차트북", fontsize=9, color=T['muted'])
    if note:
        fig.text(0.945, 0.025, note, fontsize=9.5, color=T['fg'], ha='right')


def xdates(ax, a, b):
    import matplotlib.dates as mdates
    yrs = (b - a).days / 365.25
    if yrs > 2.5:
        ax.xaxis.set_major_locator(mdates.YearLocator(base=max(1, int(np.ceil(yrs / 13)))))
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y'))
    else:
        ax.xaxis.set_major_locator(mdates.MonthLocator(bymonth=(1, 4, 7, 10) if yrs > 1 else range(1, 13, 2)))
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%y.%m'))
    ax.set_xlim(a, b + (b - a) * 0.015)


def logy(ax, lo, hi):
    """로그 축(야데니의 ratio scale) + 읽기 쉬운 눈금"""
    from matplotlib.ticker import FixedLocator, FuncFormatter, MaxNLocator, NullFormatter, NullLocator
    ax.set_yscale('log')
    if hi / lo < 2.5:
        ticks = MaxNLocator(nbins=8).tick_values(lo, hi)
    else:
        ticks = []
        sets = ([1, 1.5, 2, 2.5, 3, 4, 5, 6, 7, 8, 9], [1, 2, 3, 4, 5, 6, 7, 8, 9], [1, 1.5, 2, 3, 5, 7], [1, 2, 3, 5], [1, 2, 5], [1])
        cand = [[m * 10 ** e for e in range(int(np.floor(np.log10(lo))), int(np.ceil(np.log10(hi))) + 1) for m in ms if lo * 0.97 <= m * 10 ** e <= hi * 1.03] for ms in sets]
        ticks = next((t for t in cand if 5 <= len(t) <= 10), next((t for t in cand if len(t) <= 10), cand[-1]))
    ax.yaxis.set_major_locator(FixedLocator(ticks))
    ax.yaxis.set_minor_locator(NullLocator())
    ax.yaxis.set_minor_formatter(NullFormatter())
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: fv(v).replace('−', '-')))
    ax.set_ylim(lo * 0.96, hi * 1.04)


def leg(ax, T, handles=None, loc='best', ncol=1, **kw):
    L = ax.legend(handles=handles, loc=loc, fontsize=10.5, frameon=True, ncol=ncol, labelcolor=T['fg'], **kw)
    L.get_frame().set_facecolor(T['box'])
    L.get_frame().set_edgecolor(T['muted'])
    L.get_frame().set_alpha(0.95)
    return L


def lab(name, s, unit=''):
    return f'{name} ({md(s.index[-1])} = {fv(float(s.iloc[-1]), unit)})'


def shade(ax, T, a, P_eps=None, rec=None):
    """조정·약세장(지수 자체의 고점 대비 하락)과 미국 경기침체 음영. 범례용 조각을 돌려준다"""
    from matplotlib.patches import Patch
    hs = []
    if P_eps is not None:
        got = set()
        for pk, tr, depth, _ in P_eps:
            if tr < a:
                continue
            bear = depth <= -0.2
            ax.axvspan(max(pk, a), tr, color=T['bear' if bear else 'corr'], alpha=T['a_sh'], lw=0, zorder=0)
            got.add(bear)
        if False in got:
            hs.append(Patch(color=T['corr'], alpha=T['a_sh'] + 0.15, label='조정 (고점 대비 −10~20%)'.replace('−', '-')))
        if True in got:
            hs.append(Patch(color=T['bear'], alpha=T['a_sh'] + 0.15, label='약세장 (고점 대비 −20% 넘게)'.replace('−', '-')))
    if rec:
        hit = False
        for x, y in rec:
            x, y = pd.Timestamp(x), pd.Timestamp(y)
            if y >= a:
                ax.axvspan(max(x, a), y, color=T['rec'], alpha=T['a_rec'], lw=0, zorder=0)
                hit = True
        if hit:
            hs.append(Patch(color=T['rec'], alpha=T['a_rec'] + 0.1, label='미국 경기침체 (NBER)'))
    return hs


def since(s, years):
    return s.index[0] if years is None else max(s.index[0], s.index[-1] - pd.DateOffset(years=years))


def note_of(st, name=''):
    if st['vs50'] is None:
        return ''
    u = 'bp' if st['kind'] == 'bp' else '%'
    p = f" · 1년 범위 중 {st['pos']:.0f}%" if st['pos'] is not None else ''
    return (f'{name}: ' if name else '') + f"50일선 대비 {sp(st['vs50'], u, 0 if u == 'bp' else 1)} · 200일선 대비 {sp(st['vs200'], u, 0 if u == 'bp' else 1)}{p}".replace('−', '-')


def draw_index(ch, P, T, ctx):
    s = P[ch['tk']]
    a = since(s, ch['years'])
    m50, m200 = s.rolling(50).mean(), s.rolling(200).mean()
    w = s[a:]
    fig = canvas(T, ch['title'], ch['sub'])
    ax = fig.add_axes([0.055, 0.085, 0.89, 0.78])
    style(ax, T)
    h = [ax.plot(w.index, w.values, color=T['main'], lw=1.5, label=lab(ch['name'], w))[0],
         ax.plot(m50[a:].index, m50[a:].values, color=T['ma50'], lw=1.8, ls=(0, (1, 1.2)), label=lab('50일선', m50[a:]))[0],
         ax.plot(m200[a:].index, m200[a:].values, color=T['ma200'], lw=1.8, ls=(0, (1, 1.2)), label=lab('200일선', m200[a:]))[0]]
    h += shade(ax, T, a, episodes(s), ctx['rec'] if ch.get('rec') else None)
    logy(ax, float(w.min()), float(w.max()))
    xdates(ax, a, w.index[-1])
    leg(ax, T, h, loc='upper left')
    return fig, ax, s


def draw_ratio(ch, P, T, ctx):
    lines = [(n, ratio(P, x, y)) for n, x, y in ch['lines']]
    a = max(since(s, ch['years']) for _, s in lines)
    fig = canvas(T, ch['title'], ch['sub'])
    ax = fig.add_axes([0.055, 0.085, 0.89, 0.78])
    style(ax, T)
    h = []
    for i, (n, s) in enumerate(lines):
        w = s[a:]
        h.append(ax.plot(w.index, w.values, color=T['c'][i] if len(lines) > 1 else T['main'], lw=1.4 if len(lines) > 1 else 1.5, label=lab(n, w))[0])
    if len(lines) == 1:
        s = lines[0][1]
        for m, c, n in ((s.rolling(50).mean(), T['ma50'], '50일선'), (s.rolling(200).mean(), T['ma200'], '200일선')):
            if m[a:].notna().any():
                h.append(ax.plot(m[a:].index, m[a:].values, color=c, lw=1.7, ls=(0, (1, 1.2)), label=lab(n, m[a:].dropna()))[0])
    h += shade(ax, T, a, None, ctx['rec'] if ch.get('rec', True) else None)
    if ch.get('log'):
        lo = min(float(s[a:].min()) for _, s in lines)
        hi = max(float(s[a:].max()) for _, s in lines)
        logy(ax, lo, hi)
    xdates(ax, a, max(s.index[-1] for _, s in lines))
    leg(ax, T, h)
    main = dict(lines)[ch.get('main', lines[0][0])] if ch.get('main') else lines[0][1]
    return fig, ax, main


def draw_dual(ch, P, T, ctx):
    (na, ta, ua, la), (nb, tb, ub, lb) = ch['a'], ch['b']
    A, B = P[ta], P[tb]
    a = max(since(A, ch['years']), since(B, ch['years']))
    wa, wb = A[a:], B[a:]
    fig = canvas(T, ch['title'], ch['sub'])
    ax = fig.add_axes([0.065, 0.085, 0.87, 0.78])
    style(ax, T, right=False)
    bx = ax.twinx()
    style(bx, T, right=True)
    bx.grid(False)
    ha = ax.plot(wa.index, wa.values, color=T['c'][0], lw=1.5, label=lab(na + ' (왼쪽)', wa, ua))[0]
    hb = bx.plot(wb.index, wb.values, color=T['c'][1], lw=1.5, label=lab(nb + (' (오른쪽, 뒤집은 축)' if ch.get('invert_b') else ' (오른쪽)'), wb, ub))[0]
    if la:
        logy(ax, float(wa.min()), float(wa.max()))
    if lb:
        logy(bx, float(wb.min()), float(wb.max()))
    if ch.get('invert_b'):
        bx.invert_yaxis()
    ax.tick_params(axis='y', colors=T['c'][0])
    bx.tick_params(axis='y', colors=T['c'][1], left=False, labelleft=False)
    h = [ha, hb] + shade(ax, T, a, None, ctx['rec'] if ch.get('rec') else None)
    xdates(ax, a, max(wa.index[-1], wb.index[-1]))
    leg(bx, T, h, loc='lower right', bbox_to_anchor=(1.0, 1.005))     # 두 축 선을 다 피하려고 그림 위 오른쪽에
    return fig, ax, ch['stat'](P)


def draw_sectors(ch, P, T, ctx):
    d = P['^GSPC'].index[-1]

    def chg(s, base_date):
        x = s[s.index <= base_date]
        return (float(s.iloc[-1]) / float(x.iloc[-1]) - 1) * 100 if len(x) else None
    wk = d - pd.Timedelta(days=7)
    yb = pd.Timestamp(d.year - 1, 12, 31)
    rows = [(n, t, chg(P[t], wk), chg(P[t], yb)) for t, n in SECT if t in P]
    fig = canvas(T, ch['title'], f"{ch['sub']} · 1주 = {md(P['^GSPC'][P['^GSPC'].index <= wk].index[-1])}→{md(d)}")
    for k, (col, lab_) in enumerate(((2, '최근 1주'), (3, '연초 이후'))):
        ax = fig.add_axes([0.11 + k * 0.47, 0.085, 0.36, 0.76])
        style(ax, T, right=False)
        ax.grid(True, axis='x', ls=':', color=T['grid'])
        ax.grid(False, axis='y')
        rs = sorted([r for r in rows if r[col] is not None], key=lambda r: r[col])
        ys = range(len(rs))
        cols = [T['ref'] if r[1] == '^GSPC' else (T['up'] if r[col] >= 0 else T['down']) for r in rs]
        ax.barh(list(ys), [r[col] for r in rs], color=cols, height=0.65)
        ax.set_yticks(list(ys))
        ax.set_yticklabels([r[0] for r in rs], color=T['fg'], fontsize=11)
        ax.axvline(0, color=T['muted'], lw=0.8)
        lo, hi = min(0, min(r[col] for r in rs)), max(0, max(r[col] for r in rs))
        pad = (hi - lo) * 0.22 or 1
        ax.set_xlim(lo - pad, hi + pad)
        for y, r in zip(ys, rs):
            v = r[col]
            ax.text(v + (pad * 0.06 if v >= 0 else -pad * 0.06), y, f'{v:+.1f}%', va='center', ha='left' if v >= 0 else 'right', color=T['fg'], fontsize=10)
        ax.set_title(lab_, color=T['fg'], fontsize=13, loc='left')
    fig.text(0.945, 0.025, '빨강 = 오름 · 파랑 = 내림 · 회색 = S&P500', fontsize=9.5, color=T['muted'], ha='right')
    best = max((r for r in rows if r[1] != '^GSPC' and r[2] is not None), key=lambda r: r[2])
    worst = min((r for r in rows if r[1] != '^GSPC' and r[2] is not None), key=lambda r: r[2])
    ctx['extra']['sectors'] = [f"1주 1위 {best[0]} {sp(best[2])} · 꼴찌 {worst[0]} {sp(worst[2])}"]
    return fig, None, P['^GSPC']


def draw_path(ch, P, T, ctx):
    s = P['^NDX']
    A = s[s.index >= NETSCAPE]
    B = s[s.index >= CHATGPT]
    A, B = (A / A.iloc[0] - 1) * 100, (B / B.iloc[0] - 1) * 100
    nB = len(B)
    nA = min(len(A), max(nB + 450, 1900))
    fig = canvas(T, ch['title'], ch['sub'])
    ax = fig.add_axes([0.055, 0.1, 0.89, 0.765])
    style(ax, T)
    k = int(np.argmax(A.iloc[:nA].values))
    h = [ax.plot(range(nA), A.iloc[:nA].values, color=T['c'][1], lw=1.5, label=f'넷스케이프 상장 뒤 ({NETSCAPE} = 0%)')[0],
         ax.plot(range(nB), B.values, color=T['main'], lw=2, label=f'챗GPT 출시 뒤 ({CHATGPT} = 0%, {md(B.index[-1])} = {B.iloc[-1]:+.0f}%)')[0]]
    ax.scatter([k], [A.iloc[k]], color=T['c'][1], zorder=5, s=25)
    ax.annotate(f'닷컴 고점 {A.index[k]:%Y-%m} +{A.iloc[k]:.0f}% ({k:,}거래일째)', (k, A.iloc[k]), xytext=(10, -4), textcoords='offset points', color=T['fg'], fontsize=10)
    ax.scatter([nB - 1], [B.iloc[-1]], color=T['main'], zorder=5, s=25)
    ax.axvline(nB - 1, color=T['muted'], ls=':', lw=1)
    ax.axhline(0, color=T['muted'], lw=0.8)
    ax.set_xlim(0, nA * 1.01)
    ax.set_xlabel('기준일 뒤 거래일 수', color=T['muted'], fontsize=10)
    leg(ax, T, h)
    same = float(A.iloc[nB - 1])
    ctx['extra']['path'] = [f"챗GPT 뒤 {nB - 1:,}거래일: {sp(B.iloc[-1], '%', 0)} · 넷스케이프 뒤 같은 날: {sp(same, '%', 0)} · 닷컴 고점은 {k:,}거래일째"]
    return fig, ax, B


# ---------- 차트 목록 ----------
CHARTS = [
    dict(id='spx', kind='index', tk='^GSPC', name='S&P500', years=7, rec=True, title='S&P500과 50·200일선', sub='로그 축, 매일 · 음영 = 고점 대비 하락 구간',
         need=['^GSPC'], read='200일선 아래에 머무는 날이 길어지면 추세가 꺾인 것. 음영은 고점 대비 −10% 조정, −20% 약세장.'),
    dict(id='kospi', kind='index', tk='^KS11', name='KOSPI', years=7, title='KOSPI와 50·200일선', sub='로그 축, 매일 · 음영 = 고점 대비 하락 구간',
         need=['^KS11'], read='같은 방식을 KOSPI에. 모의 펀드 BM(KOSPI200)과 같은 방향으로 움직인다.'),
    dict(id='sectors', kind='sectors', title='S&P500 업종 성과', sub='업종 ETF 11개 가격 변화', weekly=True, need=[t for t, _ in SECT],
         read='1주 순위와 연초 이후 순위가 엇갈리면 순환매. 어느 업종이 지수를 끄는지 본다.'),
    dict(id='ew_cw', kind='ratio', lines=[('동일가중 ÷ 시총가중', '^SPXEW', '^GSPC')], years=None, title='S&P500 동일가중 ÷ 시총가중', sub='매일 · 회색 = 미국 경기침체',
         need=['^SPXEW', '^GSPC'], read='오르면 상승이 여러 종목으로 넓어지는 것, 내리면 대형주 몇 개가 지수를 끄는 것.'),
    dict(id='ndx_cw_ew', kind='ratio', lines=[('시총가중 ÷ 동일가중', '^NDX', '^NDXE')], years=None, title='나스닥100 시총가중 ÷ 동일가중', sub='매일 · 회색 = 미국 경기침체',
         need=['^NDX', '^NDXE'], read='오르면 나스닥100 안에서도 초대형주 쏠림이 커지는 것.'),
    dict(id='mags', kind='ratio', lines=[('MAGS ÷ XMAG', 'MAGS', 'XMAG')], years=None, rec=False, title='매그7 ÷ S&P500 매그7 제외', sub='MAGS(매그7 ETF) ÷ XMAG(S&P500 매그7 제외 ETF), 매일',
         need=['MAGS', 'XMAG'], read='오르면 매그7 쏠림, 내리면 나머지 493개 종목으로 퍼지는 것.'),
    dict(id='mom', kind='ratio', lines=[('SPMO ÷ SPY', 'SPMO', 'SPY')], years=None, title='모멘텀 ÷ S&P500', sub='SPMO(S&P500 모멘텀 ETF) ÷ SPY, 매일',
         need=['SPMO', 'SPY'], read='오르면 오르던 종목이 계속 오르는 장. 급히 꺾이면 주도주가 바뀌는 중일 때가 많다.'),
    dict(id='gv', kind='ratio', lines=[('성장 ÷ 가치', 'IVW', 'IVE')], years=None, log=True, title='S&P500 성장 ÷ 가치', sub='IVW ÷ IVE, 로그 축, 매일',
         need=['IVW', 'IVE'], read='금리가 내리고 이익 성장이 귀할 때 오른다.'),
    dict(id='size', kind='ratio', lines=[('S&P400 ÷ S&P500', '^SP400', '^GSPC'), ('러셀2000 ÷ S&P500', '^RUT', '^GSPC'), ('S&P600 ÷ S&P500', '^SP600', '^GSPC')],
         main='러셀2000 ÷ S&P500', years=None, title='중소형주 ÷ S&P500', sub='S&P400(중형)·S&P600(소형)·러셀2000 ÷ S&P500, 매일',
         need=['^SP400', '^SP600', '^RUT', '^GSPC'], read='내려가면 대형주 우위가 이어지는 것. 한 줄 요약은 러셀2000 기준.'),
    dict(id='q_small', kind='ratio', lines=[('S&P600 ÷ 러셀2000', '^SP600', '^RUT')], years=None, title='S&P600 ÷ 러셀2000', sub='흑자 요건이 있는 소형주 ÷ 소형주 전체, 매일',
         need=['^SP600', '^RUT'], read='오르면 소형주 안에서도 적자 기업보다 흑자 기업이 나은 장.'),
    dict(id='us_world', kind='ratio', lines=[('SPY ÷ ACWX', 'SPY', 'ACWX')], years=None, title='미국 ÷ 미국 밖', sub='SPY ÷ ACWX(전세계 미국 제외 ETF), 매일',
         need=['SPY', 'ACWX'], read='내리면 미국 밖으로 돈이 도는 것. 한국 비중 판단과 이어진다.'),
    dict(id='kq_ks', kind='ratio', lines=[('KOSDAQ ÷ KOSPI', '^KQ11', '^KS11')], years=None, rec=False, title='KOSDAQ ÷ KOSPI', sub='매일',
         need=['^KQ11', '^KS11'], read='오르면 중소형·성장주 장, 내리면 대형 수출주 장.'),
    dict(id='dow', kind='dual', a=('다우', '^DJI', '', True), b=('다우 운송', '^DJT', '', True), years=5, title='다우 vs 다우 운송', sub='둘 다 로그 축, 매일',
         need=['^DJI', '^DJT'], stat=lambda P: ratio(P, '^DJT', '^DJI'), stat_name='운송 ÷ 다우',
         read='다우 이론: 다우와 운송이 같이 신고가를 내야 추세 확인. 하나만 내면 비확인.'),
    dict(id='cu_oil', kind='dual', a=('구리', 'HG=F', '$', False), b=('브렌트유', 'BZ=F', '$', False), years=5, title='구리 vs 브렌트유', sub='근월물 선물, 매일',
         need=['HG=F', 'BZ=F'], stat=lambda P: ratio(P, 'HG=F', 'BZ=F'), stat_name='구리 ÷ 브렌트',
         read='구리는 경기, 유가는 공급 충격에도 오른다. 구리÷유가가 오르면 성장 쪽, 내리면 인플레·공급 쪽.'),
    dict(id='tnx_tlt', kind='dual', a=('미국 10년 금리', '^TNX', '%', False), b=('TLT', 'TLT', '$', False), invert_b=True, years=5, title='미국 10년 금리 vs 장기채 ETF(TLT)',
         sub='TLT 는 축을 뒤집어 같은 방향으로 겹침, 매일', need=['^TNX', 'TLT'], stat=lambda P: P['^TNX'], stat_name='미국 10년', stat_kind='bp', unit='%',
         read='금리가 오르면 장기채 값이 내린다. TLT 는 20년 넘는 채권이라 30년 금리에 더 가깝고, 분배금만큼 값이 빠지는 가격 기준이라 시간이 갈수록 조금씩 벌어진다.'),
    dict(id='ndx_jpy', kind='dual', a=('나스닥100', '^NDX', '', True), b=('엔/달러', 'JPY=X', '', False), years=5, title='나스닥100 vs 엔/달러', sub='엔/달러가 내리면 엔화 강세, 매일',
         need=['^NDX', 'JPY=X'], stat=lambda P: P['JPY=X'], stat_name='엔/달러',
         read='엔화가 급히 강해질 때(오른쪽 선 급락) 엔캐리 청산으로 나스닥이 같이 흔들린 적이 있다(2024년 8월).'),
    dict(id='path', kind='path', title='나스닥100: 넷스케이프 뒤 vs 챗GPT 뒤', sub='기준일 = 0% 로 맞춘 변화율, 거래일 수로 겹침', weekly=True, need=['^NDX'],
         read='닷컴 때와 같은 거래일 수에서 어디쯤인지. 같은 길을 간다는 뜻은 아니고, 속도 비교용.'),
]
DRAW = {'index': draw_index, 'ratio': draw_ratio, 'dual': draw_dual, 'sectors': draw_sectors, 'path': draw_path}
SHORT = {'spx': 'S&P500', 'kospi': 'KOSPI', 'sectors': '업종', 'ew_cw': 'S&P 동일÷시총', 'ndx_cw_ew': '나스닥100 시총÷동일', 'mags': '매그7÷나머지',
         'mom': '모멘텀÷S&P', 'gv': '성장÷가치', 'size': '러셀2000÷S&P', 'q_small': 'S&P600÷러셀', 'us_world': '미국÷미국 밖', 'kq_ks': 'KOSDAQ÷KOSPI',
         'dow': '운송÷다우', 'cu_oil': '구리÷브렌트', 'tnx_tlt': '미국 10년', 'ndx_jpy': '엔/달러', 'path': '나스닥100 경로'}


def extras(ch, P, s, st):
    """차트별 덧붙일 줄과 일어난 일"""
    lines, ev = [], []
    if ch['kind'] == 'index':
        full = P[ch['tk']]
        now, prev = ep_state(full), ep_state(full.iloc[:-1])
        ath = (full.iloc[-1] / full.cummax().iloc[-1] - 1) * 100
        if now:
            lines.append(f"{now['kind']} 진행 중: {md(now['peak'])} 고점 대비 {sp(now['dd'])} (가장 깊었을 때 {sp(now['depth'])})")
            top = full.idxmax()
            if top != now['peak']:
                lines.append(f"사상 최고({top:%y/%m/%d} {fv(float(full.max()))}) 대비 {sp(ath)}")
        else:
            lines.append(f'사상 최고 대비 {sp(ath)}' if ath < -0.05 else '사상 최고')
        if now and not prev:
            ev.append((10, f"{now['kind']} 들어감(고점 대비 −10%)"))
        elif now and prev and now['kind'] != prev['kind']:
            ev.append((10, '약세장 들어감(고점 대비 −20%)'))
        elif prev and not now:
            ev.append((10, f"{prev['kind']} 끝남"))
    if ch['id'] == 'dow':
        hi = {t: (P[t].iloc[-1] / P[t][P[t].index > P[t].index[-1] - pd.Timedelta(days=365)].max() - 1) * 100 for t in ('^DJI', '^DJT')}
        lines.append(f"1년 고점 대비 다우 {sp(hi['^DJI'])} · 운송 {sp(hi['^DJT'])}")
        new = {t: fresh(P[t], 1) for t in hi}
        if any(new.values()) and all(h >= -0.01 for h in hi.values()):
            ev.append((7, '다우·운송 함께 1년 신고가(확인)'))
        elif any(new.values()) and min(hi.values()) < -5:
            ev.append((7, f"{'다우' if new['^DJI'] else '운송'}만 1년 신고가(비확인)"))
    return lines, ev


def build(P, T, ids=None, save=True):
    """그리고 계산. 반환: [{id, file, title, stat, lines, events}]"""
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    font()
    ctx = {'rec': recessions(), 'extra': {}}
    if save:
        OUT.mkdir(exist_ok=True)
        for f in OUT.glob('*.png') if not ids else ():
            f.unlink()
    res = []
    for i, ch in enumerate(CHARTS, 1):
        if ids and ch['id'] not in ids:
            continue
        if any(t not in P for t in ch['need']):
            print(f"chartbook: {ch['id']} 건너뜀 — 시세 없음 {[t for t in ch['need'] if t not in P]}")
            continue
        try:
            fig, ax, s = DRAW[ch['kind']](ch, P, T, ctx)
            st = stat(s, ch.get('stat_kind', 'pct'))
            lines, ev = extras(ch, P, s, st)
            lines = ctx['extra'].get(ch['id'], []) + lines
            if ch['kind'] not in ('sectors', 'path'):
                foot(fig, T, note_of(st, ch.get('stat_name') or ch.get('main') or ''))
            else:
                foot(fig, T)
            f = OUT / f"{i:02d}-{ch['id']}.png"
            if save:
                fig.savefig(f, facecolor=fig.get_facecolor(), metadata={'Software': None})
            plt.close(fig)
            st['events'] = sorted(st['events'] + ev, key=lambda e: -e[0])
            if ch['kind'] in ('sectors', 'path'):
                st['events'] = []
            res.append({'no': i, 'id': ch['id'], 'file': str(f), 'title': ch['title'], 'stat': st, 'lines': lines, 'unit': ch.get('unit', ''),
                        'weekly': bool(ch.get('weekly')), 'read': ch['read']})
        except Exception as e:
            print(f"chartbook: {ch['id']} 못 그림 — {type(e).__name__}: {str(e)[:160]}")
    if save:
        (OUT / 'index.json').write_text(json.dumps({'made': datetime.now(KST).isoformat(timespec='seconds'), 'charts': res}, ensure_ascii=False, indent=1, default=str), encoding='utf-8')
    return res


# ---------- 글 ----------
def summary(r):
    st, u = r['stat'], r['unit']
    if r['id'] == 'sectors' or r['id'] == 'path':
        return r['lines'][0] if r['lines'] else ''
    bp = st['kind'] == 'bp'
    d1 = sp(st['d1'], 'bp', 0) if bp else sp(st['d1'])
    v50 = sp(st['vs50'], 'bp', 0) if bp else sp(st['vs50'])
    v200 = sp(st['vs200'], 'bp', 0) if bp else sp(st['vs200'])
    pos = f" · 1년 {st['pos']:.0f}%" if st['pos'] is not None else ''
    return f"{fv(st['last'], u)} ({d1}) · 50일 {v50} · 200일 {v200}{pos}"


def caption(r, k):
    st, u = r['stat'], r['unit']
    bp = st['kind'] == 'bp'
    L = [f"{k}. {r['title']}"]
    if r['id'] not in ('sectors', 'path'):
        dt = pd.Timestamp(st['date'])
        L[0] += f" — {fv(st['last'], u)} ({md(dt)})"
        f = (lambda v: sp(v, 'bp', 0)) if bp else sp
        L.append(f"1일 {f(st['d1'])} · 1주 {f(st['w1'])} · 연초 {f(st['ytd'])}")
        L.append(f"50일선 대비 {f(st['vs50'])} · 200일선 대비 {f(st['vs200'])}" + (f" · 1년 범위 중 {st['pos']:.0f}%" if st['pos'] is not None else ''))
    L += r['lines']
    if st['events']:
        L.append('일어난 것: ' + ', '.join(t for _, t in st['events']))
    L.append(f"보는 법: {r['read']}")
    return L


def pick(res, full):
    if full:
        return res
    daily = [r for r in res if not r['weekly']]
    sc = {r['id']: sum(e[0] for e in r['stat']['events']) for r in daily}
    top = [r['id'] for r in sorted(daily, key=lambda r: -sc[r['id']]) if sc[r['id']] > 0 and r['id'] != 'spx'][:5]
    ids = {'spx', *top}
    if len(ids) < 3:      # 조용한 날: 평소 대비 많이 움직인 순으로 채운다
        rest = sorted((r for r in daily if r['id'] not in ids and r['stat']['z'] is not None), key=lambda r: -abs(r['stat']['z']))
        ids |= {r['id'] for r in rest[:3 - len(ids)]}
    return [r for r in res if r['id'] in ids]


def message(res, chosen, now, full, tag=''):
    esc = html.escape
    us = next((r['stat']['date'] for r in res if r['id'] == 'spx'), '')
    kr = next((r['stat']['date'] for r in res if r['id'] == 'kospi'), '')
    L = [f"<b>Beom's Macro 차트북</b>{' ' + tag if tag else ''} · {now.month}/{now.day}({DAYS[now.weekday()]}) {now:%H:%M}",
         f"미국 {us[5:].replace('-', '/')} · 한국 {kr[5:].replace('-', '/')} 종가"]
    ev = [(r, e) for r in res for e in r['stat']['events']]
    L += ['', '<b>오늘 일어난 것</b>']
    if ev:
        seen = {}
        for r, (_, t) in sorted(ev, key=lambda x: -x[1][0]):
            seen.setdefault(r['id'], []).append(t)
        L += [f"• {esc(SHORT[i])}: {esc(', '.join(ts))}" for i, ts in list(seen.items())[:8]]
    else:
        L.append('• 이평 돌파·1년 최고/최저·큰 움직임 없음')
    L += ['', '<b>전체</b> <i>값 (1일) · 50·200일선 대비 · 1년 범위 중 위치</i>']
    L += [f"{r['no']}. {esc(SHORT[r['id']])} {esc(summary(r))}" for r in res]
    L += ['', f"<i>아래 차트 {len(chosen)}장 — " + ('주말이라 전부(위클리 차트북).' if full else '일이 생긴 것만(S&P500 은 늘). 주말에는 전부.') + '</i>']
    return '\n'.join(L)


# ---------- 보내기 ----------
def tg(method, **kw):
    for _ in range(3):
        r = requests.post(f"https://api.telegram.org/bot{config.key('MACRO_TG_TOKEN')}/{method}", timeout=60, **kw)
        if r.status_code != 429:
            return r
        time.sleep(int((r.json().get('parameters') or {}).get('retry_after', 5)) + 1)
    return r


def send(text, chosen, chat):
    r = tg('sendMessage', json={'chat_id': chat, 'text': text, 'parse_mode': 'HTML', 'disable_web_page_preview': True})
    if r.status_code != 200:
        return r, 0
    n = 0
    for r_ in chosen:
        L = caption(r_, r_['no'])
        cap = f'<b>{html.escape(L[0])}</b>\n' + '\n'.join(html.escape(x) for x in L[1:])
        rp = tg('sendPhoto', data={'chat_id': chat, 'caption': cap[:1020], 'parse_mode': 'HTML'},
                files={'photo': (Path(r_['file']).name, Path(r_['file']).read_bytes(), 'image/png')})
        if rp.status_code == 200:
            n += 1
        else:
            print(f"chartbook: 사진 {r_['id']} 실패 {rp.status_code} {rp.text[:120]}")
        time.sleep(1.1)
    return r, n


def spx_date(c):
    import store
    x = store.get(c, 'px:spx', '2000-01-01')
    return x[-1][0] if x else None


def run(full, tag='', record=None, dry=False):
    P = load([t for ch in CHARTS for t in ch['need']])
    res = build(P, DARK)
    if not res:
        print('chartbook: 그린 차트 없음')
        return 1
    now = datetime.now(KST)
    chosen = pick(res, full)
    text = message(res, chosen, now, full, tag)
    if dry:
        print(text)
        for r in chosen:
            print('\n' + '\n'.join(caption(r, r['no'])))
        return 0
    chat = config.key('MACRO_TG_CHAT')
    if not (config.key('MACRO_TG_TOKEN') and chat):
        print('chartbook: MACRO_TG_TOKEN·MACRO_TG_CHAT 없음 — 보내지 않음\n' + text)
        return 0
    r, n = send(text, chosen, chat)
    if r.status_code != 200:
        print('chartbook: 보내기 실패', r.status_code, r.text[:200])
        return 1
    print(f'chartbook: 글 1건 + 차트 {n}/{len(chosen)}장 보냄')
    if record:
        record(res)
    return 0


def auto():
    """07시대 실행 중 미국 새 종가가 들어온 첫 실행에 한 번. 상태는 macro.db kv('chartbook')"""
    import alert
    import store
    now = datetime.now(KST)
    if not (config.key('MACRO_TG_ENABLED') == '1' and config.key('MACRO_TG_TOKEN') and config.key('MACRO_TG_CHAT')):
        print('chartbook: 알림 꺼져 있음')
        return 0
    start = now.replace(hour=SLOT, minute=0, second=0, microsecond=0)
    if not 0 <= (now - start).total_seconds() / 60 < WINDOW:
        print('chartbook: 보낼 시각 아님')
        return 0
    c = store.connect()
    stt = alert.kv(c, 'chartbook') or {}
    us = spx_date(c)
    if stt.get('day') == now.strftime('%Y-%m-%d'):
        print('chartbook: 오늘 이미 보냄')
        return 0
    if us and stt.get('spx') and us <= stt['spx']:
        print(f'chartbook: 미국 새 종가 없음({us}) — 건너뜀')
        return 0

    def record(res):
        d = next((r['stat']['date'] for r in res if r['id'] == 'spx'), us)
        alert.kv(c, 'chartbook', {'day': now.strftime('%Y-%m-%d'), 'spx': d, 'at': now.isoformat(timespec='seconds')})
        c.commit()
    rc = run(full=now.weekday() >= 5, record=record)
    store.log(c, 'chartbook', rc == 0, '보냄' if rc == 0 else '실패')
    return rc


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('cmd', choices=['draw', 'text', 'send', 'auto'])
    ap.add_argument('--only', help='예: spx,kospi')
    ap.add_argument('--light', action='store_true', help='밝은 바탕(위클리·노션용)')
    ap.add_argument('--all', action='store_true', help='전부 보낸다(주말처럼)')
    ap.add_argument('--preview', action='store_true', help='[미리보기] 표시, 보낸 기록은 남기지 않음')
    a = ap.parse_args()
    if a.cmd == 'auto':
        return auto()
    if a.cmd == 'draw':
        P = load([t for ch in CHARTS for t in ch['need']])
        res = build(P, LIGHT if a.light else DARK, set(a.only.split(',')) if a.only else None)
        for r in res:
            print(f"{Path(r['file']).name:22s} {SHORT[r['id']]}: {summary(r)}" + (f"  ← {', '.join(t for _, t in r['stat']['events'])}" if r['stat']['events'] else ''))
        print(f'{OUT}: {len(res)}장')
        return 0
    return run(full=a.all, tag='[미리보기]' if a.preview else '', dry=a.cmd == 'text')


if __name__ == '__main__':
    sys.exit(main())
