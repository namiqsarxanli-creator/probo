'use strict';

const sourceDecision = {pending:'Yoxlanmayıb',approved:'Təsdiqlənib',rejected:'Uyğun deyil'};
const factDecision = {pending:'Yoxlanmayıb',accepted:'Qəbul edilib',rejected:'Çıxarılıb'};
const callDecision = {running:'İşləyir',done:'Tamamlandı',error:'Xəta',rate_limited:'Limit gözləyir',discarded:'Tətbiq edilmədi'};

function sourceReviewView(){
 const p=current(); if(!p)return noProject();
 const accepted=p.sources.filter(s=>s.review?.status==='approved').length;
 const searching=['queued','searching'].includes(p.source_discovery?.status);
 const actions=p.status==='draft'&&p.mode==='live'?`<div class="toolbar-actions">${p.sources.length<10?`<button class="button" data-command="discover-sources" ${searching?'disabled':''}>${searching?'Mənbələr axtarılır…':'Yenidən mənbə axtar'}</button><button class="button" data-action="source">+ Öz mənbəmi əlavə et</button>`:''}${accepted>=2?'<button class="button primary" data-command="start">Təsdiqlənmiş mənbələrlə başlat ↗</button>':''}</div>`:'';
 const discovery=p.mode==='live'?`<div class="info-note">${searching?'Agent mövzu üzrə açıq mənbələr axtarır…':e(p.source_discovery?.message||'Mənbə axtarışı hazırdır.')}</div>`:'';
 return `${pageHeading('SÜBUT BAZASI','Mənbə qiymətləndirməsi','Mənbəni oxu, uyğunluğunu qiymətləndir və yalnız sonra araşdırmanı başlat.',projectPicker())}<div class="section-toolbar"><span>${accepted} təsdiqlənib · ${p.sources.length} / 10 mənbə</span>${actions}</div>${discovery}<div class="source-grid">${p.sources.map((s,i)=>`<article class="panel source-card"><div class="source-top"><span class="source-number">${String(i+1).padStart(2,'0')}</span><span class="tag">${e(sourceDecision[s.review?.status]||'Yoxlanmayıb')}</span></div><h2>${e(s.title)}</h2><p class="source-url">${s.url?`<a href="${e(s.url)}" target="_blank" rel="noreferrer noopener">${e(new URL(s.url).hostname)} ↗</a>`:'Nümayiş mənbəsi'}</p><p class="source-excerpt">${e(s.body.slice(0,300))}${s.body.length>300?'…':''}</p><div class="source-meta"><span>${e({demo:'Nümayiş',pasted:'Əl ilə mətn',web:'Səhifə mətni',search:'Axtarış xülasəsi'}[s.origin]||s.origin)}</span><span>Uyğunluq: ${s.review?.relevance||'—'}/5</span><span>Saxlanıb: ${date(s.captured_at)}</span></div>${s.review?.note?`<p class="review-note">${e(s.review.note)}</p>`:''}<div class="source-bottom"><button class="text-button" data-source="${s.id}">Tam mətn ↗</button>${p.status==='draft'&&p.mode==='live'?`<button class="button" data-review-source="${s.id}">Qiymətləndir</button><button class="text-button" data-remove-source="${s.id}">Çıxar</button>`:''}</div></article>`).join('')||'<section class="panel"><h2>Mənbə gözlənilir.</h2><p>Agent mövzuya uyğun açıq mənbələri axtarır. Siz də istədiyiniz mənbəni əlavə edə bilərsiniz.</p></section>'}</div><div class="info-note">Axtarışa sifarişin adı, bazar araşdırmasında məhsul və region göndərilir. “Axtarış xülasəsi” mənbənin tam mətni deyil; URL və mətnin uyğunluğunu yoxlayın.</div>`;
}

function evidenceContext(source,quote){
 if(!source)return '';
 const body=source.body||'';
 const index=body.toLocaleLowerCase().indexOf((quote||'').toLocaleLowerCase());
 if(index<0)return body.slice(0,650);
 return `${index>180?'…':''}${body.slice(Math.max(0,index-180),Math.min(body.length,index+quote.length+180))}${index+quote.length+180<body.length?'…':''}`;
}

