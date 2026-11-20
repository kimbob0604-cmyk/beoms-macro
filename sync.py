"""macro.db 를 실행 사이에 이어 준다: 저장소 릴리스 첨부 파일(macrodb)에 압축·암호화해 덮어 올리고, 다음 실행이 받아 쓴다.

하루씩 쌓는 값(풋콜·옵션·선물 수급·받은 날 표시)은 DB 에만 있어서, 클라우드(GitHub Actions)는 매번 받기 → 수집 → 빌드 → 올리기 순서로 돈다.
릴리스 첨부는 덮어쓰면 옛 파일이 지워져 저장소가 불지 않는다. 암호(MACRO_DB_PASS) 없이는 열 수 없다.

  python3 sync.py push            # 지금 DB 를 올린다 (맥에서 처음 한 번, 그 뒤로는 클라우드가)
  python3 sync.py pull [--force]  # 올라가 있는 DB 를 받아 db/macro.db 로 (맥에서 로컬 화면을 최신으로 볼 때). 로컬이 더 새로우면 --force 없이는 안 받는다
  python3 sync.py fresh 100       # 마지막으로 올린 지 100분 안이면 skip=true (예약이 겹쳐 돌 때 건너뛰기용)
  python3 sync.py status
"""
import hashlib
import json
import lzma
import os
import secrets
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import config

TAG, ASSET, META = 'macrodb', 'macro.db.xz.enc', 'meta.json'
STAMP = config.DB.parent / 'sync.json'
ITER, MAGIC = 200_000, b'BMD1'


def slug():
    if os.environ.get('GITHUB_REPOSITORY'):
        return os.environ['GITHUB_REPOSITORY']
    url = subprocess.run(['git', 'remote', 'get-url', 'origin'], cwd=config.ROOT, capture_output=True, text=True).stdout.strip()
    if not url:
        raise SystemExit('sync: 저장소(origin)가 아직 없다')
    return url.split('github.com')[-1].lstrip(':/').removesuffix('.git')


def gh(*args, **kw):
    return subprocess.run(['gh', *args, '-R', slug()], capture_output=True, text=True, **kw)


def _key(pw, salt):
    return hashlib.pbkdf2_hmac('sha256', pw.encode(), salt, ITER, 32)


def seal(pw, data):
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    salt, nonce = secrets.token_bytes(16), secrets.token_bytes(12)
    return MAGIC + salt + nonce + AESGCM(_key(pw, salt)).encrypt(nonce, data, MAGIC)


def unseal(pw, blob):
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    if blob[:4] != MAGIC:
        raise ValueError('사본 형식이 다르다')
    return AESGCM(_key(pw, blob[4:20])).decrypt(blob[20:32], blob[32:], MAGIC)


def password():
    pw = config.key('MACRO_DB_PASS')
    if not pw:
        raise SystemExit('sync: MACRO_DB_PASS 가 없다 (이 폴더 .env 또는 저장소 비밀값)')
    return pw


def remote_meta():
    with tempfile.TemporaryDirectory() as tmp:
        r = gh('release', 'download', TAG, '-p', META, '-D', tmp, '--clobber')
        p = Path(tmp) / META
        return json.loads(p.read_text()) if r.returncode == 0 and p.exists() else None


def pack(pw):
    """지금 DB 의 일관된 사본 → 압축 → 암호화. (암호문, 원본 크기)"""
    with tempfile.TemporaryDirectory() as tmp:
        snap = Path(tmp) / 'snap.db'
        src, dst = sqlite3.connect(str(config.DB), timeout=120), sqlite3.connect(str(snap))
        src.backup(dst)                     # 다른 프로세스가 쓰는 중이어도 일관된 사본
        dst.execute('VACUUM')
        dst.close()
        src.close()
        raw = snap.read_bytes()
    return seal(pw, lzma.compress(raw, preset=3)), len(raw)


