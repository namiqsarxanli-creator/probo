// Sifariş və stok — a 3D stock dispenser: a glass drum full of balls, one colour per size
// (S green, M blue, L orange), a pipe that drops a ball in now and then (an order arriving),
// and a small robot keeping watch. The ball count follows the live demo stock, and the size
// cards and totals under the hero are drawn from the same data.
import * as THREE from '/vendor/three.module.min.js';

const tab = document.getElementById('tab-operations');
const canvas = document.getElementById('op-machine');
const still = matchMedia('(prefers-reduced-motion: reduce)').matches;
const SIZE_COLOR = {S: '#0fd65c', M: '#2a62ff', L: '#ff8c0a'};
const PER_UNIT = 12;           // balls drawn for each unit in stock
const live = () => (typeof state === 'undefined' ? null : state); // agency.js keeps it on the page

const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));

// ── cards and totals under the hero ─────────────────────────────────────
let lastKey = '';
function renderCards() {
  const op = live()?.operations;
  const key = JSON.stringify(op || null);
  if (key === lastKey) return;
  lastKey = key;
  const sizes = document.getElementById('op-sizes'), stats = document.getElementById('op-stats');
  if (!op || !op.stock.length) {
    sizes.innerHTML = '<div class="op-empty">Stok hələ yüklənməyib — yuxarıdakı düyməni basın.</div>';
    stats.innerHTML = '';
    return;
  }
  sizes.innerHTML = op.stock.map(s => {
    const out = s.quantity < 1;
    return `<article class="op-size ${out ? 'out' : ''}">
      <span class="op-ball" data-size="${esc(s.size)}"></span>
      <small>${esc(s.sku)}</small><h3>Ölçü ${esc(s.size)}</h3>
      <p>${out ? 'Bu ölçü bitib — dəyişmə üçün təklif olunmur.' : 'Dəyişmə üçün rezerv edilə bilər.'}</p>
      <div class="op-figs"><div><small>STOKDA</small><b>${s.quantity}</b></div><div><small>VƏZİYYƏT</small><b class="op-state">${out ? 'bitib' : 'var'}</b></div></div>
    </article>`;
  }).join('');
  const total = op.stock.reduce((n, s) => n + s.quantity, 0);
  const done = op.exchanges.filter(x => x.state === 'confirmed').length;
  stats.innerHTML = [[op.orders.length, 'Test sifarişi'], [total, 'Ədəd stokda'], [done, 'Təsdiqlənmiş dəyişmə']]
    .map(([n, label]) => `<div><b>${n}</b><span>${label}</span></div>`).join('');
}
setInterval(renderCards, 1000);
renderCards();