function factReviewView(){
 const p=current(); if(!p)return noProject();
 const findings=p.tasks.flatMap(t=>t.output?.findings||[]);
 const checked=findings.filter(f=>f.review?.status&&f.review.status!=='pending').length;
 const canApprove=p.mode==='demo'||(findings.length>0&&checked===findings.length&&p.tasks.every(t=>t.output?.findings.some(f=>f.review?.status==='accepted')));
 const action=p.status==='awaiting_approval'?`<div class="toolbar-actions"><button class="button" data-view="reports">Hesabata bax</button>${canApprove?'<button class="button primary" data-command="approve">✓ Hesabatı təsdiqlə</button>':''}</div>`:'<button class="button" data-view="reports">Hesabata bax</button>';
 return `${pageHeading('İNSAN BAXIŞI','Fakt yoxlama masası','Sitatın mənbədə olması avtomatik yoxlanıb; iddianın mənası və konteksti sizin qərarınızdır.',projectPicker())}<div class="section-toolbar"><span>${checked} / ${findings.length} fakt yoxlanıb · ${pill(p)}</span>${action}</div>${!findings.length?'<section class="panel"><h2>Hələ yoxlanacaq fakt yoxdur.</h2><p>Hesabat hazır olduqda iddialar burada görünəcək.</p></section>':p.tasks.map(t=>`<section class="panel review-task"><div class="panel-heading"><h2>${e(t.title)}</h2><span class="count-label">${t.output?.findings.length||0} FAKT</span></div>${(t.output?.findings||[]).map(f=>{const source=p.sources.find(s=>s.id===f.source_id);const decision=f.review?.status||'pending';return `<article class="fact-card"><div class="fact-head"><span class="tag">${e(factDecision[decision])}</span><strong>${e(f.claim)}</strong></div><div class="fact-columns"><div><small>MODELİN SİTATI</small><blockquote>${e(f.quote)}</blockquote></div><div><small>MƏNBƏ KONTEKSTİ · ${e(source?.title||'Naməlum mənbə')}</small><p>${e(evidenceContext(source,f.quote))}</p>${source?.url?`<a href="${e(source.url)}" target="_blank" rel="noreferrer noopener">Orijinal səhifə ↗</a>`:''}</div></div>${f.review?.note?`<p class="review-note">Baxış qeydi: ${e(f.review.note)}</p>`:''}${p.status==='awaiting_approval'?`<div class="review-actions"><button class="button primary" data-accept-finding="${f.id}">Qəbul et</button><button class="button" data-reject-finding="${f.id}">Çıxar / qeyd yaz</button></div>`:''}</article>`;}).join('')}</section>`).join('')}<div class="info-note">Bütün canlı faktlar yoxlanmalı və hər mərhələdə ən azı bir fakt qəbul edilməlidir. Zəif mərhələ üçün Hesabatlar bölməsindən düzəliş istəyin.</div>`;
}

