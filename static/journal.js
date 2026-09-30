/* Personal records only: no dose recommendations, recurrence or reminders. */
(()=>{
 const root=document.getElementById('journal');if(!root)return;
 const get=id=>document.getElementById(id),form=get('journalForm'),weightForm=get('journalWeightForm');
 const pad=n=>String(n).padStart(2,'0');
 const localDay=d=>`${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())}`;
 const clock=d=>`${pad(d.getHours())}:${pad(d.getMinutes())}`;
 const today=()=>localDay(new Date());
 const dateObject=s=>new Date(s+'T12:00:00');
 const niceDay=s=>dateObject(s).toLocaleDateString('fr-FR',{weekday:'long',day:'numeric',month:'long',year:'numeric'});
 const uid=()=>crypto.randomUUID?crypto.randomUUID():Array.from(crypto.getRandomValues(new Uint8Array(16)),(n,i)=>(i===6?(n&15)|64:i===8?(n&63)|128:n).toString(16).padStart(2,'0')).join('').replace(/(.{8})(.{4})(.{4})(.{4})(.{12})/,'$1-$2-$3-$4-$5');
 let selected=today(),month=selected.slice(0,7),wholeMonth=false,entries=[],weights=[],catalog=[],editing=null,clientId='',loading=false,saving=false,ready=false,requestNumber=0;
 function el(tag,cls,text){const n=document.createElement(tag);if(cls)n.className=cls;if(text!==undefined)n.textContent=text;return n;}
 function button(text,cls,fn){const n=el('button',cls,text);n.type='button';n.onclick=fn;return n;}
 const error=(id,message)=>{get(id).textContent=message;};
 function formsClosed(){form.hidden=true;weightForm.hidden=true;editing=null;}
 function weightsForMonth(){return weights.filter(w=>localDay(new Date(w.date)).startsWith(month));}
 function render(){
  const [year,m]=month.split('-').map(Number),start=new Date(year,m-1,1,12),days=new Date(year,m,0).getDate(),grid=get('journalDays');
  get('journalMonth').textContent=start.toLocaleDateString('fr-FR',{month:'long',year:'numeric'});grid.replaceChildren();
  for(let i=0;i<(start.getDay()+6)%7;i++)grid.append(el('span'));
  for(let day=1;day<=days;day++){
   const key=`${month}-${pad(day)}`,records=entries.filter(e=>e.date===key),peses=weights.filter(w=>localDay(new Date(w.date))===key);
   const b=button('','journal-day',()=>{selected=key;wholeMonth=false;render();});b.append(el('span','',day));b.dataset.date=key;b.classList.toggle('selected',!wholeMonth&&selected===key);b.setAttribute('aria-pressed',String(!wholeMonth&&selected===key));if(key===today())b.setAttribute('aria-current','date');
   const dots=el('span','journal-dots');for(const status of ['done','planned'])if(records.some(e=>e.status===status))dots.append(el('i',status));if(peses.length)dots.append(el('i','weight'));b.append(dots);
   b.setAttribute('aria-label',niceDay(key)+`, ${records.filter(e=>e.status==='done').length} effectué, ${records.filter(e=>e.status==='planned').length} prévu, ${peses.length} pesée`);grid.append(b);
  }
  get('journalPrev').disabled=month==='1900-01';get('journalNext').disabled=month==='2100-12';
  get('journalWholeMonth').setAttribute('aria-pressed',String(wholeMonth));
  const monthWeights=weightsForMonth(),last=monthWeights.at(-1);
  get('journalSummary').textContent=ready?`${entries.filter(e=>e.status==='done').length} effectué · ${entries.filter(e=>e.status==='planned').length} prévu · ${monthWeights.length} pesée${monthWeights.length>1?'s':''}${last?' · Dernier poids du mois : '+last.weight.toLocaleString('fr-FR')+' kg':''}`:'Journal non chargé';
  get('journalDayTitle').textContent=wholeMonth?'Toutes les entrées du mois':niceDay(selected);
  const filter=get('journalFilter').value,list=get('journalEntries');list.replaceChildren();
  if(!ready){list.append(el('p','journal-caption',loading?'Chargement…':'Actualisez le journal pour consulter vos entrées.'));return;}
  const records=entries.filter(e=>(wholeMonth||e.date===selected)&&(filter==='all'||filter===e.status)).map(e=>({kind:'entry',sort:e.date+'T'+e.time,value:e}));
  if(filter==='all'||filter==='weight')for(const w of monthWeights){const dt=new Date(w.date),key=localDay(dt);if(wholeMonth||key===selected)records.push({kind:'weight',sort:key+'T'+clock(dt),value:w});}
  records.sort((a,b)=>a.sort.localeCompare(b.sort));
  if(!records.length)list.append(el('p','card journal-empty',filter==='all'?'Aucune entrée pour cette période. Notez une prise ou une pesée.':'Aucune entrée pour ce filtre.'));
  for(const record of records){
   const article=el('article','card journal-entry'),data=record.value;
   if(record.kind==='weight'){
    article.append(el('span','journal-badge weight','Pesée'),el('h3','',data.weight.toLocaleString('fr-FR')+' kg'),el('p','journal-caption',niceDay(record.sort.slice(0,10))+' · '+record.sort.slice(11)),el('p','journal-caption','Reliée à votre suivi du poids'));list.append(article);continue;
   }
   article.dataset.entryId=data.id;article.append(el('span','journal-badge '+data.status,data.status==='done'?'Effectué':'Prévu'),el('h3','',data.product_name),el('p','journal-caption',data.product_format?'Format du produit : '+data.product_format:''),el('p','journal-amount',data.amount.replace('.',',')+' '+(data.unit==='U-100'?'unités U-100':data.unit)),el('p','journal-caption',niceDay(data.date)+' · '+data.time));
   if(data.note)article.append(el('p','journal-entry-note',data.note));
   const actions=el('div','journal-actions');actions.append(button('Modifier','shop-secondary',()=>openForm(data)),button('Supprimer','journal-delete',()=>removeEntry(data)));article.append(actions);list.append(article);
  }
 }
 async function load(){
  const token=++requestNumber,requestedMonth=month;loading=true;ready=false;entries=[];weights=[];error('journalNotice','Chargement du journal…');render();
  try{
   const [journal,peses,products]=await Promise.all([api('/api/journal?month='+requestedMonth),api('/api/weights'),api('/api/catalog')]);
   if(token!==requestNumber)return;
   entries=journal.entries;weights=peses;catalog=products.filter(p=>p.cat!=='Accessoires');ready=true;error('journalNotice','');
  }catch(e){if(token===requestNumber)error('journalNotice',e.message);}
  finally{if(token===requestNumber){loading=false;render();}}
 }
 function openForm(entry=null){
  if(saving)return;if(!ready){error('journalNotice','Chargez le journal avant d’ajouter une entrée.');return;}
  formsClosed();editing=entry;clientId=uid();form.reset();get('journalFormTitle').textContent=entry?'Modifier la prise':'Ajouter une prise';
  const select=get('journalProduct');select.replaceChildren(new Option('Choisir un produit',''));
  for(const p of [...catalog].sort((a,b)=>(a.name+' '+a.format).localeCompare(b.name+' '+b.format,'fr',{numeric:true})))select.add(new Option(p.name+(p.format?' · '+p.format:''),p.id));
  if(entry&&!catalog.some(p=>p.id===entry.product_id))select.add(new Option(entry.product_name+' · '+entry.product_format+' (ancien produit)',entry.product_id));
  select.value=entry?.product_id||'';get('journalDate').value=entry?.date||selected;get('journalTime').value=entry?.time||clock(new Date());get('journalAmount').value=entry?.amount?.replace('.',',')||'';get('journalUnit').value=entry?.unit||'mg';get('journalStatus').value=entry?.status||'';get('journalNote').value=entry?.note||'';error('journalFormError','');form.hidden=false;form.scrollIntoView({block:'start'});select.focus({preventScroll:true});
 }
 function setSaving(value){saving=value;form.querySelector('fieldset').disabled=value;weightForm.querySelector('fieldset').disabled=value;}
 form.onsubmit=async event=>{
  event.preventDefault();if(saving)return;
  const raw=get('journalAmount').value.trim();if(!/^\d{1,7}(?:[.,]\d{1,6})?$/.test(raw)||Number(raw.replace(',','.'))<=0){error('journalFormError','Saisissez une quantité positive, sans texte.');return;}
  const data={product_id:Number(get('journalProduct').value),date:get('journalDate').value,time:get('journalTime').value,amount:raw,unit:get('journalUnit').value,status:get('journalStatus').value,note:get('journalNote').value};
  if(editing)data.version=editing.version;else data.client_id=clientId;
  error('journalFormError','');setSaving(true);
  try{
   await api('/api/journal'+(editing?'/'+editing.id:''),{method:editing?'PATCH':'POST',body:JSON.stringify(data)});
   selected=data.date;month=selected.slice(0,7);wholeMonth=false;formsClosed();toast('Entrée enregistrée');await load();
  }catch(e){error('journalFormError',e.message);}finally{setSaving(false);}
 };
 async function removeEntry(entry){
  if(saving)return;if(!confirm('Supprimer l’entrée « '+entry.product_name+' » du '+niceDay(entry.date)+' à '+entry.time+' ?'))return;
  setSaving(true);
  try{await api('/api/journal/'+entry.id,{method:'DELETE',body:JSON.stringify({version:entry.version})});toast('Entrée supprimée');await load();}catch(e){error('journalNotice',e.message);}finally{setSaving(false);}
 }
 get('journalAdd').onclick=()=>openForm();get('journalCancel').onclick=formsClosed;get('journalWeightCancel').onclick=formsClosed;
 get('journalAddWeight').onclick=()=>{if(saving)return;if(!ready){error('journalNotice','Chargez le journal avant de noter une pesée.');return;}formsClosed();weightForm.reset();get('journalWeightDate').max=today();get('journalWeightDate').value=selected>today()?today():selected;get('journalWeightTime').value=clock(new Date());error('journalWeightError','');weightForm.hidden=false;weightForm.scrollIntoView({block:'start'});get('journalWeight').focus({preventScroll:true});};
 weightForm.onsubmit=async event=>{
  event.preventDefault();if(saving)return;
  const raw=get('journalWeight').value.trim(),dt=new Date(get('journalWeightDate').value+'T'+get('journalWeightTime').value+':00');
  if(!/^\d+(?:[.,]\d+)?$/.test(raw)||Number(raw.replace(',','.'))<25||Number(raw.replace(',','.'))>350){error('journalWeightError','Saisissez un poids entre 25 et 350 kg.');return;}
  if(!Number.isFinite(dt.getTime())||dt>new Date()){error('journalWeightError','La date et l’heure doivent correspondre à une pesée passée.');return;}
  setSaving(true);error('journalWeightError','');
  try{await api('/api/weights',{method:'POST',body:JSON.stringify({weight:raw,date:dt.toISOString()})});selected=localDay(dt);month=selected.slice(0,7);wholeMonth=false;formsClosed();toast('Pesée ajoutée au journal et au suivi');await load();}catch(e){error('journalWeightError',e.message);}finally{setSaving(false);}
 };
 function changeMonth(delta){if(saving)return;const d=dateObject(month+'-01');d.setMonth(d.getMonth()+delta);if(d.getFullYear()<1900||d.getFullYear()>2100)return;month=localDay(d).slice(0,7);selected=month+'-01';wholeMonth=true;formsClosed();load();}
 get('journalPrev').onclick=()=>changeMonth(-1);get('journalNext').onclick=()=>changeMonth(1);
 get('journalToday').onclick=()=>{if(saving)return;selected=today();month=selected.slice(0,7);wholeMonth=false;formsClosed();load();};
 get('journalWholeMonth').onclick=()=>{wholeMonth=true;render();};get('journalFilter').onchange=render;get('journalRefresh').onclick=()=>{if(!saving)load();};
 const originalGo=go;go=function(id){originalGo(id);if(id==='journal'){if(!saving)formsClosed();load();}};
 const originalBack=goBack;goBack=function(){if(root.classList.contains('active')&&(!form.hidden||!weightForm.hidden)){if(!saving)formsClosed();return;}originalBack();};
 // Existing page-back buttons were bound before this module loaded.
 root.querySelector('.page-back').onclick=()=>goBack();render();
})();
