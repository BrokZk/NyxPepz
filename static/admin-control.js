/* Reuse existing admin screens; render all editorial text as textContent. */
(()=>{
 const root=document.getElementById('admin');if(!root)return;
 const node=(tag,text,cls)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(cls)n.className=cls;return n;};
 const button=(text,fn)=>{const b=node('button',text,'shop-secondary');b.type='button';b.onclick=fn;return b;};
 const nav=node('div',undefined,'control-nav');nav.setAttribute('role','group');nav.setAttribute('aria-label','Rubriques Admin');root.querySelector('h1').insertAdjacentElement('afterend',nav);
 const panels={};let current='Dashboard',dashboardSeq=0;
 ['Dashboard','Boutique','Commandes','Marketing','Communauté','Réglages'].forEach(name=>{const p=node('div');p.dataset.controlPanel=name;panels[name]=p;root.append(p);nav.append(button(name,()=>select(name)));});
 const summary=document.getElementById('adSummary');panels.Dashboard.append(summary);
 const productManager=document.getElementById('adminProductManager');panels.Boutique.append(productManager);
 const packList=document.getElementById('adminPacks');panels.Boutique.append(packList.previousElementSibling,packList);
 const newsList=document.getElementById('adminNews');panels.Marketing.append(newsList.previousElementSibling,newsList);
 root.querySelectorAll('[data-go]').forEach(b=>{
  const target=b.dataset.go;
  const group=target==='adminOrders'?'Commandes':target==='adminSales'?'Dashboard':target==='adminPeople'?'Communauté':target==='adminGifts'||target==='giveawayAdmin'||target==='ambassadorAdmin'?'Marketing':null;
  if(group)panels[group].append(b);
 });
 panels.Réglages.append(node('h2','Réglages'),node('p','Images : téléversement Cloudinary depuis les formulaires. Paiements, livraison et accès Admin utilisent la configuration du serveur. Aucun secret n’est affiché ni modifié ici.','admin-note'));
 const dash=node('section',undefined,'control-dashboard');panels.Dashboard.prepend(dash);
 dash.append(node('h2','Dashboard Neo Biotech'));
 const filters=node('div',undefined,'control-nav'),status=node('p','Ouvrez l’Admin pour actualiser.','admin-note'),metrics=node('div',undefined,'control-metrics'),notes=node('div'),stock=node('div');status.setAttribute('role','status');
 dash.append(filters,status,metrics,notes,stock);let period='today';
 [['today','Aujourd’hui'],['7d','7 jours'],['30d','30 jours'],['all','Tout']].forEach(([value,label])=>filters.append(button(label,()=>{period=value;loadDashboard();})));
 filters.append(button('Actualiser',loadDashboard));
 const details=node('section',undefined,'control-details');details.id='dashboardDetails';details.hidden=true;details.setAttribute('aria-label','Détail du Dashboard');dash.insertBefore(details,notes);
 let detailSeq=0,detailTrigger=null;
 const money=v=>new Intl.NumberFormat('fr-FR',{style:'currency',currency:'EUR'}).format(v/100);
 function closeDetails(){detailSeq++;details.hidden=true;detailTrigger?.scrollIntoView({block:'center'});detailTrigger?.focus({preventScroll:true});}
 async function showDetails(metric,label,page=1,trigger=null){
  if(!me.is_admin)return;if(trigger)detailTrigger=trigger;
  const seq=++detailSeq;details.hidden=false;details.replaceChildren(button('‹ Retour au Dashboard',closeDetails));
  const title=node('h3',label);title.tabIndex=-1;const message=node('p','Chargement…','admin-note');message.setAttribute('role','status');details.append(title,message);
  details.scrollIntoView({block:'start'});title.focus({preventScroll:true});
  if(metric==='fees'||metric==='net'){message.textContent='Indisponible : les frais et règlements nets en euros ne sont pas vérifiés. Les montants crypto ne permettent pas de calculer un net fiable.';return;}
  try{
   const data=await api('/api/admin/dashboard/details?'+new URLSearchParams({metric,period,page}));if(seq!==detailSeq)return;
   message.textContent=data.scope+' · '+data.total+' résultat(s)';
   if(!data.items.length)details.append(node('p','Aucun résultat pour ce filtre.','admin-note'));
   data.items.forEach(item=>{
    const row=node('article',undefined,'card control-detail-row');
    row.append(node('b',item.name));if(item.username)row.append(node('p','@'+item.username));
    if(data.kind==='orders'){
     row.append(node('p',item.reference+' · '+item.status_label),node('p',money(item.total_cents)+' · '+new Date(item.created_at*1000).toLocaleString('fr-FR',{timeZone:'Europe/Paris'})),button('Ouvrir la commande',()=>window.dispatchEvent(new CustomEvent('admin-open-order',{detail:item.reference}))));
    }else if(data.kind==='clients'){
     row.append(node('p','Telegram : '+item.telegram_id+' · '+item.points+' points'));
     if(item.created_at){const raw=item.created_at;row.append(node('p','Inscrit le '+new Date(/(?:Z|[+-]\d\d:\d\d)$/.test(raw)?raw:raw+'Z').toLocaleString('fr-FR',{timeZone:'Europe/Paris'})));}
     row.append(button('Ouvrir le client',()=>window.dispatchEvent(new CustomEvent('admin-open-client',{detail:item.id}))));
    }else{
     row.append(node('p',item.format+' · '+item.stock+' en stock'),button('Gérer le stock',async()=>{
      try{adminProductItems=await api('/api/admin/products');select('Boutique');adminProductCategory=null;document.getElementById('adminProductSearch').value=item.name;renderAdminProducts();const target=document.querySelector('[data-admin-product-id="'+item.id+'"]');target?.scrollIntoView({block:'start'});target?.querySelector('.admin-stock-open')?.click();}catch(e){toast(e.message);}
     }));
    }
    details.append(row);
   });
   const pagination=node('div',undefined,'control-nav');
   const previous=button('‹ Précédent',()=>showDetails(metric,label,data.page-1)),next=button('Suivant ›',()=>showDetails(metric,label,data.page+1));previous.disabled=data.page<=1;next.disabled=data.page>=data.pages;
   pagination.append(previous,node('span','Page '+data.page+' / '+data.pages),next);details.append(pagination);
  }catch(e){if(seq!==detailSeq)return;message.textContent=e.message;details.append(button('Réessayer',()=>showDetails(metric,label,page)));}
 }
 async function loadDashboard(){
  if(!me.is_admin)return;detailSeq++;details.hidden=true;const seq=++dashboardSeq;status.textContent='Chargement…';metrics.replaceChildren();notes.replaceChildren();stock.replaceChildren();
  [...filters.children].forEach((b,i)=>b.setAttribute('aria-pressed',String(['today','7d','30d','all'][i]===period)));
  try{const d=await api('/api/admin/dashboard?period='+period);if(seq!==dashboardSeq)return;
   const eur=v=>new Intl.NumberFormat('fr-FR',{style:'currency',currency:'EUR'}).format(v/100);
   const cards=[['CA brut confirmé',eur(d.gross_cents),'gross'],['Frais','Indisponibles','fees'],['CA net','Net indisponible','net'],['Commandes aujourd’hui',d.orders_today,'orders_today'],['Commandes sur la période',d.orders_in_period,'orders_in_period'],['À préparer',d.preparing,'preparing'],['Clients inscrits',d.clients,'clients'],['Nouveaux clients sur la période',d.clients_in_period,'clients_in_period'],['Paiements à vérifier',d.payment_review,'payment_review'],['Stocks faibles',d.low_stock.length,'low_stock'],['Colis sans suivi',d.missing_tracking,'missing_tracking']];
   cards.forEach(([label,value,metric])=>{
    const c=node('button',undefined,'card control-metric-action');c.dataset.metric=metric;
    c.append(node('small',label),node('strong',String(value)));
    const link=metric==='fees'||metric==='net'?'Pourquoi indisponible ?':'Voir le détail ›';
    c.type='button';c.onclick=()=>showDetails(metric,label,1,c);c.setAttribute('aria-label',label+' : '+value+' — '+link);c.setAttribute('aria-controls','dashboardDetails');c.append(node('span',link,'control-metric-link'));
    metrics.append(c);
   });
   notes.append(node('p',d.financial_notice,'admin-note'),node('p',d.scope_notice,'admin-note'));
   if(d.history_notice)notes.append(node('p',d.history_notice+' '+d.undated_orders+' commande(s) ; exclues des périodes datées, incluses dans Tout.','control-warning'));
   notes.append(node('h3','Ventilation du CA brut'));
   Object.entries(d.payment_split).forEach(([key,v])=>notes.append(node('p',({crypto:'Crypto',other:'Autres paiements',unknown:'Moyen non renseigné'})[key]+' : '+eur(v.gross_cents)+' · '+v.orders+' commande(s)')));
   stock.append(node('h3','Stocks faibles · état actuel'));d.low_stock.forEach(p=>stock.append(node('p',p.name+' '+p.format+' : '+p.stock)));
   status.textContent='Actualisé à '+new Date(d.generated_at*1000).toLocaleTimeString('fr-FR');
  }catch(e){if(seq===dashboardSeq)status.textContent=e.message;}
 }
 function select(name){current=name;Object.entries(panels).forEach(([key,p])=>p.hidden=key!==name);[...nav.children].forEach(b=>b.setAttribute('aria-pressed',String(b.textContent===name)));if(name==='Dashboard')loadDashboard();if(name==='Boutique')loadProtocols();}
 const editorial=node('section',undefined,'control-protocols');panels.Boutique.append(editorial);editorial.append(node('h2','Protocoles informatifs'));
 const protocolStatus=node('p','','admin-note'),list=node('div'),editor=node('form',undefined,'card control-editor');protocolStatus.setAttribute('role','status');let editing=null;
 const fields={};
 function field(key,label,type='text'){const l=node('label',label),input=node(type==='textarea'?'textarea':'input');if(type!=='textarea')input.type=type;input.name=key;l.append(input);editor.append(l);fields[key]=input;return input;}
 field('title','Titre').required=true;fields.title.maxLength=200;field('category','Catégorie').required=true;fields.category.maxLength=100;
 field('description','Description','textarea');field('content','Contenu éditorial','textarea');field('image_url','URL image');
 const file=field('photo','Photo depuis votre téléphone','file');file.accept='image/png,image/jpeg,image/webp';field('sort_order','Ordre d’affichage','number');fields.sort_order.min=-100000;fields.sort_order.max=100000;
 const active=field('active','Visible dans l’app','checkbox');
 const steps=node('div',undefined,'control-steps');editor.append(node('h3','Étapes éditoriales'),steps);
 function addStep(value={title:'',text:''}){const row=node('div',undefined,'card'),label=node('label','Titre de l’étape'),title=node('input'),textLabel=node('label','Texte de l’étape'),text=node('textarea');title.value=value.title;text.value=value.text;title.maxLength=200;text.maxLength=10000;label.append(title);textLabel.append(text);row.append(label,textLabel,button('Retirer cette étape',()=>row.remove()));steps.append(row);}
 editor.append(button('Ajouter une étape',()=>addStep()));const save=node('button','Enregistrer','shop-primary');save.type='submit';editor.append(save,button('Annuler',()=>editor.hidden=true));editor.hidden=true;
 editorial.append(button('＋ Créer un protocole',()=>edit()),button('Actualiser les protocoles',loadProtocols),protocolStatus,list,editor);
 function edit(p=null){editing=p?.id??null;editor.hidden=false;editor.reset();steps.replaceChildren();['title','category','description','content','image_url'].forEach(k=>fields[k].value=p?.[k]||'');fields.sort_order.value=p?.sort_order??0;active.checked=p?.active??true;
  const legacy=p&&['mix','start','then','rhythm'].some(k=>p[k]);
  const imported=legacy?['mix','start','then','rhythm'].map((k,i)=>({title:p.blockLabels?.[i]||['Flacon → mélange','Dose de départ','Ensuite','Rythme & moment'][i],text:(p[k]||'')+(k==='mix'&&p.concentration?'\n'+p.concentration:'')})):[];
  (p?.steps?.length?p.steps:imported).forEach(addStep);editor.scrollIntoView({block:'start'});fields.title.focus();
 }
 let protocolSeq=0;
 async function loadProtocols(){if(!me.is_admin)return;const seq=++protocolSeq;protocolStatus.textContent='Chargement…';try{const data=await api('/api/admin/protocols');if(seq!==protocolSeq)return;list.replaceChildren();data.forEach(p=>{const row=node('article',undefined,'card control-protocol-row');row.append(node('b',p.title),node('p',p.category+' · '+(p.active?'Actif':'Masqué')+' · ordre '+p.sort_order),button('Modifier',()=>edit(p)),button(p.active?'Masquer':'Afficher',()=>mutate(p.id,'PATCH',{active:!p.active})),button('Supprimer',()=>{if(confirm('Supprimer « '+p.title+' » ?'))mutate(p.id,'DELETE');}));list.append(row);});protocolStatus.textContent=data.length+' protocole(s).';}catch(e){if(seq===protocolSeq)protocolStatus.textContent=e.message;}}
 async function mutate(id,method,payload){try{await api('/api/admin/protocols/'+id,{method,...(payload?{body:JSON.stringify(payload)}:{})});await loadProtocols();window.dispatchEvent(new Event('protocols-updated'));}catch(e){protocolStatus.textContent=e.message;}}
 editor.onsubmit=async event=>{event.preventDefault();save.disabled=true;try{const payload={};['title','category','description','content','image_url'].forEach(k=>payload[k]=fields[k].value);if(file.files[0])payload.image_url=await uploadPhoto(file);payload.active=active.checked;payload.sort_order=Number(fields.sort_order.value);payload.steps=[...steps.children].map(row=>({title:row.querySelector('input').value,text:row.querySelector('textarea').value}));await api('/api/admin/protocols'+(editing===null?'':'/'+editing),{method:editing===null?'POST':'PATCH',body:JSON.stringify(payload)});editor.hidden=true;await loadProtocols();window.dispatchEvent(new Event('protocols-updated'));}catch(e){protocolStatus.textContent=e.message;}finally{save.disabled=false;}};
 const previousGo=window.go;window.go=function(id){previousGo(id);if(id==='admin'&&me.is_admin)select(current);};
 Object.entries(panels).forEach(([key,p])=>p.hidden=key!=='Dashboard');nav.children[0].setAttribute('aria-pressed','true');
})();
