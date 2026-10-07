'use strict';
const studyKinds={interview:'Müsahibə',survey:'Sorğu',pilot:'Pilot satış'};
const studyMethods={convenience:'Əlçatan iştirakçılar',customer_list:'Müştəri siyahısı',random:'Təsadüfi seçim',other:'Digər seçim üsulu'};
const sizingFields={population:['Regionda potensial müştəri sayı','müştəri'],eligible_percent:['Hədəf seqmentin payı','% ümumi müştərilərdən'],reachable_percent:['Xidmət göstərə biləcəyiniz pay','% hədəf seqmentdən'],annual_spend:['Bir müştərinin illik xərci','seçilmiş valyuta / il'],capture_low:['Aşağı əldəetmə payı','% xidmət edilə bilən müştərilərdən'],capture_base:['Əsas əldəetmə payı','% xidmət edilə bilən müştərilərdən'],capture_high:['Yuxarı əldəetmə payı','% xidmət edilə bilən müştərilərdən']};
const validationNumber=value=>Number(value).toLocaleString('az-AZ',{maximumFractionDigits:2});
const validationEditable=p=>['draft','paused','awaiting_approval'].includes(p.status)&&!p.lease;
const validationDemo=p=>p.mode==='demo'?'<div class="demo-note">Nümayiş məlumatları — real bazar nəticəsi deyil.</div>':'';
function validationNoBrief(){return `${pageHeading('BAZAR YOXLAMASI','Bazar araşdırması sifarişi lazımdır')}<section class="panel module-panel"><p>Yeni sifarişdə “Bazar araşdırması” növünü seçin.</p><button class="button primary" data-action="new">Yeni sifariş</button></section>`;}
function customerView(){
 const p=current();if(!p)return noProject();if(!p.research_brief)return validationNoBrief();
 const editable=validationEditable(p);
 return `${pageHeading('REAL MÜŞTƏRİDƏN MƏLUMAT','Müştəri yoxlaması','Anonim müsahibələr, sorğular və pilot satış nəticələri.',projectPicker())}${validationDemo(p)}<section class="panel module-panel"><h2>Müsahibədə nə soruşmalı?</h2><ol><li>Bu problemlə sonuncu dəfə nə vaxt qarşılaşdınız?</li><li>İndi problemi necə həll edirsiniz, nə qədər vaxt və pul sərf edirsiniz?</li><li>Hazırkı həllin ən çətin tərəfi nədir?</li><li>Təklif olunan məhsul üçün ödəməyə hazır olduğunuz məbləğ nədir?</li><li>Pilotda faktiki ödəniş və istifadə oldu?</li></ol><p>Hər müsahibəni bir iştirakçı kimi yazın. Sorğu və pilot üçün eyni iştirakçıları təkrar saymadan qrup nəticəsi əlavə edin. Ad və əlaqə məlumatı əvəzinə anonim kod istifadə edin.</p><div class="info-note">Qeydlər lokal bazada saxlanır və AI provayderinə göndərilmir. Hesabat ixracına daxil edilir.</div></section><section class="panel module-panel"><h2>Nümunələr üzrə nəticələr</h2>${customerSummaryTable(p)}<p class="review-note">Faizlər yalnız bu qeydlərin iştirakçılarına aiddir. Fərqli qeydlərdə eyni şəxslər ola bilər; saylar unikal müştəri sayı deyil. Bu faizlər avtomatik olaraq bütün bazara tətbiq edilmir.</p></section>${editable?`<section class="panel module-panel"><h2>Yoxlama qeydi əlavə et</h2><form id="customer-study-form" class="validation-form"><div class="form-grid"><label>Yoxlama növü<select name="kind">${Object.entries(studyKinds).map(([key,label])=>`<option value="${key}">${label}</option>`).join('')}</select></label><label>Anonim qeyd / qrup kodu<input name="sample_code" minlength="3" maxlength="80" placeholder="INT-001 və ya SURVEY-001" required></label></div><div class="form-grid"><label>Region<input name="region" minlength="3" maxlength="300" value="${e(p.research_brief.region)}" required></label><label>Müştəri seqmenti<input name="segment" minlength="3" maxlength="300" value="${e(p.research_brief.audience)}" required></label></div><div class="form-grid"><label>Yoxlama tarixi<input name="observed_date" type="date" required></label><label>İştirakçıların seçimi<select name="method">${Object.entries(studyMethods).map(([key,label])=>`<option value="${key}">${label}</option>`).join('')}</select></label></div><label>İştirakçıları necə tapdınız?<input name="recruitment" minlength="5" maxlength="500" placeholder="Məsələn: kursun Instagram izləyicilərinə açıq sorğu" required></label><div class="validation-counts">${[['sample_size','İştirakçı sayı',1],['problem_count','Problemi bildirənlər',0],['intent_count','Alış niyyəti bildirənlər',0],['paid_count','Faktiki ödəniş edənlər',0]].map(([key,label,value])=>`<label>${label}<input name="${key}" type="number" min="${key==='sample_size'?1:0}" max="${key==='sample_size'?1:100000}" step="1" value="${value}" required></label>`).join('')}</div><label>Nəticə və müşahidə<textarea name="summary" minlength="10" maxlength="2000" placeholder="İştirakçıların bildirdiyi problemlər, mövcud həll və qiymət reaksiyası" required></textarea></label><button class="button primary" type="submit">Yoxlamanı saxla</button><p class="form-error" id="customer-study-error"></p></form></section>`:'<div class="info-note">Qeydləri dəyişmək üçün icraya fasilə verin. Təsdiqlənmiş hesabatın qeydləri dəyişdirilmir.</div>'}<section class="panel module-panel"><h2>Saxlanmış yoxlamalar</h2>${p.customer_studies.map(s=>`<article class="validation-record"><div><span class="tag">${e(studyKinds[s.kind])}</span><h3>${e(s.sample_code)}</h3><p>${e(s.region)} · ${e(s.segment)} · ${e(s.observed_date)}</p><p>${e(studyMethods[s.method])}: ${e(s.recruitment)}</p><p>${s.sample_size} iştirakçı · problem ${s.problem_count} · niyyət ${s.intent_count} · ödəniş ${s.paid_count}</p><p class="validation-notes">${e(s.summary)}</p></div>${editable?`<button class="text-button" data-study-remove="${s.id}">Qeydi çıxar</button>`:''}</article>`).join('')||'<p>Hələ müştəri yoxlaması əlavə edilməyib.</p>'}</section>`;
}
function customerSummaryTable(p){
 if(!p.customer_summary?.length)return '<p>Hələ nəticə yoxdur.</p>';
 return `<div class="module-scroll"><table><thead><tr><th>Nümunə</th><th>İştirakçı</th><th>Problem</th><th>Alış niyyəti</th><th>Ödəniş</th></tr></thead><tbody>${p.customer_summary.map(s=>`<tr><td>${e(studyKinds[s.kind])}<br>${e(s.region)} · ${e(s.segment)}<br><small>${e(studyMethods[s.method])} · ${s.records} qeyd</small></td><td>${s.sample_size}</td><td>${s.problem_count} / ${validationNumber(s.problem_percent)}%</td><td>${s.intent_count} / ${validationNumber(s.intent_percent)}%</td><td>${s.paid_count} / ${validationNumber(s.paid_percent)}%</td></tr>`).join('')}</tbody></table></div>`;
}
function sizingResults(p){
 const r=p.market_size_result;if(!r)return '<p>Hesablama hələ saxlanmayıb. Aşağıdakı girişləri əsaslandırıb doldurun.</p>';
 return `<div class="module-stats"><article class="panel"><span>TAM — ümumi potensial</span><strong>${validationNumber(r.tam_customers)} müştəri</strong><span>${validationNumber(r.tam_annual)} ${e(r.currency)} / il</span></article><article class="panel"><span>SAM — xidmət edilə bilən hissə</span><strong>${validationNumber(r.sam_customers)} müştəri</strong><span>${validationNumber(r.sam_annual)} ${e(r.currency)} / il</span></article></div><h3>SOM — ${r.horizon_months} ayda əldəetmə ssenariləri</h3><div class="module-scroll"><table><thead><tr><th>Ssenari</th><th>Əldəetmə payı</th><th>Müştəri</th><th>İllik potensial</th></tr></thead><tbody>${r.scenarios.map(s=>`<tr><td>${{low:'Aşağı',base:'Əsas',high:'Yuxarı'}[s.name]}</td><td>${validationNumber(s.capture_percent)}%</td><td>${validationNumber(s.customers)}</td><td>${validationNumber(s.annual_potential)} ${e(r.currency)}</td></tr>`).join('')}</tbody></table></div><p class="review-note">${r.assumption_count} fərziyyə · ${r.unverified_count} etibarsız istinad. Məbləğ əldəetmə müddətinin sonunda bu miqyasa çatanda illik potensialdır; həmin aylarda yığılmış gəlir deyil. Ssenarilər statistik etibar intervalı deyil.</p>${r.warnings.length?`<div class="info-note"><ul>${r.warnings.map(w=>`<li>${e(w)}</li>`).join('')}</ul></div>`:''}<div class="module-scroll"><table><thead><tr><th>Giriş</th><th>Rəqəm</th><th>Əsas</th><th>Qeyd</th></tr></thead><tbody>${r.provenance.map(x=>`<tr><td>${e(x.label)}</td><td>${validationNumber(x.value)}</td><td>${{assumption:'Fərziyyə',evidence:'Sübut istinadı',unverified:'İstinad etibarsızdır'}[x.status]}</td><td class="validation-wrap">${e(x.note)}</td></tr>`).join('')}</tbody></table></div>`;
}
function sizingView(){
 const p=current();if(!p)return noProject();if(!p.research_brief)return validationNoBrief();
 const model=p.market_sizing,editable=validationEditable(p);
 const evidence=p.market_evidence.filter(x=>p.sources.some(s=>s.id===x.source_id&&s.review?.status==='approved'));
 return `${pageHeading('AÇIQ DÜSTURLAR','Bazar həcmi hesablaması','Hər rəqəmin əsasını göstərən TAM, SAM və SOM modeli.',projectPicker())}${validationDemo(p)}<section class="panel module-panel"><h2>Hesablamanın mənası</h2><p><b>TAM</b> = regionda potensial müştəri sayı × bir müştərinin illik xərci.</p><p><b>SAM</b> = TAM × hədəf seqmentin payı × həmin seqmentdə xidmət göstərə biləcəyiniz pay.</p><p><b>SOM</b> = SAM × əldəetmə payı.</p><p>Məsələn, aylıq 50 AZN xərc ildə 600 AZN-dir. Eyni valyutanı və illik dövrü istifadə edin. Sorğuda alış niyyəti avtomatik satış və ya bazar payı sayılmır.</p></section><section class="panel module-panel"><h2>Saxlanmış nəticə</h2>${sizingResults(p)}</section>${editable?`<section class="panel module-panel"><h2>Rəqəmləri və əsaslandırmanı daxil et</h2><form id="market-sizing-form" class="validation-form"><div class="form-grid"><label>Valyuta<select name="currency">${['AZN','USD','EUR'].map(c=>`<option value="${c}" ${model?.currency===c?'selected':''}>${c}</option>`).join('')}</select></label><label>Əldəetmə müddəti (ay)<input name="horizon_months" type="number" min="1" max="60" step="1" value="${model?.horizon_months||12}" required></label></div>${Object.entries(sizingFields).map(([key,[label,unit]])=>{const x=model?.inputs[key];return `<fieldset class="validation-input"><legend>${label}</legend><div class="form-grid"><label>Rəqəm — ${unit}<input name="${key}_value" type="number" min="0" max="${key.includes('percent')||key.startsWith('capture_')?100:1000000000}" step="any" value="${x?.value??''}" required></label><label>Rəqəmin əsası<select name="${key}_basis" data-sizing-basis="${key}"><option value="assumption" ${x?.basis!=='evidence'?'selected':''}>Fərziyyə</option><option value="evidence" ${x?.basis==='evidence'?'selected':''}>Sübut istinadı</option></select></label></div><label>Sübut seçimi<select name="${key}_evidence_id" ${x?.basis==='evidence'?'required':'disabled'}><option value="">Sübut seçin</option>${evidence.map(item=>`<option value="${item.id}" ${x?.evidence_id===item.id?'selected':''}>${e(item.entity||'Bazar məlumatı')}: ${e(item.claim.slice(0,120))}</option>`).join('')}</select></label><label>Bu rəqəmi necə müəyyən etdiniz?<input name="${key}_note" minlength="5" maxlength="500" value="${e(x?.note||'')}" placeholder="Mənbədəki rəqəm, region, dövr və ya fərziyyənin səbəbi" required></label></fieldset>`;}).join('')}<div class="info-note">Sübut istinadı rəqəmin avtomatik doğrulanması deyil. Sitatdakı rəqəmin, regionun, dövrün və vahidin bu girişə uyğunluğunu siz yoxlayırsınız. Valyuta çevrilməsi avtomatik aparılmır.</div><button class="button primary" type="submit">Hesabla və saxla</button><p class="form-error" id="market-sizing-error"></p></form></section>`:'<div class="info-note">Modeli dəyişmək üçün icraya fasilə verin. Təsdiqlənmiş hesabatın hesablaması dəyişdirilmir.</div>'}`;
}
function validationReportBlock(p){
 if(!p.research_brief||!p.report)return '';
 return `<section class="panel module-panel"><h2>Müştəri yoxlamalarının nəticələri</h2>${customerSummaryTable(p)}<p>Nəticələr qeydə alınmış nümunələrə aiddir; bazara ümumiləşdirilmir.</p><h2>Bazar həcmi modeli</h2>${sizingResults(p)}</section>`;
}
document.addEventListener('change',event=>{
 const el=event.target;
 if(el.matches('#customer-study-form [name="kind"]')){
  const input=document.querySelector('#customer-study-form [name="sample_size"]');
  input.max=el.value==='interview'?'1':'100000';if(el.value==='interview')input.value='1';
 }
 if(el.dataset.sizingBasis){
  const select=document.querySelector(`#market-sizing-form [name="${el.dataset.sizingBasis}_evidence_id"]`);
  select.disabled=el.value!=='evidence';select.required=!select.disabled;
 }
});
document.addEventListener('submit',async event=>{
 if(event.target.id==='customer-study-form'){
  event.preventDefault();await send('customer-study-add',Object.fromEntries(new FormData(event.target)),'customer-study-error');
 }else if(event.target.id==='market-sizing-form'){
  event.preventDefault();const data=Object.fromEntries(new FormData(event.target));
  const inputs=Object.fromEntries(Object.keys(sizingFields).map(key=>[key,{value:data[key+'_value'],basis:data[key+'_basis'],evidence_id:data[key+'_evidence_id']||'',note:data[key+'_note']}])) ;
  await send('market-sizing-save',{currency:data.currency,horizon_months:data.horizon_months,inputs},'market-sizing-error');
 }
});
document.addEventListener('click',async event=>{
 const button=event.target.closest('[data-study-remove]');
 if(button)await send('customer-study-remove',{study_id:button.dataset.studyRemove});
});

