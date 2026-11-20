"""심리·포지셔닝: CNN 공탐지수(비공식 주소)·크립토 공탐지수·DIX/GEX(SqueezeMetrics)·CBOE 풋콜·S&P500 이익수익률(multpl)·CFTC 포지션 → macro.db.
python3 collect_sent.py   하나가 실패해도 나머지는 계속한다(비공식 주소는 끊길 수 있다)."""
import csv
import io
import re
import sys
from datetime import date, datetime, timezone

import requests

import store

UA = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36'}
CNN_PARTS = {'market_momentum_sp500': '시장 모멘텀 (S&P500 vs 125일선)', 'stock_price_strength': '신고가−신저가', 'stock_price_breadth': '거래량 폭', 'put_call_options': '풋콜',
             'market_volatility_vix': 'VIX', 'junk_bond_demand': '정크본드 수요', 'safe_haven_demand': '안전자산 수요'}


def cnn(c):
    j = requests.get('https://production.dataviz.cnn.io/index/fearandgreed/graphdata', headers=UA, timeout=40).json()
    ms = lambda x: datetime.fromtimestamp(x / 1000, timezone.utc).strftime('%Y-%m-%d')
    rows = {ms(p['x']): p['y'] for p in j['fear_and_greed_historical']['data']}
    fg = j['fear_and_greed']
    rows[fg['timestamp'][:10]] = fg['score']
    n = store.put(c, 'sent:cnn', list(rows.items()), name='CNN 공탐지수', grp='심리', unit='점', source='CNN(비공식 주소)', freq='매일', use='타이밍', diff=1, dec=1)
    for k, name in CNN_PARTS.items():
        p = j.get(k) or {}
        if p.get('score') is not None:
            n += store.put(c, f'sent:cnn:{k}', [(fg['timestamp'][:10], p['score'])], name=f'CNN 구성 — {name}', grp='심리', unit='점', source='CNN(비공식 주소)', freq='매일', use='타이밍', diff=1, dec=1)
    return n


def crypto(c):
    j = requests.get('https://api.alternative.me/fng/?limit=0', timeout=40).json()
    rows = [(datetime.fromtimestamp(int(x['timestamp']), timezone.utc).strftime('%Y-%m-%d'), float(x['value'])) for x in j['data']]
    return store.put(c, 'sent:crypto', rows, name='크립토 공탐지수', grp='심리', unit='점', source='alternative.me', freq='매일', use='흐름', diff=1, dec=0)


def dix(c):
    r = requests.get('https://squeezemetrics.com/monitor/static/DIX.csv', headers=UA, timeout=40)
    r.raise_for_status()
    d, g, px = [], [], []
    for row in csv.DictReader(io.StringIO(r.text)):
        d.append((row['date'], float(row['dix']) * 100))
        g.append((row['date'], float(row['gex']) / 1e9))
        px.append((row['date'], float(row['price'])))
    store.put(c, 'flow:dix_spx', px, name='S&P500 (DIX 파일, 2011~)', grp='미국 수급', unit='', source='SqueezeMetrics', freq='매일', use='흐름', diff=0, dec=0)
    n = store.put(c, 'flow:dix', d, name='DIX (다크풀 매수 비중)', grp='미국 수급', unit='%', source='SqueezeMetrics', freq='매일', use='타이밍', diff=1, dec=1)
    return n + store.put(c, 'flow:gex', g, name='GEX (딜러 감마)', grp='미국 수급', unit='십억달러', source='SqueezeMetrics', freq='매일', use='흐름', diff=0, dec=2)


