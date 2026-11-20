"""텔레그램 알림. 기본은 꺼져 있다 — MACRO_TG_ENABLED=1 이고 MACRO_TG_TOKEN·MACRO_TG_CHAT 이 있을 때만 보낸다.

  python3 alert.py --dry     # 보낼 내용을 화면에만 찍는다(보내지 않고, '보냄' 표시도 하지 않는다)
  python3 alert.py           # run_daily.py 가 빌드 뒤에 부른다

보내는 것 (같은 내용은 한 번만 — macro.db 의 alerted 표에 적어 둔다)
  · 국면 칸이 바뀜            · '오늘 바뀐 것'의 기준선 통과(바닥 신호 개수, 공탐지수, 위험선호 지수, CTA 전환, 글로벌 폭, 스트레스 지수, 베이시스 …)
  · 수집 실패(하루 한 번)
평소의 2배 넘게 움직인 지표(크로스에셋)는 매일 여러 개라 보내지 않는다.
"""
import json
import sys
from datetime import date, datetime

import requests

import config
import store

SITE = 'https://kimbob0604-cmyk.github.io/beoms-macro/'


def collect(c):
    """[(중복 확인용 열쇠, 문장)]"""
    J = lambda n: json.loads((config.DATA / n).read_text(encoding='utf-8'))
    T, S = J('today.json'), J('status.json')
    out = []
    R = T['regime']
    last_cell = c.execute("SELECT key FROM alerted WHERE key LIKE 'regime:%' ORDER BY rowid DESC LIMIT 1").fetchone()
    if not last_cell:
        c.execute('INSERT OR IGNORE INTO alerted VALUES (?,?)', (f"regime:{R['cell']}:{date.today()}", 'init'))       # 처음에는 지금 칸을 기억만 한다
    elif last_cell[0].split(':')[1] != R['cell']:
        out.append((f"regime:{R['cell']}:{date.today()}", f"국면이 '{last_cell[0].split(':')[1]}' → '{R['cell']}' 로 바뀌었다 (위험선호 {R['risk']:.0f} · 유동성·크레딧 {R['liq']:.0f})"))
    for x in T['changes']:
        out.append((f"chg:{x['date']}:{x['text'][:40]}", f"[{x['use']}] {x['text']}"))
    bad = sorted(k for k, j in S['jobs'].items() if not j['ok'])
    if bad:
        out.append((f"fail:{date.today()}:{','.join(bad)}", f"수집 실패: {', '.join(bad)}"))
    return out, T


def main():
    dry = '--dry' in sys.argv
    c = store.connect()
    c.execute('CREATE TABLE IF NOT EXISTS alerted (key TEXT PRIMARY KEY, at TEXT)')
    items, T = collect(c)
    new = [(k, t) for k, t in items if not c.execute('SELECT 1 FROM alerted WHERE key=?', (k,)).fetchone()]
    if not new:
        c.commit()
        print('alert: 새로 알릴 것 없음')
        return 0
    ib = T.get('ib') or {}
    head = f"Beom's Macro {datetime.now():%m-%d %H:%M}"
    tail = f"국면 {T['regime']['cell']} · 바닥 신호 {T['bottom']['count']}/{T['bottom']['max']}" + (f" · 위험선호 {ib['rai']['last']:+.2f} · CTA 주식 {ib['cta']['last']:+.0f}%" if ib else '')
    text = '\n'.join([head, *[f'· {t}' for _, t in new], '', tail, SITE])
    on = config.key('MACRO_TG_ENABLED') == '1' and config.key('MACRO_TG_TOKEN') and config.key('MACRO_TG_CHAT')
    if dry or not on:
        print(f'alert: {"시험" if dry else "꺼져 있음(MACRO_TG_ENABLED)"} — 보낼 내용 {len(new)}건\n{text}')
        c.rollback() if dry else c.commit()
        return 0
    r = requests.post(f"https://api.telegram.org/bot{config.key('MACRO_TG_TOKEN')}/sendMessage", json={'chat_id': config.key('MACRO_TG_CHAT'), 'text': text, 'disable_web_page_preview': True}, timeout=20)
    if r.status_code != 200:
        store.log(c, 'alert', False, f'{r.status_code} {r.text[:120]}')
        print('alert: 보내기 실패', r.status_code)
        return 1
    now = datetime.now().isoformat(timespec='seconds')
    c.executemany('INSERT OR IGNORE INTO alerted VALUES (?,?)', [(k, now) for k, _ in new])
    c.commit()
    store.log(c, 'alert', True, f'{len(new)}건')
    print(f'alert: {len(new)}건 보냄')
    return 0


if __name__ == '__main__':
    sys.exit(main())
