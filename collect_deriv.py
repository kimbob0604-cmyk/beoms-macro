"""파생·평단 재료 → macro.db.  python3 collect_deriv.py [--full]

krx   KRX Open API 선물·옵션 일별(다음 날 아침에 올라온다): KOSPI200 선물 베이시스, 달러선물 근월·차근월(통화 스왑 대용),
      KOSPI200 옵션 풋콜(거래량·미결제·대금)·스큐·행사가별 미결제
kis   한국투자증권 API(조회 전용): 시장 전체 대차잔고, 종목별 공매도 일별(수량·대금 → 공매도 평단), 외국인 지수선물 순매수(장 마감 뒤 하루 한 점)
opt   야후 옵션 체인: 미국 ETF·종목별 풋콜(거래량·미결제)과 등가격 내재변동성 (과거가 없어 오늘부터 쌓는다)
하나가 실패해도 나머지는 계속한다. 처음(또는 --full)은 선물 750일·옵션 500일을 채운다(15~20분)."""
import json
import re
import sys
import time
from datetime import date, datetime, timedelta

import requests

import config
import store

KRX = 'https://data-dbg.krx.co.kr/svc/apis/'
KIS = 'https://openapi.koreainvestment.com:9443'
K200_OPT = ('코스피200 옵션', '코스피200 위클리(목) 옵션', '코스피200 위클리(월) 옵션', '코스피200 위클리 옵션')
# 롱숏 페어 (build3 도 이 목록을 쓴다): (이름, A, B, 설명) — 한국 종목은 6자리 코드, 해외는 px: 계열
PAIRS = [
    ('삼성전자 ÷ SK하이닉스', '005930', '000660', '메모리 두 회사'),
    ('삼성전자 ÷ 삼성전자우', '005930', '005935', '보통주 ÷ 우선주'),
    ('SK스퀘어 ÷ SK하이닉스', '402340', '000660', '지주사 ÷ 자회사'),
    ('SK하이닉스 ÷ 마이크론', '000660', 'px:mu', '한·미 메모리 (환율 반영 안 함)'),
    ('SK하이닉스 ÷ CXMT', '000660', 'px:cxmt', '한·중 메모리 (환율 반영 안 함)'),
    ('현대차 ÷ 기아', '005380', '000270', '완성차'),
    ('현대차 ÷ 현대차우', '005380', '005385', '보통주 ÷ 우선주'),
    ('LG화학 ÷ LG에너지솔루션', '051910', '373220', '모회사 ÷ 자회사'),
    ('KB금융 ÷ 신한지주', '105560', '055550', '은행지주'),
    ('NAVER ÷ 카카오', '035420', '035720', '인터넷'),
    ('한화에어로스페이스 ÷ 현대로템', '012450', '064350', '방산'),
    ('HD현대중공업 ÷ 한화오션', '329180', '042660', '조선'),
]
US_OPT = {'SPY': 'S&P500 ETF', 'QQQ': '나스닥100 ETF', 'IWM': '러셀2000 ETF', 'SMH': '반도체 ETF', 'EWY': '한국 ETF', 'NVDA': '엔비디아', 'MU': '마이크론', 'ORCL': '오라클', 'CRWV': '코어위브'}
N_STOCKS = 40


def f(v):
    try:
        return float(str(v).replace(',', ''))
    except (TypeError, ValueError):
        return None


def nth_weekday(ym, n, wd):
    """ym='202612' 의 n번째 wd요일 (월=0)"""
    d = date(int(ym[:4]), int(ym[4:]), 1)
    d += timedelta(days=(wd - d.weekday()) % 7 + 7 * (n - 1))
    return d


def stocks(c):
    """공매도·평단을 볼 종목: 시총 상위 N + 페어에 든 종목"""
    last = c.execute('SELECT max(date) FROM kr_px').fetchone()[0]
    top = [r[0] for r in c.execute('SELECT code FROM kr_px WHERE date=? ORDER BY mcap DESC LIMIT ?', (last, N_STOCKS))]
    for _, a, b, _ in PAIRS:
        for x in (a, b):
            if len(x) == 6 and x not in top:
                top.append(x)
    return top


# ── KRX 선물·옵션 ──
def krx_get(ep, d, key):
    for i in range(4):                                # KRX 가 가끔 연결을 끊는다 → 쉬었다 다시
        try:
            r = requests.get(KRX + ep, headers={'AUTH_KEY': key}, params={'basDd': d}, timeout=90)
            r.raise_for_status()
            return r.json().get('OutBlock_1', [])
        except (requests.RequestException, ValueError):
            if i == 3:
                raise
            time.sleep(3 * (i + 1))


