// 추세추종: IBD식 시장 상태(분산일·팔로스루) · 지수 주봉 단계 · 미너비니 트렌드 템플릿 통과 비율 · 단계 비율 · 통과 종목
(async () => {
  MU.shell('trend');
  const { num, use, asof, esc, pm } = MU;
  let D;
  try { D = await MU.get('trend.json'); } catch (e) { return MU.fail(e); }
  MU.built(D.built);
  const $ = id => document.getElementById(id);
  const RU = D.rules, HZ = ['1개월', '3개월', '6개월', '12개월'];
  const beat = e => HZ.filter(h => e[h].mean != null && e[h].mean > e[h].base).length;
  const STG = { 1: '1단계 바닥 다지기', 2: '2단계 상승', 3: '3단계 천장 다지기', 4: '4단계 하락' };
  const stCls = s => s === 2 ? 'a' : s === 1 ? 'h' : s === 0 ? 'b' : '';
  const stgCls = s => s === 2 ? 'a' : s === 4 ? 'b' : 'h';
  const badge = (txt, c) => `<span class="ctry" style="display:inline;margin:0"><span class="${c}">${esc(txt)}</span></span>`;
  const ser = (o, name, x = {}) => ({ name, d: o.d, v: o.v, ...x });
  const mc = v => v == null ? '–' : v >= 10000 ? `${num(v / 10000, 1)}조` : `${num(v, 0)}억`;
  const SEC = { 'Information Technology': '정보기술', 'Health Care': '헬스케어', 'Financials': '금융', 'Consumer Discretionary': '경기소비재', 'Communication Services': '커뮤니케이션',
    'Industrials': '산업재', 'Consumer Staples': '필수소비재', 'Energy': '에너지', 'Utilities': '유틸리티', 'Real Estate': '부동산', 'Materials': '소재' };
  const sec = s => SEC[s] || s || '–';
  const I = Object.fromEntries(D.idx.map(x => [x.k, x]));

  // ── 시장 상태 표 ──
  const rally = x => x.state !== 0 ? '<span class="muted">–</span>' : x.rday ? `<b>${x.rday}일째</b>${x.rday < 4 ? ` <span class="small muted">(팔로스루는 ${4 - x.rday}거래일 뒤부터)</span>` : ' <span class="small muted">(팔로스루 가능 구간)</span>'}` : '<span class="small muted">저점 갱신 중 — 아직 랠리 시작 전</span>';
  const rows = D.idx.map(x => `<tr><td><b>${esc(x.name)}</b></td><td>${badge(x.label, stCls(x.state))}</td><td>${esc(MU.md(x.since))}~</td>
    <td><b>${x.dd}</b>개</td><td class="l">${rally(x)}</td><td class="${MU.sgn(x.dd_peak)}">${pm(x.dd_peak)}</td><td class="${MU.sgn(x.m50)}">${pm(x.m50)}</td>
    <td>${badge(STG[x.stage], stgCls(x.stage))} <span class="small muted">${x.weeks}주째</span></td><td class="${MU.sgn(x.ma30)}">${pm(x.ma30)}</td></tr>`).join('');
  const corr = D.idx.filter(x => x.state === 0), up = D.idx.filter(x => x.state === 2);
  const waiting = corr.filter(x => x.rday >= 1);
  $('state').innerHTML = `<h2>시장 상태 — IBD식 규칙 ${use('흐름,타이밍')} ${asof(D.idx[0]?.date)}</h2>
    <p class="sub">오닐(IBD)은 매일 시장을 '상승 확인 / 상승 압박 / 조정' 셋 중 하나로 부른다. 여기서는 그 판단을 규칙으로 옮겨 기계적으로 계산했다. 주봉 단계는 와인스타인의 30주선 기준이다.</p>
    <div class="scroll-x"><table class="tbl"><thead><tr><th>지수</th><th>시장 상태</th><th>언제부터</th><th>분산일 (25일)</th><th class="l">조정 중 랠리</th><th>63일 고점 대비</th><th>50일선 대비</th><th>주봉 단계</th><th>30주선 대비</th></tr></thead><tbody>${rows}</tbody></table></div>
    <div class="read">지금 읽으면 — ${corr.length === D.idx.length ? '<b>네 지수 모두 조정</b>이다. 추세추종 규칙으로는 새로 사지 않고 현금을 늘리는 구간이다' : up.length === D.idx.length ? '<b>네 지수 모두 상승 확인</b> 상태다' : `상승 확인 ${up.map(x => esc(x.name)).join('·') || '없음'} / 조정 ${corr.map(x => esc(x.name)).join('·') || '없음'}`}.
      ${waiting.length ? `${waiting.map(x => `${esc(x.name)} 랠리 ${x.rday}일째`).join(', ')} — 랠리 4일째 이후 하루에 ${waiting.map(x => `${esc(x.name)} +${x.gain}%`).join(', ')} 이상 오르면서 거래량이 전날보다 많으면 <b>팔로스루 데이</b>(상승 확인 전환)다.` : corr.length ? '조정 중인 지수는 아직 저점을 낮추는 중이라 랠리가 시작되지 않았다.' : ''}
      주봉 기준 ${D.idx.filter(x => x.stage === 4).map(x => esc(x.name)).join('·') || '없음'}은 4단계(30주선 아래 + 선 하락)다.</div>
    <p class="note">분산일 = 지수가 ${RU.dd_drop}% 이상 내리면서 거래량이 전날보다 많은 날(기관 매도 흔적). ${RU.dd_life}거래일이 지나거나 그날 종가보다 5% 오르면 지운다. 조정 진입 = 상승 구간 고점 대비 −${RU.corr_dd}%, 또는 분산일 ${RU.corr_dist}개 이상이면서 50일선 아래. 분산일 ${RU.press}개 이상이면 '상승 압박'.</p>`;

  // ── 지수별 카드 ──
  function idxCard(k) {
    const x = I[k];
    if (!x) return;
    const f = x.ftd.slice().reverse();
    $(`ix-${k}`).innerHTML = `<h2>${esc(x.name)} — 분산일·팔로스루 ${asof(x.date)}</h2>
      <div class="stat"><div><span>시장 상태</span><b>${esc(x.label)}</b></div><div><span>분산일 (25일)</span><b>${x.dd}개</b></div><div><span>주봉 단계</span><b>${x.stage}단계</b> <span>${x.weeks}주째</span></div></div>
      <div class="ch"></div>
      <div class="read">지금 읽으면 — ${x.state === 0 ? `<b>조정</b> (${esc(MU.md(x.since))}부터). ${x.rday ? `랠리 ${x.rday}일째 — 4일째 이후 +${x.gain}% 이상·거래량 증가가 나오면 팔로스루.` : '아직 저점을 낮추는 중.'}` : x.state === 1 ? `<b>상승 압박</b> — 분산일이 ${x.dd}개로 쌓였다. 새로 사기보다 기존 종목의 손절선을 지키는 구간.` : `<b>상승 확인</b> — 분산일 ${x.dd}개.`}
        분산일 날짜: ${x.dd_dates.map(d => esc(MU.md(d))).join(', ') || '없음'}.</div>
      <h3 class="sec-title" style="margin-top:12px">최근 팔로스루 데이</h3>
      <table class="tbl"><thead><tr><th>날짜</th><th>그날</th><th>20일 뒤</th><th>60일 뒤</th><th>결과</th></tr></thead><tbody>
      ${f.map(t => `<tr><td>${esc(MU.md(t.d))}</td><td class="up">${pm(t.chg, 2)}</td><td class="${MU.sgn(t.r20)}">${pm(t.r20)}</td><td class="${MU.sgn(t.r60)}">${pm(t.r60)}</td><td>${t.fail ? '<span class="down">실패 (랠리 저점 깸)</span>' : '<span class="muted">유지</span>'}</td></tr>`).join('')}</tbody></table>
      <p class="note">${esc(x.name)}: 과거 팔로스루 ${x.ftd_n}번 중 ${x.fail_n}번이 ${RU.dd_life}거래일 안에 랠리 저점을 깨서 실패했다.</p>`;
    MChart.line($(`ix-${k}`).querySelector('.ch'), { series: [ser(x.series, x.name), ser(x.dd_s, '분산일 개수', { axis: 'r', color: 'var(--c2)', bars: true })], hlines: [{ y: RU.press, label: `압박 ${RU.press}`, axis: 'r' }], dec: 0, decR: 0, height: 240 });
  }
  ['spx', 'kospi', 'ndx', 'kosdaq'].forEach(idxCard);

  // ── 과거 근거: 지수 신호 ──
  $('ev').innerHTML = `<h2>과거 근거 — 지수 신호 뒤 수익률 ${use('타이밍')}</h2>
    <p class="sub">각 신호가 난 날 뒤 그 지수의 평균 수익률과, 같은 기간 아무 날이나 샀을 때의 평균. 2006년(한국 지수는 같은 시점)부터.</p>
    ${D.idx.map(x => `<h3 class="sec-title" style="margin-top:14px">${esc(x.name)}</h3>${MU.evidence([['팔로스루 데이', x.ev_ftd], ['조정 진입', x.ev_corr], ['분산일 6개 이상', x.ev_dd6], ['주봉 2단계 진입', x.ev_st2]], x.name)}`).join('')}
    <div class="read">지금 읽으면 — 팔로스루 데이 뒤 네 기간 중 아무 날보다 좋았던 기간 수: ${D.idx.map(x => `${esc(x.name)} <b>${beat(x.ev_ftd)}/4</b>`).join(', ')}.
      ${D.idx.every(x => beat(x.ev_ftd) <= 2) ? '<b>팔로스루만으로는 우위가 거의 없었다</b> — 실패가 많기 때문이다. 오닐도 "팔로스루는 필요조건일 뿐, 주도주의 돌파가 따라와야 한다"고 한다. 아래 트렌드 템플릿 통과 비율이 같이 늘어나는지 함께 본다.' : '일부 지수에서는 팔로스루 뒤가 아무 날보다 좋았다.'}
      주봉 2단계 진입 뒤: ${D.idx.map(x => `${esc(x.name)} ${beat(x.ev_st2)}/4`).join(', ')}.</div>`;

  // ── 트렌드 템플릿 통과 비율 ──
  const BR = D.breadth;
  function ttCard(m, title, ixName) {
    const b = BR[m];
    if (!b) return;
    const where = b.tt <= b.q10 ? '<b>과거 하위 10% 안</b> — 강한 종목이 거의 남지 않은 바닥권' : b.tt >= b.q90 ? '<b>과거 상위 10% 안</b> — 강한 종목이 넓게 퍼진 구간' : '중간 구간';
    $(`tt-${m}`).innerHTML = `<h2>트렌드 템플릿 통과 비율 — ${title} ${use('흐름,타이밍')} ${asof(b.date)}</h2>
      <p class="sub">미너비니의 8개 조건(이평선 정배열·200일선 상승·52주 고가 근처·RS 70 이상 등)을 모두 통과한 종목의 비율.</p>
      <div class="stat"><div><span>지금</span><b>${num(b.tt, 1)}%</b> <span>20일 전 ${num(b.tt20, 1)}%</span></div><div><span>하위 10% 선</span><b>${num(b.q10, 1)}%</b></div><div><span>상위 10% 선</span><b>${num(b.q90, 1)}%</b></div><div><span>전체 기간 중</span><b>하위 ${b.tt_pct}%</b></div></div>
      <div class="ch"></div>
      <div class="read">지금 읽으면 — <b>${num(b.tt, 1)}%</b>, ${where}. 20일 전 ${num(b.tt20, 1)}%에서 ${b.tt > b.tt20 ? '늘었다' : '줄었다'}.
        미너비니식으로는 이 비율이 바닥에서 <b>빠르게 늘어나기 시작할 때</b>(주도주가 새로 나올 때)가 새 상승장의 첫 신호다.</div>`;
    MChart.line($(`tt-${m}`).querySelector('.ch'), { series: [ser(b.series, '통과 비율 (%)'), ser(b.px, ixName, { axis: 'r', color: 'var(--c5)', width: 1.2 })], hlines: [{ y: b.q10, label: '하위 10%' }, { y: b.q90, label: '상위 10%' }], dec: 1, decR: 0, height: 260 });
  }
  ttCard('kr', '한국 (KOSPI+KOSDAQ 보통주)', 'KOSPI');
  ttCard('us', '미국 (S&P500 종목)', 'S&P500');
  $('tt-ev').innerHTML = `<h2>과거 근거 — 통과 비율 신호 뒤 지수 ${use('타이밍')}</h2>
    <p class="sub">'하위·상위 10% 선'은 그날까지의 값만으로 정한다. '확산 시작' = 최근 20일 최저가 하위 10% 선 아래였고, 그 최저의 두 배 이상으로 늘어난 날.</p>
    ${['kr', 'us'].filter(m => BR[m]).map(m => `<h3 class="sec-title" style="margin-top:14px">${m === 'kr' ? '한국 → KOSPI' : '미국 → S&P500'} (${esc(BR[m].since.slice(0, 4))}년~)</h3>${MU.evidence([['통과 비율 하위 10% 이하', BR[m].ev_lo], ['바닥권에서 확산 시작 (20일 안에 두 배)', BR[m].ev_turn], ['통과 비율 상위 10% 이상', BR[m].ev_hi]], m === 'kr' ? 'KOSPI' : 'S&P500')}`).join('')}
    <div class="read">지금 읽으면 — '확산 시작' 신호 뒤 아무 날보다 좋았던 기간 수: 한국 <b>${BR.kr ? beat(BR.kr.ev_turn) : '–'}/4</b>, 미국 <b>${BR.us ? beat(BR.us.ev_turn) : '–'}/4</b>. 비율이 낮다는 것만으로는 사는 신호가 아니다(하위 10%: 한국 ${BR.kr ? beat(BR.kr.ev_lo) : '–'}/4, 미국 ${BR.us ? beat(BR.us.ev_lo) : '–'}/4). <b>낮은 곳에서 다시 늘어나는 것</b>을 기다리는 지표다.</div>`;

  // ── 단계 비율 ──
  function stCard(m, title) {
    const b = BR[m];
    if (!b) return;
    $(`st-${m}`).innerHTML = `<h2>와인스타인 단계 비율 — ${title} ${asof(b.date)}</h2>
      <p class="sub">2단계 = 150일선(≈30주선) 위 + 그 선이 20일 전보다 높음. 4단계 = 아래 + 하락.</p>
      <div class="stat"><div><span>2단계 (상승)</span><b class="up">${num(b.st2, 1)}%</b> <span>20일 전 ${num(b.st2_20, 1)}%</span></div><div><span>4단계 (하락)</span><b class="down">${num(b.st4, 1)}%</b></div></div>
      <div class="ch"></div>
      <div class="read">지금 읽으면 — ${b.st4 > b.st2 ? `<b>하락 단계 종목이 상승 단계보다 많다</b> (${num(b.st4, 0)}% vs ${num(b.st2, 0)}%). 와인스타인은 4단계 종목은 사지 말라고 한다.` : `상승 단계 종목이 더 많다 (${num(b.st2, 0)}% vs ${num(b.st4, 0)}%).`}</div>`;
    MChart.line($(`st-${m}`).querySelector('.ch'), { series: [ser(b.st2_s, '2단계 (%)', { color: 'var(--up)' }), ser(b.st4_s, '4단계 (%)', { color: 'var(--down)' })], dec: 0, height: 220 });
  }
  stCard('kr', '한국');
  stCard('us', '미국 S&P500');

  // ── 통과 종목 ──
  const L = D.lists || {};
  const chips = s => `<div class="ctry">${(s || []).map(([n, c]) => `<span>${esc(sec(n))} ${c}</span>`).join('')}</div>`;
  if (L.kr) $('lead-kr').innerHTML = `<h2>트렌드 템플릿 통과 종목 — 한국 ${asof(L.kr.asof)}</h2>
    <p class="sub">${L.kr.n.toLocaleString()}종목 중 <b>${L.kr.pass}개</b> 통과. 표는 시총 1,000억 이상만, RS(1~99) 높은 순.</p>${chips(L.kr.sectors)}
    <div class="scroll-x" style="max-height:520px;overflow:auto"><table class="tbl"><thead><tr><th>종목</th><th class="l">업종</th><th>시총</th><th>RS</th><th>52주 고가 대비</th><th>50일선 대비</th></tr></thead><tbody>
    ${L.kr.rows.map(x => `<tr><td><b>${esc(x.n)}</b> <span class="small muted">${esc(x.c)} ${esc(x.m)}</span></td><td class="l small">${esc(x.sec || '–')}</td><td>${mc(x.mc)}</td><td><b>${x.rs}</b></td><td class="${MU.sgn(x.hi)}">${pm(x.hi)}</td><td class="${MU.sgn(x.m50)}">${pm(x.m50)}</td></tr>`).join('')}</tbody></table></div>`;
  if (L.us) $('lead-us').innerHTML = `<h2>트렌드 템플릿 통과 종목 — 미국 S&P500 ${asof(L.us.asof)}</h2>
    <p class="sub">${L.us.n}종목 중 <b>${L.us.pass}개</b> 통과. RS 높은 순.</p>${chips(L.us.sectors)}
    <div class="scroll-x" style="max-height:520px;overflow:auto"><table class="tbl"><thead><tr><th>종목</th><th class="l">업종</th><th>RS</th><th>52주 고가 대비</th><th>50일선 대비</th></tr></thead><tbody>
    ${L.us.rows.map(x => `<tr><td><b>${esc(x.c)}</b> <span class="small muted">${esc(x.n)}</span></td><td class="l small">${esc(sec(x.sec))}</td><td><b>${x.rs}</b></td><td class="${MU.sgn(x.hi)}">${pm(x.hi)}</td><td class="${MU.sgn(x.m50)}">${pm(x.m50)}</td></tr>`).join('')}</tbody></table></div>`;

  // ── 규칙 ──
  $('rules').innerHTML = `<h2>계산 규칙</h2>
    <table class="tbl"><thead><tr><th>지표</th><th class="l">원래 누구의 무엇</th><th class="l">여기서 쓴 식</th></tr></thead><tbody>
    <tr><td><b>트렌드 템플릿</b></td><td class="l small">마크 미너비니, 2단계 종목 고르는 8조건</td><td class="l small">① 가격 > 150·200일선 ② 150일선 > 200일선 ③ 200일선이 21거래일 전보다 높음 ④ 50일선 > 150·200일선 ⑤ 가격 > 50일선 ⑥ 52주 저가 대비 +30% 이상 ⑦ 52주 고가 대비 −25% 이내 ⑧ RS 70 이상</td></tr>
    <tr><td><b>RS 점수</b></td><td class="l small">IBD 상대강도 등급(1~99)</td><td class="l small">0.4×3개월 + 0.2×6개월 + 0.2×9개월 + 0.2×12개월 수익률을 같은 종목군 안에서 백분위로</td></tr>
    <tr><td><b>분산일</b></td><td class="l small">윌리엄 오닐(IBD)</td><td class="l small">지수 ${RU.dd_drop}% 이하 하락 + 거래량이 전날보다 많음. ${RU.dd_life}거래일 또는 그날 종가 대비 +5%에서 소멸</td></tr>
    <tr><td><b>팔로스루 데이</b></td><td class="l small">윌리엄 오닐(IBD)</td><td class="l small">조정 중 최저 종가 뒤 첫 상승일을 랠리 1일째로 세고, 4일째 이후 하루 +${RU.ftd_gain.us}%(한국 지수 +${RU.ftd_gain.kr}%) 이상 + 거래량 증가. 그 뒤 ${RU.dd_life}거래일 안에 랠리 저점을 깨면 실패</td></tr>
    <tr><td><b>시장 상태</b></td><td class="l small">IBD 'Market Pulse'</td><td class="l small">조정 진입: 상승 구간 고점 대비 −${RU.corr_dd}%, 또는 분산일 ${RU.corr_dist}개 이상 + 50일선 아래. 상승 중 분산일 ${RU.press}개 이상이면 압박</td></tr>
    <tr><td><b>단계</b></td><td class="l small">스탠 와인스타인, 30주 이동평균 4단계</td><td class="l small">지수: 주봉 30주선과 4주 기울기(±0.5%). 종목: 150일선과 20일 기울기. 선 근처에서 방향이 애매하면 직전 단계에 따라 1(바닥)·3(천장)</td></tr>
    </tbody></table>
    <p class="note">대가들이 직접 발표하는 숫자가 아니라 같은 규칙을 공개 자료로 계산한 값이다. 숫자(−0.2%, 4일째, +1.2% 등)는 책과 IBD 설명의 대표값이고 우리 가정이 섞여 있다. 한국 종목은 보통주 전체(스팩 제외), 미국은 지금의 S&P500 구성 종목.</p>`;
})();
