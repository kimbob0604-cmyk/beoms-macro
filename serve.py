"""이 컴퓨터에서만 보는 서버.  python3 serve.py [포트] [폴더]   → http://127.0.0.1:8770
폴더를 주면 그 폴더를 연다 — 잠근 배포본 확인용: python3 site_crypt.py _site && python3 serve.py 8771 _site"""
import http.server
import os
import sys
from pathlib import Path

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else int(os.environ.get('PORT', 8770))
PUBLIC = str((Path(__file__).resolve().parent / (sys.argv[2] if len(sys.argv) > 2 else 'public')).resolve())


class Handler(http.server.SimpleHTTPRequestHandler):
    extensions_map = {**http.server.SimpleHTTPRequestHandler.extensions_map, '.js': 'text/javascript'}

    def __init__(self, *a, **k):
        super().__init__(*a, directory=PUBLIC, **k)

    def end_headers(self):
        self.send_header('Cache-Control', 'no-cache')      # 화면 파일을 고치면 새로고침 한 번에 반영되게 (바뀌지 않았으면 304)
        super().end_headers()


if __name__ == '__main__':
    with http.server.ThreadingHTTPServer(('127.0.0.1', PORT), Handler) as s:
        print(f'http://127.0.0.1:{PORT}')
        s.serve_forever()