// Source discovery updates the page while forms are being edited. Keep local drafts.
const validationDrafts=new Map();
let validationFocus=null;
function captureValidationDrafts(){
 const active=document.activeElement,activeForm=active?.closest('#customer-study-form,#market-sizing-form,#market-evidence-form,[data-market-conflict]');
 validationFocus=activeForm?{project:activeForm.dataset.draftProject||selectedId,form:activeForm.id||activeForm.dataset.marketConflict,name:active.name}:null;
 document.querySelectorAll('#customer-study-form,#market-sizing-form,#market-evidence-form,[data-market-conflict]').forEach(form=>{
  const key=(form.dataset.draftProject||selectedId)+':'+(form.id||form.dataset.marketConflict);
  if(form.dataset.dirty==='true'){
   const fields=Object.fromEntries(Array.from(form.querySelectorAll('[name]')).map(el=>[el.name,el.value]));
   validationDrafts.set(key,fields);
  }
 });
}
function restoreValidationDrafts(){
 document.querySelectorAll('#customer-study-form,#market-sizing-form,#market-evidence-form,[data-market-conflict]').forEach(form=>{
  form.dataset.draftProject=selectedId;
  const key=selectedId+':'+(form.id||form.dataset.marketConflict),fields=validationDrafts.get(key);if(!fields)return;
  for(const el of form.querySelectorAll('[name]'))if(el.name in fields)el.value=fields[el.name];
  form.dataset.dirty='true';
  if(form.id==='customer-study-form')form.elements.sample_size.max=form.elements.kind.value==='interview'?'1':'100000';
  if(form.id==='market-sizing-form')for(const key of Object.keys(sizingFields)){
   const select=form.elements[key+'_evidence_id'];select.disabled=form.elements[key+'_basis'].value!=='evidence';select.required=!select.disabled;
  }
 });
 if(validationFocus?.project===selectedId){
  const form=Array.from(document.querySelectorAll('form')).find(f=>(f.id||f.dataset.marketConflict)===validationFocus.form);
  form?.elements[validationFocus.name]?.focus();
 }
}
function clearValidationDraft(action){
 const id={'customer-study-add':'customer-study-form','market-sizing-save':'market-sizing-form','market-evidence-add':'market-evidence-form'}[action];
 if(!id)return;
 validationDrafts.delete(selectedId+':'+id);const form=document.getElementById(id);if(form)form.dataset.dirty='false';
 validationFocus=null;
}
document.addEventListener('input',event=>{const form=event.target.closest('#customer-study-form,#market-sizing-form,#market-evidence-form,[data-market-conflict]');if(form)form.dataset.dirty='true';});
document.addEventListener('change',event=>{const form=event.target.closest('#customer-study-form,#market-sizing-form,#market-evidence-form,[data-market-conflict]');if(form)form.dataset.dirty='true';});
