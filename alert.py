"""텔레그램 알림. MACRO_TG_ENABLED=1 이고 MACRO_TG_TOKEN·MACRO_TG_CHAT 이 있을 때만 보낸다(클라우드는 토큰이 있으면 켠다 — daily.yml).

  python3 alert.py --dry      # 보낼 내용을 화면에만 찍는다(보내지 않고, '보냄' 표시도 하지 않는다)
  python3 alert.py --preview  # 지금 내용을 [미리보기] 로 한 번 보낸다('보냄' 표시는 하지 않는다 — 양식 확인용)
  python3 alert.py            # run_daily.py 가 빌드 뒤에 부른다

보내는 것 (같은 내용은 한 번만 — macro.db 의 alerted 표에 적어 둔다)
  · 국면 칸이 바뀜            · '오늘 바뀐 것'의 기준선 통과(바닥 신호 개수, 공탐지수, 위험선호 지수, CTA 전환, 글로벌 폭, 스트레스 지수, 베이시스 …)
  · 수집 실패(하루 한 번)
평소의 2배 넘게 움직인 지표(크로스에셋)는 매일 여러 개라 보내지 않는다.

양식: 머리(시각) → 국면 한 줄 → 바뀐 것을 용도(비중·타이밍·흐름·섹터)별로, 문장의 ' — ' 뒤(뜻)는 한 줄 내려 기울여 → 지금 숫자 4줄 → 사이트 링크.
"""
import html
import json
import sys
from datetime import date, datetime

import requests

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


def collect(c):
    """[(중복 확인용 열쇠, 용도, 문장)]"""
    J = lambda n: json.loads((config.DATA / n).read_text(encoding='utf-8'))
    T, S = J('today.json'), J('status.json')
    out = []
    R = T['regime']
    last_cell = c.execute("SELECT key FROM alerted WHERE key LIKE 'regime:%' ORDER BY rowid DESC LIMIT 1").fetchone()
    if not last_cell:
        c.execute('INSERT OR IGNORE INTO alerted VALUES (?,?)', (f"regime:{R['cell']}:{date.today()}", 'init'))       # 처음에는 지금 칸을 기억만 한다
    elif last_cell[0].split(':')[1] != R['cell']:
        out.append((f"regime:{R['cell']}:{date.today()}", '비중', f"국면이 바뀌었다: {last_cell[0].split(':')[1]} → {R['cell']} — 비중 탭의 내 비중표를 다시 볼 때"))
    for x in T['changes']:
        out.append((f"chg:{x['date']}:{x['text'][:40]}", x['use'] if x['use'] in ORDER else '흐름', x['text']))
    bad = sorted(k for k, j in S['jobs'].items() if not j['ok'])
    if bad:
        out.append((f"fail:{date.today()}:{','.join(bad)}", '점검', f"수집 실패: {', '.join(bad)} — 해당 지표는 '늦음'으로 표시된다"))
    return out, T


def compose(new, T, tag=''):
    now = datetime.now()
    R, ib, fg = T['regime'], T.get('ib') or {}, T.get('fg') or {}
    lines = [f"<b>Beom's Macro</b>{f' {tag}' if tag else ''} · {now:%m/%d}({DAYS[now.weekday()]}) {now:%H:%M}", '']
    same = R['cell'] == R.get('cell_prev')
    lines.append(f"<b>국면 {esc(R['cell'])}</b>  위험선호 {num(R['risk'])} · 유동성·크레딧 {num(R['liq'])}"
                 + (f"  <i>(한 달 전에도 {esc(R['cell_prev'])})</i>" if same else f"  <i>(한 달 전 {esc(R.get('cell_prev') or '–')})</i>"))
    for use in ORDER:
        items = [t for _, u, t in new if u == use]
        if not items:
            continue
        lines += ['', f'<b>{use}</b>']
        for t in items:
            head, _, mean = t.partition(' — ')
            lines.append(f'• {esc(head)}')
            if mean:
                lines.append(f'   <i>{esc(mean)}</i>')
    B, H = T['bottom'], T['hot']
    snap = [f"바닥 신호 {B['count']}/{B['max']} · 과열 신호 {H['count']}/{H['max']}"]
    if fg:
        snap.append(f"공탐지수 한국 {num((fg.get('kr') or {}).get('last'))} · CNN {num((fg.get('cnn') or {}).get('last'))}"
                    + (f" · AI 크레딧 스트레스 {num(fg['stress']['last'])}" if fg.get('stress') else ''))
    if ib:
        snap.append(f"위험선호 지수 {num(ib['rai']['last'], 2, True)} · CTA 주식 {num(ib['cta']['last'], 0, True)}% · 200일선 위 나라 {num(ib['gb']['last'])}%")
    lines += ['', '<b>지금 숫자</b>', *[esc(x) for x in snap], '', f'<a href="{SITE}">사이트에서 보기</a>']
    return '\n'.join(lines)


def send(text):
    r = requests.post(f"https://api.telegram.org/bot{config.key('MACRO_TG_TOKEN')}/sendMessage",
                      json={'chat_id': config.key('MACRO_TG_CHAT'), 'text': text, 'parse_mode': 'HTML', 'disable_web_page_preview': True}, timeout=20)
    return r


def main():
    dry, preview = '--dry' in sys.argv, '--preview' in sys.argv
    c = store.connect()
    c.execute('CREATE TABLE IF NOT EXISTS alerted (key TEXT PRIMARY KEY, at TEXT)')
    items, T = collect(c)
    new = items if preview else [x for x in items if not c.execute('SELECT 1 FROM alerted WHERE key=?', (x[0],)).fetchone()]
    if not new:
        c.commit()
        print('alert: 새로 알릴 것 없음')
        return 0
    text = compose(new, T, '[미리보기]' if preview else '')
    on = (preview or config.key('MACRO_TG_ENABLED') == '1') and config.key('MACRO_TG_TOKEN') and config.key('MACRO_TG_CHAT')
    if dry or not on:
        print(f'alert: {"시험" if dry else "꺼져 있음(MACRO_TG_ENABLED)"} — 보낼 내용 {len(new)}건\n{text}')
        c.rollback() if dry else c.commit()
        return 0
    r = send(text)
    if r.status_code != 200:
        store.log(c, 'alert', False, f'{r.status_code} {r.text[:120]}')
        print('alert: 보내기 실패', r.status_code, r.text[:200])
        return 1
    if preview:
        c.rollback()
        print(f'alert: 미리보기 보냄 ({len(new)}건)\n{text}')
        return 0
    now = datetime.now().isoformat(timespec='seconds')
    c.executemany('INSERT OR IGNORE INTO alerted VALUES (?,?)', [(k, now) for k, _, _ in new])
    c.commit()
    store.log(c, 'alert', True, f'{len(new)}건')
    print(f'alert: {len(new)}건 보냄')
    return 0


if __name__ == '__main__':
    sys.exit(main())
