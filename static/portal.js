'use strict';
const params=new URLSearchParams(location.search),id=params.get('id'),token=params.get('token');
const escapeText=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const projectStatus={draft:'Qaralama',running:'İşləyir',paused:'Fasilədə',rate_limited:'Gözləyir',budget_blocked:'Büdcə gözləyir',quality_blocked:'Keyfiyyət baxışı',error:'Xəta',interrupted:'Bərpa gözləyir',awaiting_approval:'Təsdiq gözləyir',completed:'Tamamlandı'};
const itemStatus={todo:'Gözləyir',doing:'İcradadır',done:'Bitib'};
let csrf='';
async function loadPortal(){
 const box=document.getElementById('portal-content');
 try{
  const response=await fetch('/api/portal?id='+encodeURIComponent(id||'')+'&token='+encodeURIComponent(token||''));
  const p=await response.json();if(!response.ok)throw Error(p.error||'Keçid açılmadı.');csrf=p.csrf;
  box.innerHTML=`<h1>${escapeText(p.title)}</h1><p>${escapeText(p.client)} · ${escapeText(projectStatus[p.status]||p.status)}</p><section class="card"><h2>İşin gedişi</h2><p>${p.progress} / ${p.total_steps} araşdırma mərhələsi tamamlanıb.</p><progress max="${p.total_steps}" value="${p.progress}"></progress><p>${escapeText(p.objective)}</p></section><section class="card"><h2>Tapşırıqlar</h2>${p.work_items.length?`<ul>${p.work_items.map(i=>`<li>${escapeText(i.title)} — ${escapeText(i.owner)} · ${escapeText(i.due)} · ${escapeText(itemStatus[i.status]||i.status)}</li>`).join('')}</ul>`:'<p>Hələ tapşırıq yoxdur.</p>'}</section>${p.report?`<section class="card"><h2>Təsdiqlənmiş hesabat</h2><pre>${escapeText(p.report)}</pre></section>`:''}<section class="card"><h2>Rəy göndər</h2><form id="feedback-form"><textarea name="message" minlength="3" maxlength="2000" required></textarea><p><button class="button" type="submit">Rəyi saxla</button></p><p id="feedback-message" role="status"></p></form></section><section class="card"><h2>Əvvəlki rəylər</h2>${p.feedback.length?p.feedback.slice().reverse().map(f=>`<p>${escapeText(f.message)}<br><small>${escapeText(new Date(f.time).toLocaleString('az-AZ'))}</small></p>`).join(''):'<p>Hələ rəy yoxdur.</p>'}</section>`;
 }catch(error){box.innerHTML=`<section class="card error">${escapeText(error.message)}</section>`;}
}
document.addEventListener('submit',async event=>{if(event.target.id!=='feedback-form')return;event.preventDefault();const status=document.getElementById('feedback-message');status.textContent='Saxlanır…';try{const response=await fetch('/api/portal/feedback',{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},body:JSON.stringify({project_id:id,portal_token:token,message:event.target.elements.message.value})});const result=await response.json();if(!response.ok)throw Error(result.error);await loadPortal();}catch(error){status.textContent=error.message;status.className='error';}});
loadPortal();
