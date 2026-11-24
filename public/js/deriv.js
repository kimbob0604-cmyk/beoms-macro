// 파생·평단: 선물 베이시스 · 대차잔고 · 종목별 공매도 평단 · VWAP·주체별 평단 · KOSPI200 옵션 · 미국 옵션·공매도 잔고 · 롱숏 페어 · 롱숏 쏠림 · 통화 스왑
(async () => {
  MU.shell('deriv');
  const { num, use, asof, esc, pm } = MU;
  let D;
  try { D = await MU.get('deriv.json'); } catch (e) { return MU.fail(e); }
  MU.built(D.built);
  const $ = id => document.getElementById(id);
  const ser = (o, name, x = {}) => ({ name, d: o.d, v: o.v, ...x });
  const HZ = ['1개월', '3개월', '6개월', '12개월'];
  const beat = e => HZ.filter(h => e[h].mean != null && e[h].mean > e[h].base).length;
  const none = (id, title, why) => { $(id).innerHTML = `<h2>${title}</h2><p class="muted">${why}</p>`; };
  const gapc = v => v == null ? '<span class="muted">–</span>' : `<span class="${MU.sgn(v)}">${pm(v)}</span>`;
  const won = v => v == null ? '–' : num(v, 0);

  // ── 선물 베이시스 ──
  const B = D.basis;
  if (B) {
    const ff = B.fut_flow.frgn;
    $('basis').innerHTML = `<h2>KOSPI200 선물 베이시스 ${use('흐름')} ${asof(B.date)}</h2><p class="sub">베이시스 = 선물 − 현물. 보통은 선물이 조금 비싸다(이자만큼). 선물이 더 싸지면(백워데이션) 선물을 파는 쪽이 세다는 뜻.</p>
      <div class="stat"><div><span>선물(근월)</span><b>${num(B.fut)}</b></div><div><span>현물</span><b>${num(B.spot)}</b></div><div><span>베이시스</span><b class="${MU.sgn(B.basis)}">${pm(B.basis, 2, 'pt')}</b> <span>${pm(B.bp, 2)}</span></div></div>
      <div class="read">지금 읽으면 — 베이시스 <b>${pm(B.basis, 2, 'pt')}</b>: ${B.basis < 0 ? `<b>백워데이션</b>(최근 5일 중 ${B.neg5}일). 헤지·매도용 선물 물량이 많아 선물이 눌려 있다 → 싼 선물을 사고 현물을 파는 차익거래가 붙어 <b>프로그램 매도</b>가 나오기 쉬운 구간. 베이시스가 플러스로 돌아서면 그 매물이 멎는다` : '콘탱고(정상) — 선물 쪽 매도 압력이 크지 않다'}.
        선물 가격이 말하는 금리는 연 <b>${num(B.carry)}%</b> (CD 91일 ${num(B.cd)}%) — ${B.carry != null && B.carry < B.cd - 1 ? '금리보다 한참 낮다 = 선물이 싸게 거래된다' : '금리와 비슷한 수준'}.
        ${ff ? `외국인 선물 순매수: 최근일 <b>${pm(ff.last, 0, '계약')}</b>, 5일 합 ${pm(ff.sum5, 0, '계약')} (${ff.n}일치).` : '외국인 선물 순매수는 과거 자료를 내주는 곳이 없어 장 마감 뒤 하루 한 점씩 쌓는다(아직 0일치).'}</div>
      <div class="ch"></div>
      <p class="note">미결제 약정 ${num(B.oi, 1)}천 계약(20일 ${pm(B.oi_d20)}). 과거 ${B.n}일 중 베이시스(%)는 하위 ${B.pct}% 수준. 배당락이 낀 월물은 배당만큼 선물이 싸게 나온다(12월 말 배당은 3월물에 반영).</p>
      ${B.ev_back.n >= 3 ? `<h3 class="sec-title">과거 근거 — 5일 내내 백워데이션이던 날 뒤 KOSPI (${esc(B.ev_back.since.slice(0, 7))}~)</h3>${MU.evidence([['5일 연속 백워데이션', B.ev_back]])}` : ''}`;
    MChart.line($('basis').querySelector('.ch'), { series: [ser(B.series, '베이시스 5일 평균 (%)'), ser(B.k200, 'KOSPI200', { axis: 'r', color: 'var(--c5)', width: 1.2 })], hlines: [{ y: 0, label: '0' }], dec: 2, decR: 0, height: 220 });
  } else none('basis', 'KOSPI200 선물 베이시스', '선물 자료를 받는 중이다 — <code>python3 collect_deriv.py krx</code> 가 끝나면 나온다.');

  // ── 대차잔고 ──
  const L = D.loan;
  if (L) {
    $('loan').innerHTML = `<h2>대차잔고 ${use('타이밍,흐름')} ${asof(L.date)}</h2><p class="sub">빌려 간 뒤 아직 안 갚은 주식. 공매도를 하려면 먼저 빌려야 하므로 공매도의 '재료'다. 금액은 주가에 따라 움직여서 <b>주수</b>로 본다.</p>
      <div class="stat"><div><span>잔고 금액</span><b>${num(L.amt, 1)}</b> 조원</div><div><span>잔고 주수</span><b>${num(L.sh)}</b> 억 주</div><div><span>주수 20일 변화</span><b class="${MU.sgn(L.sh_d20)}">${pm(L.sh_d20)}</b></div></div>
      <p class="small muted">KOSPI ${num(L.kospi, 1)}조 · KOSDAQ ${num(L.kosdaq, 1)}조 · 최근 5일 신규 − 상환 ${pm(L.net5, 0, '만 주')} · 20일 ${pm(L.net20, 0, '만 주')} · 3년 중 상위 ${100 - L.pct}%</p>
      <div class="read">지금 읽으면 — 주수 20일 <b>${pm(L.sh_d20)}</b>: ${L.sh_d20 >= 5 ? '<b>빌려 가는 주식이 빠르게 늘고 있다</b> — 공매도·헤지 물량이 쌓이는 중. 반등하면 이 물량이 되사야 하는 숏커버 재료가 되지만, 지금은 매도 쪽 탄약이다' : L.sh_d20 <= -5 ? '<b>빌린 주식을 빠르게 갚는 중(상환)</b> — 숏커버가 진행됐다' : '큰 변화 없음'}.
        ${L.pct >= 95 ? '잔고 주수가 3년 중 가장 많은 수준이다.' : ''} 금액은 20일 ${pm(L.amt_d20)}${L.amt_d20 < 0 && L.sh_d20 > 0 ? ' — 주수는 늘었는데 금액이 준 것은 주가가 내렸기 때문' : ''}.</div><div class="ch"></div>
      <h3 class="sec-title">과거 근거 — 대차잔고 급변 뒤 KOSPI (최근 3년)</h3>${MU.evidence([['주수 20일 −5% 이하 (상환)', L.ev_cover], ['주수 20일 +5% 이상 (증가)', L.ev_build]])}
      <p class="note">자료가 3년치(${L.n}일)뿐이고 이 기간 KOSPI 가 크게 올라 '아무 날' 기준이 높다 — <b>참고만</b> 한다. 대차잔고에는 공매도 말고도 헤지·결제용으로 빌린 주식이 섞여 있다.</p>`;
    MChart.line($('loan').querySelector('.ch'), { series: [ser(L.series, '대차잔고 (억 주)'), ser(L.kospi_s, 'KOSPI', { axis: 'r', color: 'var(--c5)', width: 1.2 })], dec: 1, decR: 0, height: 220 });
  } else none('loan', '대차잔고', '자료 없음');

  // ── 종목별 공매도 평단 ──
  const SH = D.shorts || [];
  if (SH.length) {
    const hurt = SH.filter(x => x.g20 > 0), top = SH.slice(0, 3);
    $('shorts').innerHTML = `<h2>종목별 공매도 — 비중과 평균 단가 ${use('타이밍,섹터')} ${asof(SH[0].date)}</h2>
      <p class="sub">시총 상위와 페어 종목 ${SH.length}개. 공매도 평단 = 그 기간 공매도 대금 ÷ 공매도 수량. <b>현재가가 평단 위</b>면 그 기간에 판 숏이 손실 구간이다(더 오르면 되사야 한다).</p>
      <div class="read">지금 읽으면 — ${SH.length}개 중 <b>${hurt.length}개</b>에서 현재가가 20일 공매도 평단 위다${hurt.length ? ` (${hurt.sort((a, b) => b.g20 - a.g20).slice(0, 5).map(x => `${esc(x.name)} ${pm(x.g20)}`).join(', ')})` : ''} — ${hurt.length <= SH.length * 0.25 ? '<b>최근 숏의 대부분이 이익 구간</b>이라 숏커버가 급할 이유가 없다. 평단을 되찾는 종목부터 숏커버가 붙는다' : hurt.length >= SH.length * 0.6 ? '<b>최근 숏의 대부분이 손실 구간</b> — 숏커버가 주가를 미는 구간' : '종목별로 갈린다'}.
        공매도 비중이 가장 높은 종목: ${top.map(x => `${esc(x.name)} ${num(x.r5, 1)}%`).join(', ')}.</div>
      <div class="scroll-x" style="max-height:520px;overflow-y:auto"><table class="tbl"><thead><tr><th>종목</th><th>현재가</th><th>공매도 비중 5일</th><th>20일</th><th>60일</th><th>20일 공매도 평단</th><th>현재가 − 평단</th><th>60일 평단</th><th>현재가 − 평단</th><th>20일 공매도 대금</th><th>비중 60일 추이</th></tr></thead><tbody>
      ${SH.map(x => `<tr><td>${esc(x.name)}</td><td>${won(x.px)}</td><td class="b">${num(x.r5, 1)}%</td><td>${num(x.r20, 1)}%</td><td>${num(x.r60, 1)}%</td><td>${won(x.a20)}</td><td>${gapc(x.g20)}</td><td>${won(x.a60)}</td><td>${gapc(x.g60)}</td><td>${won(x.amt20)}억</td><td>${MU.spark(x.spark)}</td></tr>`).join('')}</tbody></table></div>
      <p class="note">공매도 비중 = 공매도 수량 ÷ 거래량. '현재가 − 평단'이 빨강(+)이면 숏이 물린 상태, 파랑(−)이면 숏이 이익. 비중이 높은 순으로 정렬. 잔고(아직 안 갚은 공매도)는 이 API 에 없어 거래 기준이다.</p>`;
  } else none('shorts', '종목별 공매도', '자료 없음');

  // ── VWAP · 주체별 평단 ──
  const VW = D.vwap || [];
  if (VW.length) {
    let sel = VW[0].code;
    const who = (x, k) => x[k] ? `<td class="${MU.sgn(x[k].net)}">${pm(x[k].net / 1e4, 2, '조')}</td><td>${gapc(x[k].buy_gap)}</td>` : '<td class="muted">–</td><td class="muted">–</td>';
    const draw = () => {
      const x = VW.find(v => v.code === sel), below = VW.filter(v => v.anc.ytd.gap < 0).length;
      $('vwap').innerHTML = `<h2>VWAP · 누적 VWAP · 주체별 평단 ${use('타이밍,섹터')} ${asof(VW[0].date)}</h2>
        <p class="sub">VWAP = 거래대금 ÷ 거래량 = 그 기간에 산 사람들의 평균 단가. 기준일부터 누적하면 '그날 이후 산 사람의 평단'이 된다. 현재가가 그 위면 그들이 이익, 아래면 손실(본전 매물대).</p>
        <div class="read">지금 읽으면 — 시총 상위 ${VW.length}개 중 <b>${below}개</b>가 연초 이후 누적 VWAP 아래다 = ${below >= VW.length * 0.6 ? '<b>올해 산 사람의 평균이 손실</b>. 반등하면 이 평단이 본전 매물대(저항)가 된다' : below <= VW.length * 0.3 ? '올해 산 사람 대부분이 이익 — 눌려도 받치는 가격대가 아래에 있다' : '종목별로 갈린다'}.
          <b>${esc(x.name)}</b>: 종가 ${won(x.px)}원 · 연초 누적 VWAP ${won(x.anc.ytd.v)}원(${pm(x.anc.ytd.gap)}) · 52주 고점일(${esc(MU.md(x.anc.hi.from))}) 이후 누적 VWAP ${won(x.anc.hi.v)}원(${pm(x.anc.hi.gap)}) = 고점 이후 산 사람은 평균 ${x.anc.hi.gap < 0 ? '손실' : '이익'}.
          ${x.frgn ? `외국인은 60일 동안 ${pm(x.frgn.net / 1e4, 2, '조원')}, 산 날 평단 ${won(x.frgn.buy)}원(현재가 ${pm(x.frgn.buy_gap)}).` : ''}</div>
        <div class="ch narrow"></div>
        <div class="scroll-x" style="max-height:480px;overflow-y:auto"><table class="tbl"><thead><tr><th>종목</th><th>종가</th><th>당일 VWAP 대비</th><th>연초 누적 VWAP 대비</th><th>52주 고점일 누적 대비</th><th>52주 저점일 누적 대비</th><th>60일 누적 대비</th><th>외국인 60일</th><th>산 날 평단 대비</th><th>기관 60일</th><th>산 날 평단 대비</th><th>개인 60일</th><th>산 날 평단 대비</th></tr></thead><tbody>
        ${VW.map(v => `<tr class="click${v.code === sel ? ' sel' : ''}" data-c="${v.code}"><td>${esc(v.name)}</td><td>${won(v.px)}</td><td>${gapc(v.vwap_gap)}</td><td>${gapc(v.anc.ytd.gap)}</td><td>${gapc(v.anc.hi.gap)}</td><td>${gapc(v.anc.lo.gap)}</td><td>${gapc(v.anc.d60.gap)}</td>${who(v, 'frgn')}${who(v, 'org')}${who(v, 'ind')}</tr>`).join('')}</tbody></table></div>
        <p class="note">줄을 누르면 그 종목의 종가와 누적 VWAP 을 그린다. '대비' = 현재가가 그 평단보다 몇 % 위(빨강)·아래(파랑)인가. 주체별 평단 = 최근 60거래일 중 순매수한 날의 (순매수 수량 × 그날 VWAP) 평균 — 실제 체결가가 아니라 추정이다. 종목 일봉은 기존 DB 기준이라 하루 늦을 수 있다.</p>`;
      MChart.line($('vwap').querySelector('.ch'), { series: [{ name: `${x.name} 종가`, d: x.series.d, v: x.series.px }, { name: '연초 이후 누적 VWAP', d: x.series.d, v: x.series.ytd, color: 'var(--c2)' }, { name: '52주 고점일 이후 누적 VWAP', d: x.series.d, v: x.series.hi, color: 'var(--c6)', dash: true }], dec: 0, height: 240 });
      $('vwap').querySelectorAll('tr.click').forEach(tr => tr.onclick = () => { sel = tr.dataset.c; draw(); });
    };
    draw();
  } else none('vwap', 'VWAP · 주체별 평단', '종목 일봉 DB 를 읽지 못했다.');

  // ── KOSPI200 옵션 ──
  const O = D.k200opt;
  if (O) {
    $('k200opt').innerHTML = `<h2>KOSPI200 옵션 — 풋콜·스큐 ${use('타이밍')} ${asof(O.date)}</h2><p class="sub">풋콜 = 풋 ÷ 콜. 풋(하락에 거는 옵션)이 많이 거래될수록 높다. 극단이면 역발상으로 본다. 월물 + 위클리, 정규장 기준.</p>
      <div class="stat"><div><span>거래량 풋콜 (5일 평균)</span><b>${num(O.vol5)}</b></div><div><span>미결제 풋콜</span><b>${num(O.oi)}</b></div><div><span>거래대금 풋콜</span><b>${num(O.val)}</b></div><div><span>스큐 (풋 − 콜 변동성)</span><b>${pm(O.skew, 1, '%p')}</b></div></div>
      <div class="read">지금 읽으면 — 거래량 풋콜 5일 평균 <b>${num(O.vol5)}</b> (2년 중 하위 ${O.vol_pct}%): ${O.vol_pct >= 90 ? '<b>풋 거래가 몰려 있다</b> — 하락 헤지·투기가 극단. 역발상으로는 바닥 쪽' : O.vol_pct <= 10 ? '<b>콜 거래가 몰려 있다</b> — 낙관이 극단' : '극단이 아니다'}.
        스큐 <b>${pm(O.skew, 1, '%p')}</b>${O.skew_pct != null ? ` (2년 중 하위 ${O.skew_pct}%)` : ''}: ${O.skew_pct >= 90 ? '하락 보험(외가격 풋)이 비싸다 — 급락 걱정이 가격에 들어가 있다' : O.skew_pct != null && O.skew_pct <= 10 ? '하락 보험이 싸다 — 급락 걱정이 없다(오히려 콜이 비싸다)' : '평소 수준'}.</div><div class="ch"></div>
      <h3 class="sec-title">과거 근거 — 풋콜 극단 뒤 KOSPI (${esc(O.ev_hi.since.slice(0, 7))}~)</h3>${MU.evidence([['풋콜 5일 평균이 2년 상위 5% (풋 쏠림)', O.ev_hi], ['2년 하위 5% (콜 쏠림)', O.ev_lo]])}
      <p class="note">자료 ${O.n}일치라 횟수가 적다 — 참고만 한다. 스큐 = 5% 외가격 풋의 내재변동성 − 5% 외가격 콜의 내재변동성.</p>`;
    MChart.line($('k200opt').querySelector('.ch'), { series: [ser(O.series, '거래량 풋콜 5일 평균'), ser(O.k200, 'KOSPI200', { axis: 'r', color: 'var(--c5)', width: 1.2 })], hlines: [{ y: 1, label: '1.0' }], dec: 2, decR: 0, height: 220 });
    const T = O.table;
    if (T) {
      let rs = T.rows.filter(x => Math.abs(x[0] / T.spot - 1) <= 0.1);
      if (rs.length > 36) rs = rs.filter(x => x[0] % 5 === 0);
      if (rs.length > 36) rs = rs.filter(x => x[0] % 10 === 0);
      const mx = Math.max(...rs.map(x => Math.max(x[1], x[2])), 1), near = rs.reduce((a, x) => Math.abs(x[0] - T.spot) < Math.abs(a[0] - T.spot) ? x : a, rs[0])[0];
      $('k200oi').innerHTML = `<h2>행사가별 미결제 — 옵션이 쌓인 가격대 ${use('흐름')} ${asof(T.date)}</h2><p class="sub">${esc(T.month.slice(0, 4))}년 ${+T.month.slice(4)}월물. 콜이 많이 쌓인 가격은 위쪽 저항, 풋이 많이 쌓인 가격은 아래쪽 지지로 작용하기 쉽다(옵션을 판 쪽이 그 가격을 지키려 한다).</p>
        <div class="read">지금 읽으면 — KOSPI200 <b>${num(T.spot)}</b>. 위쪽에서 콜이 가장 많이 쌓인 가격 <b>${num(T.call_wall, 1)}</b>(${pm((T.call_wall / T.spot - 1) * 100)}), 아래쪽에서 풋이 가장 많이 쌓인 가격 <b>${num(T.put_wall, 1)}</b>(${pm((T.put_wall / T.spot - 1) * 100)}) — 만기까지 이 사이가 옵션 시장이 보는 범위다(등가격 근처는 늘 많아서 현재가에서 1% 넘게 떨어진 행사가만 본다).</div>
        <div class="oi"><div class="h l">콜 미결제</div><div class="h k">행사가</div><div class="h">풋 미결제</div>
        ${rs.slice().reverse().map(x => `<div class="c l" title="${num(x[1], 0)} 계약"><i style="width:${x[1] / mx * 100}%;margin-left:auto"></i></div><div class="k${x[0] === near ? ' now' : ''}">${num(x[0], x[0] % 1 ? 1 : 0)}</div><div class="p" title="${num(x[2], 0)} 계약"><i style="width:${x[2] / mx * 100}%"></i></div>`).join('')}</div>
        <p class="note">굵은 행사가가 현재 지수에 가장 가까운 가격. 막대에 마우스를 올리면 계약 수. 현재가 ±10% 범위.</p>`;
    } else none('k200oi', '행사가별 미결제', '자료 없음');
  } else { none('k200opt', 'KOSPI200 옵션', '옵션 자료를 받는 중이다.'); none('k200oi', '행사가별 미결제', '옵션 자료를 받는 중이다.'); }

  // ── 미국 옵션 · 공매도 잔고 ──
  const U = D.usopt, cb = U.cboe;
  $('usopt').innerHTML = `<h2>미국 옵션 — 종목별 풋콜·내재변동성 ${use('타이밍,섹터')} ${asof(U.rows[0] && U.rows[0].date)}</h2><p class="sub">45일 안에 만기가 오는 옵션의 풋 ÷ 콜(거래량·미결제)과, 30일 만기 등가격 옵션의 내재변동성(시장이 보는 앞으로 한 달의 출렁임, 연율).</p>
    <table class="tbl"><thead><tr><th>종목</th><th>풋콜 (거래량)</th><th>풋콜 (미결제)</th><th>내재변동성</th><th>전일</th><th>쌓인 날</th></tr></thead><tbody>
    ${U.rows.map(x => `<tr><td>${esc(x.name)} <span class="muted small">${x.tk}</span></td><td class="b ${x.pc_vol >= 1.5 ? 'down' : ''}">${num(x.pc_vol)}</td><td>${num(x.pc_oi)}</td><td class="b">${num(x.iv, 1)}%</td><td class="muted">${x.iv_prev == null ? '–' : num(x.iv_prev, 1) + '%'}</td><td class="muted">${x.n}일</td></tr>`).join('')}</tbody></table>
    <div class="read">지금 읽으면 — ${(() => { const hi = U.rows.filter(x => x.pc_vol >= 1.5), ivs = U.rows.slice().sort((a, b) => b.iv - a.iv); return `풋 거래가 콜의 1.5배를 넘는 것: ${hi.length ? hi.map(x => `${esc(x.name)} ${num(x.pc_vol)}`).join(', ') + ' — 지수·섹터 ETF 는 헤지 수요라 원래 높다' : '없음'}. 내재변동성이 가장 높은 것: ${ivs.slice(0, 3).map(x => `${esc(x.name)} ${num(x.iv, 0)}%`).join(', ')}.`; })()}
      ${cb.pc_equity ? `미국 전체(CBOE ${esc(MU.md(cb.pc_equity.date))}): 주식 풋콜 <b>${num(cb.pc_equity.last)}</b> · 전체 ${num(cb.pc_total.last)}.` : ''}</div>
    <p class="note">야후 옵션 체인은 과거 값을 주지 않아 오늘부터 하루씩 쌓는다. 며칠 쌓이면 '평소 대비'를 붙인다. 지금은 종목끼리 비교하는 용도.</p>`;
  const SI = D.si || [];
  if (SI.length) {
    $('si').innerHTML = `<h2>미국 공매도 잔고 ${use('흐름')} ${asof(SI[0].date, 35)}</h2><p class="sub">아직 되사지 않은 공매도 수량(FINRA, 월 2회 · 2주쯤 늦게 발표). 지수 ETF 의 공매도는 헤지·펀딩 숏(다른 롱을 받치려고 지수를 파는 것)이 많다 — 풀리면 숏커버 반등.</p>
      <table class="tbl"><thead><tr><th>종목</th><th>공매도 잔고</th><th>직전 대비</th><th>커버 일수</th><th>3년 백분위</th><th>2년 추이</th></tr></thead><tbody>
      ${SI.map(x => `<tr><td>${esc(x.name)}</td><td class="b">${num(x.sh, 1)} <span class="muted small">백만 주</span></td><td>${gapc(x.chg)}</td><td>${num(x.dtc)}일</td><td>${x.pct ?? '–'}${MU.gauge(x.pct)}</td><td>${MU.spark(x.spark)}</td></tr>`).join('')}</tbody></table>
      <div class="read">지금 읽으면 — ${(() => { const hi = SI.filter(x => x.pct >= 90), lo = SI.filter(x => x.pct != null && x.pct <= 10); return `${hi.length ? `공매도 잔고가 3년 최고 수준: <b>${hi.map(x => esc(x.name)).join(', ')}</b> — 숏이 많이 쌓여 있어 반등 때 되사는 힘이 크다. ` : ''}${lo.length ? `3년 최저 수준: ${lo.map(x => esc(x.name)).join(', ')} — 숏커버 재료가 적다. ` : ''}${!hi.length && !lo.length ? '한쪽으로 몰린 종목이 없다. ' : ''}`; })()}커버 일수 = 잔고 ÷ 하루 평균 거래량(되사는 데 걸리는 날).</div>`;
  } else none('si', '미국 공매도 잔고', '자료 없음');

  // ── 롱숏 페어 ──
  const PR = D.pairs || [];
  if (PR.length) {
    let sel = (PR.slice().sort((a, b) => Math.abs(b.z ?? 0) - Math.abs(a.z ?? 0))[0]).name;
    const draw = () => {
      const x = PR.find(p => p.name === sel), ext = PR.filter(p => Math.abs(p.z ?? 0) >= 2);
      const side = p => { const [a, b] = p.name.split(' ÷ '); return p.z > 0 ? `${a}가 ${b}보다 비싸졌다 → 롱숏이라면 ${b} 매수 · ${a} 매도 쪽` : `${a}가 ${b}보다 싸졌다 → 롱숏이라면 ${a} 매수 · ${b} 매도 쪽`; };
      $('pairs').innerHTML = `<h2>롱숏 페어 — 닮은 두 종목의 벌어짐 ${use('섹터,타이밍')} ${asof(PR[0].date)}</h2>
        <p class="sub">z-점수 = (두 종목 가격비의 로그 − 최근 250일 평균) ÷ 250일 표준편차. ±2 를 넘으면 평소 범위를 벗어난 것. 반감기 = 벌어진 차이가 절반으로 줄어드는 데 걸린 평균 일수(짧을수록 빨리 되돌아온다).</p>
        <div class="read">지금 읽으면 — ±2 를 넘은 페어: ${ext.length ? ext.map(p => `<b>${esc(p.name)} ${pm(p.z, 2, '')}</b> (${side(p)}${p.ev.n >= 5 ? `; 과거 같은 자리 ${p.ev.n}번, 60일 뒤 평균 ${pm(p.ev.mean)}·이긴 비율 ${p.ev.win}%` : ''})`).join(' / ') : '없다 — 모든 페어가 평소 범위 안'}.</div>
        <div class="scroll-x"><table class="tbl"><thead><tr><th>페어</th><th class="l">관계</th><th>z-점수</th><th>20일 전</th><th>반감기</th><th>60일 베타</th><th>60일 상관</th><th>과거 ±2 뒤 60일 되돌림 수익</th><th>횟수 · 이긴 비율</th></tr></thead><tbody>
        ${PR.map(p => `<tr class="click${p.name === sel ? ' sel' : ''}" data-n="${esc(p.name)}"><td>${esc(p.name)}</td><td class="l small muted">${esc(p.note)}</td><td>${MU.zbar(p.z)}<b class="${Math.abs(p.z ?? 0) >= 2 ? MU.sgn(p.z) : ''}">${pm(p.z, 2, '')}</b></td><td class="muted">${pm(p.z20, 2, '')}</td><td>${p.hl == null ? '–' : p.hl + '일'}</td><td>${num(p.beta)}</td><td>${num(p.corr)}</td><td class="${MU.sgn(p.ev.mean)}">${p.ev.n ? pm(p.ev.mean) : '–'}</td><td class="muted">${p.ev.n ? `${p.ev.n}번 · ${p.ev.win}%` : `자료 ${p.n}일`}</td></tr>`).join('')}</tbody></table></div>
        <div class="ch narrow"></div>
        <p class="note">줄을 누르면 그 페어의 z-점수 추이를 그린다. '되돌림 수익' = z 가 ±2 를 넘은 날 벌어진 쪽의 반대로 서서 60거래일 들고 있었을 때의 평균(2012년~, 20일 안의 반복은 한 번). 평균이 플러스여도 이긴 비율이 50%대면 <b>벌어진 채로 더 가는 경우가 절반 가까이</b> 된다 — 왜 벌어졌는지(실적·지배구조)를 먼저 본다.
          베타 = A 가 B 의 하루 등락을 얼마나 따라가나(롱숏 수량 비율의 근거). 다른 조합은 <a class="lnk" href="pair.html">페어·상관 탭</a>에서 직접 고른다.</p>`;
      MChart.line($('pairs').querySelector('.ch'), { series: [{ name: `${x.name} z-점수`, d: x.series.d, v: x.series.z }, { name: '가격비', d: x.series.d, v: x.series.ratio, axis: 'r', color: 'var(--c5)', width: 1.2 }], hlines: [{ y: 2, label: '+2' }, { y: -2, label: '−2' }, { y: 0, label: '0' }], dec: 2, decR: 3, height: 240 });
      $('pairs').querySelectorAll('tr.click').forEach(tr => tr.onclick = () => { sel = tr.dataset.n; draw(); });
    };
    draw();
  } else none('pairs', '롱숏 페어', '자료 없음');

  // ── 롱숏 쏠림 ──
  const C = D.crowd || [];
  $('crowd').innerHTML = `<h2>롱숏 쏠림 ${use('흐름,비중')} ${asof(C[0] && C[0].date)}</h2><p class="sub">헤지펀드가 같은 종목에 몰려 있다가 한꺼번에 줄이면(디그로싱) 좋은 종목이 이유 없이 빠진다. 그 흔적을 ETF 로 본다.</p>
    <div class="scroll-x"><table class="tbl"><thead><tr><th>지표</th><th>5일</th><th>20일</th><th>20일 변화의 3년 백분위</th><th>120일</th></tr></thead><tbody>
    ${C.map(x => `<tr><td class="l">${esc(x.name)}<br><span class="muted small">${esc(x.read)}</span></td><td>${gapc(x.c5)}</td><td class="b">${gapc(x.c20)}</td><td>${x.pct}${MU.gauge(x.pct)}</td><td>${MU.spark(x.spark, 64)}</td></tr>`).join('')}</tbody></table></div>
    <div class="read">지금 읽으면 — ${(() => { const g = C[0], m = C[1], b = C[2]; const n = [g.pct <= 10, m.pct <= 10, b.pct >= 90].filter(Boolean).length;
      return `모멘텀 ÷ S&P500 20일 <b>${pm(m.c20)}</b>(3년 중 하위 ${m.pct}%), 헤지펀드 선호주 ÷ S&P500 <b>${pm(g.c20)}</b>, 반대베타 <b>${pm(b.c20)}</b> → ${n >= 2 ? '<b>포지션을 한꺼번에 줄이는 흔적이 뚜렷하다</b> — 주도주가 실적과 무관하게 빠지는 구간. 멎는 날이 주도주 재매수 자리' : n === 1 ? '<b>일부에서 포지션 축소 흔적</b>(주도주·모멘텀 쪽). 헤지펀드 전체가 줄이는 단계는 아니다' : '포지션 축소 흔적이 없다'}.`; })()}</div>`;

  // ── 통화 스왑 대용 ──
  const W = D.swap;
  if (W) {
    $('swap').innerHTML = `<h2>달러 조달 비용 — 통화 스왑 대용 ${use('비중')} ${asof(W.date)}</h2><p class="sub">달러선물 근월과 차근월의 가격 차는 '원화 금리 − 달러 금리'를 시장이 매긴 값이다. 실제 금리차보다 더 낮으면(베이시스 음수) 달러를 빌리는 데 웃돈이 붙었다는 뜻.</p>
      <div class="stat"><div><span>선물이 말하는 금리차</span><b>${pm(W.implied, 2, '%')}</b></div><div><span>실제 금리차</span><b>${pm(W.diff, 2, '%')}</b> <span>CD ${num(W.kr)} − SOFR ${num(W.us)}</span></div><div><span>베이시스</span><b class="${MU.sgn(W.basis)}">${pm(W.basis, 0, 'bp')}</b></div></div>
      <div class="read">지금 읽으면 — 베이시스 <b>${pm(W.basis, 0, 'bp')}</b> (${W.n}일 중 하위 ${W.pct}%${W.d20 != null ? `, 20일 ${pm(W.d20, 0, 'bp')}` : ''}): ${W.pct <= 10 ? '<b>달러 구하기가 평소보다 비싸졌다</b> — 외국인 자금·환율에 부담' : W.pct >= 90 ? '달러 조달이 평소보다 편하다' : '평소 범위'}.
        ${W.d20 != null && W.d20 <= -30 ? '20일 사이 빠르게 벌어지는 중이다.' : ''}</div><div class="ch"></div>
      <p class="note">공식 스왑포인트·통화스왑(CRS) 금리는 무료 출처가 없어 달러선물로 계산한 <b>대용</b>이다. 근월~차근월(1~2개월) 구간의 값을 3개월 금리와 비교하므로 수준보다 <b>변화</b>를 본다. 5일 평균.</p>`;
    MChart.line($('swap').querySelector('.ch'), { series: [ser(W.series, '베이시스 (bp)'), ser(W.krw, '원/달러', { axis: 'r', color: 'var(--c5)', width: 1.2 })], hlines: [{ y: 0, label: '0' }], dec: 0, decR: 0, height: 220 });
  } else none('swap', '달러 조달 비용 — 통화 스왑 대용', '달러선물 자료를 받는 중이다.');
})();
