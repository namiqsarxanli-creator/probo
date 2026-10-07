'use strict';
const $ = selector => document.querySelector(selector);
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
const usd = micro => '$' + ((micro || 0) / 1e6).toFixed(micro && micro < 1e5 ? 5 : 4);
const pct = value => value == null ? '—' : (value * 100).toFixed(0) + '%';
const clock = iso => new Date(iso).toLocaleTimeString('az-AZ', {hour: '2-digit', minute: '2-digit', second: '2-digit'});
const JOB_BADGE = {'göndərildi': 'ok', 'hazırdır': 'ok', 'qaralama': 'info', 'kölgə': 'info', 'işlənir': 'info',
  'insana ötürüldü': 'warn', 'növbədə': ''};
const WORKER_BADGE = {probation: 'info', active: 'ok', warned: 'warn', senior: 'senior', fired: 'bad', rejected: 'bad', reserve: 'info',
  laid_off: 'bad', candidate: 'info'};
const STAFFED = ['probation', 'active', 'warned', 'senior'];
const HR_KINDS = ['hire', 'reject', 'fire', 'warn', 'restore', 'confirm', 'promote', 'demote', 'layoff', 'budget', 'exam', 'vacancy', 'audit'];
const OUTCOME = {passed: 'yoxlamadan keçdi', blocked: 'BLOKLANDI', escalated: 'insana ötürdü', error: 'xəta'};

let state = null, csrf = '', lastKey = '', tab = 'soz', selTicket = null, selTender = null, tenderDocId = null;
let journalFilter = 'hr', policyVersion = null;
const dirty = new Set();
const docCache = {};

function toast(message, bad = false) {
  const box = $('#toast');
  box.textContent = message; box.className = bad ? 'bad' : ''; box.hidden = false;
  clearTimeout(toast.timer); toast.timer = setTimeout(() => { box.hidden = true; }, 5000);
}

async function post(path, body) {
  const response = await fetch(path, {method: 'POST', headers: {'Content-Type': 'application/json', 'X-CSRF-Token': csrf},
    body: JSON.stringify(body)});
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || 'Əməliyyat alınmadı.');
  if (data.csrf) csrf = data.csrf;
  lastKey = '';
  return data;
}

// The CSP forbids style attributes, so geometry is applied through the CSSOM.
function applyGeometry(root) {
  root.querySelectorAll('[data-left],[data-width]').forEach(el => {
    if (el.dataset.left !== undefined) el.style.left = Math.max(0, Math.min(100, +el.dataset.left)) + '%';
    if (el.dataset.width !== undefined) el.style.width = Math.max(0, Math.min(100, +el.dataset.width)) + '%';
  });
}

function workerNames(service) {
  const map = {};
  (state.services[service].workers || []).forEach(w => { map[w.id] = w; });
  return map;
}

function kpi(label, value, tone = '') {
  return `<div class="kpi ${tone}"><span>${esc(label)}</span><b>${value}</b></div>`;
}

// ── Söz ────────────────────────────────────────────────────────────────
function renderSoz() {
  const soz = state.services.soz, c = soz.counts;
  const answered = (c['göndərildi'] || 0) + (c['qaralama'] || 0) + (c['kölgə'] || 0);
  const workCost = soz.kpi.cost - soz.kpi.exam_cost;
  $('#soz-kpis').innerHTML = kpi('Cavablandı', answered, 'green') + kpi('İnsana ötürüldü', c['insana ötürüldü'] || 0)
    + kpi('Bloklanmış yanlış vəd', soz.kpi.blocked, 'red')
    + kpi('Müraciət başına xərc', soz.kpi.finished ? usd(workCost / soz.kpi.finished) : '—')
    + kpi('Növbədə', (c['növbədə'] || 0) + (c['işlənir'] || 0));
  $('#soz-queue').textContent = `rejim: ${state.mode} · son ${soz.jobs.length}`;
  const names = workerNames('soz');
  $('#tickets').innerHTML = soz.jobs.map(job => ticketCard(job, names)).join('')
    || '<div class="empty">Hələ müraciət yoxdur. Yuxarıdan yazın və ya stress testini işə salın.</div>';
  const doc = state.policy_document;
  $('#policy-version').textContent = 'versiya ' + doc.version;
  const marks = clauseMarks(soz.jobs.find(j => j.id === selTicket), doc.clauses);
  let category = null;
  $('#policy').innerHTML = doc.clauses.map(cl => {
    const head = cl.category !== category ? `<div class="cat">${esc(category = cl.category)}</div>` : '';
    return `${head}<div class="clause ${marks[cl.id] || ''}"><i>${cl.id}</i>${esc(cl.text)}</div>`;
  }).join('');
}

