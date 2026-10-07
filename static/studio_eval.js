'use strict';

const percentEval = value => `${Math.round((Number(value)||0)*100)}%`;

function evalView(){
 const p=current();if(!p)return noProject();
 const source=p.sources.find(s=>s.review?.status==='approved');
 const latest=p.eval_runs.at(-1);
 const taskName=id=>p.tasks.find(t=>t.id===id)?.title||'Naməlum mərhələ';
 return `${pageHeading('ÖLÇÜLƏN KEYFİYYƏT','Keyfiyyət laboratoriyası','Yoxlanmış sitat dəsti ilə saxlanmış iki namizəd profilini ölçün.',projectPicker())}
 <div class="eval-info">Bu sınaq əlavə AI çağırışı etmir. Namizədlərin əvvəlki sınaq çıxışlarını eyni mənbə və insan tərəfindən seçilmiş sitatlarla müqayisə edir. Məna doğruluğunu avtomatik təsdiqləmir.</div>
 <section class="panel module-panel"><div class="panel-heading"><h2>Golden dataset</h2><span class="count-label">v${p.eval_version} · ${p.eval_cases.length} NÜMUNƏ</span></div>
 ${source?`<p class="muted">Namizəd sınaqları ilk təsdiqlənmiş mənbədən istifadə edir: <strong>${e(source.title)}</strong>. Aşağıdakı sitat bu mənbədən sözbəsöz götürülməlidir.</p>
 <form id="eval-case-form" class="eval-form"><input name="source_id" type="hidden" value="${source.id}"><label>Mərhələ<select name="task_id">${p.tasks.map(t=>`<option value="${t.id}">${e(t.title)} · ${t.trials.length} sınaq</option>`).join('')}</select></label><label>Gözlənilən dəqiq sitat<textarea name="quote" minlength="12" maxlength="1000" required placeholder="İlk təsdiqlənmiş mənbədən 12–1000 simvolluq mətn"></textarea></label><label>İnsan qeydi<input name="note" minlength="3" maxlength="300" placeholder="Bu sitat nəyi sübut edir?" required></label><button class="button primary" type="submit">Nümunəni əlavə et</button><p id="eval-case-error" class="form-error" role="alert"></p></form>`:'<p>Başlamaq üçün sifarişdə təsdiqlənmiş mənbə lazımdır.</p>'}
 ${p.eval_cases.length?`<div class="eval-case-list">${p.eval_cases.map(c=>`<article><div><small>${e(taskName(c.task_id))}</small><blockquote>${e(c.quote)}</blockquote><p>${e(c.note)}</p></div><button class="text-button" data-eval-remove="${c.id}">Sil</button></article>`).join('')}</div>`:'<p class="muted">Hələ yoxlanmış nümunə yoxdur. Kiçik dəstdə nəticəni ehtiyatla şərh edin.</p>'}</section>
 <section class="panel module-panel"><div class="panel-heading"><h2>Eksperiment</h2><span class="count-label">${p.eval_runs.length} SAXLANMIŞ NƏTİCƏ</span></div><p>İki saxlanmış namizəd profilinin eyni mərhələlərdə tapdığı sitatları müqayisə edin. Dataset dəyişəndə yeni versiya yaranır; əvvəlki nəticə olduğu kimi qalır.</p><div class="eval-actions"><button class="button primary" data-command="eval-run" ${p.eval_cases.length?'':'disabled'}>İki profili müqayisə et</button>${p.eval_runs.length?`<a class="button" href="/api/evaluation/export?id=${encodeURIComponent(p.id)}">Nəticələri JSON endir</a>`:''}</div></section>
 ${latest?evalResult(p,latest):''}<div class="info-note">Precision: uyğun tapılan sitatlar / bütün çıxış sitatları. Recall: uyğun tapılan sitatlar / gold sitatlar. F1 onların balansıdır. Gold dəst tam deyilsə, uyğun gəlməyən sitat mütləq yanlış fakt sayılmır. Nəticə iddianın məna doğruluğu deyil.</div>`;
}

function evalResult(p,run){
 const [a,b]=run.variants;
 const rows=run.comparison.map(c=>`<tr><td>${e(c.task)}</td><td>${percentEval(c.first)}</td><td>${percentEval(c.second)}</td><td class="${c.difference<0?'eval-down':'eval-up'}">${c.difference>0?'+':''}${percentEval(c.difference)}</td></tr>`).join('');
 return `<section class="panel module-panel"><div class="panel-heading"><h2>Son müqayisə</h2><span class="count-label">DATASET v${run.dataset_version} · ${run.case_count} NÜMUNƏ</span></div><p class="muted">${date(run.time)} · Profil sırası: ${e(a.name)}, ${e(b.name)}</p><div class="eval-variants">${run.variants.map(v=>`<article><small>${e(v.name)}</small><strong>${percentEval(v.f1)} F1</strong><p>Precision ${percentEval(v.precision)} · Recall ${percentEval(v.recall)}</p><p>${v.tp}/${v.expected} gold sitat tapılıb · ${v.predicted} çıxış sitatı</p><p>Xərc ${p.mode==='live'?'$':''}${dollars(v.cost)} ${p.mode==='demo'?'kredit':''} · ${v.duration_ms} ms</p></article>`).join('')}</div><div class="module-scroll"><table><thead><tr><th>Mərhələ</th><th>${e(a.name)} F1</th><th>${e(b.name)} F1</th><th>Fərq</th></tr></thead><tbody>${rows}</tbody></table></div>${run.case_count<20?'<p class="eval-warning">Nümunə sayı 20-dən azdır. Kiçik fərqlərlə model və ya prompt qərarı verməyin.</p>':''}<details><summary>Qaçırılan sitatlar və uyğun gəlməyən çıxışlar</summary>${run.variants.map(v=>`<section><h3>${e(v.name)}</h3>${v.tasks.map(t=>`<p>${e(t.task)}: ${t.result.missed_case_ids.length} gold nümunə qaçırılıb, ${t.result.unmatched_findings.length} çıxış sitatı gold-a uyğun gəlməyib.${t.result.error?` Xəta: ${e(t.result.error)}`:''}</p>`).join('')}</section>`).join('')}</details></section>`;
}

document.addEventListener('submit',async event=>{
 if(event.target.id!=='eval-case-form')return;
 event.preventDefault();
 await send('eval-add',Object.fromEntries(new FormData(event.target)),'eval-case-error');
});
document.addEventListener('click',async event=>{
 const button=event.target.closest('button');
 if(button?.dataset.evalRemove)await send('eval-remove',{case_id:button.dataset.evalRemove});
});
