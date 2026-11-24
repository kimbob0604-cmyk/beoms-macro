// 오늘(흐름): 국면 · 신호 요약 · 오늘 바뀐 것 · 전일 미국 → 한국 · 크로스에셋 표
(async () => {
  MU.shell('today');
  const { num, chg, use, asof, esc } = MU;
  let T, M, S;
  try { [T, M, S] = await Promise.all([MU.get('today.json'), MU.get('monitor.json'), MU.get('status.json')]); } catch (e) { return MU.fail(e); }
  MU.built(T.built);

  // 늦은 자료 경고
  const bad = Object.entries(S.jobs).filter(([, j]) => !j.ok);
  if (S.stale.length || bad.length) {
    document.getElementById('stale').innerHTML = `<div class="alert">${bad.length ? `수집 실패: ${bad.map(([k, j]) => `${esc(k)} (${esc(j.at)})`).join(', ')}. ` : ''}${S.stale.length ? `갱신이 늦은 지표 ${S.stale.length}개: ${S.stale.slice(0, 6).map(s => `${esc(s.name)} ${esc(s.asof)}`).join(', ')}${S.stale.length > 6 ? ' …' : ''}` : ''}</div>`;
  }

  // 국면
  const R = T.regime;
  const cells = [['순항', '추세 따라가기, 섹터 선택이 중요', 1, 1], ['과열·균열', '신규 매수 자제, 크레딧 주시', 1, 0], ['눌림', '타이밍 신호의 무게가 가장 큼', 0, 1], ['위기', '과매도 신호가 일찍 켜진다 — 확인 뒤에', 0, 0]];
  const cell = ([n, d]) => `<div class="cell${R.cell === n ? ' now' : R.cell_prev === n ? ' was' : ''}"><b>${n}${R.cell === n ? ' ← 지금' : R.cell_prev === n ? ' (한 달 전)' : ''}</b><span>${d}</span></div>`;
  const parts = o => Object.entries(o).map(([k, v]) => `${esc(k)} <b>${v ?? '–'}</b>`).join(' · ');
  document.getElementById('regime').innerHTML = `<h2>국면 ${use('비중')}</h2>
    <p class="sub">위험선호와 유동성·크레딧을 각각 최근 2년 백분위(0~100)로 본다. 50이 기준.</p>
    <div class="regime"><div></div><div class="ax">유동성·크레딧 양호 (≥50)</div><div class="ax">유동성·크레딧 악화 (&lt;50)</div>
      <div class="ax">위험선호 높음<br>(≥50)</div>${cell(cells[0])}${cell(cells[1])}
      <div class="ax">위험선호 낮음<br>(&lt;50)</div>${cell(cells[2])}${cell(cells[3])}</div>
    <div class="read">지금 읽으면 — 위험선호 <b>${R.risk}</b> (한 달 전 ${R.risk_prev}), 유동성·크레딧 <b>${R.liq}</b> (한 달 전 ${R.liq_prev}) → <b>${esc(R.cell)}</b>${R.cell !== R.cell_prev ? ` (한 달 전 ${esc(R.cell_prev)}에서 이동)` : ''}</div>
    <p class="small muted" style="margin-top:8px">위험선호 구성(각 0~100): ${parts(R.risk_parts)}</p><p class="small muted">유동성·크레딧 구성: ${parts(R.liq_parts)}</p>
    <p class="note">유동성·크레딧 축은 신용 스프레드·연준 순유동성·금융여건·달러·실질금리로 계산한다(<a class="lnk" href="weight.html">비중 탭</a>). 국면별 주식 비중은 사이트가 정하지 않는다 — 비중 탭의 '내 비중표'에 직접 적는다.</p>`;

  // 신호 요약
  const B = T.bottom, H = T.hot;
  document.getElementById('signals').innerHTML = `<h2>과매도·과열 신호 ${use('타이밍')}</h2><p class="sub">한국 시장 전체 기준. 자세한 내용과 과거 근거는 타이밍 탭.</p>
    <div class="grid2" style="margin:0"><div><div class="muted small">바닥 신호</div><div class="big">${B.count}<small> / ${B.max}</small></div><p class="small">${B.on.length ? B.on.map(esc).join('<br>') : '<span class="muted">켜진 조건 없음</span>'}</p></div>
    <div><div class="muted small">과열 신호</div><div class="big">${H.count}<small> / ${H.max}</small></div><p class="small">${H.on.length ? H.on.map(esc).join('<br>') : '<span class="muted">켜진 조건 없음</span>'}</p></div></div>
    ${T.fg ? `<div class="kv" style="margin-top:12px">${T.fg.kr ? `<div><span>한국판 공탐지수</span> <b>${num(T.fg.kr.last, 0)}</b></div>` : ''}${T.fg.cnn ? `<div><span>CNN 공탐지수</span> <b>${num(T.fg.cnn.last, 0)}</b></div>` : ''}${T.fg.stress ? `<div><span>AI 크레딧 스트레스</span> <b>${num(T.fg.stress.last, 0)}</b> <a class="lnk small" href="credit.html">보기</a></div>` : ''}</div>` : ''}
    ${T.ib ? `<div class="kv"><div><span>위험선호 지수(RAI식)</span> <b>${MU.pm(T.ib.rai.last, 2, '')}</b></div><div><span>200일선 위인 나라</span> <b>${num(T.ib.gb.last, 0)}%</b></div><div><span>패닉/유포리아식</span> <b>${num(T.ib.pe.last, 0)}</b></div><div><span>CTA 추정 주식 포지션</span> <b>${MU.pm(T.ib.cta.last, 0)}</b> <a class="lnk small" href="ib.html">IB 지표판</a></div></div>` : ''}
    <p class="note"><a href="timing.html" style="text-decoration:underline">타이밍 탭에서 조건별 값과 신호 뒤 수익률 보기 →</a></p>`;

  // 오늘 바뀐 것
  const mv = T.movers.map(m => `<li>${use('흐름')}<span><b>${esc(m.name)}</b> ${chg(m.d1, m.diff)} — 평소의 ${num(Math.abs(m.z), 1)}배 움직임 <span class="muted small">(${esc(MU.md(m.date))})</span></span></li>`).join('');
  const ch = T.changes.map(c => `<li>${use(c.use)}<span>${esc(c.text)} <span class="muted small">(${esc(MU.md(c.date))})</span></span></li>`).join('');
  document.getElementById('changes').innerHTML = `<h2>오늘 바뀐 것</h2><p class="sub">기준선을 넘은 지표와, 하루 변화가 최근 1년 평소(표준편차)의 2배를 넘은 지표.</p>
    <ul class="chg-list">${ch + mv || '<li class="muted">기준선을 넘거나 크게 움직인 지표가 없다.</li>'}</ul>`;

  // 전일 미국 → 한국
  const U = T.us2kr, k = U.kospi;
  const rows = ['px:ndx', 'px:spx', 'px:sox'].map(key => { const u = U[key]; return `<tr><td>${esc(u.name)}</td><td>${chg(u.us_chg)}</td><td>${num(u.beta)}</td><td>${num(u.corr)}</td><td>${chg(u.implied)}</td></tr>`; }).join('');
  const c = U['px:ndx'].corr;
  document.getElementById('us2kr').innerHTML = `<h2>전일 미국 → 한국 ${use('흐름')} ${asof(U['px:ndx'].us_date)}</h2>
    <p class="sub">최근 60일 동안 KOSPI가 직전 미국 장을 얼마나 따라갔나.</p>
    <table class="tbl"><thead><tr><th>미국 (직전 장)</th><th>등락</th><th>민감도</th><th>상관</th><th>민감도 × 등락</th></tr></thead><tbody>${rows}</tbody></table>
    <div class="read">지금 읽으면 — 나스닥과의 상관 <b>${num(c)}</b>: ${c >= 0.5 ? '한국장이 미국을 강하게 따라가는 구간(매크로가 끄는 장)' : c >= 0.3 ? '미국 영향이 보통인 구간' : '미국과 따로 움직이는 구간 — 국내 요인·업종 장세에 무게'}.
      ${k.after_us ? `KOSPI ${esc(MU.md(k.date))} 실제 등락 ${chg(k.chg)}.` : `KOSPI 최근 종가는 ${esc(MU.md(k.date))} (${chg(k.chg)}) — 미국 장 이전.`}</div>
    <p class="note">'민감도 × 등락'은 과거 60일의 평균 관계를 곱한 값일 뿐 예측이 아니다.</p>`;

  // 크로스에셋 표
  let body = '';
  for (const g of M.groups) {
    const rs = M.rows.filter(r => r.grp === g);
    if (!rs.length) continue;
    body += `<tr class="grp"><td colspan="10">${esc(g)}</td></tr>` + rs.map(r => `<tr class="click" data-k="${r.k.replace(':', '_')}"><td>${esc(r.name)}</td><td class="b">${num(r.last, r.dec)}</td><td>${chg(r.d1, r.diff)}</td><td>${chg(r.w1, r.diff)}</td><td>${chg(r.m1, r.diff)}</td><td>${chg(r.ytd, r.diff)}</td>
      <td class="${Math.abs(r.z ?? 0) >= 2 ? 'zbig ' + MU.sgn(r.z) : 'muted'}">${r.z == null ? '–' : (r.z > 0 ? '+' : '') + num(r.z, 1)}</td><td>${MU.pos(r.pos)}</td><td>${MU.spark(r.spark)}</td><td class="muted small">${esc(MU.md(r.date))}</td></tr>`).join('');
  }
  document.getElementById('monitor').innerHTML = `<h2>크로스에셋 모니터 ${use('흐름')}</h2>
    <p class="sub">금리·변동성은 차이(포인트), 나머지는 %. z = 오늘 변화 ÷ 최근 1년 평소 변화. 줄을 누르면 페어 화면에서 KOSPI와 겹쳐 본다.</p>
    <div class="scroll-x"><table class="tbl"><thead><tr><th>지표</th><th>현재</th><th>1일</th><th>1주</th><th>1개월</th><th>연초 대비</th><th>z</th><th>52주 위치</th><th>60일</th><th>기준일</th></tr></thead><tbody>${body}</tbody></table></div>`;
  document.querySelectorAll('#monitor tr.click').forEach(tr => tr.onclick = () => { location.href = `pair.html?a=kr_kospi&b=${tr.dataset.k}`; });

  document.getElementById('foot').innerHTML = `자료: Yahoo Finance · CBOE · KRX Open API · 한국투자증권 API · FRED · ECOS · 금융투자협회 · CFTC · FINRA · 종목 일봉(기존 DB). 계열 ${S.n_series}개, 하루 세 번(08:25·16:40·21:30) 갱신. 이 화면은 정보 정리용이며 매수·매도 권유가 아니다.`;
})();