function ticketCard(job, names) {
  const label = job.label ? ` · etiket: ${esc(job.label.kind)}` : '';
  const attempts = job.attempts.map(a => {
    const who = names[a.worker_id] ? `${names[a.worker_id].name} (${names[a.worker_id].model_label})` : 'agent';
    const ev = a.evaluation;
    let detail = '';
    if (a.outcome === 'blocked') detail = `<div class="why">🛑 ${esc((ev.problems || [])[0] || '')}</div>`
      + (ev.sentences || []).filter(s => !s.ok).slice(0, 1).map(s => `<div class="who">Agentin cümləsi: «${esc(s.text)}»</div>`).join('');
    if (a.outcome === 'escalated') detail = `<div class="who">Səbəb: ${esc(ev.reason || '')}</div>`;
    return `<div class="attempt ${a.outcome}"><div class="who">${esc(who)} — <b>${OUTCOME[a.outcome] || a.outcome}</b> · ${a.duration_ms} ms · ${usd(a.cost)}</div>${detail}</div>`;
  }).join('');
  const r = job.result;
  const final = !r ? '' : job.status === 'insana ötürüldü'
    ? `<div class="reply handoff">👤 ${esc(r.reason || 'Əməkdaşa ötürüldü.')}</div>`
    : `<div class="reply">✉ ${esc(r.message)}</div>`;
  return `<div class="ticket ${job.id === selTicket ? 'sel' : ''}" data-ticket="${job.id}">
    <div class="head"><div><div class="msg">${esc(job.title)}</div><div class="src">${esc(job.source)}${label} · ${clock(job.created_at)}</div></div>
    <span class="badge ${JOB_BADGE[job.status] || ''}">${esc(job.status)}</span></div>${attempts}${final}</div>`;
}

function clauseMarks(job, clauses) {
  const marks = {};
  if (!job) return marks;
  job.attempts.forEach(a => (a.evaluation.sentences || []).forEach(s => {
    if (!s.span) return;
    const hit = clauses.find(cl => s.span[0] < cl.end && s.span[1] > cl.start);
    if (hit && (s.ok ? marks[hit.id] !== 'bad' : true)) marks[hit.id] = s.ok ? 'ok' : 'bad';
  }));
  return marks;
}

function renderHuman(result) {
  const body = state.policy_document.body;
  const rows = result.sentences.map(s => {
    if (s.courtesy) return `<div class="verdict neutral">${esc(s.text)}<small>nəzakət ifadəsi — fakt yoxdur</small></div>`;
    const evidence = s.span ? `<small>Qayda: «${esc(body.slice(s.span[0], s.span[1]))}»</small>` : '';
    const why = s.problems.map(p => `<div class="why">🛑 ${esc(p)}</div>`).join('');
    return `<div class="verdict ${s.ok ? 'ok' : 'bad'}">${esc(s.text)}${why}${evidence}</div>`;
  }).join('');
  $('#human-result').innerHTML = `<div class="banner ${result.ok ? 'ok' : 'bad'}">${result.ok
    ? '✓ Göndərilə bilər — hər cümlə qaydalarla təsdiqləndi.'
    : '🛑 Bloklandı — bu cavab müştəriyə getməyəcək.'}</div><div class="verdicts">${rows}</div>`;
}