def push():
    pw = password()
    t0 = time.time()
    blob, size = pack(pw)
    meta = {'at': int(time.time()), 'by': 'cloud' if os.environ.get('GITHUB_ACTIONS') else 'mac', 'db': size, 'size': len(blob), 'sha': hashlib.sha256(blob).hexdigest()}
    with tempfile.TemporaryDirectory() as tmp:
        a, m = Path(tmp) / ASSET, Path(tmp) / META
        a.write_bytes(blob)
        m.write_text(json.dumps(meta))
        if gh('release', 'view', TAG).returncode != 0:
            r = gh('release', 'create', TAG, '--prerelease', '--title', 'DB 사본 (암호화)', '--notes', '수집 실행 사이에 이어 쓰는 DB 사본입니다. 암호화되어 있어 열 수 없습니다. 실행할 때마다 덮어씁니다.')
            if r.returncode != 0:
                raise SystemExit(f'sync: 릴리스 만들기 실패 — {r.stderr.strip()[:200]}')
        r = gh('release', 'upload', TAG, '--clobber', str(a), str(m), timeout=1800)
        if r.returncode != 0:
            raise SystemExit(f'sync: 올리기 실패 — {r.stderr.strip()[:200]}')
    STAMP.write_text(json.dumps(meta))
    print(f'sync push: DB {size / 1e6:.0f}MB → {len(blob) / 1e6:.0f}MB, {time.time() - t0:.0f}초')
    return 0


def pull(force=False):
    pw = password()
    meta = remote_meta()
    if not meta:
        print('sync pull: 올라가 있는 DB 가 없다')
        return 1
    mine = json.loads(STAMP.read_text()) if STAMP.exists() else {}
    if config.DB.exists() and mine.get('sha') == meta['sha']:
        print('sync pull: 이미 최신')
        return 0
    if config.DB.exists() and not force and config.DB.stat().st_mtime > meta['at'] + 60:
        print('sync pull: 로컬 DB 가 올라가 있는 것보다 새롭다 — 그대로 둔다 (덮어쓰려면 --force, 올리려면 push)')
        return 2
    with tempfile.TemporaryDirectory() as tmp:
        r = gh('release', 'download', TAG, '-p', ASSET, '-D', tmp, '--clobber', timeout=1800)
        if r.returncode != 0:
            raise SystemExit(f'sync: 받기 실패 — {r.stderr.strip()[:200]}')
        blob = (Path(tmp) / ASSET).read_bytes()
    if hashlib.sha256(blob).hexdigest() != meta['sha']:
        raise SystemExit('sync: 받은 파일이 깨졌다 (해시 불일치)')
    raw = lzma.decompress(unseal(pw, blob))
    config.DB.parent.mkdir(exist_ok=True)
    if config.DB.exists():
        config.DB.replace(config.DB.with_suffix('.db.bak'))        # 직전 것 하나는 남긴다
    config.DB.write_bytes(raw)
    STAMP.write_text(json.dumps(meta))
    print(f'sync pull: {meta["by"]} 가 {time.strftime("%m-%d %H:%M", time.localtime(meta["at"]))} 에 올린 DB {len(raw) / 1e6:.0f}MB 를 받았다')
    return 0


def fresh(minutes):
    """이번 실행을 건너뛸지. 준비가 덜 됐을 때(비밀값·첫 DB 가 없음)도 실패로 두지 않고 건너뛴다 — 예약이 헛돌며 실패 메일을 쏟지 않게."""
    missing = [k for k in ('MACRO_DB_PASS', 'MACRO_PASS') if not config.key(k)]
    meta = None if missing else remote_meta()
    age = None if not meta else (time.time() - meta['at']) / 60
    if missing:
        skip, why = True, f'비밀값이 아직 없다({", ".join(missing)}) → 건너뜀'
    elif meta is None:
        skip, why = True, '올라가 있는 DB 가 없다(맥에서 python3 sync.py push 를 먼저) → 건너뜀'
    else:
        skip = age < minutes and os.environ.get('MACRO_FORCE') != '1'
        why = f'마지막으로 올린 지 {age:.0f}분 → {"건너뜀" if skip else "실행"}'
    print(f'{"::notice::" if os.environ.get("GITHUB_ACTIONS") else ""}sync fresh: {why}')
    if os.environ.get('GITHUB_OUTPUT'):
        with open(os.environ['GITHUB_OUTPUT'], 'a') as f:
            f.write(f'skip={"true" if skip else "false"}\n')
    return 0


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'status'
    if cmd == 'push':
        return push()
    if cmd == 'pull':
        return pull('--force' in sys.argv)
    if cmd == 'fresh':
        return fresh(float(sys.argv[2]) if len(sys.argv) > 2 else 100)
    meta = remote_meta()
    print('올라가 있는 DB:', '없음' if not meta else f'{meta["by"]} · {time.strftime("%Y-%m-%d %H:%M", time.localtime(meta["at"]))} · {meta["size"] / 1e6:.0f}MB')
    return 0


if __name__ == '__main__':
    sys.exit(main())
