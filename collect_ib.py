"""IB 지표판 재료: 국가 ETF(글로벌 폭) · 나스닥÷NYSE 거래량 · 미국 ETF 공매도 잔고(FINRA, 월 2회) → macro.db.
python3 collect_ib.py [--full]   하나가 실패해도 나머지는 계속한다."""
import sys
import time
import warnings

import requests

import store

warnings.filterwarnings('ignore')
START = '2005-01-01'
# 국가 ETF (미국 상장, 달러 기준). BofA 글로벌 폭 규칙은 현지통화 MSCI 지수를 쓰지만 무료로는 ETF 가 가장 가깝다.
COUNTRY = {
    'SPY': '미국', 'EWC': '캐나다', 'EWW': '멕시코', 'EWZ': '브라질', 'ECH': '칠레', 'EPU': '페루', 'ARGT': '아르헨티나',
    'EWU': '영국', 'EWG': '독일', 'EWQ': '프랑스', 'EWI': '이탈리아', 'EWP': '스페인', 'EWN': '네덜란드', 'EWL': '스위스', 'EWD': '스웨덴', 'EWK': '벨기에', 'EWO': '오스트리아',
    'EDEN': '덴마크', 'EFNL': '핀란드', 'ENOR': '노르웨이', 'EIRL': '아일랜드', 'EPOL': '폴란드', 'GREK': '그리스', 'TUR': '튀르키예', 'EIS': '이스라엘',
    'EZA': '남아공', 'KSA': '사우디', 'UAE': 'UAE', 'QAT': '카타르',
    'EWJ': '일본', 'EWY': '한국', 'EWT': '대만', 'MCHI': '중국', 'EWH': '홍콩', 'INDA': '인도', 'EWS': '싱가포르', 'EWM': '말레이시아', 'EIDO': '인도네시아', 'THD': '태국', 'EPHE': '필리핀', 'VNM': '베트남',
    'EWA': '호주', 'ENZL': '뉴질랜드',
}
SI = {'SPY': 'S&P500 ETF(SPY)', 'QQQ': '나스닥100 ETF(QQQ)', 'IWM': '러셀2000 ETF(IWM)', 'HYG': '하이일드 ETF(HYG)', 'SMH': '반도체 ETF(SMH)', 'NVDA': '엔비디아', 'ORCL': '오라클', 'CRWV': '코어위브'}


def country(c):
    import yfinance as yf
    have = dict(c.execute("SELECT key, count(*) FROM series WHERE key LIKE 'ctry:%' GROUP BY key"))
    full = '--full' in sys.argv or min([have.get(f'ctry:{t.lower()}', 0) for t in COUNTRY]) < 300
    kw = {'start': START} if full else {'period': '3mo'}
    d = yf.download(list(COUNTRY), interval='1d', progress=False, auto_adjust=True, threads=True, **kw)['Close']
    n = 0
    for tk, name in COUNTRY.items():
        s = d[tk].dropna() if tk in d else []
        if len(s):
            n += store.put(c, f'ctry:{tk.lower()}', [(str(i.date()), float(v)) for i, v in s.items()], name=f'{name} ETF ({tk})', grp='국가 ETF', unit='', source='Yahoo Finance', freq='매일', use='섹터', diff=0, dec=2)
    return n


def volume(c):
    """나스닥 거래량 ÷ NYSE 거래량 (씨티 패닉/유포리아 구성요소: 높으면 투기적 거래가 많다)"""
    import yfinance as yf
    have = c.execute("SELECT count(*) FROM series WHERE key='mkt:vol_ratio'").fetchone()[0]
    kw = {'start': START} if ('--full' in sys.argv or have < 300) else {'period': '3mo'}
    v = yf.download(['^IXIC', '^NYA'], interval='1d', progress=False, auto_adjust=True, threads=True, **kw)['Volume'].dropna()
    v = v[(v['^IXIC'] > 0) & (v['^NYA'] > 0)]
    r = v['^IXIC'] / v['^NYA']
    # 미국 장중에 돌면 오늘 줄이 장중 값이라 뺀다. 예전엔 마지막 줄을 늘 뺐는데, 최신일 NYSE 거래량이 0으로 와 위에서 걸러지면
    # 멀쩡한 전날까지 빠졌다(2026-11-24: 11/20 이 안 들어가 11/19 에 멈춤).
    from datetime import datetime
    from zoneinfo import ZoneInfo
    now = datetime.now(ZoneInfo('America/New_York'))
    if len(r) and r.index[-1].date() == now.date() and (now.hour, now.minute) < (16, 30):
        r = r.iloc[:-1]
    return store.put(c, 'mkt:vol_ratio', [(str(i.date()), float(x)) for i, x in r.items()], name='나스닥 ÷ NYSE 거래량', grp='미국 수급', unit='배', source='Yahoo Finance', freq='매일', use='타이밍', diff=1, dec=2)


def short_interest(c):
    """FINRA 공매도 잔고 (결제일 기준 월 2회, 발표는 약 2주 뒤)"""
    n = 0
    for tk, name in SI.items():
        r = requests.post('https://api.finra.org/data/group/otcMarket/name/consolidatedShortInterest',
                          json={'limit': 300, 'compareFilters': [{'compareType': 'equal', 'fieldName': 'symbolCode', 'fieldValue': tk}],
                                'dateRangeFilters': [{'fieldName': 'settlementDate', 'startDate': '2018-01-01', 'endDate': '2099-12-31'}]},
                          headers={'Accept': 'application/json', 'Content-Type': 'application/json'}, timeout=60)
        j = r.json() if r.status_code == 200 else []
        if not isinstance(j, list) or not j:
            continue
        sh = [(x['settlementDate'], x['currentShortPositionQuantity'] / 1e6) for x in j if x.get('currentShortPositionQuantity') is not None]
        dtc = [(x['settlementDate'], x['daysToCoverQuantity']) for x in j if x.get('daysToCoverQuantity') is not None]
        n += store.put(c, f'si:{tk.lower()}', sh, name=f'공매도 잔고 — {name}', grp='미국 수급', unit='백만 주', source='FINRA', freq='격주', use='흐름', diff=0, dec=1)
        n += store.put(c, f'si:{tk.lower()}:dtc', dtc, name=f'공매도 잔고 커버 일수 — {name}', grp='미국 수급', unit='일', source='FINRA', freq='격주', use='흐름', diff=1, dec=2)
        time.sleep(0.3)
    return n


def main():
    c = store.connect()
    out, bad = [], 0
    for name, fn in (('ib.country', country), ('ib.volume', volume), ('ib.short', short_interest)):
        try:
            n = fn(c)
            c.commit()
            store.log(c, name, n > 0, f'{n}행')
            out.append(f'{name} {n}')
        except Exception as e:
            bad += 1
            store.log(c, name, False, f'{type(e).__name__}: {e}')
            out.append(f'{name} 실패({type(e).__name__})')
    print('ib:', ' · '.join(out))
    return 0


if __name__ == '__main__':
    sys.exit(main())