// ── Tender ─────────────────────────────────────────────────────────────
function renderTender() {
  const t = state.services.tender;
  const ready = t.jobs.filter(j => j.status === 'hazırdır');
  const verified = ready.reduce((n, j) => n + j.result.card.filter(r => r.status === 'verified').length, 0);
  const conflicts = ready.reduce((n, j) => n + j.result.card.filter(r => r.status === 'conflict').length, 0);
  $('#tender-kpis').innerHTML = kpi('Analiz edilib', ready.length, 'green') + kpi('Təsdiqlənmiş sahə', verified)
    + kpi('Bloklanmış uydurma', t.kpi.blocked, 'red') + kpi('Ziddiyyət', conflicts)
    + kpi('Növbədə', (t.counts['növbədə'] || 0) + (t.counts['işlənir'] || 0));
  if (!tenderDocId && state.tenders.length) tenderDocId = state.tenders[0].id;
  $('#tender-docs').innerHTML = state.tenders.map(doc => {
    const job = t.jobs.find(j => j.document_id === doc.id);
    const status = job ? `<span class="badge ${JOB_BADGE[job.status] || ''}">${esc(job.status)}</span>` : '';
    return `<div class="docrow ${doc.id === tenderDocId ? 'sel' : ''}"><div data-doc="${doc.id}"><strong>${esc(doc.title)}</strong>
      <small>versiya ${esc(doc.version)} ${doc.sample ? '· nümunə' : ''}</small></div>
      <div class="row">${status}<button data-analyze="${doc.id}">Analiz et</button></div></div>`;
  }).join('');
  const job = t.jobs.find(j => j.id === selTender) || t.jobs.find(j => j.document_id === tenderDocId);
  const docMeta = state.tenders.find(d => d.id === tenderDocId);
  $('#tender-title').textContent = docMeta ? docMeta.title : '';
  $('#tender-card').innerHTML = tenderCard(job, workerNames('tender'));
  $('#tender-card').className = job && job.result ? '' : 'empty';
  renderTenderDoc(job);
}

function tenderCard(job, names) {
  if (!job) return 'Sənəd seçib «Analiz et» düyməsini basın.';
  const tries = job.attempts.map(a => `<div class="attempt ${a.outcome}"><div class="who">${esc(names[a.worker_id]?.name || 'analitik')}
    (${esc(names[a.worker_id]?.model_label || '')}) — <b>${OUTCOME[a.outcome] || a.outcome}</b> · ${usd(a.cost)}</div>
    ${a.outcome === 'blocked' ? (a.evaluation.problems || []).slice(0, 3).map(p => `<div class="why">🛑 ${esc(p)}</div>`).join('') : ''}</div>`).join('');
  if (!job.result) return `<div class="empty">Vəziyyət: ${esc(job.status)}</div>${tries}`;
  const flags = job.result.flags.map(f => `<div class="flag ${f.level}">${esc(f.text)}</div>`).join('');
  const rows = job.result.card.map(row => {
    const badge = {verified: '<span class="badge ok">✓ təsdiqləndi</span>', conflict: '<span class="badge warn">⚠ ziddiyyət</span>',
      missing: '<span class="badge">— tapılmadı</span>'}[row.status];
    const values = row.values.map(v => `<div>${esc(v.value)}</div><div class="q">«${esc(v.quote)}»</div>`).join('');
    return `<tr><td>${esc(row.label)}${row.critical ? '<span class="crit">kritik</span>' : ''}</td><td>${badge}${values}</td></tr>`;
  }).join('');
  return `<div class="flags">${flags}</div><table class="fields">${rows}</table>
    <div class="who">Müstəqil analitiklər: ${esc(job.result.analysts.join(', '))}</div>${tries}`;
}

async function renderTenderDoc(job) {
  if (!tenderDocId) return;
  if (!docCache[tenderDocId]) {
    try { docCache[tenderDocId] = await (await fetch('/api/document?id=' + tenderDocId)).json(); } catch { return; }
  }
  const body = docCache[tenderDocId].body || '';
  const spans = [];
  (job?.result?.card || []).forEach(row => row.values.forEach(v => v.span && spans.push(v.span)));
  let offset = 0;
  $('#tender-doc').innerHTML = body.split('\n').map(line => {
    const start = offset, end = offset + line.length;
    offset = end + 1;
    if (!line.trim()) return '';
    if (line.startsWith('#')) return `<div class="cat">${esc(line.replace(/^#+\s*/, ''))}</div>`;
    const hit = spans.some(s => s[0] < end && s[1] > start);
    return `<div class="clause ${hit ? 'ok' : ''}">${esc(line)}</div>`;
  }).join('');
}

