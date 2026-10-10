// Komanda və HR — the 3D scenes behind the section: a swirl of extruded arcs in the hero
// (it turns and opens up as you scroll), a small copy inside the headline, and tilted rings
// behind the three HR rules. Each scene renders only while its tab is open and it is on screen.
import * as THREE from '/vendor/three.module.min.js';

const tab = document.getElementById('tab-team');
const still = matchMedia('(prefers-reduced-motion: reduce)').matches;
const pointer = {x: 0, y: 0};
addEventListener('pointermove', e => {
  pointer.x = e.clientX / innerWidth * 2 - 1;
  pointer.y = e.clientY / innerHeight * 2 - 1;
}, {passive: true});

// How far the element has scrolled past the top of the viewport: 0 in view, 1 gone.
const progress = el => {
  const r = el.getBoundingClientRect();
  return Math.min(1, Math.max(0, -r.top / Math.max(1, r.height)));
};
const ease = t => 1 - Math.pow(1 - Math.min(1, Math.max(0, t)), 3);

function stage(canvas, build, {fov = 35, z = 9} = {}) {
  let renderer;
  try {
    renderer = new THREE.WebGLRenderer({canvas, antialias: true, alpha: true, powerPreference: 'high-performance'});
  } catch {
    canvas.closest('.hr-hero, .hr-rings, .hr-inline')?.classList.add('no-webgl');
    return;
  }
  renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.05;
  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(fov, 1, 0.1, 100);
  camera.position.set(0, 0, z);
  const tick = build(scene, camera);

  let visible = false, born = null, frame = 0;
  const size = () => {
    const w = canvas.clientWidth, h = canvas.clientHeight;
    if (!w || !h) return;
    renderer.setSize(w, h, false);
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
  };
  new ResizeObserver(size).observe(canvas);
  new IntersectionObserver(([entry]) => { visible = entry.isIntersecting; wake(); }).observe(canvas);
  new MutationObserver(wake).observe(tab, {attributes: true, attributeFilter: ['class']});

  function draw(now) {
    frame = 0;
    if (!visible || !tab.classList.contains('on')) return;
    if (born === null) born = now;
    const t = still ? 6 : (now - born) / 1000;
    tick(t, camera);
    renderer.render(scene, camera);
    if (!still) frame = requestAnimationFrame(draw);
  }
  function wake() {
    if (!frame && visible && tab.classList.contains('on')) {
      size();
      frame = requestAnimationFrame(draw);
    }
  }
  if (still) addEventListener('scroll', wake, {passive: true});
}

function light(scene, {warm = '#ffd2f1', cool = '#9fb0ff'} = {}) {
  scene.add(new THREE.HemisphereLight('#ffffff', '#b89be8', 1.5));
  const key = new THREE.DirectionalLight('#ffffff', 2.4);
  key.position.set(-3, 5, 6);
  const fill = new THREE.DirectionalLight(warm, 1.4);
  fill.position.set(5, -3, 3);
  const rim = new THREE.DirectionalLight(cool, 1.6);
  rim.position.set(2, 3, -5);
  scene.add(key, fill, rim);
}

// One curved blade: an annular sector, extruded and bevelled.
function blade(inner, outer, span, depth) {
  const shape = new THREE.Shape();
  shape.absarc(0, 0, outer, 0, span, false);
  shape.absarc(0, 0, inner, span, 0, true);
  shape.closePath();
  const geometry = new THREE.ExtrudeGeometry(shape, {depth, curveSegments: 48, bevelEnabled: true,
    bevelThickness: 0.05, bevelSize: 0.05, bevelSegments: 5});
  geometry.translate(0, 0, -depth / 2);
  return geometry;
}

function swirl({blades = 8, scale = 1} = {}) {
  const material = new THREE.MeshPhysicalMaterial({color: '#a487dc', roughness: 0.34, clearcoat: 0.7,
    clearcoatRoughness: 0.25, sheen: 0.6, sheenColor: new THREE.Color('#ffd9f6'), sheenRoughness: 0.4});
  const group = new THREE.Group();
  const parts = [];
  for (let i = 0; i < blades; i++) {
    const outer = i % 2 ? 1.02 : 1.28;
    const geometry = blade(outer - 0.3, outer, i % 2 ? 1.5 : 1.75, 0.34);
    const mesh = new THREE.Mesh(geometry, material);
    const pivot = new THREE.Group();
    const angle = i / blades * Math.PI * 2;
    pivot.rotation.z = angle;
    mesh.rotation.z = 0.9;
    pivot.add(mesh);
    group.add(pivot);
    parts.push({pivot, mesh, angle, offset: i % 2 ? 0.55 : 0.78, z: (i % 2 ? 0.16 : -0.16)});
  }
  group.scale.setScalar(scale);
  // Blades sit at their resting radius; `open` pushes them apart, `intro` grows them in one by one.
  group.userData.pose = (open, intro, t) => parts.forEach((p, i) => {
    const r = p.offset + open * 0.9;
    p.mesh.position.set(r, 0, p.z * (1 + open * 3));
    const grow = ease(intro * 1.6 - i * 0.07);
    p.mesh.scale.setScalar(Math.max(0.001, grow));
    p.mesh.rotation.x = Math.sin(t * 0.7 + i) * 0.08 + open * 0.6;
  });
  return group;
}

