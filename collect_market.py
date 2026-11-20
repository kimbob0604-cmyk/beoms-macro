"""시세 계열(지수·변동성·금리·환율·원자재·ETF·해외 종목) → macro.db.  python3 collect_market.py [--full]
과거가 300일 미만인 계열(처음 받는 것)과 --full 은 2005년부터, 나머지는 최근 3개월만 다시 받아 덮어쓴다."""
import sys
import time
import warnings

import store
from assets import A, UNIT

warnings.filterwarnings('ignore')
START = '2005-01-01'


def fetch(yf, tickers, full):
    """{티커: 종가 Series}. 한 번에 받다가 빠진 종목은 잠깐 쉬고 하나씩 다시 받는다 (야후가 가끔 일부만 돌려준다)"""
    if not tickers:
        return {}, 0
    kw = {'start': START} if full else {'period': '3mo'}
    out = {}
    try:
        d = yf.download(tickers, interval='1d', progress=False, auto_adjust=True, threads=True, **kw)['Close']
        if hasattr(d, 'columns'):
            out = {t: d[t].dropna() for t in tickers if t in d and len(d[t].dropna())}
        elif len(d.dropna()):
            out = {tickers[0]: d.dropna()}
    except Exception:
        pass
    lost = [t for t in tickers if t not in out]
    for rnd in range(2 if lost else 0):                      # 두 번까지: 두 번째는 20초 쉬고 남은 것만
        left = [t for t in lost if t not in out]
        if not left:
            break
        time.sleep(20 if rnd else 5)
        for t in left:
            try:
                x = yf.download(t, interval='1d', progress=False, auto_adjust=True, threads=False, **kw)['Close'].squeeze().dropna()
                if len(x):
                    out[t] = x
            except Exception:
                pass
            time.sleep(1)
    return out, len(lost)


def main():
    import yfinance as yf
    c = store.connect()
    have = dict(c.execute("SELECT key, count(*) FROM series WHERE key LIKE 'px:%' GROUP BY key"))
    new = [a[1] for a in A if '--full' in sys.argv or have.get(f'px:{a[0]}', 0) < 300]
    old = [a[1] for a in A if a[1] not in new]
    got, lost = {}, 0
    for tickers, full in ((new, True), (old, False)):
        g, l = fetch(yf, tickers, full)
        got.update(g)
        lost += l
    n, miss = 0, []
    for key, tk, name, grp, use, diff, dec in A:
        s = got.get(tk, [])
        if len(s) == 0:
            miss.append(name)
            continue
        rows = [(str(i.date()), float(v)) for i, v in s.items()]
        n += store.put(c, f'px:{key}', rows, name=name, grp=grp, unit=UNIT.get(grp, ''), source='Yahoo Finance', freq='매일', use=use, diff=diff, dec=dec)
    c.commit()
    store.log(c, 'market', len(miss) < 5, f'{n}행 (2005년부터 {len(new)}개)' + (f', 못 받음: {", ".join(miss)}' if miss else ''))
    print(f'market: {n}행 · 2005년부터 {len(new)}개 · 처음에 빠진 것 {lost}개 · 못 받음:', miss or '없음')
    return 0 if len(miss) < 5 else 1


if __name__ == '__main__':
    sys.exit(main())
