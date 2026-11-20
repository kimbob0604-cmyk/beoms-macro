"""미국 금리·신용 스프레드·유동성·경기 (FRED API) → macro.db.  python3 collect_fred.py [--full]
처음(또는 --full)은 2015년부터, 그 뒤는 최근 120일만 다시 받는다. 연준 순유동성과 CP 스프레드는 여기서 계산해 같이 쌓는다."""
import sys
from datetime import date, timedelta

import requests

import config
import store

API = 'https://api.stlouisfed.org/fred/series/observations'
S = [  # key, FRED id, 이름, 묶음, 단위, 주기, 용도, 소수
    ('hy_oas', 'BAMLH0A0HYM2', '하이일드 스프레드', '크레딧', '%p', '매일', '비중', 2), ('ccc_oas', 'BAMLH0A3HYC', 'CCC 스프레드', '크레딧', '%p', '매일', '비중', 2),
    ('b_oas', 'BAMLH0A2HYB', 'B 스프레드', '크레딧', '%p', '매일', '비중', 2), ('bb_oas', 'BAMLH0A1HYBB', 'BB 스프레드', '크레딧', '%p', '매일', '비중', 2),
    ('bbb_oas', 'BAMLC0A4CBBB', 'BBB 스프레드', '크레딧', '%p', '매일', '비중', 2), ('ig_oas', 'BAMLC0A0CM', '우량 회사채 스프레드', '크레딧', '%p', '매일', '비중', 2),
    ('us2y', 'DGS2', '미국 2년 금리', '금리', '%', '매일', '비중', 2), ('us10y', 'DGS10', '미국 10년 금리 (FRED)', '금리', '%', '매일', '비중', 2), ('us30y', 'DGS30', '미국 30년 금리 (FRED)', '금리', '%', '매일', '비중', 2),
    ('t10y2y', 'T10Y2Y', '미국 10년 − 2년', '금리', '%p', '매일', '비중', 2), ('t10y3m', 'T10Y3M', '미국 10년 − 3개월', '금리', '%p', '매일', '비중', 2),
    ('real10y', 'DFII10', '미국 실질금리 10년', '금리', '%', '매일', '비중', 2), ('bei10y', 'T10YIE', '미국 기대인플레 10년', '금리', '%', '매일', '비중', 2),
    ('tp10y', 'THREEFYTP10', '미국 기간프리미엄 10년 (킴-라이트)', '금리', '%p', '주간', '비중', 2),
    ('sofr', 'SOFR', 'SOFR', '자금시장', '%', '매일', '비중', 2), ('iorb', 'IORB', '지준부리 (IORB)', '자금시장', '%', '매일', '비중', 2),
    ('cp3m', 'DCPF3M', 'CP 3개월 (금융)', '자금시장', '%', '매일', '비중', 2), ('tb3m', 'DTB3', '미 국채 3개월', '자금시장', '%', '매일', '비중', 2),
    ('walcl', 'WALCL', '연준 총자산', '유동성', '백만달러', '주간', '비중', 0), ('tga', 'WTREGEN', '재무부 일반계정 (TGA)', '유동성', '백만달러', '주간', '비중', 0),
    ('rrp', 'RRPONTSYD', '역레포 잔액', '유동성', '십억달러', '매일', '비중', 1), ('nfci', 'NFCI', '금융여건지수 (NFCI)', '유동성', '', '주간', '비중', 3),
    ('mmf_retail', 'WRMFNS', '소매 MMF 잔고', '유동성', '십억달러', '주간', '비중', 0), ('margin_q', 'BOGZ1FL663067003Q', '미국 증권사 신용융자 (분기)', '유동성', '백만달러', '분기', '비중', 0),
    ('gdpnow', 'GDPNOW', 'GDPNow (애틀랜타 연은)', '경기', '%', '분기', '비중', 2), ('sahm', 'SAHMREALTIME', '삼 룰', '경기', '%p', '월간', '비중', 2),
    ('recprob', 'RECPROUSM156N', '침체 확률 (평활)', '경기', '%', '월간', '비중', 1), ('claims', 'ICSA', '신규 실업수당 청구', '경기', '건', '주간', '비중', 0),
    ('epu', 'USEPUINDXD', '정책 불확실성 지수', '경기', '', '매일', '비중', 0), ('umich', 'UMCSENT', '미시간 소비자심리', '경기', '', '월간', '비중', 1),
]


def fetch(k, sid, start):
    r = requests.get(API, params={'series_id': sid, 'api_key': k, 'file_type': 'json', 'observation_start': start}, timeout=40)
    r.raise_for_status()
    return [(o['date'], float(o['value'])) for o in r.json()['observations'] if o['value'] not in ('.', '')]


def main():
    k = config.key('FRED_KEY')
    c = store.connect()
    if not k:
        store.log(c, 'fred', False, 'FRED 열쇠 없음')
        return 4
    full = '--full' in sys.argv or not c.execute("SELECT 1 FROM series WHERE key='fred:hy_oas' LIMIT 1").fetchone()
    start = '2015-01-01' if full else (date.today() - timedelta(days=120)).isoformat()
    n, miss = 0, []
    for key, sid, name, grp, unit, freq, use, dec in S:
        try:
            n += store.put(c, f'fred:{key}', fetch(k, sid, start), name=name, grp=grp, unit=unit, source='FRED', freq=freq, use=use, diff=1 if unit in ('%', '%p', '') else 0, dec=dec)
        except Exception as e:
            miss.append(f'{name}({type(e).__name__})')
    c.commit()
    # 파생: 연준 순유동성 = 총자산 − TGA − 역레포 (십억달러, 총자산 발표일 기준) / CP − 국채 3개월 / SOFR − IORB
    import pandas as pd
    g = lambda key: pd.Series(dict(store.get(c, f'fred:{key}')), dtype=float)
    w, t, rr = g('walcl'), g('tga'), g('rrp')
    if len(w) and len(t) and len(rr):
        idx = w.index
        net = (w - t.reindex(idx.union(t.index)).ffill().reindex(idx)) / 1000 - rr.reindex(idx.union(rr.index)).ffill().reindex(idx)
        n += store.put(c, 'fred:netliq', list(net.dropna().round(1).items()), name='연준 순유동성', grp='유동성', unit='십억달러', source='FRED(계산)', freq='주간', use='비중', diff=0, dec=0,
                       note='총자산(WALCL) − 재무부 계좌(TGA) − 역레포(RRP)')
    for key, a, b, name in (('cp_spread', 'cp3m', 'tb3m', 'CP − 국채 3개월'), ('sofr_iorb', 'sofr', 'iorb', 'SOFR − IORB')):
        x = pd.concat([g(a), g(b)], axis=1).dropna()
        if len(x):
            n += store.put(c, f'fred:{key}', list((x.iloc[:, 0] - x.iloc[:, 1]).round(3).items()), name=name, grp='자금시장', unit='%p', source='FRED(계산)', freq='매일', use='비중', diff=1, dec=2)
    c.commit()
    store.log(c, 'fred', len(miss) < 5, f'{n}행' + (f', 못 받음: {", ".join(miss)}' if miss else ''))
    print(f'fred: {n}행', '못 받음:', miss or '없음')
    return 0 if len(miss) < 5 else 1


if __name__ == '__main__':
    sys.exit(main())