def parse_fut(rows, d):
    """그날 선물 표 → {계열: 값}"""
    day = date(int(d[:4]), int(d[4:6]), int(d[6:]))
    out, k2, usd = {}, [], []
    for x in rows:
        nm = x.get('ISU_NM', '')
        if '스프레드' in nm or '야간' in nm or x.get('MKT_NM', '정규') not in ('정규', ''):
            continue
        m = re.search(r'F (\d{6})', nm)
        if not m:
            continue
        row = (m.group(1), f(x.get('TDD_CLSPRC')), f(x.get('SPOT_PRC')), f(x.get('ACC_OPNINT_QTY')) or 0, f(x.get('ACC_TRDVOL')) or 0)
        if x.get('PROD_NM') == '코스피200 선물':
            k2.append(row)
        elif x.get('PROD_NM') == '미국달러 선물':
            usd.append(row)
    k2 = sorted(r for r in k2 if r[1] and r[2])
    if k2:
        exp = lambda ym: nth_weekday(ym, 2, 3)                       # 두 번째 목요일
        live = [r for r in k2 if exp(r[0]) >= day] or k2
        ym, fut, spot = live[0][:3]
        out.update({'drv:k200_fut': fut, 'drv:k200_spot': spot, 'drv:k200_basis': fut - spot, 'drv:k200_fut_oi': sum(r[3] for r in k2) / 1000})
        far = [r for r in live if (exp(r[0]) - day).days >= 7]
        if far:
            out['drv:k200_carry'] = (far[0][1] / far[0][2] - 1) * 365 / (exp(far[0][0]) - day).days * 100
    usd = sorted(r for r in usd if r[1])
    if usd:
        exp = lambda ym: nth_weekday(ym, 3, 0)                       # 세 번째 월요일
        live = [r for r in usd if (exp(r[0]) - day).days >= 3] or usd
        out['drv:usd_fut'] = live[0][1]
        if live[0][2]:
            out['drv:usd_spot'] = live[0][2]
        nxt = [r for r in live[1:] if r[4] > 0]
        if nxt:                                                      # 근월 → 차근월 선물 가격 차를 연율로: 원화 금리 − 달러 금리(시장이 매긴 값)
            out['drv:usd_swap'] = (nxt[0][1] / live[0][1] - 1) * 365 / (exp(nxt[0][0]) - exp(live[0][0])).days * 100
    return out


def parse_opt(rows, d, spot):
    """그날 옵션 표 → ({계열: 값}, 행사가별 미결제 표)"""
    day = date(int(d[:4]), int(d[4:6]), int(d[6:]))
    tot = {'C': [0, 0, 0], 'P': [0, 0, 0]}          # 거래량, 미결제, 대금
    month = {}
    for x in rows:
        if x.get('PROD_NM') not in K200_OPT or '야간' in x.get('ISU_NM', ''):
            continue
        side = 'C' if x.get('RGHT_TP_NM') == 'CALL' else 'P'
        v, oi, val = f(x.get('ACC_TRDVOL')) or 0, f(x.get('ACC_OPNINT_QTY')) or 0, f(x.get('ACC_TRDVAL')) or 0
        tot[side][0] += v
        tot[side][1] += oi
        tot[side][2] += val
        if x.get('PROD_NM') == '코스피200 옵션':
            m = re.search(r'[CP]\s+(\d{6})\s+([\d.]+)', x.get('ISU_NM', ''))
            if m:
                month.setdefault(m.group(1), {}).setdefault(float(m.group(2)), {})[side] = (oi, v, f(x.get('IMP_VOLT')) or 0)
    out = {}
    if tot['C'][0] and tot['P'][0]:
        out.update({'drv:k200_pc_vol': tot['P'][0] / tot['C'][0], 'drv:k200_pc_oi': tot['P'][1] / tot['C'][1] if tot['C'][1] else None,
                    'drv:k200_pc_val': tot['P'][2] / tot['C'][2] if tot['C'][2] else None})
    table = None
    yms = sorted(ym for ym in month if (nth_weekday(ym, 2, 3) - day).days >= 5) or sorted(month)
    if yms and spot:
        ks = month[yms[0]]
        near = lambda target, side: min((k for k in ks if side in ks[k] and ks[k][side][2] > 0), key=lambda k: abs(k - target), default=None)
        kp, kc = near(spot * 0.95, 'P'), near(spot * 1.05, 'C')
        if kp and kc and abs(kp / spot - 0.95) < 0.02 and abs(kc / spot - 1.05) < 0.02:
            out['drv:k200_skew'] = ks[kp]['P'][2] - ks[kc]['C'][2]      # 5% 외가격 풋 변동성 − 5% 외가격 콜 변동성
        table = {'date': f'{d[:4]}-{d[4:6]}-{d[6:]}', 'month': yms[0], 'spot': spot,
                 'rows': [[k, ks[k].get('C', (0, 0, 0))[0], ks[k].get('P', (0, 0, 0))[0], ks[k].get('C', (0, 0, 0))[1], ks[k].get('P', (0, 0, 0))[1]] for k in sorted(ks) if 0.85 <= k / spot <= 1.15]}
    return out, table


