// AI 크레딧: 스트레스 지수 · 기업별 표(주가 + CDS 보도값, 직접 입력) · 등급별 스프레드 · 사모대출 · 주가
(async () => {
  MU.shell('credit');
  const { num, use, asof, esc, pm } = MU;
  let D;
  try { D = await MU.get('credit.json'); } catch (e) { return MU.fail(e); }
  MU.built(D.built);
  const $ = id => document.getElementById(id);
  const S = D.stress, Z = D.series;
  const ser = (o, name, x = {}) => ({ name, d: o.d, v: o.v, ...x });

  // 스트레스 지수
  const hot = Object.entries(S.parts).filter(([, v]) => v != null && v >= 90).map(([k]) => k);
  $('stress').innerHTML = `<h2>AI 크레딧 스트레스 지수 ${use('비중,섹터')} ${asof(S.date)}</h2><p class="sub">아래 8개 항목이 각각 최근 2년 중 몇 %에 있는지(높을수록 나쁨)를 평균한 값. 0~100.</p>
    <div class="big">${S.last}<small> / 100 · 20일 전 ${S.prev20 ?? '–'}</small></div>${MU.parts(S.parts, 'hi')}
    <div class="read">지금 읽으면 — <b>${S.last}</b>: ${S.last >= 80 ? '<b>경계 구간(80 이상)</b>. AI 설비투자를 빚으로 대는 쪽의 조달 비용이 오르는 중 — AI·반도체 비중을 늘리기보다 지키는 쪽의 신호' : S.last >= 60 ? '평소보다 높다 — 벌어지는 속도를 본다' : S.last <= 30 ? '낮다 — 신용 쪽에서는 AI 투자에 걸림돌이 없다' : '보통 수준'}.
      ${hot.length ? `2년 중 상위 10%에 든 항목: ${hot.map(esc).join(', ')}.` : ''}</div><div class="ch narrow"></div>
    <p class="note">쓰임: 지수가 오르는데 반도체 주가가 버티면 → 주가가 뒤늦게 따라 내릴 위험. 지수가 꺾여 내려오면 → AI 관련주 반등의 조건 하나가 채워진 것. CDS 실제 값이 아니라 대용 지표의 평균이다.</p>`;
  MChart.line($('stress').querySelector('.ch'), { series: [ser(S.series, 'AI 크레딧 스트레스'), ser(Z.smh, '반도체 ETF (SMH)', { axis: 'r', color: 'var(--c5)', width: 1.2 })], hlines: [{ y: 80, label: '80 경계' }], dec: 0, decR: 0, height: 230 });

  // 기업별 표 + CDS 입력(이 브라우저에 저장)
  let mine = [];
  try { mine = JSON.parse(localStorage.getItem('macro.cds') || '[]'); } catch (e) {}
  const save = () => { try { localStorage.setItem('macro.cds', JSON.stringify(mine)); } catch (e) {} };
  const drawNames = () => {
    const rows = D.names.map(n => {
      const my = mine.filter(m => m.key === n.key).sort((a, b) => a.date < b.date ? -1 : 1);
      const all = [n.cds_prev, n.cds, ...my].filter(Boolean).sort((a, b) => a.date < b.date ? -1 : 1);
      const c = all[all.length - 1], p = all[all.length - 2];
      const src = c ? (c.url ? `<a class="lnk" href="${esc(c.url)}" target="_blank" rel="noopener">${esc(c.source)}</a>` : esc(c.source || '내 입력')) : '';
      return `<tr><td class="l"><span class="muted small">${esc(n.grp)}</span><br><b>${esc(n.name)}</b></td><td>${num(n.px)}</td><td>${MU.chg(n.m1, false, 1)}</td><td>${MU.chg(n.m3, false, 1)}</td><td class="${n.dd >= 30 ? 'down b' : ''}">−${num(n.dd, 1)}%</td><td>${MU.spark(n.spark)}</td>
        <td class="b">${c ? `${num(c.bp, 0)}bp` : '<span class="muted">–</span>'}</td><td>${c && p ? pm(c.bp - p.bp, 0, 'bp') : ''}</td><td class="l small muted">${c ? `${esc(c.date)}${c.approx ? ' 무렵' : ''} · ${src}${c.mine ? ` <button class="chip" data-del="${esc(c.id)}">지움</button>` : ''}` : '보도된 값 없음'}</td></tr>`;
    }).join('');
    $('names').innerHTML = `<h2>기업별 — 주가와 5년 CDS ${use('섹터')} ${asof(D.names[0].date)}</h2><p class="sub">주가는 매일 자동. CDS 는 기사에 나온 값(가장 최근 것)과 그 직전 값의 차이. 같은 회사라도 기사마다 집계 기관이 달라 몇 bp 는 어긋난다.</p>
      <div class="scroll-x"><table class="tbl"><thead><tr><th>기업</th><th>주가($)</th><th>1개월</th><th>3개월</th><th>52주 고점 대비</th><th>120일</th><th>5년 CDS</th><th>직전 대비</th><th class="l">날짜 · 출처</th></tr></thead><tbody>${rows}</tbody></table></div>
      <div class="inp-row"><b>CDS 값 적어 두기</b><select id="c-key">${D.names.map(n => `<option value="${n.key}">${esc(n.name)}</option>`).join('')}</select>
        <input type="date" id="c-date" value="${new Date().toISOString().slice(0, 10)}"><input type="number" id="c-bp" placeholder="bp" style="width:90px"><input type="text" id="c-src" placeholder="출처 (예: 블룸버그 기사)" style="width:220px"><button class="btn" id="c-add">추가</button></div>
      <p class="note">여기서 추가한 값은 이 브라우저에만 남는다. 계속 쌓으려면 프로젝트 폴더의 <code>cds_input.json</code> 에 한 줄 추가하면 다음 갱신부터 모든 화면에 반영된다. 읽는 법: 100bp 아래 = 우량, 300bp 안팎 = 투기등급 경계, 1,000bp 이상 = 부도 위험을 진지하게 가격에 넣는 수준.</p>`;
    $('c-add').onclick = () => {
      const bp = parseFloat($('c-bp').value), date = $('c-date').value;
      if (!(bp > 0) || !date) return;
      mine.push({ id: String(Date.now()), key: $('c-key').value, date, bp, source: $('c-src').value.trim() || '내 입력', mine: true });
      save(); drawNames();
    };
    $('names').querySelectorAll('[data-del]').forEach(b => b.onclick = () => { mine = mine.filter(m => m.id !== b.dataset.del); save(); drawNames(); });
  };
  drawNames();

  // 등급별 스프레드
  const g = Object.fromEntries(D.grades.map(r => [r.k, r]));
  const gap = g['fred:ccc_oas'].last - g['fred:bb_oas'].last;
  $('grades').innerHTML = `<h2>등급별 스프레드 ${use('비중')} ${asof(D.grades[0].date)}</h2><p class="sub">낮은 등급부터 벌어지면 약한 고리가 먼저 끊어지는 중. 네오클라우드 회사채는 B~CCC 대에 있다.</p>
    <table class="tbl"><thead><tr><th>등급</th><th>스프레드</th><th>20일 변화</th><th>3년 백분위</th></tr></thead><tbody>${D.grades.map(r => `<tr><td>${esc(r.name.replace(' 스프레드', ''))}</td><td class="b">${num(r.last)}%p</td><td>${pm(r.chg * 100, 0, 'bp')}</td><td>${r.pct}${MU.gauge(r.pct, 'hi')}</td></tr>`).join('')}</tbody></table>
    <div class="read">지금 읽으면 — CCC <b>${num(g['fred:ccc_oas'].last)}%p</b> (3년 중 상위 ${100 - g['fred:ccc_oas'].pct}%), BB <b>${num(g['fred:bb_oas'].last)}%p</b>. CCC − BB 차이 <b>${num(gap)}%p</b>:
      ${g['fred:ccc_oas'].pct >= 90 && g['fred:bb_oas'].pct < 90 ? '<b>가장 약한 등급만 따로 벌어지는 중</b> — 전체 위기라기보다 약한 회사 골라내기' : g['fred:bb_oas'].pct >= 90 ? '<b>윗등급까지 같이 벌어지는 중</b> — 신용시장 전체의 위험 회피' : '등급 간 차이가 평소 범위'}.</div><div class="ch"></div>`;
  MChart.line($('grades').querySelector('.ch'), { series: [ser(Z.hy, '하이일드 전체'), ser(Z.ccc, 'CCC', { axis: 'r', color: 'var(--c6)' })], dec: 2, decR: 1, height: 220 });

  // 사모대출
  const e = Object.fromEntries(D.etf.map(r => [r.k, r]));
  $('private').innerHTML = `<h2>사모대출 · 레버리지론 ${use('비중')} ${asof(D.etf[0].date)}</h2><p class="sub">AI 데이터센터 자금의 큰 몫이 사모대출에서 나온다. BDC(사모대출 회사) 주가가 그 시장의 체온계다.</p>
    <table class="tbl"><thead><tr><th>ETF</th><th>가격</th><th>60일 수익률</th><th>3년 중 위치</th></tr></thead><tbody>${D.etf.map(r => `<tr><td>${esc(r.name)}</td><td class="b">${num(r.last)}</td><td>${MU.chg(r.chg, false, 1)}</td><td>${r.pct}${MU.gauge(r.pct, 'lo')}</td></tr>`).join('')}</tbody></table>
    <div class="read">지금 읽으면 — BDC ETF 60일 <b>${pm(e['px:bizd'].chg)}</b>, 레버리지론 ETF <b>${pm(e['px:bkln'].chg)}</b>:
      ${e['px:bizd'].chg <= -5 && e['px:bkln'].chg > -1 ? '<b>사모대출 쪽만 빠진다</b> — 대출채권 자체보다 사모대출 회사의 부실 걱정이 가격에 들어가는 중' : e['px:bizd'].chg <= -5 ? '<b>둘 다 빠진다</b> — 대출시장 전체가 위험 회피' : '큰 스트레스 없음'}.</div><div class="ch"></div>`;
  MChart.line($('private').querySelector('.ch'), { series: [ser(Z.bizd, 'BDC ETF (BIZD)'), ser(Z.bkln, '레버리지론 ETF (BKLN)', { axis: 'r', color: 'var(--c2)' })], dec: 1, decR: 1, height: 220 });

  // 주가
  $('eq').innerHTML = `<h2>빚이 많은 쪽의 주가 ${use('섹터')}</h2><p class="sub">오라클(하이퍼스케일러 중 부채 부담이 가장 큰 곳)과 코어위브(네오클라우드). CDS 가 벌어질 때 주가가 먼저 움직이는 일이 많다.</p><div class="ch narrow"></div>
    <p class="note"><a class="lnk" href="pair.html?a=px_orcl&b=px_crwv">오라클 vs 코어위브</a> · <a class="lnk" href="pair.html?a=kr_000660&b=px_crwv">SK하이닉스 vs 코어위브</a> · <a class="lnk" href="pair.html?a=px_smh&b=credit_ai_stress">반도체 ETF vs 스트레스 지수</a> 를 페어 화면에서 겹쳐 본다.</p>`;
  MChart.line($('eq').querySelector('.ch'), { series: [ser(Z.orcl, '오라클'), ser(Z.crwv, '코어위브', { axis: 'r', color: 'var(--c6)' })], dec: 0, decR: 0, height: 230 });
})();
