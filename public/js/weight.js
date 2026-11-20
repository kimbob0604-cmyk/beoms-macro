// 비중: 국면(유동성·크레딧 축) · 내 비중표 · 신용 스프레드 · 유동성 · 금리 · 자금시장 · 한국 금리 · 밸류에이션 · 경기
(async () => {
  MU.shell('weight');
  const { num, use, asof, esc, pm } = MU;
  let D;
  try { D = await MU.get('weight.json'); } catch (e) { return MU.fail(e); }
  MU.built(D.built);
  const $ = id => document.getElementById(id);
  const R = D.regime, C = D.credit, L = D.liq, V = D.val;
  const ser = (o, name, x = {}) => ({ name, d: o.d, v: o.v, ...x });
  const row = (r, o = {}) => `<tr class="click" data-k="${r.k.replace(/:/g, '_')}"><td>${esc(o.name || r.name)}</td><td class="b">${num(r.last, o.dec ?? 2)}${esc(o.unit ?? r.unit)}</td><td>${o.bp ? pm(r.chg == null ? null : r.chg * 100, 0, 'bp') : pm(r.chg, o.cdec ?? 2, o.cunit ?? '')}</td><td>${r.pct ?? '–'}${MU.gauge(r.pct, o.bad)}</td><td class="muted small">${esc(r.date.slice(5))}</td></tr>`;
  const table = (rows, chgHead = '20일 변화') => `<table class="tbl"><thead><tr><th>지표</th><th>현재</th><th>${chgHead}</th><th>3년 백분위</th><th>기준일</th></tr></thead><tbody>${rows}</tbody></table>`;

  // 국면
  $('regime').innerHTML = `<h2>국면 — 유동성·크레딧 축 ${use('비중')}</h2><p class="sub">50 아래면 돈줄이 조이는 쪽. 오늘 탭의 국면 표에서 가로축으로 쓴다.</p>
    <div class="big">${R.liq}<small> / 100 · 한 달 전 ${R.liq_prev}</small></div>${MU.parts(R.liq_parts, 'lo')}
    <div class="read">지금 읽으면 — 위험선호 <b>${R.risk}</b>, 유동성·크레딧 <b>${R.liq}</b> → <b>${esc(R.cell)}</b>${R.cell !== R.cell_prev ? ` (한 달 전 ${esc(R.cell_prev)})` : ' (한 달 전과 같은 칸)'}. 점수가 낮은 항목이 지금 발목을 잡는 쪽이다.</div>
    <p class="note">각 항목은 최근 2년(주간 자료는 5년) 중 지금이 몇 %에 있는지다. '(역)'은 오를수록 나쁜 지표라 뒤집어 계산했다는 뜻.</p>`;

  // 내 비중표 — 사이트는 정해 주지 않는다. 내가 정한 값만 보여 준다.
  const CELLS = ['순항', '과열·균열', '눌림', '위기'];
  let mine = {};
  try { mine = JSON.parse(localStorage.getItem('macro.weights') || '{}'); } catch (e) {}
  const drawMine = () => {
    const cur = mine[R.cell];
    $('mine').innerHTML = `<h2>내 비중표 ${use('비중')}</h2><p class="sub">국면별로 내가 가져갈 주식 비중을 미리 적어 둔다. 사이트는 값을 정해 주지 않는다(이 브라우저에만 저장).</p>
      <table class="tbl"><thead><tr><th>국면</th><th class="l">뜻</th><th>내 주식 비중 (%)</th></tr></thead><tbody>${CELLS.map(c => `<tr class="${c === R.cell ? 'sel' : ''}"><td class="b">${c}${c === R.cell ? ' ← 지금' : ''}</td>
        <td class="l small muted">${{ '순항': '위험선호 높음 · 돈줄 양호', '과열·균열': '위험선호 높음 · 돈줄 악화', '눌림': '위험선호 낮음 · 돈줄 양호', '위기': '위험선호 낮음 · 돈줄 악화' }[c]}</td>
        <td><input type="text" inputmode="numeric" data-c="${c}" value="${mine[c] ?? ''}" placeholder="–" style="width:70px;text-align:right"></td></tr>`).join('')}</tbody></table>
      <div class="read">${cur != null && cur !== '' ? `지금 국면은 <b>${esc(R.cell)}</b> — 내가 정해 둔 주식 비중은 <b>${esc(cur)}%</b>.` : `지금 국면은 <b>${esc(R.cell)}</b>. 아직 이 칸의 비중을 적지 않았다.`}</div>
      <p class="note">국면이 바뀌는 날 무엇을 할지 미리 정해 두는 용도다. 숫자를 바꾸면 바로 저장된다.</p>`;
    $('mine').querySelectorAll('input').forEach(i => i.onchange = () => { mine[i.dataset.c] = i.value.trim(); try { localStorage.setItem('macro.weights', JSON.stringify(mine)); } catch (e) {} drawMine(); });
  };
  drawMine();

  // 신용 스프레드
  const hy = C.rows[0], ccc = C.rows[1];
  $('credit').innerHTML = `<h2>미국 신용 스프레드 ${use('비중')} ${asof(hy.date)}</h2><p class="sub">회사채 금리 − 국채 금리. 벌어지면 시장이 부도 위험을 크게 본다는 뜻이다.</p>
    ${table(C.rows.map(r => row(r, { bp: true, bad: 'hi' })).join(''))}
    <div class="read">지금 읽으면 — 하이일드 <b>${num(hy.last)}%p</b>, 20일 동안 <b>${pm(C.hy20, 0, 'bp')}</b> ${C.hy20 >= 50 ? '→ <b>경보</b>(20일 +50bp 이상): 주식 비중을 줄이는 쪽의 신호' : C.hy20 <= -30 ? '→ 빠르게 좁혀지는 중: 위험선호 회복' : '→ 경보 기준(20일 +50bp)에는 못 미친다'}.
      수준은 최근 3년 중 상위 ${100 - hy.pct}%${ccc.pct >= 90 ? `, 가장 약한 등급(CCC)은 상위 ${100 - ccc.pct}%로 <b>아래 등급부터 벌어지는 중</b>` : ''}.</div><div class="ch"></div>`;
  MChart.line($('credit').querySelector('.ch'), { series: [ser(C.series.hy_oas, '하이일드'), ser(C.series.bbb_oas, 'BBB'), ser(C.series.ccc_oas, 'CCC', { axis: 'r', color: 'var(--c6)' })], dec: 2, decR: 1, height: 220 });

  // 유동성
  $('liq').innerHTML = `<h2>연준 순유동성 · 금융여건 ${use('비중')} ${asof(L.date, 12)}</h2><p class="sub">순유동성 = 연준 총자산 − 재무부 계좌(TGA) − 역레포. 시장에 풀려 있는 달러의 양을 어림한 값.</p>
    <div class="stat"><div><span>순유동성</span><b>${num(L.netliq, 0)}</b> 십억달러</div><div><span>13주 변화</span><b class="${MU.sgn(L.netliq_13w)}">${pm(L.netliq_13w, 0, '')}</b></div><div><span>금융여건 NFCI</span><b>${num(L.nfci, 2)}</b></div></div>
    <p class="small muted">= 총자산 ${num(L.walcl, 0)} − TGA ${num(L.tga, 0)} − 역레포 ${num(L.rrp, 1)} (십억달러)</p>
    <div class="read">지금 읽으면 — 순유동성이 13주 동안 <b>${L.netliq_13w >= 0 ? '늘었다' : '줄었다'}</b>(${pm(L.netliq_13w, 0, '')}). ${L.netliq_13w >= 0 ? '돈줄 쪽에서는 주식에 우호적' : '돈줄이 조이는 쪽 — 밸류에이션이 높은 주식에 부담'}.
      NFCI <b>${num(L.nfci, 2)}</b>: ${L.nfci < 0 ? '0 아래 = 금융여건이 평균보다 느슨' : '0 위 = 금융여건이 평균보다 빡빡'}.</div><div class="ch"></div>`;
  MChart.line($('liq').querySelector('.ch'), { from: L.series.netliq.d[0], series: [ser(L.series.netliq, '순유동성 (십억달러)'), ser(L.series.ndx, '나스닥', { axis: 'r', color: 'var(--c5)', width: 1.2 })], dec: 0, decR: 0, height: 220 });

  // 금리
  const rr = Object.fromEntries(D.rates.rows.map(r => [r.k, r]));
  $('rates').innerHTML = `<h2>미국 금리 ${use('비중')} ${asof(rr['fred:us10y'].date)}</h2><p class="sub">10년 금리 = 실질금리 + 기대인플레. 실질금리가 오르면 성장주 할인율이 올라간다.</p>
    ${table(D.rates.rows.map(r => row(r, { bp: true, name: r.name.replace(' (FRED)', '').replace(' (킴-라이트)', '') })).join(''))}
    <div class="read">지금 읽으면 — 10년 <b>${num(rr['fred:us10y'].last)}%</b> = 실질 <b>${num(rr['fred:real10y'].last)}%</b> + 기대인플레 <b>${num(rr['fred:bei10y'].last)}%</b>. 20일 동안 실질금리 ${pm(rr['fred:real10y'].chg * 100, 0, 'bp')}, 기대인플레 ${pm(rr['fred:bei10y'].chg * 100, 0, 'bp')} →
      ${rr['fred:real10y'].chg > 0 && rr['fred:bei10y'].chg <= 0 ? '물가 기대는 내리는데 실질금리가 오른다: <b>긴축 쪽 움직임</b>(주식에 가장 불리한 조합)' : rr['fred:real10y'].chg > 0 ? '실질금리·물가 기대가 같이 오른다: 경기 기대가 섞인 상승' : rr['fred:bei10y'].chg > 0 ? '실질금리는 내리고 물가 기대가 오른다: 완화 쪽 움직임' : '둘 다 내린다: 경기 둔화 걱정 쪽'}.
      10년−2년 <b>${num(rr['fred:t10y2y'].last)}%p</b>${rr['fred:t10y2y'].last < 0 ? ' (역전)' : ''}.</div><div class="ch"></div>`;
  const RS = D.rates.series;
  MChart.line($('rates').querySelector('.ch'), { series: [ser(RS.us10y, '10년'), ser(RS.us2y, '2년'), ser(RS.real10y, '실질 10년'), ser(RS.t10y2y, '10년−2년', { axis: 'r', color: 'var(--c5)', width: 1.2 })], dec: 2, decR: 2, height: 220 });

  // 자금시장
  $('fund').innerHTML = `<h2>자금시장 스트레스 ${use('비중')}</h2><p class="sub">단기 자금이 막히는지 보는 두 가지 차이. 평소에는 0 근처, 튀면 경고.</p>
    <div class="stat"><div><span>SOFR − 지준부리(IORB)</span><b>${pm(L.sofr_iorb * 100, 0, 'bp')}</b></div><div><span>CP 3개월 − 국채 3개월</span><b>${pm(L.cp_spread * 100, 0, 'bp')}</b></div></div>
    <div class="read">지금 읽으면 — SOFR−IORB <b>${pm(L.sofr_iorb * 100, 0, 'bp')}</b>: ${L.sofr_iorb >= 0.1 ? '<b>+10bp 이상</b>, 레포 시장에 돈이 모자란다(지준 부족 신호)' : L.sofr_iorb > 0 ? '0 위지만 10bp 미만 — 지준이 넉넉하진 않다' : '0 아래, 자금 여유'}.
      CP 스프레드 <b>${pm(L.cp_spread * 100, 0, 'bp')}</b>: ${L.cp_spread >= 0.5 ? '<b>50bp 이상</b>, 기업 단기 조달이 어려워지는 중' : '50bp 아래, 정상 범위'}.</div><div class="ch"></div>
    <p class="note">분기 말·세금 납부일에는 하루 이틀 튀는 일이 흔하다. 며칠 이어질 때만 신호로 본다.</p>`;
  MChart.line($('fund').querySelector('.ch'), { series: [ser(L.series.sofr_iorb, 'SOFR − IORB (%p)'), ser(L.series.cp_spread, 'CP − 국채 3개월 (%p)')], hlines: [{ y: 0, label: '0' }], dec: 2, height: 220 });

  // 한국 금리·크레딧
  const kr = Object.fromEntries(D.kr.rows.map(r => [r.k, r]));
  $('kr').innerHTML = `<h2>한국 금리 · 회사채 스프레드 ${use('비중')} ${asof(kr['kr:ktb3y'].date)}</h2><p class="sub">국고채와 회사채(3년) 금리. 스프레드는 회사채 − 국고 3년.</p>
    ${table(D.kr.rows.map(r => row(r, r.unit === 'bp' ? { dec: 1, cdec: 1, cunit: 'bp', bad: r.k.includes('spread') ? 'hi' : '' } : { dec: 3, bp: true })).join(''))}
    <div class="read">지금 읽으면 — 회사채 AA- 스프레드 <b>${num(kr['kr:corp_spread'].last, 1)}bp</b> (20일 ${pm(kr['kr:corp_spread'].chg, 1, 'bp')}, 3년 중 상위 ${100 - kr['kr:corp_spread'].pct}%):
      ${kr['kr:corp_spread'].chg >= 10 ? '<b>빠르게 벌어지는 중</b> — 국내 신용 경색 신호' : kr['kr:corp_spread'].chg <= -5 ? '좁혀지는 중 — 국내 자금 사정 개선' : '큰 변화 없음'}. 국고 3년 ${num(kr['kr:ktb3y'].last, 2)}%, 10년−3년 ${num(kr['kr:ktb_curve'].last, 1)}bp.</div><div class="ch"></div>`;
  MChart.line($('kr').querySelector('.ch'), { series: [ser(D.kr.series.ktb3y, '국고 3년 (%)'), ser(D.kr.series.ktb10y, '국고 10년 (%)'), ser(D.kr.series.corp_spread, 'AA- 스프레드 (bp)', { axis: 'r', color: 'var(--c6)' })], dec: 2, decR: 0, height: 220 });

  // 밸류에이션 — 가정을 바꾸면 다시 계산
  const drawVal = (pe, real) => {
    const ey = 100 / pe, erp = ey - real;
    $('val').innerHTML = `<h2>주식위험프리미엄 (S&P500) ${use('비중')} ${asof(V.date)}</h2><p class="sub">주식이 채권보다 얼마나 더 주는가. 숫자를 바꾸면 다시 계산한다.</p>
      <div class="calc">이익수익률 <b>${num(ey)}%</b> <span class="muted">(= 1 ÷ PER <input type="text" id="v-pe" value="${pe}">배)</span> − 실질금리 <input type="text" id="v-real" value="${real}">% = <b class="${erp < 1 ? 'down' : ''}">${num(erp)}%p</b></div>
      <div class="read">지금 읽으면 — 주식위험프리미엄 <b>${num(erp)}%p</b>: ${erp < 0 ? '<b>0 아래</b>, 주식이 물가연동국채보다 덜 준다' : erp < 1.5 ? '<b>얇다</b>(1.5%p 미만) — 금리가 오르면 주가가 크게 흔들리는 구간' : erp < 3 ? '보통 수준' : '두텁다 — 주식이 채권보다 싸다'}.
        실러 PER(CAPE) <b>${num(V.cape, 1)}배</b>.</div>
      <div class="stat"><div><span>미국 증권사 신용융자 (분기)</span><b>${num(V.margin_q, 0)}</b> 십억달러 <span>1년 전보다 ${pm(V.margin_yoy)} · ${esc(V.margin_date.slice(0, 7))}</span></div>
        <div><span>소매 MMF 잔고</span><b>${num(V.mmf, 0)}</b> 십억달러 <span>${esc(V.mmf_date)} 기준</span></div></div>
      <p class="note">PER·CAPE 는 multpl.com 의 오늘 값(${V.n}일치 쌓임 — 추이 차트는 자료가 쌓이면 추가). 실질금리는 물가연동국채 10년. 미국 신용융자는 FINRA 월간 자료를 직접 못 받아 연준 분기 통계로 대신한다.</p>`;
    const f = () => { const a = parseFloat($('v-pe').value), b = parseFloat($('v-real').value); if (a > 0 && !isNaN(b)) drawVal(a, b); };
    $('v-pe').onchange = f; $('v-real').onchange = f;
  };
  drawVal(V.pe, V.real);

  // 경기
  const LATE = { '매일': 5, '주간': 12, '월간': 100, '분기': 250 };
  $('eco').innerHTML = `<h2>경기 ${use('비중')}</h2><p class="sub">침체 쪽으로 가는지만 본다. 발표 주기가 길어 날짜를 같이 본다.</p>
    <table class="tbl"><thead><tr><th>지표</th><th>현재</th><th>직전</th><th>변화</th><th class="l">읽는 법</th><th>주기</th><th>기준</th></tr></thead><tbody>${D.eco.map(e => `<tr><td>${esc(e.name)}</td><td class="b">${num(e.last, e.dec)}</td><td>${num(e.prev, e.dec)}</td><td>${pm(e.last - e.prev, e.dec, '')}</td><td class="l small muted">${esc(e.note)}</td><td class="muted small">${esc(e.freq)}</td><td>${asof(e.date, LATE[e.freq] || 5)}</td></tr>`).join('')}</tbody></table>`;

  document.querySelectorAll('tr.click').forEach(tr => tr.onclick = () => { location.href = `pair.html?a=px_spx&b=${tr.dataset.k}`; });
})();
