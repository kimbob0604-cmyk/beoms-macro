"""변동성 구조: CBOE VIX 기간구조(9일·3개월·6개월) + KRX VKOSPI → macro.db.  python3 collect_vol.py [--days N]
VKOSPI 는 KRX Open API 가 하루치씩만 줘서, 처음엔 --days 로 과거를 채운다(기본: 최근 15일 중 빈 날만)."""
import csv
import io
import sys
import time
from datetime import date, datetime, timedelta

import requests

import config
import store

CBOE = 'https://cdn.cboe.com/api/global/us_indices/daily_prices/{}_History.csv'
VIXES = [('vix9d', 'VIX9D', 'VIX 9일'), ('vix3m', 'VIX3M', 'VIX 3개월'), ('vix6m', 'VIX6M', 'VIX 6개월')]
KRX = 'https://data-dbg.krx.co.kr/svc/apis/idx/drvprod_dd_trd'


def cboe(c):
    n = 0
    for key, sym, name in VIXES:
        r = requests.get(CBOE.format(sym), timeout=40)
        r.raise_for_status()
        rows = []
        for row in csv.DictReader(io.StringIO(r.text)):
            try:
                rows.append((datetime.strptime(row['DATE'], '%m/%d/%Y').strftime('%Y-%m-%d'), float(row['CLOSE'])))
            except (ValueError, KeyError):
                continue
        n += store.put(c, f'vol:{key}', rows, name=name, grp='변동성', unit='pt', source='CBOE', freq='매일', use='타이밍', diff=1, dec=2)
    return n


def vkospi(c, days):
    k = config.key('KRX_API_KEY')
    if not k:
        return 0, 'KRX 열쇠 없음'
    have = {d for d, _ in store.get(c, 'vol:vkospi')}
    rows, calls = [], 0
    for back in range(1, days + 1):
        d = date.today() - timedelta(days=back)
        if d.weekday() >= 5 or d.isoformat() in have:
            continue
        r = requests.get(KRX, headers={'AUTH_KEY': k}, params={'basDd': d.strftime('%Y%m%d')}, timeout=30)
        calls += 1
        for x in r.json().get('OutBlock_1', []):
            if x.get('IDX_NM') == '코스피 200 변동성지수' and x.get('CLSPRC_IDX') not in (None, '', '-'):
                rows.append((d.isoformat(), float(x['CLSPRC_IDX'].replace(',', ''))))
        time.sleep(0.12)
    n = store.put(c, 'vol:vkospi', rows, name='VKOSPI (KOSPI200 변동성)', grp='변동성', unit='pt', source='KRX Open API', freq='매일', use='타이밍', diff=1, dec=2)
    return n, f'호출 {calls}회'


def main():
    days = int(sys.argv[sys.argv.index('--days') + 1]) if '--days' in sys.argv else 15
    c = store.connect()
    try:
        n1 = cboe(c)
        c.commit()
        store.log(c, 'vol.cboe', True, f'{n1}행')
    except Exception as e:
        n1 = 0
        store.log(c, 'vol.cboe', False, e)
    try:
        n2, msg = vkospi(c, days)
        c.commit()
        store.log(c, 'vol.vkospi', True, f'{n2}행 {msg}')
    except Exception as e:
        n2, msg = 0, str(e)
        store.log(c, 'vol.vkospi', False, e)
    print(f'vol: CBOE {n1}행, VKOSPI {n2}행 ({msg})')
    return 0


if __name__ == '__main__':
    sys.exit(main())
