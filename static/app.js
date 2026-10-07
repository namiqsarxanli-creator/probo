const $ = id => document.getElementById(id);
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const roles = {director:'Rəhbər',researcher:'Araşdırmaçı',analyst:'Analitik',editor:'Redaktor',reviewer:'Yoxlayıcı'};
const statuses = {idle:'Başlanmayıb',running:'İşləyir',paused:'Fasilədə',budget_blocked:'Büdcə gözləyir',completed:'Tamamlandı'};
let state, busy = false, version = '', pollError = false;
function error(message){$('error').textContent=message;$('error').hidden=!message;}
async function action(name,data={}){
  if(busy)return;busy=true;error('');
  document.querySelectorAll('button').forEach(b=>b.disabled=true);
  try{const res=await fetch('/api/'+name,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});const s=await res.json();if(!res.ok)throw Error(s.error);version='';render(s);}
  catch(e){error(e.message);}
  finally{busy=false;document.querySelectorAll('button').forEach(b=>b.disabled=false);if(state)render(state);}
}
function render(s){
 state=s;$('setup').hidden=!!s.id;$('company').hidden=!s.id;if(!s.id)return;
 $('mission').textContent=s.objective;$('status').textContent=statuses[s.status];
 $('toggle').textContent=s.status==='running'?'Fasilə ver':'Davam et';$('toggle').disabled=s.status==='completed';
 $('employee-count').textContent=s.employees.filter(e=>e.status==='active').length;
 $('task-count').textContent=s.tasks.filter(t=>t.status==='done').length+' / 4';
 $('spent').textContent=(s.spent/100).toFixed(2);$('remaining').textContent=((s.budget-s.spent)/100).toFixed(2)+' / '+(s.budget/100).toFixed(2)+' kredit qalıb';
 $('handoff-count').textContent=s.handoffs.length;
 if(document.activeElement!==$('new-budget'))$('new-budget').value=(s.budget/100).toFixed(2);
 $('employees').innerHTML=s.employees.map(e=>`<article class="employee ${esc(e.status)}"><div class="employee-top"><span class="avatar">${esc(e.name[0])}</span><div><strong>${esc(e.name)}</strong><small>${roles[e.role]} · ${e.status==='active'?'Aktiv':'Çıxarılıb'}</small></div></div><div class="employee-bottom"><span>${e.completed} tamamlanan iş</span>${e.role!=='director'&&e.status==='active'&&s.status!=='completed'?`<button class="fire" data-fire="${e.id}">İşdən çıxar</button>`:''}</div></article>`).join('');
 $('tasks').innerHTML=s.tasks.map(t=>`<div class="task"><div class="task-top"><strong>${esc(t.title)}</strong><span>${{queued:'Növbədə',working:'İşlənir',done:'Tamamlandı'}[t.status]}</span></div><progress max="4" value="${t.progress}" aria-label="${esc(t.title)}"></progress><small>${t.progress}/4 mərhələ · ${esc(s.employees.find(e=>e.id===t.assignee)?.name||'İşçi gözləyir')}</small></div>`).join('')||'<div class="empty">Rəhbər iş planını hazırlayır…</div>';
 $('events').innerHTML=s.events.slice(-60).reverse().map(e=>`<article class="event"><time>${new Date(e.time).toLocaleTimeString('az-AZ')}</time><p>${esc(e.message)}</p></article>`).join('');
 $('packages').innerHTML=s.handoffs.map(h=>`<div class="package"><strong>${esc(s.tasks.find(t=>t.id===h.task_id)?.title)}</strong><br>${esc(s.employees.find(e=>e.id===h.from_id)?.name)} → ${esc(s.employees.find(e=>e.id===h.to_id)?.name||'Əvəzləyici gözləyir')}<br><small>${h.progress}/4 mərhələ saxlanıldı · ${{pending:'Təhvil gözləyir',accepted:'Qəbul edildi',verified:'İş tamamlandı; təhvil yoxlanıldı'}[h.status]}</small><details><summary>Təhvil qeydləri</summary>${h.notes.map(n=>`<p>${esc(n)}</p>`).join('')}<p>${esc(h.next_step)}</p></details></div>`).join('')||'<div class="empty">Hələ təhvil yoxdur. İşləyən mütəxəssisi çıxararaq bərpa prosesini sınaya bilərsiniz.</div>';
 $('candidates').innerHTML=s.candidates.map(c=>`<details><summary>${roles[c.role]} · Seçildi: ${esc(c.selected)}</summary><table><thead><tr><th>Namizəd</th><th>Keyfiyyət</th><th>Sürət</th><th>Qənaət</th><th>Bal</th></tr></thead><tbody>${c.trials.map(t=>`<tr><td>${esc(t.name)}</td><td>${t.quality}</td><td>${t.speed}</td><td>${t.economy}</td><td>${t.score}</td></tr>`).join('')}</tbody></table><p class="empty">Sabit simulyasiya balları: 60% keyfiyyət, 20% sürət, 20% qənaət.</p></details>`).join('')||'<div class="empty">İlk işə qəbul ehtiyac yarananda başlayacaq.</div>';
 $('report-panel').hidden=!s.report;$('report').textContent=s.report||'';
}
$('create-form').addEventListener('submit',e=>{e.preventDefault();action('create',{objective:$('objective').value,budget:$('budget').value});});
$('budget-form').addEventListener('submit',e=>{e.preventDefault();action('budget',{budget:$('new-budget').value});});
$('toggle').addEventListener('click',()=>action(state.status==='running'?'pause':'resume'));
$('employees').addEventListener('click',e=>{const b=e.target.closest('[data-fire]');if(b)action('fire',{id:b.dataset.fire});});
async function poll(){try{if(!busy){const r=await fetch('/api/state');if(!r.ok)throw Error('Serverə qoşulmaq alınmadı.');const s=await r.json();const next=JSON.stringify(s);if(next!==version){version=next;render(s);}if(pollError){error('');pollError=false;}}}catch(e){pollError=true;error('Serverlə əlaqə kəsildi. Avtomatik yenidən qoşulacaq.');}finally{setTimeout(poll,1200);}}
poll();
