"""한국 금리(ECOS)·신용잔고·예탁금·반대매매(금융투자협회) + 중국 신용잔고(이스트머니 공개 자료) → macro.db.
python3 collect_kr.py [--full]   처음(또는 --full)은 2010년부터, 그 뒤는 최근 60일."""
import sys
from datetime import date, timedelta

import requests

import config
import store

UA = {'User-Agent': 'Mozilla/5.0', 'Content-Type': 'application/json'}
ECOS_ITEMS = {'국고채(3년)': ('ktb3y', '국고채 3년'), '국고채(10년)': ('ktb10y', '국고채 10년'), '회사채(3년, AA-)': ('corp_aa', '회사채 3년 AA-'),
              '회사채(3년, BBB-)': ('corp_bbb', '회사채 3년 BBB-'), 'CD(91일)': ('cd91', 'CD 91일'), '콜금리(1일, 전체거래)': ('call', '콜금리')}


def ecos(c, start):
    k = config.key('ECOS_KEY')
    if not k:
        return 0, 'ECOS 열쇠 없음'
    rows, s, e = {}, start.replace('-', ''), date.today().strftime('%Y%m%d')
    for page in range(0, 60):
        a, b = page * 10000 + 1, (page + 1) * 10000
        j = requests.get(f'https://ecos.bok.or.kr/api/StatisticSearch/{k}/json/kr/{a}/{b}/817Y002/D/{s}/{e}/', timeout=60).json()
        got = j.get('StatisticSearch', {}).get('row', [])
        for r in got:
            it = ECOS_ITEMS.get(r['ITEM_NAME1'])
            if it and r['DATA_VALUE'] not in (None, ''):
                t = r['TIME']
                rows.setdefault(it, []).append((f'{t[:4]}-{t[4:6]}-{t[6:]}', float(r['DATA_VALUE'])))
        if len(got) < 10000:
            break
    n = 0
    for (key, name), v in rows.items():
        n += store.put(c, f'kr:{key}', v, name=name, grp='한국 금리', unit='%', source='한국은행 ECOS', freq='매일', use='비중', diff=1, dec=3)
    c.commit()
    import pandas as pd
    g = lambda key: pd.Series(dict(store.get(c, f'kr:{key}')), dtype=float)
    for key, a, b, name in (('corp_spread', 'corp_aa', 'ktb3y', '회사채 AA- − 국고 3년'), ('bbb_spread', 'corp_bbb', 'ktb3y', '회사채 BBB- − 국고 3년'), ('ktb_curve', 'ktb10y', 'ktb3y', '국고 10년 − 3년')):
        x = pd.concat([g(a), g(b)], axis=1).dropna()
        if len(x):
            n += store.put(c, f'kr:{key}', list(((x.iloc[:, 0] - x.iloc[:, 1]) * 100).round(1).items()), name=name, grp='한국 금리', unit='bp', source='ECOS(계산)', freq='매일', use='비중', diff=1, dec=1)
    return n, ''


def kofia(obj, start):
    body = {'dmSearch': {'tmpV40': '1000000', 'tmpV41': '1', 'tmpV1': 'D', 'tmpV45': start.replace('-', ''), 'tmpV46': date.today().strftime('%Y%m%d'), 'OBJ_NM': obj}}
    r = requests.post('https://freesis.kofia.or.kr/meta/getMetaDataList.do', json=body, headers=UA, timeout=60)
    r.raise_for_status()
    return r.json().get('ds1', [])


def credit(c, start):
    d = lambda x: f'{x[:4]}-{x[4:6]}-{x[6:]}'
    jo = lambda v: None if v is None else v / 1e6        # 백만원 → 조원
    n = 0
    rows = kofia('STATSCU0100000070BO', start)           # 신용공여 잔고
    for key, f, name in (('credit', 'TMPV2', '신용거래융자 잔고'), ('credit_kospi', 'TMPV3', '신용거래융자 — 유가증권'), ('credit_kosdaq', 'TMPV4', '신용거래융자 — 코스닥'), ('stock_loan', 'TMPV9', '예탁증권 담보융자')):
        n += store.put(c, f'kr:{key}', [(d(r['TMPV1']), jo(r[f])) for r in rows], name=name, grp='한국 수급', unit='조원', source='금융투자협회', freq='매일', use='타이밍,비중', diff=0, dec=2)
    rows = kofia('STATSCU0100000060BO', start)           # 증시자금 추이
    for key, f, name, unit, conv, dec in (('deposit', 'TMPV2', '투자자 예탁금', '조원', jo, 2), ('misu', 'TMPV5', '위탁매매 미수금', '조원', jo, 3),
                                          ('forced', 'TMPV6', '반대매매 금액', '억원', lambda v: None if v is None else v / 100, 0), ('forced_pct', 'TMPV7', '미수금 대비 반대매매 비중', '%', lambda v: v, 1)):
        n += store.put(c, f'kr:{key}', [(d(r['TMPV1']), conv(r[f])) for r in rows], name=name, grp='한국 수급', unit=unit, source='금융투자협회', freq='매일', use='타이밍', diff=1 if unit == '%' else 0, dec=dec)
    c.commit()
    import pandas as pd
    g = lambda key: pd.Series(dict(store.get(c, f'kr:{key}')), dtype=float)
    x = pd.concat([g('credit'), g('deposit')], axis=1).dropna()
    if len(x):
        n += store.put(c, 'kr:credit_ratio', list((x.iloc[:, 0] / x.iloc[:, 1] * 100).round(2).items()), name='신용잔고 ÷ 예탁금', grp='한국 수급', unit='%', source='금융투자협회(계산)', freq='매일', use='비중', diff=1, dec=1)
    return n


def china(c, full):
    rows = []
    for p in range(1, 12 if full else 2):
        j = requests.get('https://datacenter-web.eastmoney.com/api/data/v1/get', params={'reportName': 'RPTA_RZRQ_LSHJ', 'columns': 'DIM_DATE,RZRQYE', 'sortColumns': 'dim_date', 'sortTypes': -1, 'pageSize': 500, 'pageNumber': p},
                         headers={'User-Agent': 'Mozilla/5.0'}, timeout=40).json()
        data = (j.get('result') or {}).get('data') or []
        rows += [(x['DIM_DATE'][:10], x['RZRQYE'] / 1e8) for x in data if x.get('RZRQYE')]
        if len(data) < 500:
            break
    return store.put(c, 'cn:margin', rows, name='중국 신용잔고 (융자융권)', grp='해외 수급', unit='억위안', source='이스트머니 공개 자료', freq='매일', use='흐름,비중', diff=0, dec=0)


def main():
    c = store.connect()
    full = '--full' in sys.argv or not c.execute("SELECT 1 FROM series WHERE key='kr:credit' LIMIT 1").fetchone()
    start = '2010-01-01' if full else (date.today() - timedelta(days=60)).isoformat()
    out = []
    for name, fn in (('kr.ecos', lambda: ecos(c, start)[0]), ('kr.credit', lambda: credit(c, start)), ('kr.china', lambda: china(c, full))):
        try:
            n = fn()
            c.commit()
            store.log(c, name, True, f'{n}행')
            out.append(f'{name} {n}행')
        except Exception as e:
            store.log(c, name, False, f'{type(e).__name__}: {e}')
            out.append(f'{name} 실패({type(e).__name__})')
    print('kr:', ' · '.join(out))
    return 0


if __name__ == '__main__':
    sys.exit(main())
