"""텔레그램 알림. MACRO_TG_ENABLED=1 이고 MACRO_TG_TOKEN·MACRO_TG_CHAT 이 있을 때만 보낸다(클라우드는 토큰이 있으면 켠다 — daily.yml).

  python3 alert.py --dry      # 보낼 내용을 화면에만 찍는다(보내지 않고, '보냄' 표시도 하지 않는다)
  python3 alert.py --preview  # 지금 내용을 [미리보기] 로 한 번 보낸다('보냄' 표시는 하지 않는다 — 양식 확인용)
  python3 alert.py            # run_daily.py 가 빌드 뒤에 부른다

보내는 것 (2026-11-24 사용자 요청으로 바꿈)
  · 정기 보고: 매일 08·16·20시(한국시간, 그 시각부터 90분 안의 첫 실행) — 머리 글(국면·바닥/과열 신호·지금 숫자·점검) 뒤에
    주요 차트 10장(snap.py, 다크 모드·최근 6개월)을 한 장씩, 장마다 '값 — 일간 (MoM / QoQ / YoY)' + 해석 한 줄.
  · 수시 알림: 바닥 신호나 과열 신호가 '새로 켜졌을 때'만(켜진 조건 이름으로 비교). 바닥 신호 개수·ADR 차트 2장을 붙인다.
  · 그룹방(MACRO_TG_GROUP 이 있을 때): 정기 보고만 같은 차트로, 사이트 링크·점검 줄은 뺀다(미리보기는 본인에게만, --preview --group 이면 그룹방에도).
  · 그 밖의 '오늘 바뀐 것'·수집 실패는 따로 보내지 않고 정기 보고에만 짧게 싣는다.
같은 보고·신호는 한 번만 — macro.db 의 alerted 표(보고 열쇠)와 kv 표(sig_on: 지난번 켜진 신호)에 적어 둔다.
"""
import html
import json
import sys
from pathlib import Path
from datetime import date, datetime

import requests
from zoneinfo import ZoneInfo

import config
import store

SITE = 'https://kimbob0604-cmyk.github.io/beoms-macro/'
ORDER = ['비중', '타이밍', '흐름', '섹터', '점검']
DAYS = '월화수목금토일'
esc = html.escape


def num(v, d=0, sign=False):
    if v is None:
        return '–'
    s = f'{v:+.{d}f}' if sign else f'{v:.{d}f}'
    return s.replace('-', '−')


KST = ZoneInfo('Asia/Seoul')
SLOTS = (8, 16, 20)          # 정기 보고 시각(한국시간)
WINDOW = 90                  # 그 시각부터 몇 분 안의 실행이 보낼지 (예약이 늦게 돌 때 대비)
FAIL_WHY = (('ConnectionError', '출처 사이트 접속 안 됨'), ('Timeout', '출처 응답 없음'), ('HTTPError', '출처 오류'), ('403', '출처가 막음'), ('429', '요청 너무 많음'))


def J(n):
    return json.loads((config.DATA / n).read_text(encoding='utf-8'))


def kv(c, k, v=None):
    c.execute('CREATE TABLE IF NOT EXISTS kv (k TEXT PRIMARY KEY, v TEXT)')
    if v is None:
        r = c.execute('SELECT v FROM kv WHERE k=?', (k,)).fetchone()
        return json.loads(r[0]) if r else None
    c.execute('INSERT OR REPLACE INTO kv VALUES (?,?)', (k, json.dumps(v, ensure_ascii=False)))


def head(now, tag=''):
    return f"<b>Beom's Macro</b>{f' {tag}' if tag else ''} · {now.month}/{now.day}({DAYS[now.weekday()]}) {now:%H:%M}"


def regime_line(T):
    R = T['regime']
    same = R['cell'] == R.get('cell_prev')
    return (f"<b>국면 {esc(R['cell'])}</b>  위험선호 {num(R['risk'])} · 유동성·크레딧 {num(R['liq'])}"
            + (f"  <i>(한 달 전에도 {esc(R['cell_prev'])})</i>" if same else f"  <i>(한 달 전 {esc(R.get('cell_prev') or '–')})</i>"))


