// IB 지표판: 하우스별 지표 요약 · 위험선호 지수(RAI식) · 글로벌 폭 규칙 · 패닉/유포리아식 지수
(async () => {
  MU.shell('ib');
  const { num, use, asof, esc, pm } = MU;
  let D;
  try { D = await MU.get('ib.json'); } catch (e) { return MU.fail(e); }
  MU.built(D.built);
  const $ = id => document.getElementById(id);
  const R = D.rai, G = D.gb, P = D.pe;
  const ser = (o, name, x = {}) => ({ name, d: o.d, v: o.v, ...x });
  const HZ = ['1개월', '3개월', '6개월', '12개월'];
  const beat = e => HZ.filter(h => e[h].mean != null && e[h].mean > e[h].base).length;
  const raiWord = R.last <= R.lo ? '극단적 위험 회피' : R.last <= -1 ? '위험 회피' : R.last >= R.hi ? '극단적 위험선호' : R.last >= 1 ? '위험선호' : '중립';
  const peWord = P.last <= 20 ? '패닉' : P.last >= 80 ? '유포리아' : P.last <= 35 ? '패닉 쪽' : P.last >= 65 ? '유포리아 쪽' : '중간';

  // 하우스 로고 (public/img/ib/*.png). 없는 이름은 글자만
  const LOGO = { '골드만삭스': 'gs.png', '골드만': 'gs.png', 'BofA': 'bofa.png', '씨티': 'citi.png', '모건스탠리': 'ms.jpg', '도이체': 'db.png' };
  const houseHtml = h => `<div class="house">${h.split(/\s*·\s*/).map(n => `<span class="hs">${LOGO[n] ? `<img class="hlogo" src="img/ib/${LOGO[n]}" alt="" width="22" height="22">` : ''}<b>${esc(n)}</b></span>`).join('')}</div>`;

  // 하우스별 요약
  const rows = [
    ['골드만삭스', '위험선호 지표 (RAI)', '위험자산 ÷ 안전자산 쌍 20여 개의 상대 성과를 표준화해 하나로', '쌍 13개, 3개월 상대수익률의 z-점수 평균', `<b>${pm(R.last, 2, '')}</b> · ${raiWord}`, '#rai', '아래'],
    ['BofA', '글로벌 폭 규칙', '국가 지수 중 50일선·200일선 아래 비율. 88% 넘으면 역발상 매수', `국가 ETF ${G.n}개(달러 기준)로 같은 계산`, `<b>${G.both}%</b> · ${G.both >= 88 ? '매수 신호' : '신호 아님'}`, '#gb', '아래'],
    ['씨티', '패닉/유포리아 모델', '공매도 잔고·신용융자·거래량 비·강세 설문·소매 MMF·풋콜·원자재·휘발유·풋/콜 프리미엄 9개', `9개 중 ${Object.keys(P.parts).length}개 (백분위 평균)`, `<b>${P.last}</b> · ${peWord}`, '#pe', '아래'],
    ['모건스탠리', '주식위험프리미엄', 'S&P500 이익수익률 − 실질 10년 금리', '같은 식', D.erp.last == null ? '–' : `<b>${num(D.erp.last)}%p</b> (${num(D.erp.ey)} − ${num(D.erp.real)})`, 'weight.html', '비중 탭'],
    ['골드만·노무라·도이체', '시스템 자금 (CTA·변동성 제어)', '내부 모델로 추정한 추세추종·변동성 목표 펀드의 주식 노출', '추세 신호 4개 + 변동성 목표 식으로 직접 어림', `CTA 주식 <b>${pm(D.cta_eq, 0)}</b> · 변동성 제어 <b>${D.volctl}%</b>`, 'flow.html#cta', '수급 탭'],
    ['노무라·골드만', '딜러 감마', '옵션 딜러가 지수 움직임에 맞춰 사고팔아야 하는 금액', 'SqueezeMetrics GEX', `<b>${num(D.gex.last)}</b> 십억달러`, 'flow.html#gex', '수급 탭'],
    ['BofA', 'Bull & Bear 지표', '헤지펀드 포지션·주식/채권 자금 유입·크레딧 기술 지표·주식 폭·롱온리 포지션 6개', '합치지 않음 — 자금 유입 자료(EPFR)가 유료. 재료만 표시', D.cftc ? `CFTC S&P 선물 3년 백분위: 레버리지 ${D.cftc.lev_pct} · 자산운용 ${D.cftc.am_pct}` : '–', 'flow.html#cftc', '수급 탭'],
    ['골드만삭스', '강세·약세장 지표', '실러 PER·수익률 곡선·실업률·근원 물가·ISM', '합치지 않음 — 재료만 표시', `실러 PER ${num(D.cape, 1)} · 10년−2년 ${num(D.curve)}%p · 삼 룰 ${num(D.sahm)}`, 'weight.html', '비중 탭'],
    ['BofA · 씨티', '펀드매니저 설문 · Sell Side 지표 · 경제 서프라이즈 지수', '자체 설문·자체 산출', '만들 수 없음', '<span class="muted">–</span>', '', ''],
  ];
  $('summary').innerHTML = `<h2>하우스별 지표 — 원래 정의와 우리가 만든 범위</h2><p class="sub">'지금 값'은 이 사이트가 계산한 값이다. 각 회사가 발표하는 숫자가 아니다.</p>
    <div class="scroll-x"><table class="tbl"><thead><tr><th>하우스</th><th class="l">지표</th><th class="l">원래 무엇으로 만드나</th><th class="l">우리가 만든 범위</th><th class="l">지금 값</th><th></th></tr></thead><tbody>
    ${rows.map(([h, n, o, w, v, u, t]) => `<tr><td>${houseHtml(h)}</td><td class="l"><b>${esc(n)}</b></td><td class="l small">${esc(o)}</td><td class="l small">${esc(w)}</td><td class="l">${v}</td><td>${u ? `<a class="lnk small" href="${u}">${t} →</a>` : ''}</td></tr>`).join('')}</tbody></table></div>`;

  // 위험선호 지수
  const zs = Object.entries(R.parts).sort((a, b) => (a[1] ?? 0) - (b[1] ?? 0));
  const neg = zs.filter(([, v]) => v != null && v <= -1).length;
  $('rai').innerHTML = `<h2>위험선호 지수 (RAI식) ${use('비중,흐름')} ${asof(R.date)}</h2>
    <p class="sub">위험자산 ÷ 안전자산 쌍 ${zs.length}개의 3개월 상대수익률을 각각 최근 3년 평균·표준편차로 표준화(z)한 뒤 평균. 0 = 평소, 음수 = 위험 회피.</p>
    <div class="big">${pm(R.last, 2, '')}<small> · ${raiWord} · 20일 전 ${pm(R.prev20, 2, '')} · 전체 기간 중 하위 ${R.pct}%</small></div>
    <div class="grid2" style="margin:10px 0 0"><div><table class="tbl"><thead><tr><th>쌍</th><th>z-점수</th></tr></thead><tbody>${zs.map(([k, v]) => `<tr><td>${esc(k)}</td><td>${MU.zbar(v)}<b class="${MU.sgn(v)}">${pm(v, 2, '')}</b></td></tr>`).join('')}</tbody></table></div>
    <div><div class="ch"></div></div></div>
    <div class="read">지금 읽으면 — <b>${pm(R.last, 2, '')}</b> (${raiWord}). ${zs.length}개 쌍 중 <b>${neg}개</b>가 −1 아래다 — ${neg >= zs.length * 0.6 ? '주식·크레딧·환율·변동성이 <b>한꺼번에</b> 위험 회피 쪽이다(특정 업종 문제가 아니라 시장 전체의 위험 축소)' : '일부 쌍만 약하다(시장 전체의 위험 축소는 아니다)'}.
      ${R.last <= R.lo ? `과거 하위 5% 선(<b>${pm(R.lo, 2, '')}</b>) 아래다.` : `과거 하위 5% 선은 ${pm(R.lo, 2, '')}, 상위 5% 선은 ${pm(R.hi, 2, '')}.`}
      가장 약한 쌍: ${zs.slice(0, 3).map(([k, v]) => `${esc(k)} ${pm(v, 1, '')}`).join(', ')}. 가장 강한 쌍: ${zs.slice(-2).reverse().map(([k, v]) => `${esc(k)} ${pm(v, 1, '')}`).join(', ')}.</div>
    <h3 class="sec-title" style="margin-top:16px">과거 근거 — 지수가 극단에 간 뒤 S&P500</h3>
    ${MU.evidence([['하위 5% 선 아래 (극단적 위험 회피)', R.ev_lo], ['−1 아래', R.ev_m1], ['상위 5% 선 위 (극단적 위험선호)', R.ev_hi]], 'S&P500')}
    <div class="read">지금 읽으면 — 극단적 위험 회피 뒤에는 네 기간 중 <b>${beat(R.ev_lo)}개</b>에서 아무 날보다 좋았다${beat(R.ev_lo) >= 3 ? ' → <b>이 사이트의 신호 가운데 과거에 잘 맞은 편</b>이다. 다만 미국 지수 기준이고 횟수가 ' + R.ev_lo.n + '번뿐이다' : ' → 뚜렷한 우위는 없었다'}.
      극단적 위험선호 뒤에도 ${beat(R.ev_hi)}개에서 아무 날보다 좋았다${beat(R.ev_hi) >= 3 ? ' — 위험선호가 높다는 것만으로는 파는 신호가 아니었다' : ''}.</div>
    <p class="note">쓰임(비중): 지수가 깊은 음수에서 <b>돌아서 올라올 때</b> 주식 비중을 되돌리는 근거로 쓴다. '하위 5% 선'은 그날까지의 값만으로 정한다(미래 값을 쓰지 않음). 골드만의 원래 지표는 쌍이 더 많고 가중 방식이 달라 숫자가 같지 않다.</p>`;
  MChart.line($('rai').querySelector('.ch'), { series: [ser(R.series, '위험선호 지수'), ser(R.spx, 'S&P500', { axis: 'r', color: 'var(--c5)', width: 1.2 })], hlines: [{ y: 0, label: '0' }, { y: R.lo, label: '하위 5%' }], dec: 2, decR: 0, height: 300 });

  // 글로벌 폭
  const cls = c => c.a200 && c.a50 ? 'a' : !c.a200 && !c.a50 ? 'b' : 'h';
  const above = G.ctry.filter(c => c.a200);
  $('gb').innerHTML = `<h2>글로벌 폭 규칙 (BofA식) ${use('타이밍,섹터')} ${asof(G.date)}</h2>
    <p class="sub">국가 ETF ${G.n}개 중 50일선과 200일선 <b>둘 다 아래</b>인 나라의 비율. BofA 규칙: 88%를 넘으면 '팔 만큼 팔았다'는 역발상 매수 신호.</p>
    <div class="stat"><div><span>50·200일선 모두 아래</span><b>${G.both}%</b></div><div><span>200일선 위</span><b>${G.a200}%</b> <span>20일 전 ${G.a200_prev20}%</span></div><div><span>신호 기준</span><b>88%</b></div></div>
    <div class="read">지금 읽으면 — 둘 다 아래 <b>${G.both}%</b>: ${G.both >= 88 ? '<b>88%를 넘었다 — 규칙상 매수 신호</b>' : G.both >= 70 ? `신호(88%)까지 ${88 - G.both}%p 남았다. 대부분의 나라가 이미 추세 아래다` : '신호와 거리가 멀다'}.
      200일선 위에 남은 나라는 <b>${above.length}곳</b>${above.length ? ` (${above.slice(0, 8).map(c => esc(c.name)).join(', ')}${above.length > 8 ? ' …' : ''})` : ''} — 20일 전 ${G.a200_prev20}%에서 ${G.a200}%로 ${G.a200 < G.a200_prev20 ? '줄었다' : '늘었다'}.</div>
    <div class="ctry">${G.ctry.map(c => `<span class="${cls(c)}" title="200일선 대비 ${pm(c.d200)} · 1개월 ${pm(c.m1)} · 3개월 ${pm(c.m3)}">${esc(c.name)} ${pm(c.d200, 0)}</span>`).join('')}</div>
    <p class="small muted">칩의 숫자 = 200일선 대비 %. 붉은 칩 = 두 선 모두 위, 주황 = 하나만 위, 푸른 칩 = 모두 아래. 한국 ETF(EWY)도 여기 들어 있다.</p>
    <div class="ch narrow"></div>
    <h3 class="sec-title" style="margin-top:16px">과거 근거 — 신호 뒤 전세계 주식(ACWI)</h3>
    ${MU.evidence([['둘 다 아래 88% 이상 (BofA 규칙)', G.ev88], ['둘 다 아래 70% 이상', G.ev70]], '전세계 주식 ETF(ACWI)')}
    <div class="read">지금 읽으면 — 88% 신호 뒤에는 네 기간 중 <b>${beat(G.ev88)}개</b>에서만 아무 날보다 좋았다 → ${beat(G.ev88) >= 3 ? '과거에는 잘 맞았다' : `<b>1~6개월은 아무 날과 비슷했고 12개월 뒤에야 차이가 났다</b>(${pm(G.ev88['12개월'].mean)} vs ${pm(G.ev88['12개월'].base)}). 단기 반등 신호가 아니라 '1년을 보고 나눠 사기 시작하는 자리'로 읽는다`}.</div>
    <p class="note">BofA 는 현지통화 MSCI 지수를 쓴다. 여기는 미국 상장 국가 ETF(달러 기준)라 달러가 강할 때 신호가 더 일찍 켜진다. 쓰임(섹터): 칩에서 200일선 위에 남은 나라가 지금 자금이 머무는 곳이다.</p>`;
  MChart.line($('gb').querySelector('.ch'), { series: [ser(G.series, '둘 다 아래인 나라 (%)'), ser(G.acwi, '전세계 주식 ETF', { axis: 'r', color: 'var(--c5)', width: 1.2 })], hlines: [{ y: 88, label: '88 매수 신호' }], dec: 0, decR: 0, height: 240 });

  // 패닉/유포리아식
  const meter = v => `<div class="meter"><i style="left:${v}%"></i><span style="left:12%">패닉</span><span style="left:50%">중간</span><span style="left:88%">유포리아</span></div>`;
  $('pe').innerHTML = `<h2>패닉/유포리아식 지수 (씨티식) ${use('타이밍')} ${asof(P.date)}</h2>
    <p class="sub">씨티 모델의 구성요소 9개 중 무료 자료로 되는 ${Object.keys(P.parts).length}개가 각각 최근 3년 중 몇 %에 있는지(100 = 유포리아 쪽)를 평균. 0~100.</p>
    <div class="grid2" style="margin:0"><div><div class="big">${P.last}<small> / 100 · ${peWord} · 20일 전 ${P.prev20}</small></div>${meter(P.last)}${MU.parts(P.parts)}
      <p class="small muted" style="margin-top:8px">빠진 것: 강세 설문(AAII — 자동 요청이 막혀 있음) · 풋/콜 프리미엄 비율(무료 과거 자료 없음) · 풋콜 비율(CBOE 값을 쌓는 중, ${P.pc_n}일치 — 250일이 되면 자동으로 들어간다).</p></div>
      <div><div class="ch"></div></div></div>
    <div class="read">지금 읽으면 — <b>${P.last} (${peWord})</b>, 20일 전 ${P.prev20}에서 ${P.last < P.prev20 ? '내려왔다' : '올라왔다'}. ${P.last <= 20 ? '<b>패닉 구간</b> — 씨티 모델에서는 1년 뒤 수익률이 높았던 자리' : P.last >= 80 ? '<b>유포리아 구간</b>' : '극단이 아니다 — 이 지수는 20 아래·80 위에서만 본다'}.
      구성요소가 엇갈린다 — 유포리아 쪽(80 이상): ${Object.entries(P.parts).filter(([, v]) => v >= 80).map(([k]) => esc(k)).join(', ') || '없음'} / 패닉 쪽(20 이하): ${Object.entries(P.parts).filter(([, v]) => v <= 20).map(([k]) => esc(k)).join(', ') || '없음'}.</div>
    <h3 class="sec-title" style="margin-top:16px">과거 근거 — 지수 극단 뒤 S&P500 (${esc(P.since.slice(0, 4))}년~)</h3>
    ${MU.evidence([['20 이하 (패닉)', P.ev_panic], ['80 이상 (유포리아)', P.ev_eu]], 'S&P500')}
    <div class="read">지금 읽으면 — 패닉 신호는 <b>${P.ev_panic.n}번</b>뿐이라 통계로 말하기 어렵다(표본이 너무 적다). 유포리아 뒤에는 ${beat(P.ev_eu)}개 기간에서 아무 날보다 좋았다${beat(P.ev_eu) >= 3 ? ' — <b>유포리아라는 이유로 팔았으면 손해였다</b>' : ''}.</div>
    <p class="note">원자재·휘발유가 오르면 유포리아 쪽으로 넣은 것은 <b>우리 가정</b>이다(씨티는 항목만 공개하고 부호·가중치는 공개하지 않는다). 신용융자는 분기 자료, 공매도 잔고는 월 2회 자료라 느리게 움직인다. 자료가 2015년부터라 과거 근거도 그 뒤만 본다.</p>`;
  MChart.line($('pe').querySelector('.ch'), { series: [ser(P.series, '패닉/유포리아식 지수'), ser(P.spx, 'S&P500', { axis: 'r', color: 'var(--c5)', width: 1.2 })], hlines: [{ y: 20, label: '20 패닉' }, { y: 80, label: '80 유포리아' }], dec: 0, decR: 0, height: 300 });
})();
