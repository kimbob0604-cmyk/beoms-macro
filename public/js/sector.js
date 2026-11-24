// 섹터·스타일: 상대강도 비율, 지역별 수익률, 한국 업종별 과매도 지도(업종을 누르면 같은 화면에서 종목 목록)
(async () => {
  MU.shell('sector');
  const { num, chg, use, asof, esc } = MU;
  let D, K;
  try { [D, K] = await Promise.all([MU.get('sector.json'), MU.get('kr_sector.json')]); } catch (e) { return MU.fail(e); }
  MU.built(D.built);

  // 상대강도 비율
  const rk = r => r == null ? '' : `<span class="bar" style="width:${Math.max(2, r * 0.5)}px;background:${r >= 80 ? 'var(--up)' : r <= 20 ? 'var(--down)' : 'var(--c5)'}"></span> ${r}`;
  document.getElementById('ratios').innerHTML = `<h2>상대강도 비율 ${use('섹터')} ${asof(D.ratios[0].date)}</h2>
    <p class="sub">A ÷ B 가 오르면 A 쪽이 주도. '위치'는 60일 변화가 최근 2년 중 몇 번째인지(100 = 가장 강한 상승). 줄을 누르면 오른쪽에 추이.</p>
    <table class="tbl"><thead><tr><th>비율</th><th>20일</th><th>60일</th><th>위치</th></tr></thead>
    <tbody>${D.ratios.map((r, i) => `<tr class="click" data-i="${i}"><td class="l"><b>${esc(r.name)}</b><br><span class="muted small">${esc(r.read)}</span></td><td>${chg(r.c20, false, 1)}</td><td>${chg(r.c60, false, 1)}</td><td>${rk(r.rank)}</td></tr>`).join('')}</tbody></table>`;
  const show = i => {
    const r = D.ratios[i];
    document.querySelectorAll('#ratios tr.click').forEach(tr => tr.classList.toggle('sel', +tr.dataset.i === i));
    const el = document.getElementById('ratio-chart');
    const word = r.rank == null ? '' : r.rank >= 80 ? '최근 2년 중 강한 상승 쪽' : r.rank <= 20 ? '최근 2년 중 강한 하락 쪽' : '뚜렷한 쏠림 없음';
    el.innerHTML = `<h2>${esc(r.name)} ${use('섹터')}</h2><div class="read">지금 읽으면 — 60일 변화 ${chg(r.c60, false, 1)} (위치 ${r.rank ?? '–'}): <b>${word}</b>. ${esc(r.read)}.</div><div class="ch"></div>
      <p class="note"><a href="pair.html?a=${r.a.replace(':', '_')}&b=${r.b.replace(':', '_')}" style="text-decoration:underline">두 계열을 페어 화면에서 겹쳐 보기 →</a></p>`;
    MChart.line(el.querySelector('.ch'), { series: [{ name: r.name, d: r.d, v: r.v }], height: 300, dec: 3 });
  };
  document.querySelectorAll('#ratios tr.click').forEach(tr => tr.onclick = () => show(+tr.dataset.i));
  show(0);

  // 지역
  const reg = [...D.regions].sort((a, b) => (b.m1 ?? -99) - (a.m1 ?? -99));
  document.getElementById('regions').innerHTML = `<h2>지역·지수 수익률 ${use('섹터')} ${use('흐름')}</h2><p class="sub">1개월 수익률 순. 나스닥·대만 강세 = AI·반도체, 상하이·항셍 강세 = 중국 소비·소재, 러셀 강세 = 위험선호 확산.</p>
    <div class="scroll-x"><table class="tbl"><thead><tr><th>지수</th><th>1주</th><th>1개월</th><th>3개월</th><th>6개월</th><th>기준일</th></tr></thead>
    <tbody>${reg.map(r => `<tr><td>${esc(r.name)}</td><td>${chg(r.w1, false, 1)}</td><td class="b">${chg(r.m1, false, 1)}</td><td>${chg(r.m3, false, 1)}</td><td>${chg(r.m6, false, 1)}</td><td class="muted small">${esc(MU.md(r.date))}</td></tr>`).join('')}</tbody></table></div>`;

  // 한국 업종별 과매도 지도
  let sortKey = 'adr', asc = true;
  const cols = [['name', '업종'], ['n', '종목 수'], ['adr', 'ADR(20일)'], ['rsi30', 'RSI<30 비율'], ['bblow', '볼밴 하단 이탈'], ['rsi', 'RSI 중앙값'], ['r5', '5일'], ['r20', '20일'], ['r60', '60일']];
  const draw = () => {
    const rows = [...K.sectors].sort((a, b) => (sortKey === 'name' ? a.name.localeCompare(b.name) : (a[sortKey] - b[sortKey])) * (asc ? 1 : -1));
    const low = K.sectors.filter(s => s.adr < 75).length;
    document.getElementById('krmap').innerHTML = `<h2>한국 업종별 과매도 지도 ${use('섹터')} ${use('타이밍')} ${asof(K.asof)}</h2>
      <p class="sub">종목 ${K.n.toLocaleString()}개, 업종 ${K.sectors.length}개. 머리글을 누르면 정렬, 업종을 누르면 아래에 그 업종 종목이 열린다.</p>
      <div class="read">지금 읽으면 — ADR 75 아래(과매도) 업종 <b>${low}개 / ${K.sectors.length}개</b>. 가장 눌린 업종: ${[...K.sectors].sort((a, b) => a.adr - b.adr).slice(0, 4).map(s => `<b>${esc(s.name)}</b>(${s.adr})`).join(', ')}.</div>
      <div class="scroll-x"><table class="tbl"><thead><tr>${cols.map(([k, n]) => `<th data-k="${k}" style="cursor:pointer">${n}${k === sortKey ? (asc ? ' ▲' : ' ▼') : ''}</th>`).join('')}</tr></thead>
      <tbody>${rows.map(s => `<tr class="click" data-n="${esc(s.name)}"><td>${esc(s.name)}</td><td>${s.n}</td><td class="b ${s.adr < 75 ? 'down' : s.adr > 120 ? 'up' : ''}">${num(s.adr, 1)}</td><td>${num(s.rsi30, 1)}%</td><td>${num(s.bblow, 1)}%</td><td>${num(s.rsi, 1)}</td><td>${chg(s.r5, false, 1)}</td><td>${chg(s.r20, false, 1)}</td><td>${chg(s.r60, false, 1)}</td></tr>`).join('')}</tbody></table></div>`;
    document.querySelectorAll('#krmap th').forEach(th => th.onclick = () => { const k = th.dataset.k; if (k === sortKey) asc = !asc; else { sortKey = k; asc = k !== 'rsi30' && k !== 'bblow'; } draw(); });
    document.querySelectorAll('#krmap tr.click').forEach(tr => tr.onclick = () => stocks(tr.dataset.n));
  };
  const stocks = name => {
    const s = K.sectors.find(x => x.name === name), el = document.getElementById('stocks');
    el.hidden = false;
    el.innerHTML = `<h2>${esc(name)} — 종목 (시총 순, 최대 40개) ${use('섹터')}</h2><p class="sub">%B = 볼린저 밴드 안 위치(0 아래 = 하단 밖). 종목을 누르면 KOSPI와 겹쳐 본다(시총 상위 400종목만 계열이 있다).</p>
      <div class="scroll-x"><table class="tbl"><thead><tr><th>종목</th><th>시총(억)</th><th>종가</th><th>1일</th><th>20일</th><th>RSI</th><th>%B</th></tr></thead>
      <tbody>${s.stocks.map(x => `<tr class="click" data-c="${x.c}"><td>${esc(x.n)} <span class="muted small">${x.c}</span></td><td>${x.mc == null ? '–' : x.mc.toLocaleString()}</td><td>${x.p.toLocaleString()}</td><td>${chg(x.ch)}</td><td>${chg(x.r20, false, 1)}</td>
        <td class="${x.rsi != null && x.rsi < 30 ? 'down b' : x.rsi > 70 ? 'up b' : ''}">${num(x.rsi, 1)}</td><td class="${x.b != null && x.b < 0 ? 'down b' : x.b > 1 ? 'up b' : ''}">${num(x.b, 2)}</td></tr>`).join('')}</tbody></table></div>`;
    el.querySelectorAll('tr.click').forEach(tr => tr.onclick = () => { location.href = `pair.html?a=kr_${tr.dataset.c}&b=kr_kospi`; });
    el.scrollIntoView({ behavior: 'smooth', block: 'start' });
  };
  draw();
})();