def snapshot(T):
    """수시 알림의 '지금 숫자' — 직전 값 대비 변화를 붙인다"""
    B, H = T['bottom'], T['hot']
    out = [f"바닥 신호 {B['count']}/{B['max']} · 과열 신호 {H['count']}/{H['max']}",
           ' · '.join(x for x in (f"공탐지수 한국 {move('sent:krfg')}" if series('sent:krfg') else '', f"CNN {move('sent:cnn')}" if series('sent:cnn') else '',
                                  f"AI 크레딧 스트레스 {move('credit:ai_stress')}" if series('credit:ai_stress') else '') if x),
           ' · '.join(x for x in (f"위험선호 지수 {move('ib:rai', 2)}" if series('ib:rai') else '', f"CTA 주식 {move('cta:eq', 0, '%')}" if series('cta:eq') else '',
                                  f"200일선 위 나라 {move('ib:gb_a200', 0, '%')}" if series('ib:gb_a200') else '') if x)]
    return [esc(x) for x in out if x]


def fail_lines(S):
    out = []
    for k, j in sorted(S['jobs'].items()):
        if j['ok']:
            continue
        why = next((w for key, w in FAIL_WHY if key in (j.get('msg') or '')), '수집 실패')
        out.append(f"• {esc(k)}: {why} → 그 지표만 '늦음'")
    return out


def trend_lines(T):
    """추세추종 탭 요약 두 줄: IBD식 시장 상태 + 트렌드 템플릿 통과 비율 (2026-11-24 추가)"""
    tf = T.get('trend') or {}
    if not tf.get('idx'):
        return []
    st = ' · '.join(f"{esc(x['name'])} {esc(x['label'])}" + (f"(분산일 {x['dd']})" if x['label'] != '조정' else f"(랠리 {x['rday']}일째)" if x['rday'] else '') for x in tf['idx'])
    tt = tf.get('tt') or {}
    t2 = ' · '.join(f"{'한국' if m == 'kr' else '미국'} {v['tt']}%" for m, v in tt.items() if v.get('tt') is not None)
    return ['', '<b>추세추종</b>', f'시장 상태(IBD식) {st}'] + ([f'트렌드 템플릿 통과 {t2}'] if t2 else [])


def _j(name):
    try:
        return J(name)
    except Exception:
        return {}


def pct(v, d=2):
    return '–' if v is None else f'{v:+.{d}f}%'.replace('-', '−')


def pts(v, d=2, u=''):
    return '–' if v is None else f'{v:+.{d}f}{u}'.replace('-', '−')


def big(v, d=0):
    return '–' if v is None else f'{v:,.{d}f}'


def fear_word(v):
    return '' if v is None else '극단 공포' if v < 25 else '공포' if v < 45 else '중립' if v < 55 else '탐욕' if v < 75 else '극단 탐욕'


def market_lines():
    """오늘 한국 마감 · 전일 미국 마감 · 금리·환율·원자재 (크로스에셋 표에서)"""
    rows = {r['k']: r for r in (_j('monitor.json').get('rows') or [])}

    def q(k, name=None, d=0, diff=False, unit=''):
        r = rows.get(k)
        if not r:
            return None
        ch = pts(r['d1'], 2, unit + ('p' if unit == '%' else '')) if diff else pct(r['d1'])      # 금리는 %p
        return f"{name or r['name']} {big(r['last'], d)}{unit if diff else ''} {ch}"
    L = []
    kr = [x for x in (q('px:kospi', 'KOSPI'), q('px:kosdaq', 'KOSDAQ', 1)) if x]
    us = [x for x in (q('px:spx', 'S&P500'), q('px:ndx', '나스닥'), q('px:sox', '반도체지수')) if x]
    rate = [x for x in (q('px:vix', 'VIX', 1, True), q('px:us10y', '미 10년', 2, True, '%'), q('px:dxy', '달러지수', 1)) if x]
    asset = [x for x in (q('px:usdkrw', '원/달러', 1), q('px:wti', 'WTI', 1), q('px:gold', '금'), q('px:btc', '비트코인')) if x]
    kd = (rows.get('px:kospi') or {}).get('date', '')
    ud = (rows.get('px:spx') or {}).get('date', '')
    if kr:
        L.append(f"한국({kd[5:].replace('-', '/')}) " + ' · '.join(kr))
    if us:
        L.append(f"미국({ud[5:].replace('-', '/')}) " + ' · '.join(us))
    if rate:
        L.append(' · '.join(rate))
    if asset:
        L.append(' · '.join(asset))
    return [esc(x) for x in L]