// ── hero swirl ───────────────────────────────────────────────────────
const hero = document.querySelector('#tab-team .hr-hero');
stage(document.getElementById('hr-swirl'), (scene, camera) => {
  light(scene);
  const shape = swirl({scale: 1.05});
  const orbit = new THREE.Mesh(new THREE.TorusGeometry(3.1, 0.014, 12, 220),
    new THREE.MeshBasicMaterial({color: '#ffffff', transparent: true, opacity: 0.75}));
  const moon = new THREE.Mesh(new THREE.SphereGeometry(0.2, 48, 32),
    new THREE.MeshPhysicalMaterial({color: '#2b2f6b', roughness: 0.3, clearcoat: 1}));
  const pearl = new THREE.Mesh(new THREE.SphereGeometry(0.12, 32, 24),
    new THREE.MeshPhysicalMaterial({color: '#ffffff', roughness: 0.1, clearcoat: 1, transparent: true, opacity: 0.85}));
  const system = new THREE.Group();
  system.add(shape, orbit, moon, pearl);
  scene.add(system);
  return t => {
    const wide = camera.aspect > 1.15;
    const p = progress(hero);
    system.position.set(wide ? 3.3 : 0, wide ? -0.35 : -1.1, 0);
    shape.userData.pose(ease(p * 1.4), t / 1.6, t);
    shape.rotation.z = -t * 0.32 - p * 3.2;
    system.rotation.x = -0.55 + pointer.y * 0.18 + p * 0.5;
    system.rotation.y = 0.35 + pointer.x * 0.25;
    orbit.rotation.set(1.2, 0.25, 0);
    const a = t * 0.45;
    moon.position.set(Math.cos(a) * 3.1, Math.sin(a) * 3.1 * Math.cos(1.2), Math.sin(a) * 3.1 * Math.sin(1.2));
    pearl.position.set(Math.cos(a + 2.6) * 3.1, Math.sin(a + 2.6) * 3.1 * Math.cos(1.2), Math.sin(a + 2.6) * 3.1 * Math.sin(1.2));
    system.scale.setScalar(1 + p * 0.35);
  };
});

// ── the small swirl inside the headline ──────────────────────────────
stage(document.getElementById('hr-mini'), scene => {
  light(scene);
  const shape = swirl({scale: 1.45});
  scene.add(shape);
  shape.rotation.x = -0.45;
  return t => {
    shape.userData.pose(0, t / 1.2, t);
    shape.rotation.z = -t * 0.9;
  };
}, {fov: 30, z: 7});

// ── rings behind the HR rules ────────────────────────────────────────
const band = document.querySelector('#tab-team .hr-rings');
stage(document.getElementById('hr-ring'), (scene, camera) => {
  light(scene, {warm: '#c9b8ff', cool: '#7d8cff'});
  const ring = (inner, outer, depth) => {
    const shape = new THREE.Shape();
    shape.absarc(0, 0, outer, 0, Math.PI * 2, false);
    shape.holes.push(new THREE.Path().absarc(0, 0, inner, 0, Math.PI * 2, true));
    const g = new THREE.ExtrudeGeometry(shape, {depth, curveSegments: 160, bevelEnabled: true,
      bevelThickness: 0.04, bevelSize: 0.04, bevelSegments: 4});
    g.translate(0, 0, -depth / 2);
    return g;
  };
  const metal = new THREE.MeshPhysicalMaterial({color: '#6f6ff2', emissive: '#2b2ca8', emissiveIntensity: 0.35,
    roughness: 0.22, metalness: 0.25, clearcoat: 0.8, clearcoatRoughness: 0.2});
  const big = new THREE.Mesh(ring(2.05, 2.3, 0.42), metal);
  const small = new THREE.Mesh(ring(0.42, 0.55, 0.16), metal);
  const track = new THREE.LineLoop(new THREE.BufferGeometry().setFromPoints(
    Array.from({length: 180}, (_, i) => new THREE.Vector3(Math.cos(i / 180 * Math.PI * 2), Math.sin(i / 180 * Math.PI * 2), 0))),
    new THREE.LineBasicMaterial({color: '#aab0ff', transparent: true, opacity: 0.45}));
  track.scale.setScalar(1.05);
  const dots = [0, 2.1, 4.2].map(() => new THREE.Mesh(new THREE.SphereGeometry(0.045, 16, 12),
    new THREE.MeshBasicMaterial({color: '#ffffff'})));
  const group = new THREE.Group();
  group.add(big, small, track, ...dots);
  scene.add(group);
  return t => {
    const wide = camera.aspect > 1.15;
    const r = band.getBoundingClientRect();
    const through = 1 - (r.top + r.height) / (innerHeight + r.height); // 0 entering, 1 leaving
    group.position.set(0, wide ? 0 : 0.6, 0);
    group.scale.setScalar(wide ? 0.82 : 0.7);
    group.rotation.y = 0.62 + Math.sin(t * 0.35) * 0.1 + through * 0.35 + pointer.x * 0.1;
    group.rotation.x = 0.12 + pointer.y * 0.08;
    small.rotation.y = t * 0.9;
    small.rotation.x = t * 0.4;
    dots.forEach((d, i) => {
      const a = t * 0.6 + i * 2.1;
      d.position.set(Math.cos(a) * 1.05, Math.sin(a) * 1.05, 0);
    });
  };
});
