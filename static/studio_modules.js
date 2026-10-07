'use strict';
const usd = n => Number(n||0).toLocaleString('az-AZ',{minimumFractionDigits:2,maximumFractionDigits:2});
const workStatus = {todo:'Gözləyir',doing:'İcradadır',done:'Bitib'};
const field = (name,label,value,type='number',step='0.01') => `<label>${label}<input name="${name}" type="${type}" step="${step}" value="${e(value)}" required></label>`;

function workView(){
 const p=current(); if(!p)return noProject();
 const today=new Date().toISOString().slice(0,10);
 const items=p.work_items.slice().sort((a,b)=>a.due.localeCompare(b.due));
 return `${pageHeading('İCRA PLANI','Tapşırıq və təqvim','Məsul şəxs, son tarix və vəziyyəti sifarişlə birlikdə saxlayın.',projectPicker())}
 <section class="panel module-panel"><h2>Yeni tapşırıq</h2><form id="work-form" class="module-form">
 <label>Tapşırıq<input name="title" minlength="3" maxlength="180" required></label>
 <label>Məsul şəxs<input name="owner" minlength="2" maxlength="100" required></label>
 <label>Son tarix<input name="due" type="date" value="${today}" required></label>
 <button class="button primary" type="submit">Əlavə et</button><p class="form-error" id="work-error" role="alert"></p></form></section>
 <section class="panel module-panel"><div class="panel-heading"><h2>Tarixə görə işlər</h2><span class="count-label">${items.length} TAPŞIRIQ</span></div><p><a class="button" href="/api/calendar?id=${encodeURIComponent(p.id)}">Təqvim faylını endir (.ics)</a></p>
 ${items.length?items.map(i=>`<article class="work-row"><div><strong>${e(i.title)}</strong><small>${e(i.owner)} · ${e(i.due)}${i.status!=='done'&&i.due<today?' · Gecikib':''}</small></div><select aria-label="${e(i.title)} vəziyyəti" data-work-status="${i.id}">${Object.entries(workStatus).map(([key,label])=>`<option value="${key}" ${key===i.status?'selected':''}>${label}</option>`).join('')}</select><button class="text-button" data-work-remove="${i.id}">Sil</button></article>`).join(''):'<p>Hələ tapşırıq yoxdur.</p>'}
 </section>`;
}

function financeView(){
 const p=current();if(!p)return noProject();const f=p.finance_plan||{};const summary=p.finance_projection;
 return `${pageHeading('PUL AXINI','Maliyyə planı','Rəqəmləri siz daxil edirsiniz; hesablamalar lokal aparılır.',projectPicker())}
 <section class="panel module-panel"><h2>Fərziyyələr</h2><form id="finance-form" class="finance-form">
 ${field('starting_cash','İlkin vəsait (USD)',f.starting_cash??10000)}
 ${field('monthly_customers','Aylıq yeni müştəri',f.monthly_customers??25)}
 ${field('price','Müştəri üzrə aylıq gəlir (USD)',f.price??30)}
 ${field('variable_cost','Müştəri üzrə aylıq xərc (USD)',f.variable_cost??8)}
 ${field('fixed_cost','Sabit aylıq xərc (USD)',f.fixed_cost??1500)}
 ${field('churn','Aylıq müştəri itkisi (%)',f.churn??3)}
 ${field('growth','Yeni müştəri artımı (%)',f.growth??0)}
 ${field('months','Müddət (ay)',f.months??12,'number','1')}
 <button class="button primary" type="submit">Planı hesabla və saxla</button><p class="form-error" id="finance-error" role="alert"></p></form></section>
 ${summary?`<div class="module-stats"><article class="panel"><span>SON VƏSAİT</span><strong>$${usd(summary.ending_cash)}</strong></article><article class="panel"><span>CƏMİ GƏLİR</span><strong>$${usd(summary.total_revenue)}</strong></article><article class="panel"><span>CƏMİ XƏRC</span><strong>$${usd(summary.total_costs)}</strong></article><article class="panel"><span>MƏNFİ VƏSAİT</span><strong>${summary.first_negative_month?summary.first_negative_month+'-ci ay':'Yoxdur'}</strong></article></div>${financeTable(summary.rows)}`:''}
 <div class="info-note">Bu sadə fərziyyə modelidir, bazar proqnozu və ya mühasibat hesabatı deyil. Gəlir aktiv müştərilərin aylıq ödənişi kimi, itki isə əvvəlki müştərilərə tətbiq edilir. Vergi, borc və birdəfəlik xərclər daxil deyil. AI istifadə xərci bu plandan ayrıdır.</div>`;
}

function financeTable(rows){return `<section class="panel module-panel"><h2>Aylıq pul axını</h2><div class="module-scroll"><table><thead><tr><th>Ay</th><th>Aktiv müştəri</th><th>Gəlir</th><th>Xərc</th><th>Xalis</th><th>Vəsait</th></tr></thead><tbody>${rows.map(r=>`<tr><td>${r.month}</td><td>${usd(r.customers)}</td><td>$${usd(r.revenue)}</td><td>$${usd(r.costs)}</td><td>$${usd(r.net)}</td><td>$${usd(r.cash)}</td></tr>`).join('')}</tbody></table></div></section>`;}