_SER = {}
REG_PREV = None          # 전날 국면 점수 [위험선호, 유동성·크레딧] — main 이 kv 에서 채운다


def series(k):
    """화면용 계열 파일(public/data/s/<k>.json)에서 [(날짜, 값)] — 파생 계열(공탐지수·RAI·CTA 등)도 여기 있다"""
    if k not in _SER:
        try:
            d = json.loads((config.DATA / 's' / f"{k.replace(':', '_')}.json").read_text(encoding='utf-8'))
            _SER[k] = [(x, v) for x, v in zip(d['d'], d['v']) if v is not None]
        except Exception:
            _SER[k] = []
    return _SER[k]


def move(k, d=0, unit='', how='diff', cd=None):
    """'16 (−1)' 꼴: 지금 값과 직전 값 대비 변화. how='pct' 면 변화율. 직전 값이 5일 넘게 떨어져 있으면(주간 자료) '전주'를 붙인다"""
    s = series(k)
    if not s:
        return None
    last = s[-1][1]
    if len(s) < 2:
        return f'{num(last, d)}{unit}'
    (d0, p), (d1, _) = s[-2], s[-1]
    gap = (date.fromisoformat(d1) - date.fromisoformat(d0)).days
    tag = '전주 ' if gap >= 5 else ''
    if how == 'pct' and p:
        ch = small((last / p - 1) * 100, 1, '%')
    else:
        ch = small(last - p, d if cd is None else cd, '%p' if unit in ('%', '%p') else unit if unit in ('bp', 'pt') else '')
    return f'{last:,.{d}f}'.replace('-', '−') + f'{unit} ({tag}{ch})'


def small(ch, d, unit=''):
    """변화 표시. 반올림하면 0 이 되는 작은 변화는 자리를 두 개까지 늘리고, 그래도 0 이면 '보합'"""
    cd = d
    while cd < d + 2 and ch and round(ch, cd) == 0:
        cd += 1
    return '보합' if round(ch, cd) == 0 else pts(ch, cd, unit)


def zmove(k):
    """직전 대비 변화가 평소 하루 변화(최근 250번의 표준편차)의 몇 배인가"""
    s = [v for _, v in series(k)][-251:]
    if len(s) < 60:
        return None
    df = [b - a for a, b in zip(s, s[1:])]
    m = sum(df) / len(df)
    sd = (sum((x - m) ** 2 for x in df) / len(df)) ** 0.5
    return None if not sd else df[-1] / sd


BIG = [('sent:krfg', '한국판 공탐지수'), ('sent:cnn', 'CNN 공탐지수'), ('credit:ai_stress', 'AI 크레딧 스트레스'), ('ib:rai', '위험선호 지수'), ('ib:gb_a200', '200일선 위 나라 비율'),
       ('cta:eq', 'CTA 추정 주식 포지션'), ('cta:volctl', '변동성 제어 노출'), ('kr:credit', '신용잔고'), ('kr:forced_pct', '반대매매 비중'), ('flow:dix', 'DIX'), ('flow:gex', 'GEX'),
       ('fred:hy_oas', '하이일드 스프레드'), ('fred:ccc_oas', 'CCC 스프레드'), ('drv:k200_basis', 'KOSPI200 베이시스'), ('drv:k200_pc_vol', 'KOSPI200 풋콜'), ('drv:loan_sh', '대차잔고'),
       ('drv:swap_basis', '달러 조달 비용'), ('px:vix', 'VIX'), ('px:usdkrw', '원/달러'), ('px:us10y', '미 10년 금리')]


def big_moves(n=4, cut=1.5):
    """평소보다 크게 움직인 숫자 위에서 n개"""
    out = []
    for k, name in BIG:
        z = zmove(k)
        if z is not None and abs(z) >= cut:
            out.append((abs(z), f"{esc(name)} {'올랐다' if z > 0 else '내렸다'} — 평소 하루 변화의 {abs(z):.1f}배"))
    return [t for _, t in sorted(out, reverse=True)[:n]]


