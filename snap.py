"""텔레그램 알림용 차트 캡처. 빌드된 화면(public/, 잠그기 전)을 이 컴퓨터 안에서 잠깐 띄워 칸(section)별로 찍는다.

  python3 snap.py            # _snap/NN.png 로 찍고 (파일, 한 줄 설명) 목록을 찍는다

- 클라우드(Actions)는 러너에 깔린 Google Chrome 을 쓰고(브라우저 내려받기 없음), 없으면 playwright 의 chromium 을 받는다.
- 다크 모드, 칸 안의 그래프(.ch)만 찍는다. 한 줄 설명은 그 칸의 '지금 읽으면 — …' 문장 첫 문장을 쓴다(없으면 칸 제목).
- 2026-11-24 사용자 요청: 정기 알림(08·16·20시)은 주요 차트 캡처 + 한 줄 설명으로.
"""
import functools
import http.server
import re
import shutil
import subprocess
import sys
import threading
from pathlib import Path

import config

OUT = config.ROOT / '_snap'
# (화면, 칸 id, 짧은 이름) — 텔레그램 앨범은 10장까지
SHOTS = [
    ('timing', 'c-count', '바닥 신호 개수'),
    ('timing', 'c-adr', 'ADR (20일)'),
    ('timing', 'c-vix', 'VIX 기간구조'),
    ('timing', 'fg-kr', '한국판 공탐지수'),
    ('ib', 'rai', '위험선호 지수'),
    ('ib', 'gb', '글로벌 폭'),
    ('flow', 'cta', 'CTA 포지션'),
    ('flow', 'credit', '한국 신용잔고'),
    ('credit', 'stress', 'AI 크레딧 스트레스'),
    ('weight', 'credit', '미국 신용 스프레드'),
]


def _browser(p):
    for kw in ({'channel': 'chrome'}, {}):
        try:
            return p.chromium.launch(**kw)
        except Exception:
            continue
    subprocess.run([sys.executable, '-m', 'playwright', 'install', 'chromium'], check=False, capture_output=True)
    return p.chromium.launch()


def _ensure_playwright():
    try:
        import playwright  # noqa: F401
    except ImportError:
        subprocess.run([sys.executable, '-m', 'pip', 'install', '-q', 'playwright'], check=False)


def caption(text: str, name: str) -> str:
    t = re.sub(r'\s+', ' ', text or '').strip()
    t = re.sub(r'^지금 읽으면\s*[—-]\s*', '', t)
    first = re.split(r'(?<=\.)\s', t, maxsplit=1)[0] if t else ''
    if len(first) > 110:
        first = first[:108].rstrip() + '…'
    return f'{name} — {first}' if first else name


def shoot(shots=SHOTS, width=760):
    """[(png 경로, 한 줄 설명)]"""
    _ensure_playwright()
    from playwright.sync_api import sync_playwright
    shutil.rmtree(OUT, ignore_errors=True)
    OUT.mkdir()
    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a):
            pass
    handler = functools.partial(Quiet, directory=str(config.PUBLIC))
    srv = http.server.ThreadingHTTPServer(('127.0.0.1', 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f'http://127.0.0.1:{srv.server_address[1]}'
    out = []
    try:
        with sync_playwright() as p:
            b = _browser(p)
            pg = b.new_page(viewport={'width': width, 'height': 1000}, device_scale_factor=2, color_scheme='dark')
            pg.add_init_script("try { localStorage.setItem('theme', 'dark'); } catch (e) {}")   # 2026-11-24 사용자: 다크 모드로
            cur = None
            for i, (page, sec, name) in enumerate(shots, 1):
                try:
                    if page != cur:
                        pg.goto(f'{base}/{page}.html', wait_until='networkidle', timeout=60000)
                        pg.wait_for_timeout(1500)
                        cur = page
                    el = pg.locator(f'#{sec}').first
                    el.scroll_into_view_if_needed(timeout=10000)
                    read = el.locator('.read').first
                    text = read.inner_text(timeout=2000) if read.count() else ''
                    f = OUT / f'{i:02d}-{page}-{sec}.png'
                    chart = el.locator('.ch:has(svg)').first      # 그래프 부분만(글 카드·설명 빼고) — 2026-11-24 사용자 요청
                    (chart if chart.count() else el).screenshot(path=str(f), timeout=20000)
                    out.append((f, caption(text, name)))
                except Exception as e:
                    print(f'snap: {page}#{sec} 못 찍음 — {type(e).__name__}: {str(e)[:120]}')
            b.close()
    finally:
        srv.shutdown()
    return out


if __name__ == '__main__':
    for f, c in shoot():
        print(f.name, '|', c)
