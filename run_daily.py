"""매일 갱신: 수집 → 빌드. 하루 세 번(08:25 미국 마감·KRX 전일 자료 뒤, 16:40 한국 마감 뒤, 21:30 금투협·FRED 갱신 뒤) launchd 가 돌린다.

  python3 run_daily.py          # 전부
  python3 run_daily.py --build  # 빌드만

수집기 하나가 실패해도 나머지는 계속하고, 실패는 status.json 에 남아 화면 위에 경고로 뜬다.
한국 폭 지표는 KRX Open API(다음 날 08시쯤)에서 전 종목 일봉을 직접 받아 채운다. 신용잔고·예탁금은 금융투자협회가 하루 늦게 올린다.
KRX 선물·옵션도 다음 날 아침에 올라온다. 외국인 선물 순매수는 16:40 실행 때 그날 값 한 점을 쌓는다(과거를 내주는 곳이 없다).
"""
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
JOBS = [('market', ['collect_market.py']), ('vol', ['collect_vol.py']), ('breadth', ['collect_breadth.py']),
        ('fred', ['collect_fred.py']), ('kr', ['collect_kr.py']), ('sent', ['collect_sent.py']), ('ib', ['collect_ib.py']), ('deriv', ['collect_deriv.py'])]


def main():
    log = ROOT / 'logs' / f'{datetime.now():%Y-%m-%d}.log'
    log.parent.mkdir(exist_ok=True)
    jobs = [] if '--build' in sys.argv else JOBS
    bad = 0
    with log.open('a', encoding='utf-8') as f:
        for name, cmd in [*jobs, ('build', ['build.py'])]:
            f.write(f'\n[{datetime.now():%H:%M:%S}] {name}\n')
            f.flush()
            r = subprocess.run([sys.executable, *cmd], cwd=ROOT, stdout=f, stderr=subprocess.STDOUT, timeout=1800)
            if r.returncode:
                bad += 1
                if name != 'build':       # 수집 실패를 기록 (build 가 status.json 에 싣는다)
                    import store
                    store.log(store.connect(), name, False, f'종료 코드 {r.returncode}')
            print(f'{name}: {"정상" if not r.returncode else f"실패({r.returncode})"}')
        if jobs:      # 알림(꺼져 있으면 아무것도 보내지 않는다)
            subprocess.run([sys.executable, 'alert.py'], cwd=ROOT, stdout=f, stderr=subprocess.STDOUT, timeout=600)   # 정기 보고는 차트 캡처로 1~2분
    if '--report' in sys.argv:      # 출처별로 됐는지·막혔는지 (클라우드 시험용)
        import sqlite3
        c = sqlite3.connect(ROOT / 'db' / 'macro.db')
        print('\n출처별 결과 (오늘):')
        for at, job, ok, msg in c.execute("SELECT max(at), job, ok, msg FROM runlog WHERE at>=date('now','localtime') GROUP BY job ORDER BY job"):
            print(f'  {"됨  " if ok else "막힘"} {job:14s} {at[11:16]}  {msg}')
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