def summary_line(T):
    """맨 위 한 줄: 국면 · 신호 · 심리를 이어 붙인다 (판단·권유 없이 지금 상태만)"""
    R, B, H, fg = T['regime'], T['bottom'], T['hot'], T.get('fg') or {}
    kr, cnn = (fg.get('kr') or {}).get('last'), (fg.get('cnn') or {}).get('last')
    move_ = f"{R['cell']} 국면 유지" if R['cell'] == R.get('cell_prev') else f"{R.get('cell_prev')} → {R['cell']} 국면 전환"
    sig = f"바닥 신호 {B['count']}/{B['max']}" + (f" · 과열 신호 {H['count']}/{H['max']}" if H['count'] else '')
    mood = f"심리 {fear_word(min(x for x in (kr, cnn) if x is not None))}" if kr is not None or cnn is not None else ''
    return esc(' · '.join(x for x in (move_, sig, mood) if x))


def report_text(T, S, shots, now, tag='', link=True):
    """정기 보고 글. 2026-11-26 사용자: 분량을 늘리고 깔끔하게 → 숫자마다 직전 값 대비 변화를 붙이고, 점검(수집 실패) 칸은 뺀다.
    칸: 요약 → 크게 움직인 숫자 → 국면 → 시장 → 신호판 → 오늘 바뀐 것 → 심리·수급 → 크레딧·유동성 → IB 지표 → 추세추종 → 파생 → 차트 안내 → 링크"""
    R, B, H = T['regime'], T['bottom'], T['hot']
    Tm = _j('timing.json').get('boards') or {}
    bp, hp = (Tm.get('bottom') or {}).get('prev'), (Tm.get('hot') or {}).get('prev')
    L = [head(now, tag), summary_line(T), '<i>괄호 안은 직전 값 대비 변화(주간 자료는 전주 대비)</i>']

    def sec(title, lines):
        lines = [x for x in lines if x]
        if lines:
            L.extend(['', f'<b>{title}</b>', *lines])

    def j(*xs):
        return ' · '.join(esc(x) for x in xs if x)

    sec('크게 움직인 숫자', big_moves())
    rp = REG_PREV
    sec('국면', [f"{esc(R['cell'])} — 위험선호 {num(R['risk'])}" + (f" ({pts(R['risk'] - rp[0], 0)})" if rp else '') + f" · 유동성·크레딧 {num(R['liq'])}"
                 + (f" ({pts(R['liq'] - rp[1], 0)})" if rp else '') + f" <i>한 달 전 {num(R.get('risk_prev'))} · {num(R.get('liq_prev'))}</i>"])
    sec('시장', market_lines())
    cnt = lambda now_, prev_: f" ({pts(now_ - prev_, 0)})" if prev_ is not None and now_ != prev_ else ' (그대로)' if prev_ is not None else ''
    sig = [f"바닥 {B['count']}/{B['max']}{cnt(B['count'], bp)} · 과열 {H['count']}/{H['max']}{cnt(H['count'], hp)}"]
    if B['on']:
        sig.append(f"켜진 바닥 신호: {esc(', '.join(B['on']))}")
    if H['on']:
        sig.append(f"켜진 과열 신호: {esc(', '.join(H['on']))}")
    sec('신호판', sig)
    ch = []
    for x in T.get('changes') or []:
        h_, _, mean = x['text'].partition(' — ')
        ch.append(f"• {esc(h_)}" + (f" <i>— {esc(mean)}</i>" if mean else ''))
    sec('오늘 바뀐 것', ch[:8])
    F = _j('flow.json')
    rank = (F.get('credit') or {}).get('forced_rank')
    sec('심리·수급', [
        j(f"공탐지수 한국 {move('sent:krfg')}" if series('sent:krfg') else '', f"CNN {move('sent:cnn')}" if series('sent:cnn') else ''),
        j(f"신용잔고 {move('kr:credit', 2, '조', 'pct')}" if series('kr:credit') else '', f"반대매매 비중 {move('kr:forced_pct', 1, '%')}" if series('kr:forced_pct') else '', f"반대매매 3년 상위 {num(100 - rank)}%" if rank is not None else ''),
        j(f"CTA 추정 주식 {move('cta:eq', 0, '%')}" if series('cta:eq') else '', f"변동성 제어 노출 {move('cta:volctl', 0, '%')}" if series('cta:volctl') else ''),
        j(f"DIX {move('flow:dix', 1, '%')}" if series('flow:dix') else '', f"GEX {move('flow:gex', 2)}" if series('flow:gex') else '')])
    sec('크레딧·유동성', [
        j(f"하이일드 스프레드 {move('fred:hy_oas', 2, '%p')}" if series('fred:hy_oas') else '', f"CCC {move('fred:ccc_oas', 2, '%p')}" if series('fred:ccc_oas') else ''),
        j(f"AI 크레딧 스트레스 {move('credit:ai_stress')}" if series('credit:ai_stress') else ''),
        j(f"연준 순유동성 {move('fred:netliq', 0, '십억$')}" if series('fred:netliq') else '', f"금융여건 NFCI {move('fred:nfci', 2, cd=3)}" if series('fred:nfci') else '')])
    sec('IB 지표', [
        j(f"위험선호 지수(RAI식) {move('ib:rai', 2)}" if series('ib:rai') else ''),
        j(f"글로벌 폭(신호선 88%): 둘 다 아래 {move('ib:gb_both', 0, '%')}" if series('ib:gb_both') else '', f"200일선 위 {move('ib:gb_a200', 0, '%')}" if series('ib:gb_a200') else ''),
        j(f"패닉/유포리아식 {move('ib:pe')}" if series('ib:pe') else '')])
    L += trend_lines(T)
    sec('파생', [
        j(f"KOSPI200 베이시스 {move('drv:k200_basis', 2, 'pt')}" if series('drv:k200_basis') else '', f"옵션 풋콜 {move('drv:k200_pc_vol', 2)}" if series('drv:k200_pc_vol') else ''),
        j(f"대차잔고 {move('drv:loan_sh', 2, '억 주', 'pct')}" if series('drv:loan_sh') else '', f"달러 조달(스왑 대용) {move('drv:swap_basis', 0, 'bp')}" if series('drv:swap_basis') else '')])
    if shots:
        L += ['', f'<i>아래 차트 {len(shots)}장 — 최근 6개월, 장마다 일간·MoM·QoQ·YoY 변화</i>']
    if link:
        L += ['', f'<a href="{SITE}">사이트에서 보기</a>']
    text = '\n'.join(L)
    return text if len(text) <= 4000 else text[:3990] + '…'


