// 페어 겹쳐 보기: 두 계열을 이중 축으로 겹치고 상관·선행후행·괴리를 계산한다. 지수 9개 주간 상관 히트맵, 닮은 지표 찾기.
(async () => {
  MU.shell('pair');
  const { num, esc } = MU;
  let CAT;
  try { CAT = await MU.get('catalog.json'); } catch (e) { return MU.fail(e); }
  const byKey = new Map(CAT.map(c => [c.k, c])), byName = new Map(CAT.map(c => [c.name, c]));
  document.getElementById('cat').innerHTML = CAT.map(c => `<option value="${esc(c.name)}">${esc(c.grp)}</option>`).join('');
  const PRESETS = [['SK하이닉스 vs CXMT', 'kr_000660', 'px_cxmt'], ['SK하이닉스 vs 마이크론', 'kr_000660', 'px_mu'], ['삼성전자 vs SK하이닉스', 'kr_005930', 'kr_000660'], ['SK하이닉스 vs 코어위브', 'kr_000660', 'px_crwv'],
    ['KOSPI vs 나스닥', 'kr_kospi', 'px_ndx'], ['KOSPI vs 반도체지수', 'kr_kospi', 'px_sox'], ['KOSPI vs 원/달러', 'kr_kospi', 'px_usdkrw'], ['KOSPI vs 구리', 'kr_kospi', 'px_copper'],
    ['KOSPI vs ADR', 'kr_kospi', 'kr_adr20'], ['KOSPI vs VKOSPI', 'kr_kospi', 'vol_vkospi'], ['S&P500 vs 하이일드 ETF', 'px_spx', 'px_hyg'], ['닛케이 vs 엔/달러', 'px_nikkei', 'px_usdjpy'], ['오라클 vs 코어위브', 'px_orcl', 'px_crwv'],
    ['KOSPI vs 한국 신용잔고', 'kr_kospi', 'kr_credit'], ['KOSPI vs 중국 신용잔고', 'kr_kospi', 'cn_margin'], ['상하이 vs 중국 신용잔고', 'px_shcomp', 'cn_margin'], ['S&P500 vs 하이일드 스프레드', 'px_spx', 'fred_hy_oas'],
    ['나스닥 vs 연준 순유동성', 'px_ndx', 'fred_netliq'], ['반도체 ETF vs AI 크레딧 스트레스', 'px_smh', 'credit_ai_stress'], ['KOSPI vs 한국판 공탐지수', 'kr_kospi', 'sent_krfg'], ['S&P500 vs DIX', 'px_spx', 'flow_dix'],
    ['S&P500 vs 위험선호 지수', 'px_spx', 'ib_rai'], ['S&P500 vs CTA 추정 포지션', 'px_spx', 'cta_spx'], ['KOSPI vs CTA 추정 포지션', 'kr_kospi', 'cta_kospi'], ['KOSPI vs 대차잔고', 'kr_kospi', 'drv_loan_sh'],
    ['KOSPI vs 선물 베이시스', 'kr_kospi', 'drv_k200_basis'], ['KOSPI vs 옵션 풋콜', 'kr_kospi', 'drv_k200_pc_vol'], ['원/달러 vs 통화 스왑 대용', 'px_usdkrw', 'drv_swap_basis'], ['전세계 주식 vs 글로벌 폭', 'px_acwi', 'ib_gb_a200']];
  const PERIODS = [['6개월', 126], ['1년', 252], ['3년', 756], ['전체', 99999]];
  const q = new URLSearchParams(location.search);
  const st = { a: q.get('a') || 'kr_000660', b: q.get('b') || 'px_cxmt', p: +(q.get('p') || 252) };
  if (!byKey.has(st.a)) st.a = 'kr_kospi';
  if (!byKey.has(st.b)) st.b = 'px_ndx';
  const cache = new Map();
  const load = async k => { if (!cache.has(k)) cache.set(k, await MU.get(`s/${k}.json`)); return cache.get(k); };

  // ── 계산 ──
  const mean = a => a.reduce((s, x) => s + x, 0) / a.length;
  function corr(x, y) {
    const n = Math.min(x.length, y.length);
    if (n < 10) return null;
    const mx = mean(x), my = mean(y);
    let sxy = 0, sxx = 0, syy = 0;
    for (let i = 0; i < n; i++) { const a = x[i] - mx, b = y[i] - my; sxy += a * b; sxx += a * a; syy += b * b; }
    return sxx && syy ? sxy / Math.sqrt(sxx * syy) : null;
  }
  const ret = v => v.slice(1).map((x, i) => x / v[i] - 1);
  function align(A, B, n) {      // 같은 날짜에 둘 다 값이 있는 날만
    const mb = new Map(B.d.map((d, i) => [d, B.v[i]]));
    const d = [], a = [], b = [];
    A.d.forEach((x, i) => { const y = mb.get(x); if (y != null && A.v[i] != null && A.v[i] > 0 && y > 0) { d.push(x); a.push(A.v[i]); b.push(y); } });
    const k = Math.max(0, d.length - n);
    return { d: d.slice(k), a: a.slice(k), b: b.slice(k) };
  }
  function weekly(d, v) {         // 주의 마지막 거래일 값
    const out = [], wk = s => { const t = new Date(s + 'T00:00:00Z'); return Math.floor((t.getTime() / 864e5 + 3) / 7); };
    d.forEach((s, i) => { if (i === d.length - 1 || wk(d[i + 1]) !== wk(s)) out.push(v[i]); });
    return out;
  }
  function stats(X) {
    const ra = ret(X.a), rb = ret(X.b);
    const roll = { d: [], v: [] };
    for (let i = 60; i <= ra.length; i++) { roll.d.push(X.d[i]); roll.v.push(corr(ra.slice(i - 60, i), rb.slice(i - 60, i))); }
    const lead = [];
    for (let k = -10; k <= 10; k++) {      // k>0: A가 k일 먼저 → corr(rA[t], rB[t+k])
      const x = k >= 0 ? ra.slice(0, ra.length - k) : ra.slice(-k), y = k >= 0 ? rb.slice(k) : rb.slice(0, rb.length + k);
      lead.push({ k, c: corr(x, y) });
    }
    const mb = mean(rb), ma = mean(ra);
    let cov = 0, vb = 0;
    rb.forEach((y, i) => { cov += (ra[i] - ma) * (y - mb); vb += (y - mb) ** 2; });
    const lr = X.a.map((x, i) => Math.log(x / X.b[i])), gap = { d: [], v: [] };
    for (let i = 120; i <= lr.length; i++) { const w = lr.slice(i - 120, i), m = mean(w), sd = Math.sqrt(mean(w.map(x => (x - m) ** 2))); gap.d.push(X.d[i - 1]); gap.v.push(sd ? (lr[i - 1] - m) / sd : null); }
    return { n: X.d.length, level: corr(X.a, X.b), daily: corr(ra, rb), weekly: corr(ret(weekly(X.d, X.a)), ret(weekly(X.d, X.b))), roll, lead, beta: vb ? cov / vb : null, gap };
  }
  const f2 = v => v == null ? '–' : (v >= 0 ? '+' : '') + num(v, 2);

  // ── 그리기 ──
  async function draw() {
    const [A, B] = await Promise.all([load(st.a), load(st.b)]);
    const X = align(A, B, st.p + 1);
    history.replaceState(null, '', `?a=${st.a}&b=${st.b}&p=${st.p}`);
    document.getElementById('a').value = A.name; document.getElementById('b').value = B.name;
    document.querySelectorAll('#period button').forEach(b => b.classList.toggle('on', +b.dataset.p === st.p));
    if (X.d.length < 30) { document.getElementById('overlay').innerHTML = `<p class="muted">겹치는 날이 ${X.d.length}일뿐이라 계산할 수 없다.</p>`; ['stats', 'read', 'roll', 'lead', 'gap'].forEach(i => document.getElementById(i).innerHTML = ''); return; }
    const S = stats(X);
    MChart.line(document.getElementById('overlay'), { height: 320, series: [{ name: A.name, d: X.d, v: X.a }, { name: B.name, d: X.d, v: X.b, axis: 'r', color: 'var(--c2)' }] });
    const best = S.lead.filter(l => l.c != null).reduce((m, l) => Math.abs(l.c) > Math.abs(m.c) ? l : m, { k: 0, c: 0 });
    const g = S.gap.v[S.gap.v.length - 1];
    document.getElementById('stats').innerHTML = [['수준 상관', f2(S.level)], ['일간 수익률 상관', f2(S.daily)], ['주간 수익률 상관', f2(S.weekly)], ['60일 롤링 (최근)', f2(S.roll.v[S.roll.v.length - 1])],
      ['민감도 (A의 B에 대한 베타)', f2(S.beta)], ['괴리 z (최근)', f2(g)], ['겹친 날', `${S.n}일`], ['기간', `${X.d[0].slice(2)} ~ ${X.d[X.d.length - 1].slice(2)}`]].map(([k, v]) => `<div><span>${k}</span><b>${v}</b></div>`).join('');
    const dl = Math.abs((S.level ?? 0) - (S.daily ?? 0));
    document.getElementById('read').innerHTML = `지금 읽으면 — 일간 수익률 상관 <b>${f2(S.daily)}</b>: ${Math.abs(S.daily ?? 0) >= 0.6 ? '강하게 같이 움직인다' : Math.abs(S.daily ?? 0) >= 0.3 ? '어느 정도 같이 움직인다' : '거의 따로 움직인다'}.
      ${dl >= 0.3 ? `수준 상관(${f2(S.level)})이 훨씬 높은 것은 같은 방향 추세 때문이다 — 그림에서 붙어 보여도 매일의 움직임은 덜 닮았다. ` : ''}
      ${best.k === 0 ? '같은 날의 상관이 가장 높다(뚜렷한 선행 없음).' : `<b>${best.k > 0 ? esc(A.name) : esc(B.name)}</b>이(가) ${Math.abs(best.k)}일 먼저 움직일 때 상관이 가장 높다(${f2(best.c)})${Math.abs(best.c) < 0.3 ? ' — 다만 약해서 우연일 수 있다' : ''}.`}
      ${g != null && Math.abs(g) >= 2 ? ` 괴리 z ${f2(g)}: <b>${g > 0 ? esc(A.name) : esc(B.name)}</b> 쪽이 상대보다 크게 앞서 있다.` : ''}`;
    MChart.line(document.getElementById('roll'), { series: [{ name: '60일 롤링 상관', d: S.roll.d, v: S.roll.v }], hlines: [{ y: 0, label: '0' }], height: 220, dec: 2 });
    MChart.line(document.getElementById('gap'), { series: [{ name: '괴리 z', d: S.gap.d, v: S.gap.v }], hlines: [{ y: 2, label: '+2' }, { y: -2, label: '−2' }, { y: 0, label: '0' }], height: 220, dec: 2 });
    // 선행·후행 막대
    const W = 760, H = 220, L = 40, R = 10, T = 10, Bm = 26, bw = (W - L - R) / 21, Y = c => T + (1 - (c + 1) / 2) * (H - T - Bm);
    let s = `<line class="gl" x1="${L}" x2="${W - R}" y1="${Y(0)}" y2="${Y(0)}"/>`;
    [-1, -0.5, 0.5, 1].forEach(t => { s += `<line class="gl" x1="${L}" x2="${W - R}" y1="${Y(t)}" y2="${Y(t)}"/><text class="ax" x="${L - 6}" y="${Y(t) + 3.5}" text-anchor="end">${t}</text>`; });
    S.lead.forEach((l, i) => {
      if (l.c == null) return;
      const x = L + i * bw + 3;
      s += `<rect x="${x}" y="${Math.min(Y(l.c), Y(0))}" width="${bw - 6}" height="${Math.abs(Y(l.c) - Y(0))}" fill="${l.k === 0 ? 'var(--c5)' : l.k > 0 ? 'var(--c1)' : 'var(--c2)'}" opacity="${l.k === best.k ? 1 : .6}"><title>${l.k}일: ${f2(l.c)}</title></rect>`;
      if (l.k % 2 === 0) s += `<text class="ax" x="${x + (bw - 6) / 2}" y="${H - 8}" text-anchor="middle">${l.k > 0 ? '+' : ''}${l.k}</text>`;
    });
    const el = document.getElementById('lead');
    el.className = 'mc';
    el.innerHTML = `<div class="legend"><span><i style="background:var(--c2)"></i>${esc(B.name)} 먼저 (−)</span><span><i style="background:var(--c1)"></i>${esc(A.name)} 먼저 (+)</span></div><svg viewBox="0 0 ${W} ${H}" role="img" aria-label="선행 후행 교차상관">${s}</svg>`;
    heat();
  }

  // 지수 9개 주간 수익률 상관
  const IDX = ['px_kospi', 'px_kosdaq', 'px_spx', 'px_ndx', 'px_rut', 'px_nikkei', 'px_twii', 'px_hsi', 'px_shcomp'];
  async function heat() {
    const all = await Promise.all(IDX.map(load));
    const W = all.map(s => { const k = Math.max(0, s.d.length - st.p); return { n: s.name, m: new Map(s.d.slice(k).map((d, i) => [d, s.v[k + i]])), d: s.d.slice(k) }; });
    const cell = (i, j) => {
      if (i === j) return 1;
      const d = W[i].d.filter(x => W[j].m.has(x));
      return corr(ret(weekly(d, d.map(x => W[i].m.get(x)))), ret(weekly(d, d.map(x => W[j].m.get(x)))));
    };
    const col = c => c == null ? 'transparent' : `color-mix(in srgb, ${c >= 0 ? 'var(--up)' : 'var(--down)'} ${Math.round(Math.abs(c) * 55)}%, transparent)`;
    document.getElementById('heat').innerHTML = `<h2>주요 지수 상관 — 주간 수익률 ${MU.use('흐름')}</h2><p class="sub">위에서 고른 기간. 주간 수익률을 쓰는 이유: 아시아와 미국은 장 시간이 달라 일간으로는 상관이 낮게 나온다. 칸을 누르면 그 두 지수를 위에서 겹쳐 본다.</p>
      <div class="scroll-x"><table class="tbl"><thead><tr><th></th>${W.map(w => `<th>${esc(w.n)}</th>`).join('')}</tr></thead>
      <tbody>${W.map((w, i) => `<tr><td>${esc(w.n)}</td>${W.map((_, j) => { const c = cell(i, j); return `<td class="click" data-a="${IDX[i]}" data-b="${IDX[j]}" style="background:${col(c)};cursor:pointer">${c == null ? '–' : num(c, 2)}</td>`; }).join('')}</tr>`).join('')}</tbody></table></div>`;
    document.querySelectorAll('#heat td.click').forEach(td => td.onclick = () => { if (td.dataset.a !== td.dataset.b) { st.a = td.dataset.a; st.b = td.dataset.b; draw(); scrollTo({ top: 0, behavior: 'smooth' }); } });
  }

  // 닮은 지표 찾기
  document.getElementById('scan').onclick = async () => {
    const msg = document.getElementById('scan-msg'), A = await load(st.a);
    const pool = [...CAT.filter(c => c.grp !== '한국 종목'), ...CAT.filter(c => c.grp === '한국 종목').slice(0, 100)].filter(c => c.k !== st.a);
    const res = [];
    for (let i = 0; i < pool.length; i += 12) {
      msg.textContent = `${Math.min(i + 12, pool.length)} / ${pool.length}`;
      await Promise.all(pool.slice(i, i + 12).map(async c => {
        try { const X = align(A, await load(c.k), st.p + 1); if (X.d.length >= 60) res.push({ ...c, c: corr(ret(X.a), ret(X.b)), n: X.d.length }); } catch (e) {}
      }));
    }
    msg.textContent = `${res.length}개 계산`;
    const ok = res.filter(r => r.c != null).sort((a, b) => b.c - a.c), row = r => `<tr class="click" data-k="${r.k}"><td>${esc(r.name)}</td><td class="muted small">${esc(r.grp)}</td><td class="b ${MU.sgn(r.c)}">${f2(r.c)}</td><td class="muted small">${r.n}일</td></tr>`;
    document.getElementById('scan-out').innerHTML = `<table class="tbl"><thead><tr><th>계열</th><th>묶음</th><th>일간 수익률 상관</th><th>겹친 날</th></tr></thead>
      <tbody><tr class="grp"><td colspan="4">같이 움직이는 것</td></tr>${ok.slice(0, 12).map(row).join('')}<tr class="grp"><td colspan="4">반대로 움직이는 것</td></tr>${ok.slice(-6).reverse().map(row).join('')}</tbody></table>`;
    document.querySelectorAll('#scan-out tr.click').forEach(tr => tr.onclick = () => { st.b = tr.dataset.k; draw(); scrollTo({ top: 0, behavior: 'smooth' }); });
  };

  // 입력
  document.getElementById('period').innerHTML = PERIODS.map(([n, p]) => `<button data-p="${p}">${n}</button>`).join('');
  document.querySelectorAll('#period button').forEach(b => b.onclick = () => { st.p = +b.dataset.p; draw(); });
  document.getElementById('presets').innerHTML = PRESETS.filter(p => byKey.has(p[1]) && byKey.has(p[2])).map(([n, a, b]) => `<button class="chip" data-a="${a}" data-b="${b}">${esc(n)}</button>`).join('');
  document.querySelectorAll('#presets .chip').forEach(c => c.onclick = () => { st.a = c.dataset.a; st.b = c.dataset.b; draw(); });
  for (const id of ['a', 'b']) {
    const el = document.getElementById(id);
    el.onfocus = () => { el.value = ''; };
    el.onchange = () => { const c = byName.get(el.value); if (c) { st[id] = c.k; draw(); } };
    el.onblur = () => { if (!byName.has(el.value)) el.value = byKey.get(st[id]).name; };
  }
  draw().catch(MU.fail);
})();
