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
ZOOM = 180            # 최근 며칠만 보이게 찍을지 (2026-11-24 사용자: 당겨서 최근 변화를 보이게)
# (화면, 칸 id, 짧은 이름, 변화 표시 방식, 단위, 몇 번째 계열) — pct: 변화율(%), diff: 차이(단위)
SHOTS = [
    ('timing', 'c-count', '바닥 신호 개수', 'diff', '개', 0),
    ('timing', 'c-adr', 'ADR (20일)', 'pct', '', 0),
    ('timing', 'c-vix', 'VIX', 'pct', '', 1),
    ('timing', 'c-vkospi', 'VKOSPI', 'pct', '', 0),
    ('timing', 'fg-kr', '한국판 공탐지수', 'diff', 'pt', 0),
    ('ib', 'rai', '위험선호 지수', 'diff', '', 0),
    ('flow', 'cta', 'CTA S&P500 포지션', 'diff', '%p', 0),
    ('flow', 'credit', '한국 신용잔고', 'pct', '', 0),
    ('credit', 'stress', 'AI 크레딧 스트레스', 'diff', 'pt', 0),
    ('weight', 'credit', '하이일드 스프레드', 'pct', '', 0),
    ('trend', 'tt-kr', '트렌드 템플릿 통과 — 한국', 'diff', '%p', 0),
    ('trend', 'tt-us', '트렌드 템플릿 통과 — S&P500', 'diff', '%p', 0),
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


LEVEL_UNIT = {'트렌드 템플릿 통과 — 한국': '%', '트렌드 템플릿 통과 — S&P500': '%', 'CTA S&P500 포지션': '%', '하이일드 스프레드': '%p', '한국 신용잔고': '조원', 'ADR (20일)': '%'}


def _at(d, v, days):
    """마지막 날에서 days 일 전(그날 또는 그 전 가장 가까운 값)"""
    from datetime import date, timedelta
    last = date.fromisoformat(d[-1][:10])
    cut = (last - timedelta(days=days)).isoformat()
    for x, y in zip(reversed(d), reversed(v)):
        if x[:10] <= cut and y is not None:
            return y
    return None


def stats(name, mode, unit, d, v):
    """'VKOSPI 55.83 — 일간 −15.0% (MoM +5.0% / QoQ +25.0% / YoY +27.0%)'"""
    pairs = [(x, y) for x, y in zip(d, v) if y is not None]
    if len(pairs) < 2:
        return ''
    d, v = [x for x, _ in pairs], [y for _, y in pairs]
    last, prev = v[-1], v[-2]
    def ch(old):
        if old is None:
            return '–'
        if mode == 'pct':
            return '–' if not old else f'{(last / old - 1) * 100:+.1f}%'.replace('-', '−')
        dec = 1 if name.startswith('트렌드') else 0 if unit in ('개', '%p') and float(last).is_integer() else (2 if abs(last) < 10 else 1)
        return f'{last - old:+.{dec}f}{unit}'.replace('-', '−')
    lv = f'{last:,.0f}' if abs(last) >= 1000 else f'{last:.2f}'.rstrip('0').rstrip('.') if unit != '개' else f'{last:.0f}'
    if name.startswith('트렌드'):
        lv = f'{last:.1f}'
    lv += LEVEL_UNIT.get(name, '')
    return f"{name} {lv.replace('-', '−')} — 일간 {ch(prev)} (MoM {ch(_at(d, v, 30))} / QoQ {ch(_at(d, v, 91))} / YoY {ch(_at(d, v, 365))})"


def shoot(shots=SHOTS, width=760):
    """[(png 경로, 설명)] — 설명 = 숫자 변화 한 줄 + 해석 한 줄"""
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
            for i, (page, sec, name, mode, unit, si) in enumerate(shots, 1):
                try:
                    if page != cur:
                        pg.goto(f'{base}/{page}.html?zoom={ZOOM}', wait_until='networkidle', timeout=60000)
                        pg.wait_for_timeout(1500)
                        cur = page
                    el = pg.locator(f'#{sec}').first
                    el.scroll_into_view_if_needed(timeout=10000)
                    read = el.locator('.read').first
                    text = read.inner_text(timeout=2000) if read.count() else ''
                    f = OUT / f'{i:02d}-{page}-{sec}.png'
                    chart = el.locator('.ch:has(svg)').first      # 그래프 부분만(글 카드·설명 빼고) — 2026-11-24 사용자 요청
                    (chart if chart.count() else el).screenshot(path=str(f), timeout=20000)
                    ser = (chart if chart.count() else el).evaluate(
                        f"e => {{ const c = e.matches('.ch') ? e : e.querySelector('.ch'); const s = c && c.__spec && c.__spec.series[{si}]; return s ? {{d: s.d, v: s.v}} : null; }}")
                    num = stats(name, mode, unit, ser['d'], ser['v']) if ser else ''
                    read = caption(text, '').lstrip(' —') if text else ''
                    out.append((f, '\n'.join(x for x in (num or name, read) if x)))
                except Exception as e:
                    print(f'snap: {page}#{sec} 못 찍음 — {type(e).__name__}: {str(e)[:120]}')
            b.close()
    finally:
        srv.shutdown()
    return out


if __name__ == '__main__':
    for f, c in shoot():
        print(f.name, '|', c.replace(chr(10), ' / '))
