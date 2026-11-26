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
    ib, fg, B, H = T.get('ib') or {}, T.get('fg') or {}, T['bottom'], T['hot']
    out = [f"바닥 신호 {B['count']}/{B['max']} · 과열 신호 {H['count']}/{H['max']}"]
    if fg:
        out.append(f"공탐지수 한국 {num((fg.get('kr') or {}).get('last'))} · CNN {num((fg.get('cnn') or {}).get('last'))}"
                   + (f" · AI 크레딧 스트레스 {num(fg['stress']['last'])}" if fg.get('stress') else ''))
    if ib:
        out.append(f"위험선호 지수 {num(ib['rai']['last'], 2, True)} · CTA 주식 {num(ib['cta']['last'], 0, True)}% · 200일선 위 나라 {num(ib['gb']['last'])}%")
    return [esc(x) for x in out]


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


def summary_line(T):
    """맨 위 한 줄: 국면 · 신호 · 심리를 이어 붙인다 (판단·권유 없이 지금 상태만)"""
    R, B, H, fg = T['regime'], T['bottom'], T['hot'], T.get('fg') or {}
    kr, cnn = (fg.get('kr') or {}).get('last'), (fg.get('cnn') or {}).get('last')
    move = f"{R['cell']} 국면 유지" if R['cell'] == R.get('cell_prev') else f"{R.get('cell_prev')} → {R['cell']} 국면 전환"
    sig = f"바닥 신호 {B['count']}/{B['max']}" + (f" · 과열 신호 {H['count']}/{H['max']}" if H['count'] else '')
    mood = f"심리 {fear_word(min(x for x in (kr, cnn) if x is not None))}" if kr is not None or cnn is not None else ''
    return esc(' · '.join(x for x in (move, sig, mood) if x))


def report_text(T, S, shots, now, tag='', link=True):
    """정기 보고 글 (2026-11-26 사용자: 분량을 늘리고 깔끔하게). 칸 순서: 요약 → 국면 → 시장 → 신호판·바뀐 것 → 심리·수급 → 크레딧·유동성 → IB 지표 → 추세추종 → 파생 → 차트 안내 → 점검 → 링크"""
    R, B, H, ib, fg = T['regime'], T['bottom'], T['hot'], T.get('ib') or {}, T.get('fg') or {}
    F, W, C, D = _j('flow.json'), _j('weight.json'), _j('cta.json'), _j('deriv.json')
    I = _j('ib.json')
    L = [head(now, tag), summary_line(T)]

    def sec(title, lines):
        lines = [x for x in lines if x]
        if lines:
            L.extend(['', f'<b>{title}</b>', *lines])

    sec('국면', [f"{esc(R['cell'])} — 위험선호 {num(R['risk'])} <i>(한 달 전 {num(R.get('risk_prev'))})</i> · 유동성·크레딧 {num(R['liq'])} <i>(한 달 전 {num(R.get('liq_prev'))})</i>"])
    sec('시장', market_lines())
    sig = [f"바닥 {B['count']}/{B['max']} · 과열 {H['count']}/{H['max']}"]
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

    cr, dx = F.get('credit') or {}, F.get('dix') or {}
    kr, cnn = (fg.get('kr') or {}).get('last'), (fg.get('cnn') or {}).get('last')
    sec('심리·수급', [
        f"공탐지수 한국 {num(kr)} · CNN {num(cnn)}" if kr is not None or cnn is not None else '',
        f"신용잔고 {num(cr.get('last'), 2)}조 (20일 {pct(cr.get('d20'), 1)}) · 반대매매 비중 {num(cr.get('forced_pct'), 1)}% (3년 상위 {num(100 - cr['forced_rank'])}%)" if cr.get('last') is not None and cr.get('forced_rank') is not None else '',
        f"CTA 추정 주식 {num((C.get('eq') or {}).get('last'), 0, True)}% (1개월 {pts((C.get('eq') or {}).get('m'), 0, '%p')}) · 변동성 제어 노출 {num((C.get('volctl') or {}).get('last'))}%" if C.get('eq') else '',
        f"DIX 5일 {num(dx.get('avg5'), 1)}% · GEX {num(dx.get('gex'), 2)}" if dx.get('avg5') is not None else ''])
    hy = next((r for r in (W.get('credit') or {}).get('rows') or [] if r['k'] == 'fred:hy_oas'), None)
    ccc = next((r for r in (W.get('credit') or {}).get('rows') or [] if r['k'] == 'fred:ccc_oas'), None)
    liq = W.get('liq') or {}
    sec('크레딧·유동성', [
        f"하이일드 스프레드 {num(hy['last'], 2)}%p (20일 {pts(hy['chg'] * 100 if hy.get('chg') is not None else None, 0, 'bp')})" + (f" · CCC {num(ccc['last'], 2)}%p" if ccc else '') if hy else '',
        f"AI 크레딧 스트레스 {num(fg['stress']['last'])}/100" if fg.get('stress') else '',
        f"연준 순유동성 13주 {pts(liq.get('netliq_13w'), 0)}(십억$) · 금융여건 NFCI {num(liq.get('nfci'), 2)}" if liq.get('netliq_13w') is not None else ''])
    g, pe = I.get('gb') or {}, I.get('pe') or {}
    sec('IB 지표', [
        f"위험선호 지수(RAI식) {num(ib['rai']['last'], 2, True)} (20일 전 {num((I.get('rai') or {}).get('prev20'), 2, True)})" if ib.get('rai') else '',
        f"글로벌 폭: 50·200일선 모두 아래 {num(g.get('both'))}% (신호 88%) · 200일선 위 {num(g.get('a200'))}%" if g else '',
        f"패닉/유포리아식 {num(pe.get('last'))}/100" if pe.get('last') is not None else ''])
    L += trend_lines(T)
    bs, ln, op = D.get('basis') or {}, D.get('loan') or {}, D.get('k200opt') or {}
    sec('파생', [
        f"KOSPI200 베이시스 {pts(bs.get('basis'), 2, 'pt')} · 옵션 풋콜 5일 {num(op.get('vol5'), 2)}" if bs else '',
        f"대차잔고 주수 20일 {pct(ln.get('sh_d20'), 1)}" + (f" · 달러 조달(스왑 대용) {pts(D['swap']['basis'], 0, 'bp')}" if D.get('swap') else '') if ln else ''])
    if shots:
        L += ['', f'<i>아래 차트 {len(shots)}장 — 최근 6개월, 장마다 일간·MoM·QoQ·YoY 변화</i>']
    bad = fail_lines(S)
    if bad:
        L += ['', '<b>점검</b>', *bad]
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
