"""경로와 열쇠. 열쇠는 환경변수(클라우드의 비밀값) → 이 폴더 .env → 기존 프로젝트들의 .env 순서로 이름으로 찾아 읽는다."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DB = ROOT / 'db' / 'macro.db'
PUBLIC = ROOT / 'public'
DATA = PUBLIC / 'data'
DASH = Path.home() / "Beom's Dashboard"            # 기존 대시보드: DB 를 읽기만 한다
HIST_DB = DASH / 'db' / 'history.db'               # 종목 일봉 2010~ (hp), 지수 2005~ (hidx)
DASH_DB = DASH / 'db' / 'dashboard.db'             # 최근 일봉(ohlc_daily)·업종(naver_sector)·지수(index_daily)
# 혼자 돌기: 기존 대시보드 DB 없이 macro.db 안의 종목 일봉(kr_px)·이름·업종·수급만으로 계산한다 (클라우드, 또는 MACRO_STANDALONE=1)
STANDALONE = os.environ.get('MACRO_STANDALONE') == '1' or not HIST_DB.exists()

_SOURCES = [(ROOT / '.env', ''), (DASH / '.env', ''), (Path.home() / 'stock-dashboard' / '.env', ''), (Path.home() / 'kbj' / '.env', 'KBJ_')]


def key(name: str) -> str:
    if os.environ.get(name):
        return os.environ[name]
    for path, prefix in _SOURCES:
        if not path.exists():
            continue
        for line in path.read_text(encoding='utf-8').splitlines():
            k, _, v = line.strip().partition('=')
            if k.strip() in (name, prefix + name) and v.strip():
                return v.strip().strip('"\'')
    return ''
