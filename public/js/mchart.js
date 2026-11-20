// 선 차트 (SVG, 외부 라이브러리 없음). 왼쪽·오른쪽 두 축, 기준선, 마우스를 올리면 그날 값.
// MChart.line(el, { series: [{ name, d: [날짜], v: [값], axis: 'l'|'r', color: 'var(--c1)', width, step }], hlines: [{ y, label, axis }], height, dec, bars: bool })
const MChart = (() => {
  const COLORS = ['var(--c1)', 'var(--c2)', 'var(--c3)', 'var(--c4)', 'var(--c5)', 'var(--c6)'];
  const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  function ticks(lo, hi, n = 4) {
    const span = hi - lo || Math.abs(hi) || 1, raw = span / n, mag = 10 ** Math.floor(Math.log10(raw)), e = raw / mag;
    const step = (e >= 7.5 ? 10 : e >= 3.5 ? 5 : e >= 1.5 ? 2 : 1) * mag, out = [];
    for (let v = Math.ceil(lo / step) * step; v <= hi + step * 1e-6; v += step) out.push(+v.toPrecision(12));
    return out;
  }
  const fmt = (v, dec) => v == null ? '–' : Math.abs(v) >= 10000 ? Math.round(v).toLocaleString('ko-KR') : v.toLocaleString('ko-KR', { maximumFractionDigits: dec ?? (Math.abs(v) >= 100 ? 1 : 2) });

  function line(el, spec) {
    const W = 760, H = spec.height || 260, L = 46, R = spec.series.some(s => s.axis === 'r') ? 50 : 14, T = 10, B = 22;
    const dates = [...new Set(spec.series.flatMap(s => s.d))].sort();
    if (spec.from) { while (dates.length && dates[0] < spec.from) dates.shift(); }
    const n = dates.length;
    if (!n) { el.innerHTML = '<p class="muted small">자료 없음</p>'; return; }
    const ix = new Map(dates.map((d, i) => [d, i]));
    const ser = spec.series.map((s, k) => {
      const a = new Array(n).fill(null);
      s.d.forEach((d, i) => { const j = ix.get(d); if (j != null) a[j] = s.v[i]; });
      return { ...s, a, color: s.color || COLORS[k % COLORS.length], axis: s.axis || 'l' };
    });
    const ext = ax => {
      let lo = Infinity, hi = -Infinity;
      ser.filter(s => s.axis === ax).forEach(s => s.a.forEach(v => { if (v != null) { lo = Math.min(lo, v); hi = Math.max(hi, v); } }));
      (spec.hlines || []).filter(h => (h.axis || 'l') === ax).forEach(h => { lo = Math.min(lo, h.y); hi = Math.max(hi, h.y); });
      if (lo === Infinity) return null;
      if (spec.zero && ax === 'l') lo = Math.min(lo, 0);
      const m = (hi - lo || Math.abs(hi) || 1) * 0.07;
      return [lo - (spec.zero && lo === 0 ? 0 : m), hi + m];
    };
    const eL = ext('l'), eR = ext('r');
    const X = i => L + (n === 1 ? 0 : i / (n - 1) * (W - L - R));
    const Yf = e => v => T + (1 - (v - e[0]) / (e[1] - e[0])) * (H - T - B);
    const YL = eL && Yf(eL), YR = eR && Yf(eR);
    let g = '';
    if (eL) ticks(eL[0], eL[1]).forEach(t => { g += `<line class="gl" x1="${L}" x2="${W - R}" y1="${YL(t)}" y2="${YL(t)}"/><text class="ax" x="${L - 6}" y="${YL(t) + 3.5}" text-anchor="end">${fmt(t, spec.dec)}</text>`; });
    if (eR) ticks(eR[0], eR[1]).forEach(t => { g += `<text class="ax" x="${W - R + 6}" y="${YR(t) + 3.5}">${fmt(t, spec.decR ?? spec.dec)}</text>`; });
    const step = Math.max(1, Math.round(n / 6));
    for (let i = 0; i < n; i += step) g += `<text class="ax" x="${X(i)}" y="${H - 6}" text-anchor="middle">${dates[i].slice(2, 7).replace('-', '.')}</text>`;
    (spec.hlines || []).forEach(h => {
      const y = ((h.axis || 'l') === 'l' ? YL : YR)(h.y);
      g += `<line class="hl" x1="${L}" x2="${W - R}" y1="${y}" y2="${y}"/><text class="hlt" x="${W - R - 4}" y="${y - 3}" text-anchor="end">${esc(h.label ?? h.y)}</text>`;
    });
    ser.forEach(s => {
      const Y = s.axis === 'l' ? YL : YR;
      if (s.bars) {
        const bw = Math.max(1, (W - L - R) / n * 0.7);
        s.a.forEach((v, i) => { if (v != null) g += `<rect x="${X(i) - bw / 2}" y="${Math.min(Y(v), Y(0))}" width="${bw}" height="${Math.abs(Y(v) - Y(0))}" fill="${s.color}" opacity=".75"/>`; });
        return;
      }
      let d = '', pen = false;
      s.a.forEach((v, i) => { if (v == null) return; d += `${pen ? 'L' : 'M'}${X(i).toFixed(1)} ${Y(v).toFixed(1)}`; pen = true; });
      g += `<path d="${d}" fill="none" stroke="${s.color}" stroke-width="${s.width || 1.6}" ${s.dash ? 'stroke-dasharray="4 3"' : ''} stroke-linejoin="round"/>`;
    });
    el.classList.add('mc');
    el.innerHTML = `<div class="legend">${ser.map(s => `<span><i style="background:${s.color}"></i>${esc(s.name)}${s.axis === 'r' ? ' (오른쪽)' : ''}</span>`).join('')}</div>
      <svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(spec.title || ser.map(s => s.name).join(', '))}">${g}<line class="cur" y1="${T}" y2="${H - B}" style="display:none"/></svg><div class="tip"></div>`;
    const svg = el.querySelector('svg'), cur = el.querySelector('.cur'), tip = el.querySelector('.tip');
    const move = ev => {
      const r = svg.getBoundingClientRect(), x = ((ev.touches ? ev.touches[0].clientX : ev.clientX) - r.left) / r.width * W;
      const i = Math.max(0, Math.min(n - 1, Math.round((x - L) / (W - L - R) * (n - 1))));
      cur.style.display = ''; cur.setAttribute('x1', X(i)); cur.setAttribute('x2', X(i));
      tip.style.display = 'block';
      tip.innerHTML = `<b>${dates[i]}</b><br>` + ser.map(s => `<i style="background:${s.color}"></i>${esc(s.name)} <b>${fmt(s.a[i], s.axis === 'r' ? (spec.decR ?? spec.dec) : spec.dec)}</b>`).join('<br>');
      const px = X(i) / W * r.width;
      tip.style.left = `${px > r.width / 2 ? px - tip.offsetWidth - 10 : px + 10}px`;
      tip.style.top = `${svg.offsetTop + 8}px`;
    };
    svg.addEventListener('mousemove', move); svg.addEventListener('touchmove', move, { passive: true });
    svg.addEventListener('mouseleave', () => { cur.style.display = 'none'; tip.style.display = 'none'; });
  }
  return { line, fmt, COLORS };
})();