META = {
    'drv:k200_fut': ('KOSPI200 선물 (근월)', 'pt', 0, 2, '흐름'), 'drv:k200_spot': ('KOSPI200', 'pt', 0, 2, '흐름'), 'drv:k200_basis': ('KOSPI200 선물 베이시스 (선물 − 현물)', 'pt', 1, 2, '흐름'),
    'drv:k200_fut_oi': ('KOSPI200 선물 미결제', '천 계약', 0, 1, '흐름'), 'drv:k200_carry': ('KOSPI200 선물 내재 금리 (연율)', '%', 1, 2, '흐름'),
    'drv:usd_fut': ('달러선물 (근월)', '원', 0, 1, '흐름'), 'drv:usd_spot': ('원/달러 (선물 표의 현물가)', '원', 0, 1, '흐름'), 'drv:usd_swap': ('달러선물 내재 금리차 (원 − 달러, 연율)', '%', 1, 2, '비중'),
    'drv:k200_pc_vol': ('KOSPI200 옵션 풋콜 — 거래량', '배', 1, 2, '타이밍'), 'drv:k200_pc_oi': ('KOSPI200 옵션 풋콜 — 미결제', '배', 1, 2, '타이밍'),
    'drv:k200_pc_val': ('KOSPI200 옵션 풋콜 — 거래대금', '배', 1, 2, '타이밍'), 'drv:k200_skew': ('KOSPI200 옵션 스큐 (5% 외가격 풋 − 콜 변동성)', '%p', 1, 2, '타이밍'),
}


def krx(c):
    from concurrent.futures import ThreadPoolExecutor
    key = config.key('KRX_API_KEY')
    c.executescript('CREATE TABLE IF NOT EXISTS drv_done (ep TEXT, date TEXT, PRIMARY KEY (ep, date)) WITHOUT ROWID; CREATE TABLE IF NOT EXISTS blob (key TEXT PRIMARY KEY, date TEXT, json TEXT);')
    done = {(e, d) for e, d in c.execute('SELECT ep, date FROM drv_done')}
    today = date.today()
    first = not any(e == 'fut' for e, _ in done) or '--full' in sys.argv
    lastdone = max((d for e, d in done if e == 'opt'), default=None)
    back = 1100 if first or not lastdone else min(1100, max(12, (today - date.fromisoformat(lastdone)).days + 3))      # 오래 꺼져 있었으면 그 사이를 다 채운다
    days = [today - timedelta(days=i) for i in range(1, back)]
    days = sorted(d for d in days if d.weekday() < 5)
    got, lastrow = {'fut': 0, 'opt': 0}, {}

    def save(vals, iso):
        for k, v in vals.items():
            if v is not None:
                c.execute('INSERT OR REPLACE INTO series VALUES (?,?,?)', (k, iso, float(v)))
                lastrow[k] = (iso, v)

    def sweep(ep, path, todo, handle):
        """todo 날짜를 4개씩 동시에 받아 날짜 순서대로 저장. 값과 '받았음' 표시를 같이 저장해 중간에 끊겨도 이어서 받는다."""
        with ThreadPoolExecutor(4) as pool:
            for i, (d, rows) in enumerate(zip(todo, pool.map(lambda d: krx_get(path, d.strftime('%Y%m%d'), key), todo))):
                iso = d.isoformat()
                if rows:
                    handle(rows, d.strftime('%Y%m%d'), iso)
                    got[ep] += 1
                if rows or (today - d).days > 5:                          # 최근 며칠은 아직 안 올라왔을 수 있어 빈 날을 '끝'으로 치지 않는다
                    c.execute('INSERT OR REPLACE INTO drv_done VALUES (?,?)', (ep, iso))
                if i % 10 == 9:
                    c.commit()
        c.commit()

    sweep('fut', 'drv/fut_bydd_trd', [d for d in days[-750:] if ('fut', d.isoformat()) not in done], lambda rows, ds, iso: save(parse_fut(rows, ds), iso))

    def opt(rows, ds, iso):
        spot = (c.execute("SELECT value FROM series WHERE key='drv:k200_spot' AND date=?", (iso,)).fetchone() or [None])[0]
        vals, table = parse_opt(rows, ds, spot)
        save(vals, iso)
        if table:
            old = c.execute("SELECT date FROM blob WHERE key='k200_oi'").fetchone()
            if not old or old[0] <= table['date']:
                c.execute('INSERT OR REPLACE INTO blob VALUES (?,?,?)', ('k200_oi', table['date'], json.dumps(table)))
    sweep('opt', 'drv/opt_bydd_trd', [d for d in days[-500:] if ('opt', d.isoformat()) not in done], opt)
    n = 0
    for k, (name, unit, diff, dec, use) in META.items():                  # 설명·기준일 갱신
        n += store.put(c, k, [lastrow[k]] if k in lastrow else [], name=name, grp='파생', unit=unit, source='KRX Open API', freq='매일', use=use, diff=diff, dec=dec)
    return got['fut'] + got['opt'], f'선물 {got["fut"]}일 · 옵션 {got["opt"]}일'