// ── Team ───────────────────────────────────────────────────────────────
function renderTeam() {
  ['soz', 'tender'].forEach(service => {
    const s = state.services[service];
    const staffed = s.workers.filter(w => STAFFED.includes(w.status)).length;
    const hiring = state.hiring.includes(service) ? ' · işə qəbul imtahanı gedir…' : '';
    $(`#team-${service}-meta`).textContent = `${staffed}/${s.headcount} yer tutulub${hiring}`;
    const order = w => STAFFED.includes(w.status) ? 0 : 1;
    $(`#team-${service}`).innerHTML = s.workers.slice().sort((a, b) => order(a) - order(b)).map(workerCard).join('')
      || '<div class="empty">Hələ heç kim işə götürülməyib. Şirkət özü imtahan keçirib işçi götürəcək.</div>';
    applyGeometry($(`#team-${service}`));
  });
  const entries = state.journal.filter(j => journalFilter === 'all' || HR_KINDS.includes(j.kind));
  $('#journal').innerHTML = entries.map(j => `<div class="entry ${j.kind}"><time>${clock(j.time)} · ${j.service === 'soz' ? 'Söz' : 'Tender'}</time>${esc(j.message)}</div>`).join('')
    || '<div class="empty">Jurnal boşdur.</div>';
}

function workerCard(w) {
  const s = w.stats, limit = state.policy.fire_rate;
  const meter = s.judged ? `<div class="meter"><div class="band" data-left="${s.low * 100}" data-width="${(s.high - s.low) * 100}"></div>
      <div class="point" data-left="${(s.block_rate || 0) * 100}"></div><div class="limit" data-left="${limit * 100}"></div></div>
      <div class="meter-note">bloklanma ${pct(s.block_rate)} · 95% interval ${pct(s.low)}–${pct(s.high)} · hədd ${pct(limit)}</div>`
    : '<div class="meter-note">hələ real iş yoxdur</div>';
  const gone = STAFFED.includes(w.status) ? '' : 'gone';
  return `<div class="worker ${w.status} ${gone}">
    <div class="name"><div class="avatar">${esc(w.name[0])}</div><div><b>${esc(w.name)}</b><small>${esc(w.model_label)} · ${esc(w.persona_label)}</small></div></div>
    <span class="badge ${WORKER_BADGE[w.status] || ''}">${esc(state.statuses[w.status] || w.status)}</span>
    ${meter}
    <div class="stat">Yoxlanmış cavab <b>${s.judged}</b></div>
    <div class="stat">Bloklanan <b>${s.blocked}</b></div>
    <div class="stat">İnsana ötürdü <b>${s.escalated}</b></div>
    <div class="stat">Uğurlu cavab başına xərc <b>${s.cost_per_pass ? usd(s.cost_per_pass) : '—'}</b></div>
    <div class="stat">İmtahan balı <b>${w.exam_score == null ? '—' : pct(w.exam_score)}</b></div>
    <div class="stat">Maaş (1M token) <b>$${state.models[w.model].input} / $${state.models[w.model].output}</b></div></div>`;
}

// ── Policy ─────────────────────────────────────────────────────────────
function renderPolicy() {
  document.querySelectorAll('#modes button').forEach(b => b.classList.toggle('on', b.dataset.mode === state.mode));
  const form = $('#settings-form');
  Object.keys(state.policy).forEach(key => {
    const input = form.elements[key];
    if (input && !dirty.has(key) && document.activeElement !== input) input.value = state.policy[key];
  });
  const area = $('#policy-form').elements.body;
  if (policyVersion !== state.policy_document.version && !dirty.has('policy') && document.activeElement !== area) {
    area.value = state.policy_document.body; policyVersion = state.policy_document.version;
  }
}

function render() {
  if (!state) return;
  const budget = state.policy.monthly_budget_usd;
  $('#spend').textContent = `Bu ay: ${usd(state.spent)} / $${budget}`;
  const link = $('#link');
  link.textContent = state.ready ? 'AI bağlıdır' : 'AI bağlantısı yoxdur';
  link.classList.toggle('live', state.ready);
  renderSoz(); renderTender(); renderTeam(); renderPolicy();
}

