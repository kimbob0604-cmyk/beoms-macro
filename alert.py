"""텔레그램 알림. MACRO_TG_ENABLED=1 이고 MACRO_TG_TOKEN·MACRO_TG_CHAT 이 있을 때만 보낸다(클라우드는 토큰이 있으면 켠다 — daily.yml).

  python3 alert.py --dry      # 보낼 내용을 화면에만 찍는다(보내지 않고, '보냄' 표시도 하지 않는다)
  python3 alert.py --preview  # 지금 내용을 [미리보기] 로 한 번 보낸다('보냄' 표시는 하지 않는다 — 양식 확인용)
  python3 alert.py            # run_daily.py 가 빌드 뒤에 부른다

보내는 것 (2026-11-24 사용자 요청으로 바꿈)
  · 정기 보고: 매일 08·16·20시(한국시간, 그 시각부터 90분 안의 첫 실행) — 머리 글(국면·바닥/과열 신호·지금 숫자·점검) 뒤에
    주요 차트 10장(snap.py 가 화면을 찍음)을 앨범으로, 장마다 한 줄 설명.
  · 수시 알림: 바닥 신호나 과열 신호가 '새로 켜졌을 때'만(켜진 조건 이름으로 비교). 바닥 신호 개수·ADR 차트 2장을 붙인다.
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


def report_text(T, S, shots, now, tag=''):
    B, H = T['bottom'], T['hot']
    L = [head(now, tag), '', regime_line(T), '', '<b>지금 숫자</b>', *snapshot(T)]
    if B['on']:
        L.append(f"<i>켜진 바닥 신호: {esc(', '.join(B['on']))}</i>")
    if H['on']:
        L.append(f"<i>켜진 과열 신호: {esc(', '.join(H['on']))}</i>")
    if shots:
        L += ['', '<b>차트</b> (아래 앨범)']
        L += [f"{i}. {esc(c)}" for i, (_, c) in enumerate(shots, 1)]
    bad = fail_lines(S)
    if bad:
        L += ['', '<b>점검</b>', *bad]
    L += ['', f'<a href="{SITE}">사이트에서 보기</a>']
    text = '\n'.join(L)
    return text if len(text) <= 4000 else text[:3990] + '…'


def signal_text(T, new_b, new_h, now, tag=''):
    B, H = T['bottom'], T['hot']
    L = [head(now, tag), '']
    if new_b:
        L += [f"<b>바닥 신호 새로 켜짐</b> → {B['count']}/{B['max']}", *[f'• {esc(x)}' for x in new_b], '<i>과매도 쪽 조건이 하나 더 켜졌다 — 타이밍 탭에서 신호 뒤 수익률 확인</i>', '']
    if new_h:
        L += [f"<b>과열 신호 새로 켜짐</b> → {H['count']}/{H['max']}", *[f'• {esc(x)}' for x in new_h], '<i>과열 쪽 조건이 하나 더 켜졌다 — 비중 줄일 자리인지 확인</i>', '']
    L += [regime_line(T), '', *snapshot(T), '', f'<a href="{SITE}timing.html">타이밍 탭에서 보기</a>']
    return '\n'.join(L)


def tg(method, **kw):
    return requests.post(f"https://api.telegram.org/bot{config.key('MACRO_TG_TOKEN')}/{method}", timeout=60, **kw)


def send(text, shots=()):
    chat = config.key('MACRO_TG_CHAT')
    r = tg('sendMessage', json={'chat_id': chat, 'text': text, 'parse_mode': 'HTML', 'disable_web_page_preview': True})
    if r.status_code != 200 or not shots:
        return r
    media, files = [], {}
    for i, (f, cap) in enumerate(list(shots)[:10]):
        files[f'p{i}'] = (Path(f).name, Path(f).read_bytes(), 'image/png')
        media.append({'type': 'photo', 'media': f'attach://p{i}', 'caption': f'{i + 1}. {cap}'[:1000]})
    if len(media) == 1:
        return tg('sendPhoto', data={'chat_id': chat, 'caption': media[0]['caption']}, files={'photo': files['p0']})
    return tg('sendMediaGroup', data={'chat_id': chat, 'media': json.dumps(media, ensure_ascii=False)}, files=files)


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
                shots = snap.shoot([(p, s, n) for p, s, n in want])
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