# ── 한국투자증권 ──
def kis_token(s):
    files = [config.ROOT / '.cache' / 'kis_token.json', config.DASH / '.cache' / 'kis_token.json', config.DASH.parent / 'stock-dashboard' / 'cache' / 'kis_token.json']
    for p in files:                                                   # 토큰 발급은 1분에 한 번이라 다른 프로젝트가 받아 둔 것을 먼저 쓴다(읽기만)
        try:
            d = json.loads(p.read_text(encoding='utf-8'))
            if d.get('token') and time.time() < d.get('expires', 0) - 600:
                return d['token']
        except (OSError, ValueError):
            continue
    r = s.post(f'{KIS}/oauth2/tokenP', json={'grant_type': 'client_credentials', 'appkey': config.key('KIS_APP_KEY'), 'appsecret': config.key('KIS_APP_SECRET')}, timeout=15).json()
    if not r.get('access_token'):
        raise RuntimeError(f"토큰 발급 실패: {r.get('error_description') or r.get('msg1')}")
    files[0].parent.mkdir(exist_ok=True)
    files[0].write_text(json.dumps({'token': r['access_token'], 'expires': time.time() + int(r.get('expires_in', 86400))}), encoding='utf-8')
    return r['access_token']


def kis(c):
    s = requests.Session()
    h = {'authorization': f'Bearer {kis_token(s)}', 'appkey': config.key('KIS_APP_KEY'), 'appsecret': config.key('KIS_APP_SECRET'), 'custtype': 'P'}

    def call(path, tr, params):
        for _ in range(3):
            j = s.get(f'{KIS}/uapi/domestic-stock/v1/quotations/{path}', headers={**h, 'tr_id': tr}, params=params, timeout=20).json()
            time.sleep(0.08)
            if j.get('rt_cd') == '0':
                return j
            time.sleep(0.6)                                           # 초당 호출 제한에 걸리면 쉬었다 다시
        raise RuntimeError(f"{path}: {j.get('msg1')}")
    today = date.today()
    ymd = lambda d: d.strftime('%Y%m%d')
    iso = lambda x: f'{x[:4]}-{x[4:6]}-{x[6:]}'
    n = 0
    # 1) 시장 전체 대차잔고 (한 번에 100거래일)
    for mk, nm in (('1', 'kospi'), ('2', 'kosdaq')):
        have = c.execute('SELECT count(*) FROM series WHERE key=?', (f'drv:loan_{nm}',)).fetchone()[0]
        rows, end = [], today
        for _ in range(8 if (have < 300 or '--full' in sys.argv) else 1):
            j = call('daily-loan-trans', 'HHPST074500C0', {'MRKT_DIV_CLS_CODE': mk, 'MKSC_SHRN_ISCD': '', 'START_DATE': ymd(end - timedelta(days=140)), 'END_DATE': ymd(end), 'CTS': ''})
            o = [x for x in j.get('output1') or [] if x.get('bsop_date') and f(x.get('rmnd_stcn'))]        # 휴장일(값 0)은 뺀다
            if not o:
                break
            rows += o
            end = datetime.strptime(min(x['bsop_date'] for x in o), '%Y%m%d').date() - timedelta(days=1)
        kor = 'KOSPI' if nm == 'kospi' else 'KOSDAQ'
        put = lambda key, fld, div, name, unit, dec, diff=0: store.put(c, key, [(iso(x['bsop_date']), f(x[fld]) / div) for x in rows if f(x.get(fld)) is not None], name=name, grp='파생', unit=unit, source='한국투자증권 API', freq='매일', use='타이밍,흐름', diff=diff, dec=dec)
        n += put(f'drv:loan_{nm}', 'rmnd_amt', 1e6, f'대차잔고 금액 — {kor}', '조원', 1)
        n += put(f'drv:loan_{nm}_sh', 'rmnd_stcn', 1e8, f'대차잔고 주수 — {kor}', '억 주', 2)
        n += put(f'drv:loan_{nm}_new', 'new_stcn', 1e4, f'대차 신규 — {kor}', '만 주', 0)
        n += put(f'drv:loan_{nm}_rdmp', 'rdmp_stcn', 1e4, f'대차 상환 — {kor}', '만 주', 0)
    # 2) 종목별 공매도 일별 (수량·대금·평균가)
    c.execute('CREATE TABLE IF NOT EXISTS short_daily (date TEXT, code TEXT, close REAL, vol REAL, sqty REAL, ratio REAL, samt REAL, avg REAL, PRIMARY KEY (date, code)) WITHOUT ROWID')
    have = dict(c.execute('SELECT code, count(*) FROM short_daily GROUP BY code'))
    codes, bad = stocks(c), 0
    for code in codes:
        try:
            ends = [today] if have.get(code, 0) >= 150 and '--full' not in sys.argv else [today, today - timedelta(days=150)]
            for end in ends:
                j = call('daily-short-sale', 'FHPST04830000', {'FID_COND_MRKT_DIV_CODE': 'J', 'FID_INPUT_ISCD': code, 'FID_INPUT_DATE_1': ymd(end - timedelta(days=149 if len(ends) > 1 else 45)), 'FID_INPUT_DATE_2': ymd(end)})
                rows = [(iso(x['stck_bsop_date']), code, f(x.get('stck_clpr')), f(x.get('acml_vol')), f(x.get('ssts_cntg_qty')), f(x.get('ssts_vol_rlim')), f(x.get('ssts_tr_pbmn')), f(x.get('avrg_prc')))
                        for x in j.get('output2') or [] if x.get('stck_bsop_date') and f(x.get('acml_vol'))]
                rows = [r for r in rows if r[0] < today.isoformat() or datetime.now().hour >= 16]      # 장중의 오늘 값은 덜 찬 값이라 뺀다
                c.executemany('INSERT OR REPLACE INTO short_daily VALUES (?,?,?,?,?,?,?,?)', rows)
                n += len(rows)
        except Exception:
            bad += 1
    # 2-1) 주체별 순매수 수량(외국인·기관·개인) — 평단 계산용, 시총 상위 30종목. 한 번에 최근 30거래일
    import seed
    seed.schema(c)
    last = c.execute('SELECT max(date) FROM kr_px').fetchone()[0]
    ask = today if datetime.now().hour * 60 + datetime.now().minute >= 15 * 60 + 45 else today - timedelta(days=1)      # 장중(~15:40)에는 오늘 날짜로 물으면 거절된다
    for code in [r[0] for r in c.execute('SELECT code FROM kr_px WHERE date=? ORDER BY mcap DESC LIMIT 30', (last,))]:
        try:
            j = call('investor-trade-by-stock-daily', 'FHPTJ04160001', {'FID_COND_MRKT_DIV_CODE': 'UN', 'FID_INPUT_ISCD': code, 'FID_INPUT_DATE_1': ymd(ask), 'FID_ORG_ADJ_PRC': '', 'FID_ETC_CLS_CODE': '1'})
            rows = [(iso(x['stck_bsop_date']), code, f(x.get('frgn_ntby_qty')), f(x.get('orgn_ntby_qty')), f(x.get('prsn_ntby_qty'))) for x in j.get('output2') or []
                    if x.get('stck_bsop_date') and f(x.get('frgn_ntby_qty')) is not None and (iso(x['stck_bsop_date']) < today.isoformat() or datetime.now().hour >= 18)]      # 그날 값은 저녁에 확정된다
            c.executemany('INSERT OR REPLACE INTO kr_flow VALUES (?,?,?,?,?)', rows)
            n += len(rows)
        except Exception:
            bad += 1
    # 3) 외국인 KOSPI200 선물 순매수: 장 마감(15:45) 뒤의 그날 누적 값을 하루 한 점으로 쌓는다
    now = datetime.now()
    if now.weekday() < 5 and now.hour * 60 + now.minute >= 15 * 60 + 50:
        j = call('inquire-investor-time-by-market', 'FHPTJ04030000', {'FID_INPUT_ISCD': 'K2I', 'FID_INPUT_ISCD_2': 'F001'})
        o = (j.get('output') or [{}])[0]
        if any(f(o.get(k)) for k in ('frgn_seln_vol', 'frgn_shnu_vol')):      # 휴장일은 0
            for k, nm in (('frgn', '외국인'), ('orgn', '기관'), ('prsn', '개인')):
                n += store.put(c, f'drv:fut_{k}', [(today.isoformat(), f(o.get(f'{k}_ntby_qty')))], name=f'KOSPI200 선물 순매수 — {nm}', grp='파생', unit='계약', source='한국투자증권 API', freq='매일', use='흐름', diff=1, dec=0)
    return n, f'종목 {len(codes)}개' + (f' (실패 {bad})' if bad else '')