def cboe_pc(c):
    t = requests.get('https://www.cboe.com/us/options/market_statistics/daily/', headers=UA, timeout=40).text
    out = {}
    for key, pat, name in (('pc_total', r'TOTAL PUT/CALL RATIO[^0-9]*([\d.]+)', '미국 풋콜 — 전체'), ('pc_equity', r'EQUITY PUT/CALL RATIO[^0-9]*([\d.]+)', '미국 풋콜 — 주식'), ('pc_index', r'INDEX PUT/CALL RATIO[^0-9]*([\d.]+)', '미국 풋콜 — 지수')):
        m = re.search(pat, t)
        if m:
            out[key] = (name, float(m.group(1)))
    m = re.search(r'"selectedDate"\s*:\s*"(\d{4}-\d{2}-\d{2})"', t) or re.search(r'(\d{4}-\d{2}-\d{2})', t)
    d = m.group(1) if m else date.today().isoformat()
    return sum(store.put(c, f'sent:{k}', [(d, v)], name=nm, grp='심리', unit='배', source='CBOE 일별 통계', freq='매일', use='타이밍', diff=1, dec=2) for k, (nm, v) in out.items())


def multpl(c):
    n = 0
    for key, page, name, unit in (('sp_ey', 's-p-500-earnings-yield', 'S&P500 이익수익률', '%'), ('sp_cape', 'shiller-pe', '실러 PER (CAPE)', '배'), ('sp_pe', 's-p-500-pe-ratio', 'S&P500 PER', '배')):
        t = requests.get(f'https://www.multpl.com/{page}', headers=UA, timeout=40).text
        m = re.search(r'Current[^:]*:\s*</b>\s*([\d.]+)', t)
        if m:
            n += store.put(c, f'val:{key}', [(date.today().isoformat(), float(m.group(1)))], name=name, grp='밸류에이션', unit=unit, source='multpl.com', freq='매일', use='비중', diff=1, dec=2)
    return n


CFTC = [('sp', 'E-MINI S&P 500', 'S&P500 선물'), ('nq', 'NASDAQ MINI', '나스닥100 선물'), ('rty', 'RUSSELL E-MINI', '러셀2000 선물'), ('ust10', 'UST 10Y NOTE', '미 국채 10년 선물'),
        ('vix', 'VIX FUTURES', 'VIX 선물'), ('jpy', 'JAPANESE YEN', '엔 선물'), ('usd', 'USD INDEX', '달러지수 선물')]


def cftc(c):
    n = 0
    for key, name, kor in CFTC:
        r = requests.get('https://publicreporting.cftc.gov/resource/gpe5-46if.json', params={'$where': f"contract_market_name='{name}'", '$order': 'report_date_as_yyyy_mm_dd DESC', '$limit': 300,
                         '$select': 'report_date_as_yyyy_mm_dd,lev_money_positions_long,lev_money_positions_short,asset_mgr_positions_long,asset_mgr_positions_short,open_interest_all'}, timeout=60)
        r.raise_for_status()
        lev, am = [], []
        for x in r.json():
            d = x['report_date_as_yyyy_mm_dd'][:10]
            f = lambda k: float(x.get(k) or 0)
            lev.append((d, (f('lev_money_positions_long') - f('lev_money_positions_short')) / 1000))
            am.append((d, (f('asset_mgr_positions_long') - f('asset_mgr_positions_short')) / 1000))
        n += store.put(c, f'cftc:{key}:lev', lev, name=f'{kor} — 레버리지 펀드 순포지션', grp='CFTC', unit='천 계약', source='CFTC', freq='주간', use='흐름', diff=0, dec=1)
        n += store.put(c, f'cftc:{key}:am', am, name=f'{kor} — 자산운용 순포지션', grp='CFTC', unit='천 계약', source='CFTC', freq='주간', use='흐름', diff=0, dec=1)
    return n


def main():
    c = store.connect()
    out = []
    for name, fn in (('sent.cnn', cnn), ('sent.crypto', crypto), ('sent.dix', dix), ('sent.cboe', cboe_pc), ('sent.multpl', multpl), ('sent.cftc', cftc)):
        try:
            n = fn(c)
            c.commit()
            store.log(c, name, n > 0, f'{n}행')
            out.append(f'{name} {n}')
        except Exception as e:
            store.log(c, name, False, f'{type(e).__name__}: {e}')
            out.append(f'{name} 실패({type(e).__name__})')
    print('sent:', ' · '.join(out))
    return 0


if __name__ == '__main__':
    sys.exit(main())