function scenariosView(){
 const p=current();if(!p)return noProject();if(!p.finance_plan)return `${pageHeading('NƏ OLARSA?','Ssenarilər','Əvvəl maliyyə planını qurun.',projectPicker())}<section class="panel module-panel"><p>Ssenarini hesablamaq üçün əsas plan lazımdır.</p><button class="button primary" data-view="finance">Maliyyə planını aç</button></section>`;
 const base=p.finance_projection;
 return `${pageHeading('NƏ OLARSA?','Ssenarilər','Satış, xərc və gecikmə dəyişəndə pul axınının necə dəyişdiyini görün.',projectPicker())}
 <section class="panel module-panel"><h2>Yeni ssenari</h2><form id="scenario-form" class="finance-form">
 <label>Ad<input name="name" minlength="3" maxlength="100" placeholder="Rəqib qiyməti endirdi" required></label>
 ${field('sales_multiplier','Satış əmsalı (1 = dəyişmir)',1)}
 ${field('cost_multiplier','Xərc əmsalı (1 = dəyişmir)',1)}
 ${field('delay_months','Satış gecikməsi (ay)',0,'number','1')}
 <button class="button primary" type="submit">Ssenarini saxla</button><p class="form-error" id="scenario-error" role="alert"></p></form></section>
 <section class="panel module-panel"><h2>Müqayisə</h2><div class="module-scroll"><table><thead><tr><th>Ssenari</th><th>Satış / xərc / gecikmə</th><th>Son vəsait</th><th>Əsas plandan fərq</th><th>Mənfi vəsait</th><th></th></tr></thead><tbody><tr><td>Əsas plan</td><td>1× / 1× / 0 ay</td><td>$${usd(base.ending_cash)}</td><td>—</td><td>${base.first_negative_month||'Yoxdur'}</td><td></td></tr>${p.scenarios.map(s=>`<tr><td>${e(s.name)}</td><td>${s.sales_multiplier}× / ${s.cost_multiplier}× / ${s.delay_months} ay</td><td>$${usd(s.projection.ending_cash)}</td><td>$${usd(s.projection.ending_cash-base.ending_cash)}</td><td>${s.projection.first_negative_month||'Yoxdur'}</td><td><button class="text-button" data-scenario-remove="${s.id}">Sil</button></td></tr>`).join('')}</tbody></table></div></section>
 <div class="info-note">Ssenarilər yalnız saxlanmış plana tətbiq edilir və real sifariş büdcəsini dəyişmir. Nəticələr daxil etdiyiniz fərziyyələrə əsaslanan hesablamadır.</div>`;
}

function portalView(){
 const p=current();if(!p)return noProject();
 const link=p.portal_token?`${location.origin}/portal?id=${encodeURIComponent(p.id)}&token=${encodeURIComponent(p.portal_token)}`:'';
 return `${pageHeading('MÜŞTƏRİ BAXIŞI','Müştəri portalı','Müştəri işin gedişini görür və rəy yaza bilir.',projectPicker())}
 <section class="panel module-panel"><h2>Lokal giriş keçidi</h2><p>Keçidi yaratdıqdan sonra bu kompüterdə ayrıca pəncərədə açıb yoxlaya bilərsiniz. Bu pilot internetdən giriş təmin etmir.</p>
 ${link?`<p class="portal-link"><a href="${e(link)}" target="_blank" rel="noreferrer noopener">Müştəri baxışını aç ↗</a></p><button class="button" data-portal-create="1">Keçidi yenilə</button> <button class="button" data-portal-revoke="1">Girişi bağla</button>`:'<button class="button primary" data-portal-create="1">Keçid yarat</button>'}</section>
 <section class="panel module-panel"><div class="panel-heading"><h2>Müştəri rəyləri</h2><span class="count-label">${p.client_feedback.length} RƏY</span></div>${p.client_feedback.length?p.client_feedback.slice().reverse().map(f=>`<article class="feedback-row"><small>${date(f.time)}</small><p>${e(f.message)}</p></article>`).join(''):'<p>Hələ rəy yoxdur.</p>'}</section>`;
}

document.addEventListener('submit',async event=>{
 const id=event.target.id;
 const actions={'work-form':['work-add','work-error'],'finance-form':['finance-plan','finance-error'],'scenario-form':['scenario-add','scenario-error']};
 if(!actions[id])return;event.preventDefault();
 const [action,error]=actions[id];await send(action,Object.fromEntries(new FormData(event.target)),error);
});
document.addEventListener('change',async event=>{
 if(event.target.dataset.workStatus)await send('work-status',{item_id:event.target.dataset.workStatus,status:event.target.value});
});
document.addEventListener('click',async event=>{
 const b=event.target.closest('button');if(!b)return;
 if(b.dataset.workRemove)await send('work-remove',{item_id:b.dataset.workRemove});
 if(b.dataset.scenarioRemove)await send('scenario-remove',{scenario_id:b.dataset.scenarioRemove});
 if(b.dataset.portalCreate)await send('portal-create');
 if(b.dataset.portalRevoke)await send('portal-revoke');
});