def signal_text(T, new_b, new_h, now, tag=''):
    """수시 알림: 바닥·과열 신호가 새로 켜졌을 때. 정기 보고와 같은 모양으로 짧게"""
    B, H = T['bottom'], T['hot']
    L = [head(now, tag), summary_line(T)]
    if new_b:
        L += ['', f"<b>바닥 신호 새로 켜짐</b> → {B['count']}/{B['max']}", *[f'• {esc(x)}' for x in new_b], '<i>과매도 쪽 조건이 하나 더 켜졌다 — 타이밍 탭에서 신호 뒤 수익률 확인</i>']
    if new_h:
        L += ['', f"<b>과열 신호 새로 켜짐</b> → {H['count']}/{H['max']}", *[f'• {esc(x)}' for x in new_h], '<i>과열 쪽 조건이 하나 더 켜졌다 — 비중 줄일 자리인지 확인</i>']
    L += ['', '<b>시장</b>', *market_lines(), '', '<b>지금 숫자</b>', *snapshot(T), '', f'<a href="{SITE}timing.html">타이밍 탭에서 보기</a>']
    return '\n'.join(L)


def tg(method, **kw):
    return requests.post(f"https://api.telegram.org/bot{config.key('MACRO_TG_TOKEN')}/{method}", timeout=60, **kw)


def send(text, shots=(), chat=None):
    """글 한 건 뒤에 차트를 한 장씩 따로 보낸다(앨범으로 묶으면 작게 뭉개져서 — 2026-11-24 사용자). 사진 설명: 첫 줄(숫자 변화)은 굵게"""
    chat = chat or config.key('MACRO_TG_CHAT')
    r = tg('sendMessage', json={'chat_id': chat, 'text': text, 'parse_mode': 'HTML', 'disable_web_page_preview': True})
    if r.status_code != 200:
        return r
    for i, (f, cap) in enumerate(shots, 1):
        first, _, rest = cap.partition('\n')
        html_cap = f'<b>{i}. {esc(first)}</b>' + (f'\n{esc(rest)}' if rest else '')
        rp = tg('sendPhoto', data={'chat_id': chat, 'caption': html_cap[:1020], 'parse_mode': 'HTML'},
                files={'photo': (Path(f).name, Path(f).read_bytes(), 'image/png')})
        if rp.status_code != 200:
            print(f'alert: 사진 {i} 실패 {rp.status_code} {rp.text[:120]}')
    return r


