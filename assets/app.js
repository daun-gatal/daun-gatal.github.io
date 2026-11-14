// Fills the live numbers and charts from data/stats.json (rebuilt nightly).
(function () {
  const NS = 'http://www.w3.org/2000/svg';
  const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

  const get = (obj, path) => path.split('.').reduce((o, k) => (o == null ? o : o[k]), obj);
  const el = (tag, cls, text) => {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    return e;
  };
  const sv = (tag, attrs) => {
    const e = document.createElementNS(NS, tag);
    for (const k in attrs) e.setAttribute(k, attrs[k]);
    return e;
  };

  function fillNumbers(s) {
    document.querySelectorAll('[data-stat]').forEach((node) => {
      const v = get(s, node.dataset.stat);
      if (v == null) return;
      node.textContent = node.dataset.fmt === 'n' ? Number(v).toLocaleString('en-US') : v;
    });
  }

  function starChart(hist) {
    const svg = document.getElementById('star-chart');
    if (!svg || !hist.length) return;
    const W = 520, H = 150, top = Math.max(10, ...hist.map((p) => p.stars));
    const pts = hist.map((p, i) => [W * i / Math.max(1, hist.length - 1), H - (H - 10) * p.stars / top]);
    const line = pts.map((p) => p[0].toFixed(1) + ',' + p[1].toFixed(1)).join(' ');
    svg.replaceChildren(
      sv('line', { x1: 0, y1: H, x2: W, y2: H, stroke: '#30363d' }),
      sv('line', { x1: 0, y1: 80, x2: W, y2: 80, stroke: '#21262d', 'stroke-dasharray': '3 4' }),
      sv('polygon', { points: `0,${H} ${line} ${W},${H}`, fill: 'rgba(245,217,10,0.12)' }),
      sv('polyline', { points: line, fill: 'none', stroke: '#f5d90a', 'stroke-width': 2.5, 'stroke-linejoin': 'round' }),
      sv('circle', { cx: Math.min(pts.at(-1)[0], W - 4), cy: pts.at(-1)[1], r: 4, fill: '#f5d90a' })
    );
    const label = (x, txt, anchor) => {
      const t = sv('text', { x, y: 166, fill: '#8b949e', 'font-size': 11, 'font-family': 'JetBrains Mono, monospace', 'text-anchor': anchor });
      t.textContent = txt;
      svg.appendChild(t);
    };
    const name = (m) => MONTHS[+m.slice(5, 7) - 1].toUpperCase() + ' ' + m.slice(2, 4);
    label(0, name(hist[0].month), 'start');
    label(W, name(hist.at(-1).month), 'end');
    svg.setAttribute('aria-label', `CHouse UI stars grew from ${hist[0].stars} in ${name(hist[0].month)} to ${hist.at(-1).stars} in ${name(hist.at(-1).month)}`);
  }

  function columns(container, items, opts) {
    if (!container || !items.length) return;
    const top = Math.max(1, ...items.map((i) => i.count));
    container.style.gridTemplateColumns = `repeat(${items.length}, minmax(0, 1fr))`;
    container.replaceChildren(...items.map((it) => {
      const col = el('div', 'col');
      if (opts.tag) col.appendChild(el('div', 'tag', it.tag || ''));
      if (opts.values) col.appendChild(el('div', 'val', it.count));
      const bar = el('div', 'bar');
      bar.style.height = it.count ? Math.max(4, Math.round(opts.max * it.count / top)) + 'px' : '3px';
      bar.style.background = it.count ? opts.color(it) : '#30363d';
      col.append(bar, el('div', 'lab', it.label));
      return col;
    }));
  }

  function bezi(b) {
    const buckets = b.buckets || [];
    const unit = b.buckets_unit || 'day';
    const cap = document.getElementById('bz-caption');
    if (cap) cap.textContent = unit === 'day' ? 'Releases per day since v0.1' : 'Releases per week, last 16 weeks';
    let tagged = buckets;
    if (unit === 'day') {
      // label each day with the short tags released on it
      const byDay = {};
      b.release_dates.forEach((d, i) => { (byDay[d] = byDay[d] || []).push(b.release_tags[i].replace(/\.0$/, '')); });
      const start = new Date(b.release_dates[0] + 'T00:00:00Z');
      tagged = buckets.map((k, i) => {
        const d = new Date(start.getTime() + i * 864e5).toISOString().slice(0, 10);
        return Object.assign({}, k, { label: String(+d.slice(8)), tag: (byDay[d] || []).join(' ') });
      });
    }
    columns(document.getElementById('bz-chart'), tagged, { max: 90, tag: unit === 'day', color: () => '#4493f8' });
  }

  function heat(cal) {
    const box = document.getElementById('heatmap');
    if (!box) return;
    const cells = [];
    cal.forEach((w, wi) => {
      // first week may start mid-week: pad so rows line up with weekdays
      if (wi === 0) for (let p = 0; p < 7 - w.length; p++) cells.push(el('i', 'l0'));
      for (const lv of w) cells.push(el('i', 'l' + lv));
    });
    box.replaceChildren(...cells);
  }

  function months(list) {
    const items = list.map((m) => ({ count: m.count, label: MONTHS[+m.month.slice(5, 7) - 1][0] }));
    const top = Math.max(...items.map((i) => i.count));
    columns(document.getElementById('months'), items, {
      max: 100, values: true,
      color: (it) => (it.count >= top * 0.6 ? '#f5d90a' : 'rgba(245,217,10,0.45)'),
    });
  }

  fetch('data/stats.json', { cache: 'no-cache' })
    .then((r) => r.json())
    .then((s) => {
      fillNumbers(s);
      starChart(s.chouse.star_history);
      bezi(s.bezisync);
      heat(s.calendar);
      months(s.months);
    })
    .catch(() => { /* static fallback numbers stay in place */ });
})();
