"""배포용 사이트 폴더를 만든다: 화면 파일은 그대로, 데이터(public/data/**)는 암호로 잠가서.

  python3 site_crypt.py _site          # _site/ 에 화면 + 잠근 데이터(<경로>.enc) + data/lock.json
  python3 site_crypt.py --check        # 암호가 있는지, 잠글 파일 수·크기만

- 암호는 MACRO_PASS (이 폴더 .env 또는 저장소 비밀값). 없으면 만들지 않는다 — 잠그지 않은 데이터는 밖에 올리지 않는다.
- 파일마다 AES-256-GCM. 열쇠 = PBKDF2-SHA256(암호, salt, 25만 번). salt 는 lock_salt.txt(비밀 아님, 저장소에 둔다) — 바뀌면 화면에서 암호를 다시 넣어야 한다.
- IV 는 HMAC(열쇠, 경로 + 내용 해시)로 정해 같은 파일은 늘 같은 암호문이 나온다.
- 화면(mu.js)은 data/lock.json 이 있으면 암호를 물어 브라우저 안에서 풀고, 열쇠를 그 기기에 기억한다.
"""
import base64
import hashlib
import hmac
import json
import os
import shutil
import sys
from pathlib import Path

import config

SALT = config.ROOT / 'lock_salt.txt'
ITER = 250_000
CHECK = b'beoms-macro-ok'


def key_of(pw):
    if not SALT.exists():
        SALT.write_text(os.urandom(16).hex())
    salt = bytes.fromhex(SALT.read_text().strip())
    return hashlib.pbkdf2_hmac('sha256', pw.encode('utf-8'), salt, ITER, dklen=32), salt


def seal(key, rel, data):
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    iv = hmac.new(key, rel.encode() + hashlib.sha256(data).digest(), hashlib.sha256).digest()[:12]
    return iv + AESGCM(key).encrypt(iv, data, None)


def main():
    pw = config.key('MACRO_PASS').strip()
    files = [p for p in sorted(config.DATA.rglob('*')) if p.is_file()]
    if '--check' in sys.argv:
        print(f'암호 {"있음" if pw else "없음"} · 잠글 파일 {len(files)}개 · {sum(p.stat().st_size for p in files) / 1e6:.1f}MB')
        return 0
    if not pw:
        print('site_crypt: MACRO_PASS 가 없어 배포용 폴더를 만들지 않는다')
        return 1
    out = Path(sys.argv[1] if len(sys.argv) > 1 else '_site').resolve()
    if out.exists():
        shutil.rmtree(out)
    shutil.copytree(config.PUBLIC, out, ignore=shutil.ignore_patterns('data', '.DS_Store'))
    mu = out / 'js' / 'mu.js'
    js = mu.read_text(encoding='utf-8')
    if js.count('const LOCKED = false;') != 1:
        print('site_crypt: mu.js 에서 잠금 표시를 찾지 못했다')
        return 1
    mu.write_text(js.replace('const LOCKED = false;', 'const LOCKED = true;'), encoding='utf-8')
    key, salt = key_of(pw)
    n = size = 0
    for p in files:
        rel = p.relative_to(config.DATA).as_posix()
        dst = out / 'data' / (rel + '.enc')
        dst.parent.mkdir(parents=True, exist_ok=True)
        blob = seal(key, rel, p.read_bytes())
        dst.write_bytes(blob)
        n, size = n + 1, size + len(blob)
    b64 = lambda b: base64.b64encode(b).decode()
    (out / 'data' / 'lock.json').write_text(json.dumps({'v': 1, 'salt': b64(salt), 'iter': ITER, 'check': b64(seal(key, 'check', CHECK))}))
    (out / '.nojekyll').write_text('')
    print(f'site_crypt: {out.name}/ 에 화면 + 잠근 데이터 {n}개 ({size / 1e6:.1f}MB)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
