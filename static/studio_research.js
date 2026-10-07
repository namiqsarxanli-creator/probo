'use strict';
function researchView(){
 const p=current();if(!p)return noProject();
 const b=p.research_brief;
 if(!b)return `${pageHeading('BAZAR ARAŞDIRMASI','Araşdırma çərçivəsi')}<section class="panel"><h2>Bu sifariş ümumi araşdırmadır.</h2><p>Yeni sifariş yaradanda “Bazar araşdırması” seçin və məhsul, region, müştəri və qərarı yazın.</p><button class="button primary" data-action="new">Yeni sifariş</button></section>`;
 const options=p.sources.filter(s=>s.review?.status==='approved').map(s=>`<option value="${s.id}">${e(s.title)}</option>`).join('');
 return `${pageHeading('QƏRAR ÜÇÜN SÜBUT','Bazar araşdırması','Suallar, mənbələr və yoxlanmış məlumatlar.',projectPicker())}${p.mode==='demo'?'<div class="demo-note">Nümayiş: mənbələr və sübutlar uydurmadır; real bazar nəticəsi deyil.</div>':''}<section class="panel"><h2>${e(b.product)}</h2><p><b>Region:</b> ${e(b.region)} · <b>Müştəri:</b> ${e(b.audience)}</p><p><b>Qərar:</b> ${e(b.decision)}</p><div class="info-note">${['queued','searching'].includes(p.source_discovery?.status)?'Agent suallar üzrə mənbə axtarır…':e(p.source_discovery?.message||'Plan hazırdır.')}</div><button class="button" data-view="sources">Mənbələri yoxla ↗</button></section><section class="panel"><h2>Araşdırma planı və məlumat boşluqları</h2>${p.research_plan.map(q=>{const c=p.market_coverage.find(x=>x.id===q.id);return `<article class="source-card"><h3>${e(q.title)}</h3><p>${e(q.question)}</p><p>${e({queued:'Növbədə',searching:'Axtarılır',done:'Axtarış bitdi',error:'Axtarış alınmadı'}[q.status])} · ${q.source_ids.filter(id=>p.sources.some(s=>s.id===id)).length} mənbə · ${c?.count||0} yoxlanmış sübut</p>${q.error?`<p class="form-error">${e(q.error)}</p>`:''}${!c?.count?'<p class="review-note">Məlumat çatışmır — bu suala hələ yoxlanmış cavab yoxdur.</p>':''}</article>`;}).join('')}</section><section class="panel"><h2>Sübut cədvəli</h2>${p.market_evidence.map(x=>{const s=p.sources.find(s=>s.id===x.source_id);return `<article class="source-card"><span class="tag">${e(p.research_plan.find(q=>q.id===x.question_id)?.title)}</span><h3>${e(x.entity||'Bazar məlumatı')}</h3><p>${e(x.claim)}</p><blockquote>${e(x.quote)}</blockquote><p>${e(s?.title)} · ${e(x.region||'Region qeyd edilməyib')} · ${e(x.published_date||'Məlumat tarixi məlum deyil')}</p>${x.stale?'<p class="review-note">Məlumat bir ildən köhnədir; aktuallığını yoxlayın.</p>':''}${s?.review?.status!=='approved'?'<p class="form-error">Mənbə artıq təsdiqlənmiş deyil.</p>':''}${x.conflict_note?`<p class="form-error">Ziddiyyət: ${e(x.conflict_note)}</p>`:''}<form data-market-conflict="${x.id}"><label>Ziddiyyət və ya düzəliş qeydi<input name="note" minlength="3" maxlength="1000" required value="${e(x.conflict_note)}"></label><button class="button" type="submit">Qeydi saxla</button></form><button class="text-button" data-market-remove="${x.id}">Sübutu çıxar</button></article>`;}).join('')||'<p>Hələ sübut yoxdur. Mənbələri təsdiqləyib dəqiq sitat əlavə edin.</p>'}</section><section class="panel"><h2>Yoxlanmış məlumat əlavə et</h2>${options?`<form id="market-evidence-form"><label>Araşdırma sualı<select name="question_id">${p.research_plan.map(q=>`<option value="${q.id}">${e(q.title)}</option>`).join('')}</select></label><label>Təsdiqlənmiş mənbə<select name="source_id">${options}</select></label><label>Rəqib / təşkilat adı (lazım olarsa)<input name="entity" maxlength="180"></label><label>Mənbədə göstərilən məlumat<textarea name="claim" minlength="8" maxlength="1200" required></textarea></label><label>Mənbədən dəqiq sitat<textarea name="quote" minlength="12" maxlength="1000" required></textarea></label><div class="form-grid"><label>Məlumatın aid olduğu region<input name="region" maxlength="300" value="${e(b.region)}"></label><label>Məlumatın tarixi (məlumdursa)<input name="published_date" type="date"></label></div><button class="button primary" type="submit">Sitatı yoxla və saxla</button><p class="form-error" id="market-evidence-error"></p></form>`:'<p>Əvvəl Mənbə qiymətləndirməsi bölməsində uyğun mənbəni təsdiqləyin.</p>'}</section>`;
}
document.addEventListener('change',event=>{
 if(event.target.name!=='research_type')return;
 const market=event.target.value==='market';
 const container=document.getElementById('market-brief-fields');
 container.hidden=!market;
 container.querySelectorAll('input').forEach(input=>{input.required=market;input.disabled=!market;});
});
document.addEventListener('submit',async event=>{
 if(event.target.id==='market-evidence-form'){
  event.preventDefault();await send('market-evidence-add',Object.fromEntries(new FormData(event.target)),'market-evidence-error');
 }else if(event.target.dataset.marketConflict){
  event.preventDefault();await send('market-evidence-conflict',{evidence_id:event.target.dataset.marketConflict,...Object.fromEntries(new FormData(event.target))});
 }
});
document.addEventListener('click',async event=>{
 const button=event.target.closest('[data-market-remove]');
 if(button)await send('market-evidence-remove',{evidence_id:button.dataset.marketRemove});
});
