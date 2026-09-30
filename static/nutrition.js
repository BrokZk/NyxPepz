/* Private meal diary. Nutritional snapshots and all saved calculations belong to the server. */
(()=>{
 const root=document.getElementById('nutrition');if(!root)return;
 const get=id=>document.getElementById(id),esc=escapeHTML;
 async function api(url,options={}){const response=await fetch(url,{...options,headers:{'Content-Type':'application/json',...(options.headers||{})}});const data=await response.json().catch(()=>({}));if(!response.ok){const error=new Error(data.error||'Service temporairement indisponible. Réessayez.');error.status=response.status;throw error;}return data;}
 const localDay=d=>[d.getFullYear(),String(d.getMonth()+1).padStart(2,'0'),String(d.getDate()).padStart(2,'0')].join('-');
 const today=()=>localDay(new Date()),dateObject=s=>new Date(s+'T12:00:00');
 const niceDate=s=>new Intl.DateTimeFormat('fr-FR',{day:'numeric',month:'long',year:'numeric'}).format(dateObject(s));
 const number=n=>new Intl.NumberFormat('fr-FR',{maximumFractionDigits:1}).format(n||0),decimal=value=>{const s=String(value).trim();return /^\d+(?:[.,]\d{1,3})?$/.test(s)?Number(s.replace(',','.')):NaN;};
 const norm=s=>String(s||'').normalize('NFD').replace(/[\u0300-\u036f]/g,'').replace(/œ/g,'oe').replace(/æ/g,'ae').toLowerCase().replace(/[^a-z0-9]+/g,' ').trim();
 const mealNames={breakfast:'Petit-déjeuner',lunch:'Déjeuner',dinner:'Dîner',snack:'Collation'};
 let selected=today(),tab='day',day=null,profile=null,profileResult=null,foods=null,foodLoad=null,foodChoice=null,editing=null,source='search',pending=null,saving=false,ready=false,loadNumber=0,resultNumber=0,searchLimit=12;
 const applyTargets=document.createElement('button');applyTargets.id='nutApplyTargets';applyTargets.type='button';applyTargets.className='nut-secondary';applyTargets.textContent='Appliquer mes repères à cette journée';applyTargets.hidden=true;get('nutBalance').after(applyTargets);
 function notice(id,text){const node=get(id);node.textContent=text||'';if(id==='nutNotice')node.hidden=!text;}
 function setBusy(value){saving=value;root.querySelectorAll('button').forEach(b=>{if(value){b.dataset.nutPreviouslyDisabled=b.disabled?'1':'0';b.disabled=true;}else if('nutPreviouslyDisabled' in b.dataset){b.disabled=b.dataset.nutPreviouslyDisabled==='1';delete b.dataset.nutPreviouslyDisabled;}});get('nutEntryForm').querySelectorAll('input,select').forEach(e=>e.disabled=value||Boolean(pending));}
 function applyDate(){get('nutDate').value=selected;get('nutDate').max=today();get('nutDateLabel').textContent=selected===today()?'Aujourd’hui':niceDate(selected);get('nutNextDay').disabled=selected>=today();}
 async function loadDay(){const seq=++loadNumber;const result=await api('/api/nutrition/day?date='+selected);if(seq!==loadNumber)return;day=result;ready=true;renderDay();}
 async function loadProfile(){profileResult=await api('/api/nutrition/profile');profile=profileResult.profile;fillProfile();renderEstimate();}
 async function load(){notice('nutNotice','');get('nutAdd').disabled=true;try{await Promise.all([loadDay(),loadProfile()]);renderDay();if(tab==='history')await loadHistory();}catch(e){notice('nutNotice',e.message);}finally{get('nutAdd').disabled=!ready||saving;}}
 function displayProgress(id,value,target){get(id).hidden=!target;get(id).max=target||1;get(id).value=Math.min(value||0,target||1);}
 function renderDay(){
  if(!day)return;applyDate();const totals=day.totals||{},targets=day.targets||{};
  get('nutKcal').textContent=number(Math.round(totals.kcal||0));get('nutProtein').textContent=number(totals.protein_g);
  get('nutKcalGoal').textContent=targets.kcal_target?'Objectif : '+number(targets.kcal_target)+' kcal':'Objectif à définir';
  get('nutProteinGoal').textContent=targets.protein_target_g?'Repère : '+number(targets.protein_target_g)+' g':'Repère à définir';
  const delta=(targets.kcal_target||0)-(totals.kcal||0);
  get('nutKcalRemaining').textContent=targets.kcal_target?(delta>=0?number(Math.round(delta))+' kcal jusqu’à l’objectif':number(Math.round(-delta))+' kcal au-dessus de l’objectif'):'';
  get('nutProteinRemaining').textContent=totals.protein_incomplete?'Total partiel : valeur manquante':targets.protein_target_g?(totals.protein_g>=targets.protein_target_g?'Repère atteint':number(Math.max(0,targets.protein_target_g-totals.protein_g))+' g jusqu’au repère'):'';
  displayProgress('nutKcalProgress',totals.kcal,targets.kcal_target);displayProgress('nutProteinProgress',totals.protein_g,targets.protein_target_g);
  get('nutDayStatus').textContent=day.complete?'Saisie terminée':'Journée en cours';
  let balance=targets.maintenance_kcal?'Maintien estimé : '+number(targets.maintenance_kcal)+' kcal / jour. ':'';
  if(day.complete&&day.estimated_deficit_kcal!=null){const gap=day.estimated_deficit_kcal;balance+=gap>=0?'Déficit estimé sur les repas saisis : '+number(gap)+' kcal.':'Apport estimé au-dessus du maintien : '+number(-gap)+' kcal.';balance+=' Les quantités et les besoins restent des estimations.';}
  else balance+='Le bilan calorique sera affiché une fois la saisie du jour terminée.';
  if(day.complete&&targets.kcal_target&&totals.kcal<targets.kcal_target*.75)balance+=' Apport saisi nettement inférieur au repère : vérifiez que la journée est complète. Un déficit plus grand n’est pas un objectif à rechercher.';
  get('nutBalance').textContent=balance;
  get('nutSetupTitle').textContent=profile?'Mon profil nutrition':'Calculer mes besoins';
  get('nutSetupHint').textContent=profile?number(profile.age)+' ans · '+number(profile.height_cm)+' cm · '+number(profile.weight_kg)+' kg. Vos objectifs tiennent aussi compte de votre activité.':'Âge, taille, poids et activité : définissez vos objectifs de calories et de protéines.';
  get('nutSetupAction').innerHTML=(profile?'Modifier mon profil':'Renseigner mon profil')+' <span aria-hidden="true">›</span>';
  const latest=profileResult?.estimate;applyTargets.hidden=day.complete||!latest||!day.entries.length||['kcal_target','protein_target_g','maintenance_kcal'].every(key=>latest[key]===targets[key]);
  get('nutComplete').textContent=day.complete?'Reprendre la saisie du jour':'J’ai terminé ma saisie du jour';get('nutComplete').disabled=!day.entries.length||saving;
  const host=get('nutMeals');host.replaceChildren();
  Object.entries(mealNames).forEach(([key,label])=>{
   const entries=day.entries.filter(e=>e.meal===key),kcal=entries.reduce((n,e)=>n+e.kcal,0),protein=entries.reduce((n,e)=>n+(e.protein_g||0),0),partial=entries.some(e=>e.protein_g==null);
   const section=document.createElement('section');section.className='nut-meal';section.dataset.meal=key;
   section.innerHTML=`<header class="nut-meal-head"><div><h3>${label}</h3><small>${entries.length?number(Math.round(kcal))+' kcal · '+number(protein)+' g de protéines'+(partial?' (partiel)':''):'Aucun aliment enregistré'}</small></div><button type="button" aria-label="Ajouter au ${label.toLowerCase()}">＋</button></header>`;
   section.querySelector('button').onclick=()=>openEditor(key);
   if(!entries.length){const p=document.createElement('p');p.className='nut-empty';p.textContent='Ajoutez un aliment ou retrouvez vos favoris.';section.append(p);}
   entries.forEach(entry=>{
    const item=document.createElement('article');item.className='nut-entry';item.dataset.entry=entry.id;
    item.innerHTML=`<strong>${esc(entry.name)}</strong><small>${number(entry.grams)} g · ${number(Math.round(entry.kcal))} kcal · ${entry.protein_g==null?'Protéines non renseignées':number(entry.protein_g)+' g de protéines'}</small><div class="nut-entry-actions"><button type="button" data-action="edit">Modifier</button><button type="button" data-action="favorite">☆ Favori</button><button type="button" data-action="delete">Supprimer</button></div>`;
    item.querySelector('[data-action=edit]').onclick=()=>openEditor(entry.meal,entry);
    item.querySelector('[data-action=favorite]').onclick=()=>mutate(async()=>{await api('/api/nutrition/favorites',{method:'POST',body:JSON.stringify({entry_id:entry.id})});toast('Aliment ajouté aux favoris');});
    item.querySelector('[data-action=delete]').onclick=()=>removeEntry(entry);section.append(item);
   });host.append(section);
  });
 }
 async function mutate(action){if(saving||pending)return;notice('nutNotice','');setBusy(true);try{await action();}catch(e){notice('nutNotice',e.message);}finally{setBusy(false);if(day)renderDay();}}
 async function removeEntry(entry){if(!confirm('Supprimer « '+entry.name+' » de cette journée ?'))return;await mutate(async()=>{await api('/api/nutrition/entries/'+entry.id,{method:'DELETE',body:JSON.stringify({version:entry.version})});await loadDay();});}
 function setTab(next){if(saving||pending)return;const changed=tab!==next;closeEditor();tab=next;root.querySelectorAll('[data-nut-tab]').forEach(b=>b.setAttribute('aria-selected',String(b.dataset.nutTab===tab)));['day','history','profile'].forEach(t=>get({day:'nutDayPanel',history:'nutHistoryPanel',profile:'nutProfilePanel'}[t]).hidden=t!==tab);notice('nutNotice','');if(changed){root.querySelector('.nut-tabs').scrollIntoView({block:'start',behavior:'instant'});if(tab==='profile')get('nutProfilePanel').focus({preventScroll:true});}if(tab==='history')loadHistory().catch(e=>notice('nutNotice',e.message));}
 async function catalog(){if(foods)return foods;if(!foodLoad)foodLoad=fetch('/static/nutrition-foods.json?v=2025.1').then(r=>{if(!r.ok)throw Error('La base alimentaire est indisponible. Vous pouvez utiliser « Étiquette ».');return r.json();}).then(data=>{if(!Array.isArray(data))throw Error('Base alimentaire indisponible.');foods=data.map(f=>({...f,search:norm(f.name)}));return foods;}).catch(e=>{foodLoad=null;throw e;});return foodLoad;}
 function showResults(items,kind,total){
  const host=get('nutFoodResults');host.replaceChildren();
  if(!items.length){host.innerHTML='<p class="nut-food-empty">'+(kind==='search'?'Aucun résultat. Précisez le nom ou utilisez les valeurs de l’étiquette.':kind==='favorite'?'Ajoutez vos aliments habituels aux favoris depuis un repas enregistré.':'Vos derniers aliments apparaîtront ici après leur enregistrement.')+'</p>';return;}
  items.forEach(food=>{
   const line=document.createElement('div'),pick=document.createElement('button');pick.type='button';pick.className='nut-food';
   const known=food.kcal_per_100g!=null;
   pick.innerHTML=`<strong>${esc(food.name)}</strong><small>${known?number(food.kcal_per_100g)+' kcal':'Énergie non renseignée'} · ${food.protein_per_100g==null?'Protéines non renseignées':number(food.protein_per_100g)+' g prot.'} / 100 g${kind==='search'?'':' · Portion précédente : '+number(food.grams||100)+' g'}</small>`;
   pick.disabled=!known;pick.onclick=()=>selectFood(kind==='search'?food:{...food,id:food.food_id},food.grams||100);line.append(pick);
   if(kind==='favorite'){const remove=document.createElement('button');remove.className='nut-refresh';remove.type='button';remove.textContent='Retirer des favoris';remove.onclick=()=>mutate(async()=>{await api('/api/nutrition/favorites/'+food.id,{method:'DELETE'});await chooseSource('favorite');});line.append(remove);}host.append(line);
  });
  if(total>items.length){const more=document.createElement('button');more.className='nut-secondary';more.type='button';more.textContent='Voir plus de résultats ('+total+')';more.onclick=()=>{searchLimit+=12;searchFoods();};host.append(more);}
 }
 async function searchFoods(){const seq=++resultNumber,q=norm(get('nutSearch').value);if(q.length<2){get('nutFoodResults').innerHTML='<p class="nut-food-empty">Tapez au moins deux lettres. Les valeurs de la base sont des moyennes pour 100 g.</p>';return;}
  get('nutFoodResults').textContent='Recherche…';try{const list=await catalog();if(seq!==resultNumber||source!=='search')return;const tokens=q.split(' '),matches=list.filter(f=>tokens.every(t=>f.search.includes(t)));matches.sort((a,b)=>Number(b.search.startsWith(q))-Number(a.search.startsWith(q)));showResults(matches.slice(0,searchLimit),'search',matches.length);}catch(e){if(seq===resultNumber)get('nutFoodResults').textContent=e.message;}}
 async function chooseSource(next){if(pending)return;source=next;resultNumber++;get('nutEntryForm').hidden=true;foodChoice=null;root.querySelectorAll('[data-nut-source]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.nutSource===source)));get('nutSearchArea').hidden=source!=='search';get('nutFoodResults').replaceChildren();
  if(source==='manual'){get('nutEntryForm').reset();get('nutMeal').value=openMeal;get('nutGrams').value='100';get('nutManualFields').hidden=false;get('nutSelected').hidden=true;get('nutEntryForm').hidden=false;get('nutPreview').textContent='';get('nutManualName').focus();return;}
  if(source==='search'){searchLimit=12;get('nutSearch').value='';searchFoods();return;}
  const seq=resultNumber;get('nutFoodResults').textContent='Chargement…';try{const result=await api('/api/nutrition/'+(source==='recent'?'recent':'favorites'));if(seq===resultNumber)showResults(result.foods||[],source,0);}catch(e){if(seq===resultNumber)get('nutFoodResults').textContent=e.message;}
 }
 let openMeal='lunch';
 function openEditor(meal,entry=null){if(!ready||saving||pending)return;openMeal=meal||'lunch';editing=entry;get('nutEntryEditor').hidden=false;get('nutSources').hidden=Boolean(entry);get('nutEntryTitle').textContent=entry?'Modifier la portion':'Ajouter un aliment';notice('nutEntryError','');get('nutEntryForm').querySelectorAll('input,select').forEach(e=>e.disabled=false);get('nutSaveEntry').textContent='Enregistrer';
  if(entry)selectFood({...entry,id:entry.food_id},entry.grams);else chooseSource('search');
  get('nutEntryEditor').scrollIntoView({block:'start',behavior:'smooth'});
 }
 function selectFood(food,grams){foodChoice=food;get('nutEntryForm').hidden=false;get('nutManualFields').hidden=true;get('nutSelected').hidden=false;get('nutSelected').innerHTML='<b>'+esc(food.name)+'</b><small>'+esc(food.source||'ANSES-Ciqual 2025')+' · Valeurs pour 100 g</small>';get('nutGrams').value=String(grams).replace('.',',');get('nutMeal').value=openMeal;notice('nutEntryError','');preview();}
 function closeEditor(){if(saving||pending)return false;get('nutEntryEditor').hidden=true;editing=null;foodChoice=null;resultNumber++;return true;}
 function entryData(){const grams=decimal(get('nutGrams').value);if(!Number.isFinite(grams)||grams<.1||grams>3000)throw Error('Indiquez une quantité entre 0,1 et 3 000 g.');const base={date:selected,meal:get('nutMeal').value,grams};
  if(editing)return {version:editing.version,grams,meal:base.meal};
  if(foodChoice?.id)return {...base,food_id:foodChoice.id};
  const name=foodChoice?.name||get('nutManualName').value.trim();const kcal=foodChoice?foodChoice.kcal_per_100g:decimal(get('nutManualKcal').value),rawProtein=get('nutManualProtein').value.trim(),protein=foodChoice?foodChoice.protein_per_100g:rawProtein?decimal(rawProtein):null;
  if(!name||name.length>180)throw Error('Indiquez le nom de l’aliment (180 caractères maximum).');if(!Number.isFinite(kcal)||kcal<0||kcal>1000)throw Error('Indiquez les kcal pour 100 g, entre 0 et 1 000.');if(protein!==null&&(!Number.isFinite(protein)||protein<0||protein>100))throw Error('Indiquez les protéines pour 100 g, entre 0 et 100, ou laissez vide.');return {...base,food_id:null,name,kcal_per_100g:kcal,protein_per_100g:protein};
 }
 function preview(){try{const data=entryData(),food=editing||foodChoice||data;const grams=data.grams;get('nutPreview').textContent=number(Math.round(food.kcal_per_100g*grams/100))+' kcal · '+(food.protein_per_100g==null?'Protéines non renseignées':number(food.protein_per_100g*grams/100)+' g de protéines');}catch{get('nutPreview').textContent='Complétez les valeurs et la quantité pour voir le total.';}}
 get('nutEntryForm').onsubmit=async event=>{
  event.preventDefault();if(saving)return;notice('nutEntryError','');
  try{if(!pending){const data=entryData();if(!editing)data.client_id=crypto.randomUUID();pending={data,entryId:editing?.id};}}catch(e){notice('nutEntryError',e.message);return;}
  setBusy(true);let saved=false;
  try{await api('/api/nutrition/entries'+(pending.entryId?'/'+pending.entryId:''),{method:pending.entryId?'PATCH':'POST',body:JSON.stringify(pending.data)});saved=true;}
  catch(e){
   try{await loadDay();saved=pending.entryId?day.entries.some(row=>row.id===pending.entryId&&row.grams===pending.data.grams&&row.meal===pending.data.meal):day.entries.some(row=>row.client_id===pending.data.client_id);}catch{}
   if(!saved){if([400,401,403,404,409].includes(e.status)){pending=null;if(editing){const fresh=day?.entries.find(row=>row.id===editing.id);if(fresh)editing=fresh;}notice('nutEntryError',e.message+' Vérifiez la saisie avant de réessayer.');get('nutSaveEntry').textContent='Enregistrer';}else{notice('nutEntryError',e.message+' Réessayez pour confirmer la sauvegarde. La saisie est conservée.');get('nutSaveEntry').textContent='Réessayer l’enregistrement';}}
  }finally{
   if(saved)pending=null;setBusy(false);
   if(saved){closeEditor();toast('Repas enregistré');try{await loadDay();}catch(e){notice('nutNotice',e.message);}get('nutMeals').scrollIntoView({block:'start',behavior:'smooth'});}
  }
 };
 function fillProfile(){const p=profile||{};get('nutAge').value=p.age||'';get('nutHeight').value=p.height_cm||'';get('nutWeight').value=p.weight_kg||profileResult?.latest_weight?.weight||'';get('nutSex').value=p.sex||'female';get('nutActivity').value=p.activity||'sedentary';get('nutGoal').value=p.goal||'maintain';get('nutProteinMode').value=p.protein_mode||'standard';get('nutStandardOk').checked=Boolean(p.standard_calculation_ok);get('nutCustomKcal').value=p.custom_kcal??'';get('nutCustomProtein').value=p.custom_protein_g??'';
  const w=profileResult?.latest_weight;get('nutWeightHint').textContent=w?'Dernière pesée du suivi : '+number(w.weight)+' kg. Le poids du profil change uniquement quand vous le confirmez ici.':'Le poids saisi ici sert au calcul. Vos pesées sont gérées dans « Suivi du poids ».';
 }
 function renderEstimate(){const estimate=profileResult?.estimate,target=get('nutEstimate');if(!estimate){target.replaceChildren();return;}const rows=[['Maintien estimé',estimate.maintenance_kcal,' kcal'],['Objectif calorique',estimate.kcal_target,' kcal'],['Repère en protéines',estimate.protein_target_g,' g']];if(estimate.planned_deficit_kcal>0)rows.push(['Déficit prévu avec cet objectif',estimate.planned_deficit_kcal,' kcal']);target.innerHTML='<h2>Vos repères enregistrés</h2><dl>'+rows.map(([label,value,unit])=>'<div><dt>'+label+'</dt><dd>'+(value==null?'Non calculé':number(value)+unit)+'</dd></div>').join('')+'</dl><p>'+esc(estimate.notice||'Les besoins réels peuvent différer. Ajustez vos repères avec un professionnel si nécessaire.')+'</p><p>La journée en cours d’aujourd’hui utilise ces repères après enregistrement. Les autres journées conservent leurs valeurs ; vous pouvez actualiser une journée encore ouverte.</p><button type="button" class="nut-primary" id="nutViewDay">Voir ma journée</button>';get('nutViewDay').onclick=()=>setTab('day');}
 get('nutProfileForm').onsubmit=async event=>{event.preventDefault();if(saving||pending)return;notice('nutProfileError','');const nullable=id=>get(id).value.trim()?decimal(get(id).value):null;
  const data={version:profile?.version||0,age:Number(get('nutAge').value),height_cm:decimal(get('nutHeight').value),weight_kg:decimal(get('nutWeight').value),sex:get('nutSex').value,activity:get('nutActivity').value,goal:get('nutGoal').value,protein_mode:get('nutProteinMode').value,standard_calculation_ok:get('nutStandardOk').checked,custom_kcal:nullable('nutCustomKcal'),custom_protein_g:nullable('nutCustomProtein')};
  if(!Number.isFinite(data.height_cm)||!Number.isFinite(data.weight_kg)||[data.custom_kcal,data.custom_protein_g].some(x=>x!==null&&!Number.isFinite(x))){notice('nutProfileError','Vérifiez les nombres saisis. Vous pouvez utiliser une virgule pour les décimales.');return;}
  setBusy(true);try{profileResult=await api('/api/nutrition/profile',{method:'PUT',body:JSON.stringify(data)});profile=profileResult.profile;renderEstimate();await loadDay();if(selected===today()&&day.version>0&&!day.complete){day=await api('/api/nutrition/day',{method:'POST',body:JSON.stringify({date:selected,version:day.version,complete:false,refresh_targets:true})});renderDay();}toast('Repères enregistrés');get('nutEstimate').scrollIntoView({block:'center',behavior:'smooth'});}catch(e){notice('nutProfileError',e.message);try{const latest=await api('/api/nutrition/profile');profile=latest.profile;}catch{}}finally{setBusy(false);}
 };
 async function loadHistory(){const month=get('nutMonth').value;if(!/^\d{4}-\d{2}$/.test(month))return;const target=get('nutHistory');target.textContent='Chargement…';const result=await api('/api/nutrition/history?month='+month);if(get('nutMonth').value!==month)return;target.replaceChildren();if(!result.days.length){target.innerHTML='<p class="nut-intro">Aucune journée enregistrée ce mois-ci.</p>';return;}
  result.days.forEach(row=>{const b=document.createElement('button');b.type='button';b.className='nut-history-day';b.innerHTML='<div><strong>'+esc(niceDate(row.date))+'</strong><small>'+number(Math.round(row.totals.kcal))+' kcal · '+number(row.totals.protein_g)+' g de protéines'+(row.totals.protein_incomplete?' (partiel)':'')+'</small><small>'+(row.complete?'Saisie terminée':'Saisie en cours')+'</small></div><span aria-hidden="true">›</span>';b.onclick=()=>{selected=row.date;setTab('day');loadDay().catch(e=>notice('nutNotice',e.message));};target.append(b);});
 }
 function changeDay(delta){if(saving||pending)return;const d=dateObject(selected);d.setDate(d.getDate()+delta);const value=localDay(d);if(value>today()||d.getFullYear()<1900)return;closeEditor();selected=value;applyDate();loadDay().catch(e=>notice('nutNotice',e.message));}
 get('nutDate').value=selected;get('nutMonth').value=selected.slice(0,7);get('nutMonth').max=today().slice(0,7);
 get('nutDate').onchange=()=>{if(saving||pending||!/^\d{4}-\d{2}-\d{2}$/.test(get('nutDate').value)||get('nutDate').value>today()){applyDate();return;}closeEditor();selected=get('nutDate').value;loadDay().catch(e=>notice('nutNotice',e.message));};
 get('nutPrevDay').onclick=()=>changeDay(-1);get('nutNextDay').onclick=()=>changeDay(1);get('nutToday').onclick=()=>{if(saving||pending)return;closeEditor();selected=today();loadDay().catch(e=>notice('nutNotice',e.message));};
 get('nutMonth').onchange=()=>loadHistory().catch(e=>notice('nutNotice',e.message));get('nutRefresh').onclick=()=>{if(!saving&&!pending)load();};get('nutAdd').onclick=()=>{const h=new Date().getHours();openEditor(h<11?'breakfast':h<15?'lunch':h<18?'snack':'dinner');};get('nutSetup').onclick=()=>setTab('profile');
 root.querySelectorAll('[data-nut-tab]').forEach(b=>b.onclick=()=>setTab(b.dataset.nutTab));root.querySelectorAll('[data-nut-source]').forEach(b=>b.onclick=()=>chooseSource(b.dataset.nutSource));get('nutSearch').oninput=()=>{searchLimit=12;searchFoods();};
 ['nutGrams','nutManualName','nutManualKcal','nutManualProtein'].forEach(id=>get(id).oninput=preview);get('nutEntryClose').onclick=get('nutCancelEntry').onclick=()=>{if(pending)notice('nutEntryError','Réessayez l’enregistrement pour confirmer cette saisie avant de la fermer.');else closeEditor();};
 get('nutComplete').onclick=()=>mutate(async()=>{day=await api('/api/nutrition/day',{method:'POST',body:JSON.stringify({date:selected,version:day.version,complete:!day.complete})});});
 applyTargets.onclick=()=>mutate(async()=>{day=await api('/api/nutrition/day',{method:'POST',body:JSON.stringify({date:selected,version:day.version,complete:false,refresh_targets:true})});toast('Repères appliqués à cette journée');});
 get('nutExport').onclick=()=>mutate(async()=>{const data=await api('/api/nutrition/export');const url=URL.createObjectURL(new Blob([JSON.stringify(data,null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download='nyxpepz-nutrition-'+today()+'.json';document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),30000);toast('Export de vos données préparé');});
 get('nutErase').onclick=()=>{if(!confirm('Effacer définitivement votre profil nutritionnel, vos repas et vos favoris ? Vos pesées resteront dans le suivi de poids.'))return;mutate(async()=>{await api('/api/nutrition',{method:'DELETE',body:JSON.stringify({confirm:true})});ready=false;day=null;profile=null;closeEditor();selected=today();await load();toast('Suivi nutritionnel effacé');});};
 const originalGo=go;go=function(id){originalGo(id);if(id==='nutrition'){applyDate();if(!saving&&!pending){closeEditor();load();}}};
 const originalBack=goBack;goBack=function(){if(root.classList.contains('active')){if(!get('nutEntryEditor').hidden){if(pending)notice('nutEntryError','Réessayez l’enregistrement pour confirmer cette saisie.');else closeEditor();return;}if(tab!=='day'){setTab('day');return;}}originalBack();};root.querySelector('.page-back').onclick=()=>goBack();
})();
