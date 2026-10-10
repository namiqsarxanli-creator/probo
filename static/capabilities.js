'use strict';
let traceJob = null, traceKey = '', currentTrace = null, traceGeneration = 0;
let companyLoaded = false;
const fitLabels = {matches:'✓ Sənəd uyğun gəlir', fails:'✕ Tələb ödənmir', missing:'? Sübut çatışmır'};
const baseRender = render;
render = function() {
  baseRender();
  if (!companyLoaded && state.company_profile) {
    if (!$('#company-form [name=name]').value && !$('#company-form [name=body]').value) {
      $('#company-form [name=name]').value=state.company_profile.name||'';
      $('#company-form [name=body]').value=state.company_profile.body||'';
    }
    companyLoaded=true;
  }
  const op = state.operations;
  if (op) {
    $('#operation-orders').innerHTML = op.orders.map(o => `<div class="tool-note"><b>TEST ${esc(o.id)} · ${esc(o.product)}</b><p>${esc(o.status)} · Ölçü ${esc(o.size)} · Qəbul: ${esc(o.received_on)}</p></div>`).join('') || '<p>Test məlumatları yüklənməyib.</p>';
    $('#operation-stock').innerHTML = op.stock.map(s => `<span class="badge">${esc(s.sku)} / ${esc(s.size)}: ${s.quantity}</span>`).join(' ');
    $('#operation-exchanges').innerHTML = op.exchanges.map(x => `<p>${esc(x.order_id)} → ${esc(x.size)} · ${x.state==='confirmed'?'✓ Stok rezerv edildi':'Təsdiq gözləyir'} ${x.state==='prepared'?`<button type="button" data-exchange="${x.id}">Test dəyişməni təsdiqlə</button>`:''}</p>`).join('') || '<p>Hələ əməliyyat yoxdur.</p>';
  }
  if (traceJob) {
    const job = Object.values(state.services).flatMap(s=>s.jobs).find(j=>j.id===traceJob);
    const key = JSON.stringify(job);
    if (key!==traceKey) { traceKey=key; loadTrace(traceJob); }
  }
};
async function getCapability(path) {
  const response = await fetch(path); const data = await response.json();
  if (!response.ok) throw new Error(data.error || 'Məlumat alınmadı.'); return data;
}
async function loadTrace(id) {
  const generation = ++traceGeneration;
  try {
    const result = await getCapability('/api/trace?job_id='+encodeURIComponent(id));
    if (generation!==traceGeneration) return;
    currentTrace=result;
    $('#decision-map').innerHTML=`<p class="muted">Qayda versiyası ${esc(result.document.version)} · ${esc(result.notice)}</p><div class="decision-flow">${result.steps.map((s,i)=>`<article class="decision-step ${s.status==='blocked'?'blocked':''}"><small>ADDIM ${i+1}</small><h3>${esc(s.title)}</h3><span class="cap-status">${esc(OUTCOME[s.status]||s.status)}</span><p>${esc(s.detail)}</p>${s.duration_ms!=null?`<small>${s.duration_ms} ms · ${usd(s.cost)}</small>`:''}${s.tool?`<div class="tool-note">TEST · ${esc(s.tool.name)}<br>Sifariş ${esc(s.tool.order.id)} · ${esc(s.tool.order.status)}<br>Məlumat lokal bazadan oxundu.</div>`:''}${(s.evidence||[]).map((ev,n)=>`<button type="button" data-evidence-step="${i}" data-evidence-index="${n}">${esc(ev.text||ev.quote)} ↗<small>${ev.ok?'Sitat yoxlamadan keçib':'Sitat yoxlamada keçməyib'}</small></button>`).join('')}</article>`).join('')}</div>`;
  } catch(error) { toast(error.message,true); }
}
document.addEventListener('click', async event=>{
  const b=event.target.closest('button'); if(!b) return;
  try {
    if(b.dataset.trace){traceJob=b.dataset.trace;traceKey='';chooseTab('trace');return render();}
    if(b.dataset.evidenceStep!==undefined){
      const ev=currentTrace.steps[+b.dataset.evidenceStep].evidence[+b.dataset.evidenceIndex];
      const body=currentTrace.document.body, points=Array.from(body), span=ev.span;
      $('#decision-source').innerHTML=`<p>${esc(ev.quote)}</p><pre class="evidence-source">${span?esc(points.slice(0,span[0]).join(''))+'<mark>'+esc(points.slice(span[0],span[1]).join(''))+'</mark>'+esc(points.slice(span[1]).join('')):esc(body)}</pre>`;
      $('#decision-source mark')?.scrollIntoView({block:'center',behavior:'smooth'});return;
    }
    if(b.id==='load-operations'){await post('/api/operations/demo',{});return toast('Test sifarişləri hazırdır. Mesaj Agentliyində 48213 barədə soruşun.');}
    if(b.dataset.exchange){await post('/api/operations/confirm',{exchange_id:b.dataset.exchange});$('#exchange-preview').textContent='✓ Test müraciəti təsdiqləndi; əvəzləyici ölçü stokda rezerv edildi.';return toast('Test stok rezerv edildi.');}
    if(b.id==='company-example'){
      const year=new Date().getFullYear()-1;
      $('#company-form [name=name]').value='NÜMUNƏ — Demo Təchizat MMC';
      $('#company-form [name=body]').value=`NÜMUNƏ SƏNƏD — real şirkət məlumatı deyil.\n${year} illik dövriyyə: 600 000 AZN.\n${year}-05-10 tarixli oxşar müqavilə uğurla icra edilib: Müqavilə A.\n${year}-09-15 tarixli oxşar müqavilə uğurla icra edilib: Müqavilə B.\nVergi arayışı təqdim edilməyib.`;return;
    }
    if(b.id==='company-check'){
      if(!tenderDocId) throw new Error('Tender sənədi seçin.');
      const result=await getCapability('/api/company/fit?document_id='+encodeURIComponent(tenderDocId));
      const label={fails:'Maneə tapıldı',incomplete:'Məlumat çatışmır',document_match:'Tanına bilən tələblər sənədə uyğun gəlir'}[result.outcome];
      $('#company-fit').className='';
      $('#company-fit').innerHTML=`<div class="banner ${result.outcome==='fails'?'bad':'warn'}"><b>${esc(label)}</b> · ${esc(result.profile||'Şirkət profili yoxdur')}</div><p>${esc(result.notice)}</p><small>Tender ${esc(result.document_version)} · Şirkət ${esc(result.profile_version||'—')}</small><table class="fit-grid"><thead><tr><th>Tələb</th><th>Şirkət sənədinin sübutu</th><th>Nəticə</th></tr></thead><tbody>${result.rows.map(r=>`<tr><td>${esc(r.clause)} · ${esc(r.requirement)}</td><td><blockquote>${esc(r.proof||'Sübut yoxdur')}</blockquote></td><td><b class="status-${r.status}">${esc(fitLabels[r.status])}</b><p>${esc(r.explanation)}</p></td></tr>`).join('')}</tbody></table>`;return;
    }
  }catch(error){toast(error.message,true);}
});
onSubmit('#company-form',async data=>{await post('/api/company',data);$('#company-fit').textContent='Profil yeniləndi. Müqayisəni yenidən başladın.';toast('Şirkət profili və sübut sənədi saxlanıldı.');});
onSubmit('#exchange-form',async data=>{const r=await post('/api/operations/prepare',data);$('#exchange-preview').innerHTML=`<div class="banner warn">TEST ${esc(r.order.id)}: ${esc(r.order.size)} → ${esc(r.size)}. Stok hələ dəyişməyib.</div>${r.rules.map(c=>`<p>${esc(c.id)} · ${esc(c.text)}</p>`).join('')}<button type="button" data-exchange="${r.id}" class="primary">Test dəyişməni təsdiqlə və stoku rezerv et</button>`;});