def due_slot(c, now):
    for h in SLOTS:
        start = now.replace(hour=h, minute=0, second=0, microsecond=0)
        if 0 <= (now - start).total_seconds() / 60 < WINDOW:
            key = f'report:{now:%Y-%m-%d}:{h:02d}'
            if not c.execute('SELECT 1 FROM alerted WHERE key=?', (key,)).fetchone():
                return key
    return None


def main():
    dry, preview = '--dry' in sys.argv, '--preview' in sys.argv
    now = datetime.now(KST)
    c = store.connect()
    c.execute('CREATE TABLE IF NOT EXISTS alerted (key TEXT PRIMARY KEY, at TEXT)')
    T, S = J('today.json'), J('status.json')
    global REG_PREV
    hist = kv(c, 'regime_hist') or {}
    today = now.date().isoformat()
    prev_day = max((d for d in hist if d < today), default=None)
    REG_PREV = hist.get(prev_day)
    hist[today] = [T['regime']['risk'], T['regime']['liq']]
    if not dry and not preview:
        kv(c, 'regime_hist', dict(sorted(hist.items())[-60:]))
    on = (preview or config.key('MACRO_TG_ENABLED') == '1') and config.key('MACRO_TG_TOKEN') and config.key('MACRO_TG_CHAT')
    tag = '[미리보기]' if preview else ''

    # 1) 수시: 새로 켜진 신호
    prev = kv(c, 'sig_on')
    cur = {'bottom': T['bottom']['on'], 'hot': T['hot']['on']}
    new_b = [x for x in cur['bottom'] if prev and x not in prev.get('bottom', [])]
    new_h = [x for x in cur['hot'] if prev and x not in prev.get('hot', [])]
    jobs = []
    if new_b or new_h:
        jobs.append(('signal', signal_text(T, new_b, new_h, now, tag), [('timing', 'c-count', '바닥 신호 개수'), ('timing', 'c-adr', 'ADR (20일)')]))
    # 2) 정기 보고
    slot = None if preview else due_slot(c, now)
    if slot or preview:
        jobs.append(('report', None, None))
    if not jobs:
        if not dry:
            kv(c, 'sig_on', cur)
            c.commit()
        print('alert: 보낼 것 없음' + ('' if prev else ' (신호 상태를 처음 기억함)'))
        return 0

    import snap
    sent = 0
    for kind, text, want in jobs:
        try:
            if kind == 'report':
                shots = snap.shoot()
                text = report_text(T, S, shots, now, tag)
            else:
                shots = snap.shoot([x for x in snap.SHOTS if (x[0], x[1]) in {(p, s) for p, s, _ in want}])
                shots = [(f, cap) for f, cap in shots]
        except Exception as e:                       # 캡처가 안 되면 글만 보낸다
            print(f'alert: 캡처 실패 — {type(e).__name__}: {str(e)[:160]}')
            shots = []
            if kind == 'report':
                text = report_text(T, S, [], now, tag)
        if dry or not on:
            print(f'alert: {"시험" if dry else "꺼져 있음"} — {kind}, 차트 {len(shots)}장\n{text}')
            continue
        r = send(text, shots)
        if r.status_code != 200:
            store.log(c, 'alert', False, f'{kind} {r.status_code} {r.text[:120]}')
            print('alert: 보내기 실패', kind, r.status_code, r.text[:200])
            continue
        sent += 1
        group = config.key('MACRO_TG_GROUP')       # 그룹방(2026-11-24 사용자): 정기 보고만, 사이트 링크·점검 줄 없이
        if kind == 'report' and group and (not preview or '--group' in sys.argv):
            rg = send(report_text(T, {'jobs': {}}, shots, now, tag, link=False), shots, chat=group)
            if rg.status_code != 200:
                store.log(c, 'alert', False, f'group {rg.status_code} {rg.text[:120]}')
                print('alert: 그룹방 보내기 실패', rg.status_code, rg.text[:200])
        if kind == 'report' and slot:
            c.execute('INSERT OR IGNORE INTO alerted VALUES (?,?)', (slot, now.isoformat(timespec='seconds')))
    if not dry and not preview:
        kv(c, 'sig_on', cur)
    c.commit()
    if sent:
        store.log(c, 'alert', True, f'{sent}건')
    print(f'alert: {sent}건 보냄')
    return 0


if __name__ == '__main__':
    sys.exit(main())