// ── the machine ─────────────────────────────────────────────────────────
let renderer;
try {
  renderer = new THREE.WebGLRenderer({canvas, antialias: true, alpha: true});
} catch {
  canvas.closest('.op-stage')?.classList.add('no-webgl');
}
if (renderer) {
  renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.NeutralToneMapping;
  renderer.toneMappingExposure = 1.1;
  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(32, 1, 0.1, 100);
  camera.position.set(0, 2.2, 13);
  camera.lookAt(0, 0.6, 0);

  scene.add(new THREE.HemisphereLight('#9fb8ff', '#0a1236', 1.4));
  const key = new THREE.DirectionalLight('#ffffff', 2.6); key.position.set(4, 6, 6); scene.add(key);
  const rim = new THREE.DirectionalLight('#3fa2ff', 3); rim.position.set(-6, 3, -4); scene.add(rim);
  const glow = new THREE.PointLight('#4b7bff', 30, 12); glow.position.set(0, 0.4, 2.5); scene.add(glow);

  const machine = new THREE.Group();
  scene.add(machine);
  const navy = new THREE.MeshPhysicalMaterial({color: '#2d3f9e', roughness: 0.35, metalness: 0.3, clearcoat: 0.8});
  const darkNavy = new THREE.MeshPhysicalMaterial({color: '#1a2466', roughness: 0.5, metalness: 0.3});
  const glass = new THREE.MeshPhysicalMaterial({color: '#9fc0ff', roughness: 0.05, metalness: 0, transparent: true, opacity: 0.22,
    clearcoat: 1, side: THREE.DoubleSide, depthWrite: false});

  // drum: base, glass body, collar and lid
  const R = 1.55, H = 2.4;
  const base = new THREE.Mesh(new THREE.CylinderGeometry(R * 1.04, R * 1.1, 1.5, 64), darkNavy); base.position.y = -1.25; machine.add(base);
  for (let i = 0; i < 8; i++) {   // the slotted lower chamber
    const slot = new THREE.Mesh(new THREE.BoxGeometry(0.08, 1.1, 0.06), navy);
    const a = (i / 8) * Math.PI - Math.PI / 2 + 0.2;
    slot.position.set(Math.sin(a) * R * 1.06, -1.25, Math.cos(a) * R * 1.06); slot.rotation.y = a; machine.add(slot);
  }
  const body = new THREE.Mesh(new THREE.CylinderGeometry(R, R, H, 64, 1, true), glass); body.position.y = 0.7; machine.add(body);
  const collar = new THREE.Mesh(new THREE.CylinderGeometry(R * 1.06, R * 1.06, 0.22, 64), navy); collar.position.y = -0.45; machine.add(collar);
  const lid = new THREE.Mesh(new THREE.CylinderGeometry(R * 0.98, R * 1.06, 0.4, 64), navy); lid.position.y = 2.05; machine.add(lid);
  const cap = new THREE.Mesh(new THREE.CylinderGeometry(0.45, 0.55, 0.25, 32), navy); cap.position.y = 2.35; machine.add(cap);

  // pipe from above, curving down into the lid
  const path = new THREE.CatmullRomCurve3([
    new THREE.Vector3(3.4, 6.5, -0.4), new THREE.Vector3(3.3, 4.2, -0.2), new THREE.Vector3(2.6, 3.4, 0),
    new THREE.Vector3(0.9, 3.25, 0), new THREE.Vector3(0.1, 2.9, 0), new THREE.Vector3(0, 2.4, 0)]);
  machine.add(new THREE.Mesh(new THREE.TubeGeometry(path, 120, 0.3, 24, false), glass));

  // balls in the drum: an instanced pile, rebuilt when the stock changes
  const ballGeo = new THREE.SphereGeometry(0.2, 24, 16);
  const ballMat = new THREE.MeshPhysicalMaterial({roughness: 0.28, clearcoat: 1, clearcoatRoughness: 0.15});
  const MAX = 160;
  const pile = new THREE.InstancedMesh(ballGeo, ballMat, MAX);
  pile.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
  machine.add(pile);
  let balls = [];
  const dummy = new THREE.Object3D();
  function fill(stock) {
    const colours = [];
    (stock || [{size: 'S', quantity: 2}, {size: 'M', quantity: 0}, {size: 'L', quantity: 3}])
      .forEach(s => { for (let i = 0; i < Math.min(s.quantity * PER_UNIT, 60); i++) colours.push(SIZE_COLOR[s.size] || '#cccccc'); });
    for (let i = colours.length - 1; i > 0; i--) { const j = Math.random() * (i + 1) | 0; [colours[i], colours[j]] = [colours[j], colours[i]]; }
    // stack in rings from the floor of the glass upward
    balls = colours.slice(0, MAX).map((c, i) => {
      const perLayer = 22, layer = Math.floor(i / perLayer), k = i % perLayer;
      const ring = k < 14 ? 1.15 : 0.6, n = k < 14 ? 14 : 8, a = (k % n) / n * Math.PI * 2 + layer * 0.4;
      return {c: new THREE.Color(c), x: Math.cos(a) * ring, y: -0.12 + layer * 0.36 + (k < 14 ? 0 : 0.18), z: Math.sin(a) * ring, p: Math.random() * 6};
    });
    pile.count = balls.length;
    balls.forEach((b, i) => pile.setColorAt(i, b.c));
    if (pile.instanceColor) pile.instanceColor.needsUpdate = true;
  }
  let stockKey = '';

  // a ball travelling down the pipe
  const runner = new THREE.Mesh(ballGeo, new THREE.MeshPhysicalMaterial({color: SIZE_COLOR.L, roughness: 0.25, clearcoat: 1}));
  runner.scale.setScalar(1.15);
  machine.add(runner);

  // robot: white body, black visor with glowing eyes
  const robot = new THREE.Group();
  const white = new THREE.MeshPhysicalMaterial({color: '#e8eef8', roughness: 0.3, clearcoat: 1});
  const visor = new THREE.MeshPhysicalMaterial({color: '#05070f', roughness: 0.1, clearcoat: 1});
  const eye = new THREE.MeshBasicMaterial({color: '#4fd1ff'});
  const head = new THREE.Mesh(new THREE.SphereGeometry(0.62, 40, 32), white);
  const face = new THREE.Mesh(new THREE.SphereGeometry(0.5, 40, 32), visor);
  face.position.set(0, 0.06, 0.2); face.scale.set(1, 0.78, 0.9);
  const eyes = [-0.18, 0.18].map(x => { const e = new THREE.Mesh(new THREE.SphereGeometry(0.075, 16, 12), eye); e.position.set(x, 0.08, 0.66); return e; });
  const torso = new THREE.Mesh(new THREE.CapsuleGeometry(0.42, 0.55, 8, 24), white); torso.position.y = -0.95;
  const badge = new THREE.Mesh(new THREE.CylinderGeometry(0.16, 0.16, 0.05, 6), new THREE.MeshBasicMaterial({color: '#3f7cff'}));
  badge.rotation.x = Math.PI / 2; badge.position.set(0, -0.85, 0.42);
  const ring = new THREE.Mesh(new THREE.TorusGeometry(0.5, 0.02, 8, 48), new THREE.MeshBasicMaterial({color: '#4fd1ff'}));
  ring.rotation.x = Math.PI / 2; ring.position.y = -1.85;
  robot.add(head, face, ...eyes, torso, badge, ring);
  robot.position.set(2.6, -0.3, 1.2); robot.rotation.y = -0.5;
  scene.add(robot);

  // little floating scout on the left
  const scout = new THREE.Group();
  const scoutHead = new THREE.Mesh(new THREE.SphereGeometry(0.42, 32, 24), visor);
  const scoutBand = new THREE.Mesh(new THREE.SphereGeometry(0.43, 32, 24, 0, Math.PI * 2, Math.PI * 0.55, Math.PI * 0.45), white);
  const scoutEyes = [-0.12, 0.12].map(x => { const e = new THREE.Mesh(new THREE.SphereGeometry(0.05, 12, 10), eye); e.position.set(x, 0.05, 0.4); return e; });
  scout.add(scoutHead, scoutBand, ...scoutEyes);
  scout.position.set(-2.8, 0.6, 1.0);
  scene.add(scout);

  let visible = false, frame = 0, born = null;
  const size = () => {
    const w = canvas.clientWidth, h = canvas.clientHeight;
    if (!w || !h) return;
    renderer.setSize(w, h, false); camera.aspect = w / h; camera.updateProjectionMatrix();
  };
  new ResizeObserver(size).observe(canvas);
  new IntersectionObserver(([e]) => { visible = e.isIntersecting; wake(); }).observe(canvas);
  new MutationObserver(wake).observe(tab, {attributes: true, attributeFilter: ['class']});
  const pointer = {x: 0, y: 0};
  addEventListener('pointermove', e => { pointer.x = e.clientX / innerWidth * 2 - 1; pointer.y = e.clientY / innerHeight * 2 - 1; }, {passive: true});

  function draw(now) {
    frame = 0;
    if (!visible || !tab.classList.contains('on')) return;
    if (born === null) born = now;
    const t = still ? 3 : (now - born) / 1000;
    const op = live()?.operations;
    const k = JSON.stringify(op?.stock || null);
    if (k !== stockKey) { stockKey = k; fill(op?.stock?.length ? op.stock : null); }

    // the pile settles in, then jiggles gently as if the drum hums
    const settle = Math.min(1, t / 1.6);
    balls.forEach((b, i) => {
      const drop = (1 - Math.min(1, Math.max(0, settle * 2 - i / balls.length))) * 3;
      dummy.position.set(b.x, b.y + drop + Math.sin(t * 3 + b.p) * 0.015, b.z);
      dummy.updateMatrix(); pile.setMatrixAt(i, dummy.matrix);
    });
    pile.instanceMatrix.needsUpdate = true;

    // an order rolls down the pipe every few seconds, colour taken from the sizes in stock
    const cycle = 4.2, u = (t % cycle) / cycle;
    runner.visible = u < 0.75;
    if (runner.visible) runner.position.copy(path.getPointAt(Math.min(1, u / 0.75)));
    if (u < 0.02) {
      const sizes = (op?.stock || []).filter(s => s.quantity > 0).map(s => s.size);
      const pick = sizes.length ? sizes[(t / cycle | 0) % sizes.length] : 'L';
      runner.material.color.set(SIZE_COLOR[pick]);
    }

    machine.rotation.y = -0.35 + pointer.x * 0.12 + Math.sin(t * 0.3) * 0.05;
    machine.rotation.x = pointer.y * 0.04;
    robot.position.y = -0.3 + Math.sin(t * 1.4) * 0.08;
    robot.rotation.y = -0.45 + Math.sin(t * 0.8) * 0.2;
    eyes.forEach(e => { e.scale.y = (t % 3.7) < 0.12 ? 0.15 : 1; });
    ring.scale.setScalar(1 + Math.sin(t * 2) * 0.08);
    scout.position.y = 0.6 + Math.sin(t * 1.1 + 1) * 0.18;
    scout.rotation.y = Math.sin(t * 0.6) * 0.5;
    glow.intensity = 26 + Math.sin(t * 2) * 6;

    const wide = camera.aspect > 1.1;
    scene.position.set(wide ? 0.4 : 0, wide ? -0.4 : -0.2, 0);
    camera.position.z = wide ? 13 : 15.5;
    renderer.render(scene, camera);
    if (!still) frame = requestAnimationFrame(draw);
  }
  function wake() {
    if (!frame && visible && tab.classList.contains('on')) { size(); frame = requestAnimationFrame(draw); }
  }
  if (still) setInterval(wake, 1500);
}
