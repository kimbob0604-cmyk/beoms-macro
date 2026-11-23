// 수급·포지셔닝: 한국 신용잔고·반대매매·예탁금 · 중국 신용잔고 · CFTC 선물 포지션 · CTA·변동성 제어 모델 · DIX/GEX
(async () => {
  MU.shell('flow');
  const { num, use, asof, esc, pm } = MU;
  let D;
  try { D = await MU.get('flow.json'); } catch (e) { return MU.fail(e); }
  MU.built(D.built);
  const $ = id => document.getElementById(id);
  const C = D.credit, CN = D.china, X = D.dix;
  const ser = (o, name, x = {}) => ({ name, d: o.d, v: o.v, ...x });
  const kospi = ser(C.kospi_s, 'KOSPI', { axis: 'r', color: 'var(--c5)', width: 1.2 });

  // 신용잔고
  $('credit').innerHTML = `<h2>한국 신용잔고 ${use('타이밍,비중')} ${asof(C.date)}</h2><p class="sub">증권사에서 돈을 빌려 산 주식의 잔액(신용거래융자). 쌓이면 하락 때 매물이 된다.</p>
    <div class="stat"><div><span>신용잔고</span><b>${num(C.last)}</b> 조원</div><div><span>5일 변화</span><b class="${MU.sgn(C.d5)}">${pm(C.d5)}</b></div><div><span>20일 변화</span><b class="${MU.sgn(C.d20)}">${pm(C.d20)}</b></div></div>
    <p class="small muted">유가증권 ${num(C.kospi)}조 · 코스닥 ${num(C.kosdaq)}조 · 3년 중 상위 ${100 - C.pct}% 수준 · 예탁증권 담보융자 ${num(C.loan)}조</p>
    <div class="read">지금 읽으면 — ${C.d20 <= -8 ? `20일 동안 <b>${pm(C.d20)}</b>: <b>빚이 빠르게 털리는 중</b>(강제 청산 포함). 줄어드는 속도가 멎는 날이 매물 부담이 끝나는 자리다` : C.d20 >= 8 ? `20일 동안 <b>${pm(C.d20)}</b>: <b>빚이 빠르게 쌓이는 중</b> — 과열 쪽 신호` : `20일 변화 ${pm(C.d20)}: 큰 변화 없음`}.
      ${C.d5 <= -3 ? '5일 −3% 이하(급감 신호)가 켜져 있다.' : C.d5 > 0 && C.d20 <= -8 ? `최근 5일은 다시 ${pm(C.d5)} — 감소가 멎었다.` : ''}</div><div class="ch"></div>`;
  MChart.line($('credit').querySelector('.ch'), { series: [ser(C.series.credit, '신용잔고 (조원)'), kospi], dec: 1, decR: 0, height: 220 });

  // 반대매매
  $('forced').innerHTML = `<h2>반대매매 ${use('타이밍')} ${asof(C.date)}</h2><p class="sub">미수금을 못 갚아 증권사가 강제로 판 금액. 미수금 대비 비중이 튀면 투매의 끝 무렵이다.</p>
    <div class="stat"><div><span>반대매매 금액</span><b>${num(C.forced, 0)}</b> 억원</div><div><span>미수금 대비 비중</span><b>${num(C.forced_pct, 1)}%</b></div><div><span>3년 중 위치</span><b>상위 ${100 - C.forced_rank}%</b></div></div>
    <div class="read">지금 읽으면 — 비중 <b>${num(C.forced_pct, 1)}%</b>, 최근 3년 중 상위 ${100 - C.forced_rank}%: ${C.forced_rank >= 95 ? '<b>강제 청산이 몰리는 구간</b>. 며칠 이어진 뒤 줄어들면 수급 바닥 후보' : C.forced_rank >= 80 ? '평소보다 많다 — 빚 낸 계좌가 흔들리는 중' : '평소 수준'}.</div><div class="ch"></div>
    <p class="note">하루 값이 들쭉날쭉해서 며칠 묶어서 본다. 아래 '과거 근거'는 5일 평균이 3년 상위 5%에 든 날 기준.</p>`;
  MChart.line($('forced').querySelector('.ch'), { zero: true, series: [ser(C.series.forced_pct, '미수금 대비 반대매매 (%)'), kospi], dec: 1, decR: 0, height: 220 });

  // 과거 근거
  const beat = e => ['1개월', '3개월', '6개월', '12개월'].filter(h => e[h].mean != null && e[h].mean > e[h].base).length;
  $('ev').innerHTML = `<h2>과거 근거 — 빚이 털린 뒤 KOSPI ${use('타이밍')}</h2><p class="sub">2011년 이후. "신용잔고가 급감하면 바닥"이라는 말이 실제로 맞았는지 본다.</p>
    ${MU.evidence([['신용잔고 5일 −3% 이하', C.ev_drop], ['반대매매 비중 5일 평균이 3년 상위 5%', C.ev_forced]])}
    <div class="read">지금 읽으면 — 신용잔고 급감은 네 기간 중 <b>${beat(C.ev_drop)}개</b>, 반대매매 급증은 <b>${beat(C.ev_forced)}개</b>에서만 아무 날보다 나았다 → ${beat(C.ev_drop) + beat(C.ev_forced) >= 6 ? '과거에는 잘 맞은 신호다' : '<b>이것 하나로 바닥이라고 보긴 어렵다.</b> 급감이 멎는지, 타이밍 탭의 다른 신호와 같이 켜지는지를 본다'}.</div>`;

  // 예탁금
  $('deposit').innerHTML = `<h2>예탁금 · 신용 ÷ 예탁금 ${use('비중')} ${asof(C.date)}</h2><p class="sub">예탁금 = 주식 사려고 계좌에 넣어 둔 돈(대기 자금). 신용 ÷ 예탁금 = 대기 자금에 비해 빚이 얼마나 많은가.</p>
    <div class="stat"><div><span>투자자 예탁금</span><b>${num(C.deposit, 1)}</b> 조원</div><div><span>20일 변화</span><b class="${MU.sgn(C.deposit_d20)}">${pm(C.deposit_d20)}</b></div><div><span>신용 ÷ 예탁금</span><b>${num(C.ratio, 1)}%</b></div></div>
    <div class="read">지금 읽으면 — 신용 ÷ 예탁금 <b>${num(C.ratio, 1)}%</b> (3년 중 하위 ${C.ratio_pct}%): ${C.ratio_pct >= 80 ? '<b>빚 비중이 높다</b> — 하락 때 매물이 커질 수 있는 구조' : C.ratio_pct <= 20 ? '빚 비중이 낮다 — 매물 부담이 가벼운 구조' : '보통 수준'}.
      예탁금이 20일 동안 ${pm(C.deposit_d20)} ${C.deposit_d20 <= -5 ? '— <b>대기 자금이 빠져나가는 중</b>' : C.deposit_d20 >= 5 ? '— 대기 자금이 들어오는 중' : ''}.</div><div class="ch"></div>`;
  MChart.line($('deposit').querySelector('.ch'), { series: [ser(C.series.deposit, '예탁금 (조원)'), ser(C.series.credit_ratio, '신용 ÷ 예탁금 (%)', { axis: 'r', color: 'var(--c2)' })], dec: 0, decR: 0, height: 220 });

  // 중국 신용잔고
  $('china').innerHTML = `<h2>중국 신용잔고 ${use('흐름,비중')} ${asof(CN.date)}</h2><p class="sub">상하이·선전 융자융권 잔액. 중국 개인의 빚투 크기 — 중국 관련주·KOSPI 와 같이 움직인 구간이 많다.</p>
    <div class="stat"><div><span>잔액</span><b>${num(CN.last, 0)}</b> 억위안</div><div><span>20일 변화</span><b class="${MU.sgn(CN.d20)}">${pm(CN.d20)}</b></div></div>
    <div class="read">지금 읽으면 — 20일 동안 <b>${pm(CN.d20)}</b>: ${CN.d20 <= -5 ? '<b>중국에서도 빚이 털리는 중</b> — 아시아 전체가 위험 회피' : CN.d20 >= 5 ? '중국 개인 자금이 빠르게 들어오는 중' : '큰 변화 없음'}.
      <a class="lnk" href="pair.html?a=kr_kospi&b=cn_margin&p=756">KOSPI 와 겹쳐 보기 →</a></div><div class="ch"></div>`;
  MChart.line($('china').querySelector('.ch'), { series: [ser(CN.series, '중국 신용잔고 (억위안)'), ser(CN.sh, '상하이종합', { axis: 'r', color: 'var(--c5)', width: 1.2 })], dec: 0, decR: 0, height: 220 });

  // CFTC
  let sel = D.cftc[0].key;
  const drawC = () => {
    const c = D.cftc.find(x => x.key === sel), sp = D.cftc[0];
    const word = p => p >= 90 ? '3년 중 가장 매수 쪽' : p <= 10 ? '3년 중 가장 매도 쪽' : p >= 70 ? '매수 쪽으로 치우침' : p <= 30 ? '매도 쪽으로 치우침' : '중간';
    $('cftc').innerHTML = `<h2>CFTC 선물 포지션 ${use('흐름')} ${asof(sp.date, 12)}</h2><p class="sub">미국 선물시장에서 레버리지 펀드(헤지펀드·CTA)와 자산운용사가 순매수인지 순매도인지. 단위 천 계약, 매주 한 번.</p>
      <div class="scroll-x"><table class="tbl"><thead><tr><th>선물</th><th>레버리지 펀드 순포지션</th><th>1주 변화</th><th>3년 백분위</th><th>자산운용 순포지션</th><th>1주 변화</th><th>3년 백분위</th></tr></thead><tbody>
      ${D.cftc.map(x => `<tr class="click${x.key === sel ? ' sel' : ''}" data-k="${x.key}"><td>${esc(x.name)}</td><td class="b ${MU.sgn(x.lev)}">${pm(x.lev, 1, '')}</td><td>${pm(x.lev_w, 1, '')}</td><td>${x.lev_pct}${MU.gauge(x.lev_pct)}</td><td class="b ${MU.sgn(x.am)}">${pm(x.am, 1, '')}</td><td>${pm(x.am_w, 1, '')}</td><td>${x.am_pct}${MU.gauge(x.am_pct)}</td></tr>`).join('')}</tbody></table></div>
      <div class="read">지금 읽으면 — S&P500 선물: 레버리지 펀드 <b>${pm(sp.lev, 0, '')}천 계약</b>(${word(sp.lev_pct)}, 1주 ${pm(sp.lev_w, 0, '')}), 자산운용 <b>${pm(sp.am, 0, '')}천 계약</b>(${word(sp.am_pct)}).
        ${sp.am_pct >= 90 ? '자산운용사 매수가 3년 최대 수준 — <b>더 살 여력이 적다</b>.' : sp.am_pct <= 10 ? '자산운용사 포지션이 3년 최저 수준 — <b>팔 만큼 판 상태</b>.' : ''} 백분위가 0이나 100에 가까울 때(한쪽으로 몰렸을 때)만 되돌림 신호로 본다.</div>
      <div class="ch narrow"></div><p class="note">줄을 누르면 그 선물의 3년 추이를 그린다. 레버리지 펀드의 주가지수 순매도에는 현·선물 차익거래 몫이 섞여 있어 방향보다 <b>변화</b>와 <b>백분위</b>를 본다.</p>`;
    MChart.line($('cftc').querySelector('.ch'), { series: [{ name: `${c.name} — 레버리지 펀드`, d: c.series.d, v: c.series.lev }, { name: '자산운용', d: c.series.d, v: c.series.am }], hlines: [{ y: 0, label: '0' }], dec: 0, height: 220 });
    $('cftc').querySelectorAll('tr.click').forEach(tr => tr.onclick = () => { sel = tr.dataset.k; drawC(); });
  };
  drawC();

  // CTA 추정 포지션 · 변동성 제어 (3단계 모델)
  let T = null;
  try { T = await MU.get('cta.json'); } catch (e) { console.warn(e); }
  if (T) {
    const E = T.eq, V = T.volctl, sp = T.rows.find(x => x.k === 'px:spx'), ks = T.rows.find(x => x.k === 'kr:kospi');
    const fmt = (v, dec) => num(v, v >= 1000 ? 0 : dec);
    const trig = (x, t) => `<td class="${t.on ? '' : 'muted'}">${fmt(t.level, x.dec)} <span class="small ${MU.sgn(t.dist)}">${pm(t.dist)}</span><br><span class="small ${t.on ? 'up' : 'down'}">${t.on ? '매수' : '매도'}</span></td>`;
    // 지금 신호와 반대쪽에 있는 가장 가까운 가격
    const next = x => {
      const up = x.trig.filter(t => !t.on).sort((a, b) => a.dist - b.dist)[0], dn = x.trig.filter(t => t.on).sort((a, b) => b.dist - a.dist)[0];
      return `<span class="muted">내일 종가 기준 — </span>${up ? `<b>${fmt(up.level, x.dec)}</b>(${pm(up.dist)}) 위로 올라서면 ${up.n}일 신호가 매수로 바뀐다` : '네 신호가 모두 매수다'}${dn ? `, <b>${fmt(dn.level, x.dec)}</b>(${pm(dn.dist)}) 아래로 내려가면 ${dn.n}일 신호가 매도로 바뀐다` : ' — 네 신호가 모두 매도라 더 팔 것이 없다'}`;
    };
    const beat = e => ['1개월', '3개월', '6개월', '12개월'].filter(h => e[h].mean != null && e[h].mean > e[h].base).length;
    const cor = f => f.map(x => `${esc(x.name)} <b>${num(x.corr)}</b>`).join(' · ');
    $('cta').innerHTML = `<h2>CTA 추정 포지션 — 추세추종 모델 ${use('흐름')} ${asof(sp.date)}</h2>
      <p class="sub">CTA(추세추종 펀드)는 오르는 자산을 사고 내리는 자산을 판다. 자산마다 ${T.hz.join('·')}일 전 가격보다 높으면 +1, 낮으면 −1 을 주고 평균한 뒤, 변동성이 크면 크기를 줄인다(목표 ${T.target}% ÷ 60일 변동성, 최대 1배) → −100%(전부 매도) ~ +100%(전부 매수).</p>
      <div class="stat"><div><span>주식 7개 지수 평균</span><b class="${MU.sgn(E.last)}">${pm(E.last, 0)}</b></div><div><span>1주 변화</span><b class="${MU.sgn(E.w)}">${pm(E.w, 0, '%p')}</b></div><div><span>1개월 변화</span><b class="${MU.sgn(E.m)}">${pm(E.m, 0, '%p')}</b></div><div><span>3년 중 위치</span><b>하위 ${E.pct}%</b></div></div>
      <div class="scroll-x"><table class="tbl"><thead><tr><th>자산</th><th>추정 포지션</th><th>1주 변화</th><th>1개월 변화</th><th>현재가</th>${T.hz.map(n => `<th>${n}일 신호가 바뀌는 가격</th>`).join('')}</tr></thead><tbody>
      ${['주식', '채권', '통화', '원자재'].map(g => `<tr class="grp"><td colspan="${5 + T.hz.length}">${g}</td></tr>` + T.rows.filter(x => x.cls === g).map(x => `<tr><td>${esc(x.name)}</td><td class="b ${MU.sgn(x.pos)}">${pm(x.pos, 0)}</td><td>${pm(x.pos_w, 0, '')}</td><td>${pm(x.pos_m, 0, '')}</td><td>${fmt(x.px, x.dec)}</td>${x.trig.map(t => trig(x, t)).join('')}</tr>`).join('')).join('')}</tbody></table></div>
      <div class="read">지금 읽으면 — 주식 평균 <b>${pm(E.last, 0)}</b>(1개월 ${pm(E.m, 0, '%p')}, 3년 중 하위 ${E.pct}%): ${E.last <= -25 ? '<b>추세추종 자금이 주식을 파는 쪽에 서 있다.</b> 이미 많이 판 상태라 추가 매도 여력은 줄었고, 아래 가격을 되찾으면 기계적 매수로 바뀐다' : E.last >= 50 ? '추세추종 자금이 주식을 많이 들고 있다 — 꺾이면 팔 물량이 많다' : '중간 — 한쪽으로 몰려 있지 않다'}.
        <b>S&P500</b> ${pm(sp.pos, 0)}: ${next(sp)}. <b>KOSPI</b> ${pm(ks.pos, 0)}(변동성 ${num(ks.vol, 0)}%라 크기가 작다): ${next(ks)}.</div>
      <div class="grid2" style="margin:12px 0 0"><div class="ch" id="cta-sp"></div><div class="ch" id="cta-ks"></div></div>
      <h3 class="sec-title" style="margin-top:16px">이 모델을 얼마나 믿을 수 있나</h3>
      <p class="small">실제 CTA 전략 ETF 와의 주간 수익률 상관(최근 2년): ${cor(T.fit)}. 125·250일 신호만 쓰면 ${cor(T.fit_long)}.
        → <b>방향은 절반쯤 닮았다.</b> 실제 펀드는 장기 신호의 비중이 더 크다는 뜻이므로, 위 표에서 <b>125일·250일 가격</b>을 더 무겁게 본다. IB 가 내는 CTA 추정치와 숫자가 같지는 않다.</p>
      <h3 class="sec-title" style="margin-top:16px">과거 근거 — 추정 포지션이 한쪽 끝에 간 뒤 (2006년~)</h3>
      ${MU.evidence([['S&P500 추정 포지션 −50% 이하 (매도)', T.ev_short], ['S&P500 추정 포지션 +100% (전부 매수)', T.ev_long]], 'S&P500')}
      ${MU.evidence([['KOSPI 추정 포지션 −50% 이하 (매도)', T.ev_kshort]], 'KOSPI')}
      <div class="read">지금 읽으면 — S&P500 은 매도 전환 뒤 ${beat(T.ev_short)}개 기간에서만 아무 날보다 나았다(사는 신호도 파는 신호도 아니다 — <b>수급 흐름 파악용</b>). KOSPI 는 매도 전환 뒤 ${beat(T.ev_kshort)}개 기간에서만 나았다${beat(T.ev_kshort) === 0 ? ' — <b>네 기간 모두 아무 날보다 낮았다. KOSPI 는 추세가 꺾인 뒤 서둘러 사지 않는 편이 나았다</b>(추세가 이어지는 시장)' : ''}.</div>`;
    MChart.line($('cta-sp'), { series: [ser(T.spx.series, 'S&P500 추정 포지션 (%)'), ser(T.spx.px, 'S&P500', { axis: 'r', color: 'var(--c5)', width: 1.2 })], hlines: [{ y: 0, label: '0' }], dec: 0, decR: 0, height: 220 });
    MChart.line($('cta-ks'), { series: [ser(T.kospi.series, 'KOSPI 추정 포지션 (%)'), ser(T.kospi.px, 'KOSPI', { axis: 'r', color: 'var(--c5)', width: 1.2 })], hlines: [{ y: 0, label: '0' }], dec: 0, decR: 0, height: 220 });

    $('volctl').innerHTML = `<h2>변동성 제어 펀드 추정 노출 ${use('흐름')} ${asof(V.date)}</h2>
      <p class="sub">변동성이 오르면 주식을 기계적으로 줄이는 자금(변동성 목표 펀드·변액보험 등). 추정 노출 = 목표 변동성 10% ÷ (1개월·3개월 실현 변동성 중 큰 값), 최대 150%.</p>
      <div class="stat"><div><span>추정 주식 노출</span><b>${V.last}%</b></div><div><span>20일 변화</span><b class="${MU.sgn(V.d20)}">${pm(V.d20, 0, '%p')}</b></div><div><span>S&P500 실현 변동성</span><b>${num(V.rv1, 1)}%</b> <span>1개월 · 3개월 ${num(V.rv3, 1)}%</span></div><div><span>3년 중 위치</span><b>하위 ${V.pct}%</b></div></div>
      <div class="read">지금 읽으면 — 노출 <b>${V.last}%</b>, 20일 동안 <b>${pm(V.d20, 0, '%p')}</b>: ${V.d20 <= -20 ? '<b>변동성이 올라 기계적으로 주식을 줄인 구간</b>. 이 매도는 변동성이 가라앉아야 되돌아온다 — 1개월 변동성이 3개월 아래로 내려오는 때를 본다' : V.d20 >= 20 ? '변동성이 가라앉아 주식을 다시 채우는 구간(기계적 매수)' : '큰 변화 없음'}.
        ${V.rv1 > V.rv3 ? `지금은 1개월 변동성(${num(V.rv1, 1)}%)이 3개월(${num(V.rv3, 1)}%)보다 높아 <b>아직 줄이는 쪽</b>이다.` : '1개월 변동성이 3개월보다 낮아 되채우는 쪽이다.'}</div>
      <div class="ch narrow"></div>`;
    MChart.line($('volctl').querySelector('.ch'), { series: [ser(V.series, '추정 노출 (%)'), ser(T.spx.px, 'S&P500', { axis: 'r', color: 'var(--c5)', width: 1.2 })], hlines: [{ y: 100, label: '100%' }], dec: 0, decR: 0, height: 220 });
  }

  // DIX
  $('dix').innerHTML = `<h2>DIX — 다크풀 매수 비중 ${use('타이밍')} ${asof(X.date)}</h2><p class="sub">미국 장외(다크풀) 거래 중 '공매도로 표시된' 비중. 시장조성자가 매수 주문을 받아 줄 때 공매도로 찍히므로, 높으면 장외에서 사는 쪽이 많다는 뜻.</p>
    <div class="stat"><div><span>DIX</span><b>${num(X.last, 1)}%</b></div><div><span>5일 평균</span><b>${num(X.avg5, 1)}%</b></div><div><span>3년 중 위치</span><b>하위 ${X.pct}%</b></div></div>
    <div class="read">지금 읽으면 — 5일 평균 <b>${num(X.avg5, 1)}%</b>: ${X.avg5 >= 45 ? '<b>45% 이상</b>, 장외에서 꾸준히 받아 가는 중(매수 우위)' : X.avg5 <= 40 ? '40% 아래, 장외 매수가 약하다' : '40~45% 사이, 중립'}.</div><div class="ch"></div>`;
  MChart.line($('dix').querySelector('.ch'), { series: [ser(X.avg5_s, 'DIX 5일 평균 (%)'), ser(X.spx, 'S&P500', { axis: 'r', color: 'var(--c5)', width: 1.2 })], hlines: [{ y: 45, label: '45' }], dec: 1, decR: 0, height: 220 });

  // GEX
  $('gex').innerHTML = `<h2>GEX — 딜러 감마 ${use('흐름')} ${asof(X.date)}</h2><p class="sub">옵션을 판 딜러가 지수 1% 움직임에 맞춰 사고팔아야 하는 금액(추정). 양수면 딜러가 움직임을 눌러 주고, 음수면 키운다.</p>
    <div class="stat"><div><span>GEX</span><b class="${X.gex < 0 ? 'down' : ''}">${num(X.gex)}</b> 십억달러</div><div><span>3년 중 위치</span><b>하위 ${X.gex_pct}%</b></div></div>
    <div class="read">지금 읽으면 — GEX <b>${num(X.gex)}</b>: ${X.gex < 0 ? '<b>음수</b> — 딜러가 내릴 때 팔고 오를 때 사야 해서 하루 변동폭이 커지는 구간' : X.gex_pct <= 15 ? '양수지만 3년 중 낮은 편 — 변동을 눌러 주는 힘이 약하다(하루 등락이 커지기 쉽다)' : '양수 — 딜러가 변동을 눌러 주는 구간(하루 등락이 작다)'}.</div><div class="ch"></div>`;
  $('dixev').innerHTML = `<h2>과거 근거 — DIX·GEX 신호 뒤 S&P500 ${use('타이밍')}</h2><p class="sub">2011년 이후.</p>${MU.evidence([['DIX 5일 평균 45% 이상', X.ev45], ['GEX 음수', X.ev_gexneg]], 'S&P500')}
    <div class="read">지금 읽으면 — 두 신호 모두 아무 날보다 조금 나은 정도다(미국 지수는 아무 날에 사도 많이 올랐다). <b>사는 근거라기보다 '팔 자리는 아니다'를 확인하는 용도</b>로 쓴다.</div>`;
  MChart.line($('gex').querySelector('.ch'), { zero: true, series: [ser(X.gex_s, 'GEX (십억달러)', { bars: true, color: 'var(--c3)' }), ser(X.spx, 'S&P500', { axis: 'r', color: 'var(--c5)', width: 1.2 })], dec: 1, decR: 0, height: 220 });
})();
