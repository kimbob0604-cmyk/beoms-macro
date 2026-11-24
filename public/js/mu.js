// Beom's Macro 공통: 머리(탭)·테마·숫자 포맷·용도 배지·작은 선 그림
const MU = (() => {
  const TABS = [['index.html', '오늘', 'today'], ['timing.html', '타이밍', 'timing'], ['trend.html', '추세추종', 'trend'], ['weight.html', '비중', 'weight'], ['sector.html', '섹터', 'sector'], ['flow.html', '수급', 'flow'], ['credit.html', 'AI 크레딧', 'credit'], ['deriv.html', '파생·평단', 'deriv'], ['ib.html', 'IB 지표판', 'ib'], ['pair.html', '페어·상관', 'pair'], ['glossary.html', '지표 사전', 'glossary']];
  const SOON = [];
  const USE = { '흐름': 'flow', '타이밍': 'timing', '비중': 'weight', '섹터': 'sector' };
  const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

  function shell(active) {
    const h = document.createElement('header');
    h.className = 'top';
    h.innerHTML = `<div class="brand">Beom's Macro</div><nav class="tabs">${TABS.map(([u, n, id]) => `<a class="tab${id === active ? ' on' : ''}" href="${u}">${n}</a>`).join('')}${SOON.map(n => `<span class="tab off" title="다음 단계에서 추가">${n}</span>`).join('')}</nav>
      <div class="top-right"><span id="built"></span><button id="theme" class="icon-btn" aria-label="다크 모드 전환" title="다크 모드 전환">◐</button></div>`;
    document.body.prepend(h);
    document.getElementById('theme').onclick = () => {
      const cur = document.documentElement.dataset.theme || (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
      const next = cur === 'dark' ? 'light' : 'dark';
      document.documentElement.dataset.theme = next;
      try { localStorage.setItem('theme', next); } catch (e) {}
      document.dispatchEvent(new Event('themechange'));
    };
  }
  const built = t => { const el = document.getElementById('built'); if (el && t) el.textContent = `갱신 ${t}`; };
  // 데이터 받기. 배포본(data/lock.json 이 있음)은 파일이 암호로 잠겨 있어 브라우저 안에서 푼다. 이 컴퓨터의 로컬 화면은 잠겨 있지 않다.
  const b64 = t => Uint8Array.from(atob(t), c => c.charCodeAt(0));
  const stamp = () => Math.floor(Date.now() / 60000);
  const LOCKED = false;      // site_crypt.py 가 배포본에서 true 로 바꾼다
  let keyP = null;
  function unlock() {
    if (!LOCKED) return null;
    if (keyP) return keyP;
    keyP = (async () => {
      const r = await fetch(`data/lock.json?t=${stamp()}`).catch(() => null);
      if (!r || !r.ok) return null;                                  // 잠기지 않은 화면(로컬)
      const lock = await r.json(), salt = b64(lock.salt), chk = b64(lock.check);
      const ok = async k => { try { await crypto.subtle.decrypt({ name: 'AES-GCM', iv: chk.slice(0, 12) }, k, chk.slice(12)); return true; } catch (e) { return false; } };
      const id = 'macro.key.' + lock.salt.slice(0, 8);               // 암호가 바뀌면(=salt 가 바뀌면) 다시 묻는다
      try {
        const saved = localStorage.getItem(id);
        if (saved) { const k = await crypto.subtle.importKey('raw', b64(saved), 'AES-GCM', false, ['decrypt']); if (await ok(k)) return k; }
      } catch (e) {}
      return new Promise(resolve => {
        const box = document.createElement('div');
        box.className = 'lock';
        box.innerHTML = `<form class="card"><h2>Beom's Macro</h2><p class="sub">암호를 넣으면 이 기기에 기억한다.</p><input type="password" id="lock-pw" autocomplete="current-password" placeholder="암호" autofocus><button class="btn" type="submit">열기</button><p class="small down" id="lock-msg"></p></form>`;
        document.body.appendChild(box);
        box.querySelector('form').onsubmit = async ev => {
          ev.preventDefault();
          const msg = box.querySelector('#lock-msg');
          msg.textContent = '확인 중…';
          const base = await crypto.subtle.importKey('raw', new TextEncoder().encode(box.querySelector('#lock-pw').value), 'PBKDF2', false, ['deriveKey']);
          const k = await crypto.subtle.deriveKey({ name: 'PBKDF2', hash: 'SHA-256', salt, iterations: lock.iter }, base, { name: 'AES-GCM', length: 256 }, true, ['decrypt']);
          if (!(await ok(k))) { msg.textContent = '암호가 맞지 않는다.'; return; }
          try { localStorage.setItem(id, btoa(String.fromCharCode(...new Uint8Array(await crypto.subtle.exportKey('raw', k))))); } catch (e) {}
          box.remove();
          resolve(k);
        };
      });
    })();
    return keyP;
  }
  const get = async name => {
    const k = await unlock();
    const r = await fetch(`data/${name}${k ? '.enc' : ''}?t=${stamp()}`);
    if (!r.ok) throw new Error(`${name} ${r.status}`);
    if (!k) return r.json();
    const b = new Uint8Array(await r.arrayBuffer());
    return JSON.parse(new TextDecoder().decode(await crypto.subtle.decrypt({ name: 'AES-GCM', iv: b.slice(0, 12) }, k, b.slice(12))));
  };

  const num = (v, d = 2) => v == null ? '–' : Number(v).toLocaleString('ko-KR', { minimumFractionDigits: d, maximumFractionDigits: d });
  const sgn = v => v > 0 ? 'up' : v < 0 ? 'down' : '';
  // 변화: diff 면 포인트 차이, 아니면 %
  const chg = (v, diff, d) => v == null ? '<span class="muted">–</span>' : `<span class="${sgn(v)}">${v > 0 ? '+' : ''}${num(v, d ?? 2)}${diff ? '' : '%'}</span>`;
  const use = s => String(s || '').split(',').filter(Boolean).map(u => `<span class="use ${USE[u] || ''}">${esc(u)}</span>`).join(' ');
  const days = d => Math.round((Date.now() - new Date(d + 'T00:00:00').getTime()) / 864e5);
  // late: 며칠 넘게 지나면 '늦음' (매일 5 · 주간 12 · 월간 100 · 분기 250)
  // 날짜 표기: 2026-11-23 → 11/23 (사용자 요청 2026-11-24)
  const THIS_YEAR = String(new Date().getFullYear());
  const md1 = (y, m, d) => y === THIS_YEAR ? `${+m}/${+d}` : `${y}/${+m}/${+d}`;   // 올해는 11/23, 다른 해는 2025/1/31
  const md = d => { const m = String(d ?? '').match(/^(\d{4})-(\d{2})-(\d{2})/); return m ? md1(m[1], m[2], m[3]) : String(d ?? ''); };
  // 화면에 남은 2026-11-23 꼴 글자(빌드가 만든 문장·표·툴팁)도 11/23 으로 바꾼다 — 입력칸·스크립트는 건드리지 않는다
  const DATE_RE = /\b(\d{4})-(\d{2})-(\d{2})\b/g;
  const fixDates = root => {
    const w = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, { acceptNode: n => /^(SCRIPT|STYLE|TEXTAREA|INPUT)$/.test(n.parentNode?.nodeName) ? NodeFilter.FILTER_REJECT : NodeFilter.FILTER_ACCEPT });
    for (let n; (n = w.nextNode());) if (DATE_RE.test(n.nodeValue)) { DATE_RE.lastIndex = 0; n.nodeValue = n.nodeValue.replace(DATE_RE, (_, y, m, d) => md1(y, m, d)); } else DATE_RE.lastIndex = 0;
  };
  if (typeof MutationObserver !== 'undefined') document.addEventListener('DOMContentLoaded', () => {
    fixDates(document.body);
    new MutationObserver(ms => { for (const m of ms) for (const n of m.addedNodes) if (n.nodeType === 1) fixDates(n); else if (n.nodeType === 3 && n.parentNode) fixDates(n.parentNode); }).observe(document.body, { childList: true, subtree: true });
  });
  const asof = (d, late = 5) => d ? `<span class="asof${days(d) > late ? ' late' : ''}">${esc(md(d))} 기준${days(d) > late ? ' · 늦음' : ''}</span>` : '';
  const pm = (v, d = 1, u = '%') => v == null ? '–' : `${v > 0 ? '+' : ''}${num(v, d)}${u}`;
  // 0~100 점수 막대. bad='hi' 면 높을수록 경고색
  const gauge = (v, bad) => v == null ? '' : `<span class="gauge${bad === 'hi' && v >= 80 || bad === 'lo' && v <= 20 ? ' warn' : ''}"><i style="width:${Math.max(2, Math.min(100, v))}%"></i></span>`;
  // z-점수 막대: 가운데가 0, 오른쪽이 +. lim 은 막대 끝의 값
  const zbar = (z, lim = 3) => z == null ? '' : `<span class="zbar"><i class="${z >= 0 ? 'p' : 'n'}" style="${z >= 0 ? 'left:50%' : `right:50%`};width:${Math.min(50, Math.abs(z) / lim * 50)}%"></i></span>`;
  const parts = (o, bad) => `<div class="parts">${Object.entries(o).map(([k, v]) => `<div><span>${esc(k)}</span>${gauge(v, bad)}<b>${v ?? '–'}</b></div>`).join('')}</div>`;
  // 과거 근거 표: rows = [[이름, {n, dates, since, '1개월': {mean, win, base, base_win}, …}], …]
  function evidence(rows, target = 'KOSPI') {
    const HZ = ['1개월', '3개월', '6개월', '12개월'];
    const line = ([nm, e]) => `<tr><td>${esc(nm)}</td><td>${e.n}</td>${HZ.map(h => { const x = e[h]; return `<td class="${x.mean == null ? 'muted' : x.mean > x.base ? 'up' : 'down'}">${pm(x.mean)}</td><td class="muted">${pm(x.base)}</td>`; }).join('')}<td class="small muted" style="text-align:left">${(e.dates || []).slice(-3).join(', ')}</td></tr>`;
    return `<div class="scroll-x"><table class="tbl"><thead><tr><th>신호</th><th>횟수</th>${HZ.map(h => `<th>${h} 뒤</th><th>아무 날</th>`).join('')}<th class="l">최근 발생</th></tr></thead><tbody>${rows.map(line).join('')}</tbody></table></div>
      <p class="note">신호 뒤 ${esc(target)} 평균 수익률과, 같은 기간 아무 날이나 샀을 때의 평균. 20거래일 안의 반복은 한 번으로 센다. 빨강 = 아무 날보다 좋음, 파랑 = 나쁨. 그날까지의 값만 써서 계산한다.</p>`;
  }

  function spark(vals, w = 84, h = 22) {
    const v = (vals || []).filter(x => x != null);
    if (v.length < 2) return '';
    const lo = Math.min(...v), hi = Math.max(...v), sp = hi - lo || 1;
    const pts = v.map((x, i) => `${(i / (v.length - 1) * w).toFixed(1)},${(h - 2 - (x - lo) / sp * (h - 4)).toFixed(1)}`).join(' ');
    const col = v[v.length - 1] >= v[0] ? 'var(--up)' : 'var(--down)';
    return `<svg class="spark" width="${w}" height="${h}" viewBox="0 0 ${w} ${h}"><polyline points="${pts}" fill="none" stroke="${col}" stroke-width="1.4"/></svg>`;
  }
  const pos = p => p == null ? '' : `<span class="pos" title="52주 위치 ${p}%"><i style="left:${p}%"></i></span>`;
  const fail = e => { const m = document.querySelector('main'); m.insertAdjacentHTML('afterbegin', `<div class="alert">데이터를 불러오지 못했다: ${esc(e.message)} — <code>python3 run_daily.py</code> 를 먼저 실행.</div>`); console.error(e); };
  return { md, shell, built, get, num, chg, sgn, use, asof, days, spark, pos, esc, fail, pm, gauge, parts, evidence, zbar };
})();
