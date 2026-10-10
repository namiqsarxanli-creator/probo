'use strict';
// Siyasət — the glowing orb of rules (a slowly turning sphere of points, with threads out to
// the sections it governs) and the three steps that take turns being lit.
(() => {
  const tab = document.getElementById('tab-policy');
  const canvas = document.getElementById('pl-orb');
  if (!tab || !canvas) return;
  const still = matchMedia('(prefers-reduced-motion: reduce)').matches;
  const ctx = canvas.getContext('2d');

  // Points spread evenly over a sphere (Fibonacci lattice), plus a few loose sparks inside.
  const points = [];
  const N = 520;
  for (let i = 0; i < N; i++) {
    const y = 1 - (i / (N - 1)) * 2, r = Math.sqrt(1 - y * y), a = i * 2.399963;
    points.push([Math.cos(a) * r, y, Math.sin(a) * r, Math.random()]);
  }
  for (let i = 0; i < 90; i++) {
    const u = Math.random() * 2 - 1, a = Math.random() * Math.PI * 2, s = Math.cbrt(Math.random()) * 0.85;
    points.push([Math.cos(a) * Math.sqrt(1 - u * u) * s, u * s, Math.sin(a) * Math.sqrt(1 - u * u) * s, Math.random()]);
  }

  let visible = false, frame = 0;
  function size() {
    const dpr = Math.min(devicePixelRatio || 1, 2);
    canvas.width = canvas.clientWidth * dpr; canvas.height = canvas.clientHeight * dpr;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  }
  function draw(now) {
    frame = 0;
    if (!visible || !tab.classList.contains('on')) return;
    const w = canvas.clientWidth, h = canvas.clientHeight, t = still ? 4 : now / 1000;
    const cx = w * 0.56, cy = h * 0.52, R = Math.min(w, h) * 0.27;
    ctx.clearRect(0, 0, w, h);
    // threads to the three sections, with a bead travelling along each
    const nodes = [...tab.querySelectorAll('.pl-node')].map(n => {
      const b = n.getBoundingClientRect(), c = canvas.getBoundingClientRect();
      return [b.left - c.left, b.top - c.top + b.height / 2];
    });
    nodes.forEach(([nx, ny], i) => {
      ctx.strokeStyle = 'rgba(217,244,239,.35)'; ctx.lineWidth = 1;
      ctx.beginPath(); ctx.moveTo(cx, cy); ctx.lineTo(nx, ny); ctx.stroke();
      const k = (t * 0.25 + i / 3) % 1;
      ctx.fillStyle = 'rgba(217,244,239,.9)';
      ctx.beginPath(); ctx.arc(cx + (nx - cx) * k, cy + (ny - cy) * k, 2.4, 0, Math.PI * 2); ctx.fill();
    });
    // halo
    const halo = ctx.createRadialGradient(cx, cy, R * 0.2, cx, cy, R * 1.6);
    halo.addColorStop(0, 'rgba(140,240,220,.20)'); halo.addColorStop(0.55, 'rgba(120,220,210,.10)'); halo.addColorStop(1, 'rgba(120,220,210,0)');
    ctx.fillStyle = halo; ctx.beginPath(); ctx.arc(cx, cy, R * 1.6, 0, Math.PI * 2); ctx.fill();
    // the sphere: rotate about y (and a little about x), nearer points brighter and bigger
    const ay = t * 0.25, ax = 0.35 + Math.sin(t * 0.2) * 0.1;
    const sy = Math.sin(ay), cyy = Math.cos(ay), sx = Math.sin(ax), cxx = Math.cos(ax);
    for (const [x, y, z, seed] of points) {
      const x1 = x * cyy + z * sy, z1 = -x * sy + z * cyy;
      const y2 = y * cxx - z1 * sx, z2 = y * sx + z1 * cxx;
      const depth = (z2 + 1) / 2;
      const twinkle = 0.65 + 0.35 * Math.sin(t * 2 + seed * 20);
      ctx.fillStyle = `rgba(${200 + 55 * depth | 0},255,${235 + 20 * depth | 0},${(0.15 + 0.85 * depth) * twinkle})`;
      ctx.beginPath(); ctx.arc(cx + x1 * R, cy + y2 * R, 0.6 + depth * 1.7, 0, Math.PI * 2); ctx.fill();
    }
    // rim
    ctx.strokeStyle = 'rgba(190,250,235,.35)'; ctx.lineWidth = 1.5;
    ctx.beginPath(); ctx.arc(cx, cy, R * 1.02, 0, Math.PI * 2); ctx.stroke();
    if (!still) frame = requestAnimationFrame(draw);
  }
  function wake() {
    if (!frame && visible && tab.classList.contains('on')) { size(); frame = requestAnimationFrame(draw); }
  }
  new ResizeObserver(() => { if (visible) size(); }).observe(canvas);
  new IntersectionObserver(([e]) => { visible = e.isIntersecting; wake(); }).observe(canvas);
  new MutationObserver(wake).observe(tab, {attributes: true, attributeFilter: ['class']});

  // steps take turns, unless the reader points at one
  const steps = [...tab.querySelectorAll('.pl-steps li')];
  let current = 0, paused = false;
  const show = i => steps.forEach((li, k) => li.classList.toggle('on', k === i));
  steps.forEach((li, i) => li.addEventListener('mouseenter', () => { paused = true; current = i; show(i); }));
  tab.querySelector('.pl-steps')?.addEventListener('mouseleave', () => { paused = false; });
  if (!still) setInterval(() => {
    if (paused || !tab.classList.contains('on')) return;
    current = (current + 1) % steps.length; show(current);
  }, 3600);
})();