# ── 미국 옵션 체인 ──
def us_opt(c):
    import yfinance as yf
    day = c.execute("SELECT max(date) FROM series WHERE key='px:spy'").fetchone()[0]
    if not day:
        return 0, '기준일 없음'
    d0 = date.fromisoformat(day)
    n, bad = 0, []
    for tk, name in US_OPT.items():
        try:
            T = yf.Ticker(tk)
            exps = [e for e in T.options if 0 <= (date.fromisoformat(e) - d0).days <= 45][:8]
            cv = pv = co = po = 0
            iv, best = None, 99
            px = (c.execute('SELECT value FROM series WHERE key=? ORDER BY date DESC LIMIT 1', (f'px:{tk.lower()}',)).fetchone() or [None])[0] or float(T.fast_info['last_price'])
            for e in exps:
                ch = T.option_chain(e)
                cv += ch.calls.volume.fillna(0).sum()
                pv += ch.puts.volume.fillna(0).sum()
                co += ch.calls.openInterest.fillna(0).sum()
                po += ch.puts.openInterest.fillna(0).sum()
                gap = abs((date.fromisoformat(e) - d0).days - 30)
                if gap < best and len(ch.calls) and len(ch.puts):          # 30일에 가장 가까운 만기의 등가격 변동성
                    a = ch.calls.iloc[(ch.calls.strike - px).abs().argsort()[:1]].impliedVolatility.iloc[0]
                    b = ch.puts.iloc[(ch.puts.strike - px).abs().argsort()[:1]].impliedVolatility.iloc[0]
                    if a > 0.01 and b > 0.01:
                        iv, best = (a + b) / 2 * 100, gap
                time.sleep(0.2)
            put = lambda key, v, nm, unit, dec: store.put(c, f'opt:{tk.lower()}:{key}', [(day, v)], name=f'{name} 옵션 — {nm}', grp='미국 옵션', unit=unit, source='Yahoo Finance 옵션 체인', freq='매일', use='타이밍', diff=1, dec=dec)
            if cv > 0:
                n += put('pc_vol', pv / cv, '풋콜(거래량)', '배', 2)
            if co > 0:
                n += put('pc_oi', po / co, '풋콜(미결제)', '배', 2)
            if iv:
                n += put('iv', iv, '등가격 내재변동성', '%', 1)
        except Exception:
            bad.append(tk)
    return n, f'{len(US_OPT) - len(bad)}종목' + (f' (실패 {",".join(bad)})' if bad else '')


def main():
    c = store.connect()
    out = []
    for name, fn in (('deriv.krx', krx), ('deriv.kis', kis), ('deriv.opt', us_opt)):
        if len(sys.argv) > 1 and sys.argv[1] in ('krx', 'kis', 'opt') and not name.endswith(sys.argv[1]):
            continue
        try:
            n, msg = fn(c)
            c.commit()
            store.log(c, name, n > 0 or name == 'deriv.krx', f'{n}행 · {msg}')
            out.append(f'{name} {n}행({msg})')
        except Exception as e:
            c.commit()
            store.log(c, name, False, f'{type(e).__name__}: {e}')
            out.append(f'{name} 실패({type(e).__name__}: {str(e)[:80]})')
    print('deriv:', ' · '.join(out))
    return 0


if __name__ == '__main__':
    sys.exit(main())
