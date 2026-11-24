// 타이밍: 바닥·과열 신호판, 과거 근거(신호 뒤 KOSPI 수익률), 과매도 지표 차트
(async () => {
  MU.shell('timing');
  const { num, use, asof, esc } = MU;
  let D;
  let F = null;
  try { D = await MU.get('timing.json'); } catch (e) { return MU.fail(e); }
  try { F = await MU.get('sentiment.json'); } catch (e) { console.warn(e); }
  MU.built(D.built);
  const S = D.series, B = D.boards, HZ = B.horizons, base = B.base;
  const pm = v => v == null ? '–' : `${v > 0 ? '+' : ''}${num(v, 1)}%`;
  const cls = (v, b) => v == null ? 'muted' : v > b ? 'up' : v < b ? 'down' : '';

  function board(id, b, title, sub) {
    const conds = b.conds.map(c => {
      const a = c.alone['6개월'];
      return `<div class="cond${c.on ? ' on' : ''}"><i class="dot"></i><span class="nm">${esc(c.name)}</span><span class="val">${esc(c.value ?? '')}</span>
        <span class="ev" title="이 조건 하나만 켜졌던 과거 ${c.alone.n}번의 6개월 뒤 KOSPI">단독 ${c.alone.n}번 · 6개월 뒤 ${pm(a.mean)} (${a.win ?? '–'}%)</span></div>`;
    }).join('');
    document.getElementById(id).innerHTML = `<h2>${title} ${use('타이밍')} ${asof(b.date)}</h2><p class="sub">${sub}</p>
      <div class="big">${b.count}<small> / ${b.max} · 전일 ${b.prev}</small></div>${conds}`;
  }
  board('bottom', B.bottom, '바닥 신호판', `과매도 조건 ${B.bottom.max}개 중 켜진 개수 (가격 6개 + 빚 2개: 반대매매·신용잔고)`);
  board('hot', B.hot, '과열 신호판', `과열 조건 ${B.hot.max}개 중 켜진 개수`);

  // 과거 근거
  const head = `<tr><th>켜진 개수</th><th>횟수</th>${HZ.map(h => `<th>${h} 뒤 평균</th><th>오른 비율</th>`).join('')}<th class="l">최근 발생</th></tr>`;
  const line = (label, x, now) => `<tr class="${now ? 'sel' : ''}"><td>${label}</td><td>${x.n}</td>${HZ.map(h => `<td class="${cls(x[h].mean, base[h].mean)}">${pm(x[h].mean)}</td><td>${x[h].win ?? '–'}%</td>`).join('')}<td class="l small muted">${(x.dates || []).slice(-3).join(', ')}</td></tr>`;
  const baseRow = `<tr class="grp"><td>아무 날이나 샀을 때 (비교 기준)</td><td></td>${HZ.map(h => `<td>${pm(base[h].mean)}</td><td>${base[h].win}%</td>`).join('')}<td></td></tr>`;
  const b6 = B.bottom.by_count.find(x => x.k === Math.max(1, B.bottom.count)) || B.bottom.by_count[0];
  const better = HZ.filter(h => b6[h].mean != null && b6[h].mean > base[h].mean).length;
  // 신호판 전체가 비교 기준을 얼마나 이기는지: (개수 × 기간) 칸 중 평균이 기준보다 높은 비율, 조건 하나씩은 6개월 기준
  const cellsAll = B.bottom.by_count.filter(x => x.n >= 10).flatMap(x => HZ.map(h => x[h].mean != null && x[h].mean > base[h].mean));
  const winShare = cellsAll.length ? Math.round(cellsAll.filter(Boolean).length / cellsAll.length * 100) : null;
  const strong = B.bottom.conds.filter(c => c.alone.n >= 10 && c.alone['6개월'].mean != null && c.alone['6개월'].mean - base['6개월'].mean >= 3).map(c => `${c.name}(6개월 뒤 ${pm(c.alone['6개월'].mean)}, ${c.alone.n}번)`);
  const verdict = winShare == null ? '' : `표본 10번 이상인 칸 중 <b>${winShare}%</b>만 비교 기준을 이겼다 → ${winShare >= 70 ? '과거에는 꽤 잘 맞은 신호다' : winShare >= 50 ? '기준보다 조금 나은 정도라 <b>참고용</b>으로 본다' : '아무 날이나 산 것과 차이가 없어 <b>참고용</b>이다(이 기간 KOSPI가 크게 올라 비교 기준이 높다)'}.
      ${strong.length ? `조건 하나만 봤을 때 차이가 큰 것: ${strong.join(', ')}.` : '조건 하나만으로 기준을 3%p 넘게 이긴 것은 없다.'}`;
  document.getElementById('evidence').innerHTML = `<h2>과거 근거 — 신호 뒤 KOSPI 수익률 ${use('타이밍')}</h2>
    <p class="sub">${esc(B.since)} 이후. 조건이 그 개수 이상 켜진 날(20거래일 안의 반복은 한 번으로) 뒤의 KOSPI 수익률. 빨강 = 아무 날이나 샀을 때보다 좋음, 파랑 = 나쁨.</p>
    <div class="scroll-x"><table class="tbl"><thead>${head}</thead><tbody>${baseRow}
      <tr class="grp"><td colspan="${3 + HZ.length * 2}">바닥 신호 (과매도)</td></tr>${B.bottom.by_count.map(x => line(`${x.k}개 이상`, x, x.k === B.bottom.count)).join('')}
      <tr class="grp"><td colspan="${3 + HZ.length * 2}">과열 신호</td></tr>${B.hot.by_count.map(x => line(`${x.k}개 이상`, x, x.k === B.hot.count)).join('')}</tbody></table></div>
    <div class="read">지금 읽으면 — 바닥 신호 <b>${B.bottom.count}개</b>. ${B.bottom.count ? `과거 ${b6.k}개 이상 켜진 ${b6.n}번을 보면, ${HZ.length}개 기간 중 <b>${better}개</b>에서 비교 기준(아무 날이나 샀을 때)보다 평균 수익률이 높았다.` : ''}
      ${verdict}</div>
    <p class="note">표본이 적은 칸(횟수 10 미만)은 우연일 수 있다. 12개월 뒤 수익률은 아직 1년이 안 지난 최근 신호를 빼고 계산한다.</p>`;

  // 공탐지수
  if (F) {
    const meter = v => `<div class="meter"><i style="left:${v}%"></i><span style="left:12%">극단 공포</span><span style="left:50%">중립</span><span style="left:88%">극단 탐욕</span></div>`;
    const K = F.kr, C = F.cnn, P = F.pc;
    const kEl = document.getElementById('fg-kr');
    kEl.innerHTML = `<h2>한국판 공탐지수 ${use('타이밍')} ${asof(K.date)}</h2><p class="sub">아래 8개 항목이 각각 최근 2년 중 몇 %에 있는지(0 = 공포, 100 = 탐욕)를 평균한 값. CNN 지수와 같은 방식으로 직접 만든다.</p>
      <div class="big">${num(K.last, 0)}<small> / 100 · ${esc(K.word)}</small></div>${meter(K.last)}${MU.parts(K.parts, 'lo')}
      <div class="read">지금 읽으면 — <b>${num(K.last, 0)} (${esc(K.word)})</b>: ${K.last <= 20 ? '<b>20 아래</b>. 대부분의 항목이 2년 중 바닥권 — 다만 아래 과거 근거처럼 이 지수만으로는 반등을 맞히지 못했다' : K.last >= 80 ? '<b>80 위</b>, 탐욕 구간' : '극단이 아니다 — 이 지수는 20 아래·80 위에서만 본다'}.</div><div class="ch"></div>`;
    MChart.line(kEl.querySelector('.ch'), { from: K.series.d[Math.max(0, K.series.d.length - 500)], series: [{ name: '한국판 공탐지수', d: K.series.d, v: K.series.v }, { name: 'KOSPI', d: S['kr:kospi'].d, v: S['kr:kospi'].v, axis: 'r', color: 'var(--c5)', width: 1.2 }], hlines: [{ y: 20, label: '20' }, { y: 80, label: '80' }], dec: 0, decR: 0, height: 220 });
    const uEl = document.getElementById('fg-us');
    uEl.innerHTML = C ? `<h2>CNN 공탐지수 (미국) ${use('타이밍')} ${asof(C.date)}</h2><p class="sub">미국 주식시장의 심리. 7개 항목 평균, 25 아래 = 극단 공포 · 75 위 = 극단 탐욕.</p>
      <div class="big">${num(C.last, 0)}<small> / 100 · ${esc(C.word)}</small></div>${meter(C.last)}${MU.parts(C.parts, 'lo')}
      <div class="read">지금 읽으면 — <b>${num(C.last, 0)} (${esc(C.word)})</b>: ${C.last < 25 ? '<b>극단 공포</b> — 역발상 매수 검토 구간' : C.last < 45 ? '공포 쪽이지만 극단(25 아래)은 아니다' : C.last > 75 ? '<b>극단 탐욕</b> — 신규 매수 자제' : '극단이 아니다'}.
        크립토 공탐지수 <b>${F.crypto.last ?? '–'}</b> (${esc(F.crypto.word || '')}).
        ${P.pc_equity ? `미국 풋콜 비율(${esc(MU.md(P.pc_equity.date))}): 주식 <b>${num(P.pc_equity.last)}</b> · 전체 ${num(P.pc_total.last)} · 지수 ${num(P.pc_index.last)} — 주식 풋콜이 1.0 을 넘으면 공포.` : ''}</div><div class="ch"></div>
      <p class="note">CNN 은 공식 자료 주소가 아니라서 끊길 수 있다(끊기면 '늦음' 표시). 풋콜 비율은 CBOE 가 과거 값을 내주지 않아 오늘부터 하루씩 쌓는다(${P.pc_equity ? P.pc_equity.n : 0}일치).</p>` : '<h2>CNN 공탐지수</h2><p class="muted">자료 없음</p>';
    if (C) MChart.line(uEl.querySelector('.ch'), { series: [{ name: 'CNN 공탐지수', d: C.series.d, v: C.series.v }], hlines: [{ y: 25, label: '25' }, { y: 75, label: '75' }], dec: 0, height: 220 });
    const beat = e => ['1개월', '3개월', '6개월', '12개월'].filter(h => e[h].mean != null && e[h].mean > e[h].base).length;
    document.getElementById('fg-ev').innerHTML = `<h2>과거 근거 — 한국판 공탐지수 극단 뒤 KOSPI ${use('타이밍')}</h2><p class="sub">2012년 이후. 지수가 20 아래·80 위로 간 날 뒤의 KOSPI.</p>
      ${MU.evidence([['공탐지수 20 이하 (극단 공포)', K.fear], ['공탐지수 80 이상 (극단 탐욕)', K.greed]])}
      <div class="read">지금 읽으면 — 극단 공포 뒤에는 네 기간 중 <b>${beat(K.fear)}개</b>에서만 아무 날보다 나았다 → ${beat(K.fear) >= 3 ? '과거에는 역발상 매수가 통했다' : '<b>공포라는 이유만으로 사서는 이기지 못했다.</b> 떨어지는 장에서 먼저 켜지기 때문이다. 지수가 20 아래에서 <b>되돌아 올라오는 날</b>과 신호판을 같이 본다'}.
        극단 탐욕 뒤에는 ${beat(K.greed)}개에서 아무 날보다 나았다${beat(K.greed) >= 3 ? ' — <b>탐욕은 파는 신호가 아니었다</b>(강한 장이 이어진 경우가 많다)' : ''}.</div>`;
  }

  const now = D.now, pct = D.pct;
  const card = (id, title, read, draw, date) => { const el = document.getElementById(id); el.innerHTML = `<h2>${title} ${use('타이밍')} ${asof(date || D.asof)}</h2><div class="read">지금 읽으면 — ${read}</div><div class="ch"></div>`; draw(el.querySelector('.ch')); };
  const ser = (k, name, o = {}) => ({ name, d: S[k].d, v: S[k].v, ...o });
  const from = S['kr:kospi'].d[Math.max(0, S['kr:kospi'].d.length - 500)];

  card('c-adr', 'ADR (20일 등락비율)', `<b>${num(now['kr:adr20'], 1)}</b> (KOSPI ${num(now['kr:adr20:kospi'], 1)} · KOSDAQ ${num(now['kr:adr20:kosdaq'], 1)}) — ${now['kr:adr20'] < 75 ? '75 아래, <b>과매도 구간</b>' : now['kr:adr20'] > 120 ? '120 위, <b>과열 구간</b>' : '75~120 사이, 중립'}. 최근 3년 중 하위 ${pct['kr:adr20']}%.`,
    el => MChart.line(el, { from, series: [ser('kr:adr20', 'ADR 20일'), ser('kr:kospi', 'KOSPI', { axis: 'r', color: 'var(--c5)', width: 1.2 })], hlines: [{ y: 75, label: '75 과매도' }, { y: 120, label: '120 과열' }], decR: 0 }));

  card('c-breadth', '볼밴 하단 이탈 · RSI 과매도 · 신저가 비율', `볼밴 하단 이탈 <b>${num(now['kr:bblow'], 1)}%</b> (3년 중 상위 ${100 - pct['kr:bblow']}%) · RSI 30 미만 <b>${num(now['kr:rsi30'], 1)}%</b> (상위 ${100 - pct['kr:rsi30']}%) · 52주 신저가 <b>${num(now['kr:nl'], 1)}%</b> (상위 ${100 - pct['kr:nl']}%). 급등했다가 꺾이는 날이 투매 정점 후보다.`,
    el => MChart.line(el, { from, zero: true, series: [ser('kr:bblow', '볼밴 하단 이탈 %'), ser('kr:rsi30', 'RSI<30 %'), ser('kr:nl', '신저가 %')], dec: 1 }));

  card('c-ma', '이평선 위 종목 비율', `60일선 위 <b>${num(now['kr:ma60'], 1)}%</b> · 200일선 위 <b>${num(now['kr:ma200'], 1)}%</b> — ${now['kr:ma60'] < 20 ? '20% 아래: 대부분 종목이 중기 추세 아래(과매도)' : now['kr:ma60'] > 80 ? '80% 위: 과열' : '중립 구간'}.`,
    el => MChart.line(el, { from, zero: true, series: [ser('kr:ma60', '60일선 위 %'), ser('kr:ma200', '200일선 위 %')], hlines: [{ y: 20, label: '20' }, { y: 80, label: '80' }], dec: 1 }));

  card('c-count', '바닥 신호 개수 추이', `켜진 조건 수(막대)와 KOSPI. 개수가 치솟은 뒤 줄어드는 구간이 투매가 끝나는 자리다.`,
    el => MChart.line(el, { from, zero: true, series: [{ name: '바닥 신호 개수', d: B.bottom.hist.d, v: B.bottom.hist.v, bars: true, color: 'var(--u-timing)' }, ser('kr:kospi', 'KOSPI', { axis: 'r', color: 'var(--c5)', width: 1.2 })], dec: 0, decR: 0 }), B.bottom.date);

  const t = D.term, inv = t['vol:vix9d'] > t['vol:vix3m'];
  card('c-vix', 'VIX 기간구조', `9일 <b>${num(t['vol:vix9d'])}</b> · 1개월 <b>${num(t['px:vix'])}</b> · 3개월 <b>${num(t['vol:vix3m'])}</b> · 6개월 <b>${num(t['vol:vix6m'])}</b> — ${inv ? '<b>역전</b>(단기 > 장기): 패닉 진행 중. 역전이 풀리는 날이 확인 신호' : '정상(단기 < 장기): 패닉 아님'}.`,
    el => MChart.line(el, { from, series: [ser('vol:vix9d', 'VIX 9일'), ser('px:vix', 'VIX 1개월'), ser('vol:vix3m', 'VIX 3개월', { color: 'var(--c5)' })], hlines: [{ y: 30, label: '30' }], dec: 1 }), D.term_date);

  const vk = D.vkospi;
  card('c-vkospi', 'VKOSPI', vk ? `<b>${num(vk.last)}</b> — ${vk.pct == null ? `과거 자료 ${vk.n}일치(백분위는 60일 이상 쌓이면 표시)` : `최근 3년 중 상위 ${100 - vk.pct}%${vk.pct >= 90 ? ': <b>공포 구간</b>' : ''}`}. 급등 뒤 꺾일 때를 본다.` : '자료 없음',
    el => S['vol:vkospi'] && MChart.line(el, { from, series: [ser('vol:vkospi', 'VKOSPI'), ser('kr:kospi', 'KOSPI', { axis: 'r', color: 'var(--c5)', width: 1.2 })], dec: 1, decR: 0 }), vk && vk.date);
})();