function usageView(){
 const p=current(); if(!p)return noProject();
 const input=p.calls.reduce((n,c)=>n+(Number(c.usage?.prompt_tokens)||0),0);
 const output=p.calls.reduce((n,c)=>n+(Number(c.usage?.completion_tokens)||0),0);
 return `${pageHeading('İCRA AUDİTİ','İcra və xərclər','Hər çağırışın vəziyyəti, token istifadəsi və hesablanan xərci.',projectPicker())}<div class="usage-summary"><article class="panel"><span>SƏRF / REZERV</span><strong>$${dollars(p.spent)}</strong><small>$${dollars(p.budget)} büdcədən</small></article><article class="panel"><span>ÇAĞIRIŞ</span><strong>${p.calls.length}</strong><small>${p.calls.filter(c=>c.status==='rate_limited').length} limit gözləməsi</small></article><article class="panel"><span>TOKEN</span><strong>${(input+output).toLocaleString('az-AZ')}</strong><small>${input} giriş · ${output} çıxış</small></article></div><section class="panel"><div class="panel-heading"><h2>Çağırış jurnalı</h2><span class="count-label">${p.calls.length} QEYD</span></div>${p.calls.length?`<div class="usage-table"><div class="usage-head"><span>VAXT / İCRAÇI</span><span>NÖV / MODEL</span><span>VƏZİYYƏT</span><span>TOKEN / XƏRC</span></div>${p.calls.slice().reverse().map(c=>`<div class="usage-row"><span><strong>${e(c.agent)}</strong><small>${date(c.time)}${c.duration_ms?` · ${c.duration_ms} ms`:''}</small></span><span>${c.purpose==='trial'?'Namizəd sınağı':'Əsas iş'}<small>${e(c.model||'Köhnə qeyd')}</small></span><span>${e(callDecision[c.status]||c.status)}${c.error?`<small>${e(c.error)}</small>`:''}</span><span>${Number(c.usage?.prompt_tokens)||0} / ${Number(c.usage?.completion_tokens)||0}<small>$${dollars(c.cost||0)}${c.estimated?' · təxmini':''}</small></span></div>`).join('')}</div>`:'<p class="empty-inline">Hələ AI çağırışı yoxdur.</p>'}</section><div class="info-note">Xərc tətbiqdəki tariflə hesablanır, provayder fakturası deyil. Cavabı bilinməyən çağırışların rezervi ehtiyat üçün saxlanılır.</div>`;
}

document.addEventListener('click',async event=>{
 const button=event.target.closest('button'); if(!button||button.disabled)return;
 const p=current(); if(!p)return;
 if(button.dataset.reviewSource){
  const source=p.sources.find(s=>s.id===button.dataset.reviewSource); if(!source)return;
  detail(source.title,`<p class="source-url">${source.url?`<a href="${e(source.url)}" target="_blank" rel="noreferrer noopener">${e(source.url)}</a>`:'Nümayiş mənbəsi'}</p><p class="form-hint">Növ: ${e(source.origin)} · Saxlanıb: ${date(source.captured_at)}</p><pre class="source-full">${e(source.body)}</pre><form id="review-source-form"><input type="hidden" name="source_id" value="${source.id}"><label>Qərar<select name="status"><option value="approved" ${source.review?.status==='approved'?'selected':''}>Təsdiqlə</option><option value="rejected" ${source.review?.status==='rejected'?'selected':''}>Uyğun deyil</option></select></label><label>Mövzuya uyğunluq (1–5)<select name="relevance">${[1,2,3,4,5].map(n=>`<option value="${n}" ${source.review?.relevance===n?'selected':''}>${n}</option>`).join('')}</select></label><label>Qeyd<textarea name="note" maxlength="1000">${e(source.review?.note||'')}</textarea></label><button class="button primary" type="submit">Qiymətləndirməni saxla</button><p class="form-error" id="review-source-error" role="alert"></p></form>`);
 }
 if(button.dataset.acceptFinding){await send('review-finding',{finding_id:button.dataset.acceptFinding,status:'accepted'});}
 if(button.dataset.rejectFinding){
  const finding=p.tasks.flatMap(t=>t.output?.findings||[]).find(f=>f.id===button.dataset.rejectFinding); if(!finding)return;
  detail('Faktı hesabatdan çıxar',`<p>${e(finding.claim)}</p><blockquote>${e(finding.quote)}</blockquote><form id="review-finding-form"><input type="hidden" name="finding_id" value="${finding.id}"><label>Səbəb və ya düzəliş qeydi<textarea name="note" maxlength="1000">${e(finding.review?.note||'')}</textarea></label><button class="button primary" type="submit">Faktı çıxar</button><p class="form-error" id="review-finding-error" role="alert"></p></form>`);
 }
});

document.addEventListener('submit',async event=>{
 if(event.target.id==='review-source-form'){
  event.preventDefault();
  if(await send('review-source',Object.fromEntries(new FormData(event.target)),'review-source-error'))document.getElementById('detail-dialog').close();
 }
 if(event.target.id==='review-finding-form'){
  event.preventDefault();
  const data=Object.fromEntries(new FormData(event.target)); data.status='rejected';
  if(await send('review-finding',data,'review-finding-error'))document.getElementById('detail-dialog').close();
 }
});