function chooseTab(next) {
  tab = ['soz', 'tender', 'team', 'policy'].includes(next) ? next : 'soz';
  document.querySelectorAll('#tabs button').forEach(b => b.classList.toggle('on', b.dataset.tab === tab));
  document.querySelectorAll('.tab').forEach(s => s.classList.toggle('on', s.id === 'tab-' + tab));
  if (location.hash.slice(1) !== tab) history.replaceState(null, '', '#' + tab);
}

async function poll() {
  try {
    const response = await fetch('/api/state');
    const next = await response.json();
    csrf = next.csrf;
    const key = JSON.stringify(next);
    if (key !== lastKey) { lastKey = key; state = next; render(); }
  } catch {
    $('#link').textContent = 'server cavab vermir'; $('#link').classList.remove('live');
  } finally { setTimeout(poll, 1500); }
}

// ── events ─────────────────────────────────────────────────────────────
document.addEventListener('click', async event => {
  const el = event.target.closest('button,[data-ticket],[data-doc]');
  if (!el) return;
  try {
    if (el.dataset.tab) return chooseTab(el.dataset.tab);
    if (el.dataset.ticket) { selTicket = el.dataset.ticket; return render(); }
    if (el.dataset.doc) { tenderDocId = el.dataset.doc; selTender = null; return render(); }
    if (el.dataset.filter) {
      journalFilter = el.dataset.filter;
      document.querySelectorAll('#journal-filters button').forEach(b => b.classList.toggle('on', b === el));
      return render();
    }
    if (el.dataset.analyze) {
      el.disabled = true;
      const result = await post('/api/tender', {document_id: el.dataset.analyze});
      tenderDocId = el.dataset.analyze; selTender = result.job_id;
      return toast('Tender iki müstəqil analitikə göndərildi.');
    }
    if (el.dataset.mode) { await post('/api/mode', {mode: el.dataset.mode}); return toast('İş rejimi dəyişdi.'); }
    if (el.id === 'stress') {
      el.disabled = true;
      const result = await post('/api/stress', {count: 40});
      setTimeout(() => { el.disabled = false; }, 3000);
      return toast(`${result.queued} etiketli müraciət növbəyə əlavə edildi.`);
    }
  } catch (error) { toast(error.message, true); el.disabled = false; }
});

function onSubmit(id, handler) {
  $(id).addEventListener('submit', async event => {
    event.preventDefault();
    const button = event.target.querySelector('button[type="submit"]');
    button.disabled = true;
    try { await handler(Object.fromEntries(new FormData(event.target)), event.target); }
    catch (error) { toast(error.message, true); }
    finally { button.disabled = false; }
  });
}

onSubmit('#ticket-form', async (data, form) => {
  const result = await post('/api/ticket', {message: data.message});
  selTicket = result.job_id; form.reset(); toast('Müraciət növbəyə düşdü.');
});
onSubmit('#human-form', async data => { renderHuman(await post('/api/human', {text: data.text})); });
onSubmit('#tender-form', async (data, form) => {
  const result = await post('/api/tender/upload', {title: data.title, body: data.body});
  tenderDocId = result.document.id; form.reset(); toast('Tender əlavə edildi. İndi «Analiz et» düyməsini basın.');
});
onSubmit('#settings-form', async data => {
  const policy = {};
  Object.entries(data).forEach(([k, v]) => { if (v !== '') policy[k] = Number(v); });
  await post('/api/settings', {policy}); dirty.clear(); toast('Siyasət saxlanıldı.');
});
onSubmit('#policy-form', async data => {
  const result = await post('/api/policy', {body: data.body});
  dirty.delete('policy'); toast('Yeni qaydalar versiyası: ' + result.document.version);
});
$('#settings-form').addEventListener('input', event => dirty.add(event.target.name));
$('#policy-form').addEventListener('input', () => dirty.add('policy'));
window.addEventListener('hashchange', () => chooseTab(location.hash.slice(1)));

chooseTab(location.hash.slice(1));
poll();
