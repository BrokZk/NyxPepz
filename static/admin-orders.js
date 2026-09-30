/* Private order workflow. Payment and delivery transitions remain server-owned. */
(()=>{
 const root=document.getElementById('adminOrders');if(!root)return;
 const get=id=>document.getElementById(id);
 const el=(tag,cls,text)=>{const n=document.createElement(tag);if(cls)n.className=cls;if(text!==undefined)n.textContent=text;return n;};
 const button=(label,fn,cls='ao-secondary')=>{const b=el('button',cls,label);b.type='button';b.onclick=fn;return b;};
 const money=c=>new Intl.NumberFormat('fr-FR',{style:'currency',currency:'EUR'}).format((c||0)/100);
 const date=t=>new Intl.DateTimeFormat('fr-FR',{dateStyle:'medium',timeStyle:'short'}).format(new Date(t*1000));
 const countries={FR:'France',BE:'Belgique',ES:'Espagne'};
 const groups={preparing:['Bordereaux à faire','Commandes payées ou offertes : préparez les étiquettes Mondial Relay avec les coordonnées de chaque commande.','Aucun bordereau à faire.'],payments:['Paiements','Les paiements en attente ou à vérifier sont regroupés ici.','Aucun paiement en attente ou à vérifier.'],ready:['Prêts à envoyer','Les bordereaux sont faits. Marquez les colis expédiés après leur dépôt.','Aucun colis prêt à envoyer.'],shipping:['En livraison','Colis expédiés ou disponibles au point de retrait.','Aucun colis en livraison.'],history:['Historique','Toutes les commandes payées ou offertes, avec leur état actuel.','Aucune commande payée ou offerte dans l’historique.']};
 let group='preparing',cursors=[null],page=0,next=null,selected=null,selectedRef=null;
 let listSeq=0,detailSeq=0,listController,detailController,loading=false,busy=false,verified=false,dirty=true,loaded=false,scroll=0,returnRef=null;
 const active=()=>root.classList.contains('active');
 function note(id,text){get(id).textContent=text;get(id).hidden=!text;}
 async function request(url,options={}){
  const response=await fetch(url,{credentials:'same-origin',cache:'no-store',...options,headers:{'Content-Type':'application/json',...(options.headers||{})}});
  const data=await response.json().catch(()=>({}));if(!response.ok){const e=Error(data.error||'La commande n’a pas pu être chargée.');e.status=response.status;throw e;}return data;
 }
 function cancelList(){listSeq++;listController?.abort();}
 function cancelDetail(){detailSeq++;detailController?.abort();}
 function status(o){return ['paid','gifted'].includes(o.status)?(o.preparation?.prepared?'Prêt à envoyer':'Bordereau à faire'):o.status_label;}
 function stage(o){return ['paid','gifted'].includes(o.status)?(o.preparation?.prepared?'ready':'preparing'):['awaiting_payment','payment_review'].includes(o.status)?'payments':['shipped','available'].includes(o.status)?'shipping':'history';}
 function person(o){return [o.contact.first_name,o.contact.last_name].filter(Boolean).join(' ')||'Client';}
 function controls(){
  get('aoPrevious').disabled=loading||busy||page===0;get('aoNext').disabled=loading||busy||!next;
  get('aoPage').textContent='Page '+(page+1);
  get('aoRefresh').disabled=busy;get('aoRefreshDetail').disabled=busy;
  root.querySelectorAll('[data-order-group],.ao-order-row').forEach(b=>{b.disabled=busy;});
  root.querySelectorAll('[data-ao-mutate]').forEach(b=>{b.disabled=busy||!verified;});
 }
 function setGroup(value){if(busy)return;group=value;cursors=[null];page=0;next=null;dirty=true;loadList();}
 function row(o){
  const li=el('li'),b=button('',()=>openDetail(o.reference),'ao-order-row');b.dataset.reference=o.reference;b.disabled=busy;
  const top=el('span','ao-row-top');top.append(el('strong','',person(o)),el('b','',money(o.total_cents)));
  const middle=el('span','ao-row-middle');if(o.is_gift)b.append(el('span','gift-order-badge','Cadeau · offert'));
  middle.append(el('span','ao-badge ao-status-'+o.status,status(o)),el('span','ao-row-arrow','›'));
  const bottom=el('small','ao-row-meta',date(o.created_at)+' · '+o.reference);
  b.setAttribute('aria-label','Ouvrir la commande de '+person(o)+', '+status(o)+', '+money(o.total_cents)+', '+o.reference);
  b.append(top,middle,bottom);if(o.payment_help_requested)b.append(el('small','ao-help-request','Autre paiement demandé'));
  li.append(b);return li;
 }
 function restoreList(){scrollTo({top:scroll,behavior:'instant'});if(returnRef){[...get('aoList').querySelectorAll('[data-reference]')].find(b=>b.dataset.reference===returnRef)?.focus({preventScroll:true});}}
 async function loadList({restore=false}={}){
  cancelList();const seq=listSeq;listController=new AbortController();loading=true;next=null;
  get('aoList').replaceChildren();get('aoList').setAttribute('aria-busy','true');note('aoListError','');get('aoRetry').hidden=true;
  get('aoGroupTitle').textContent=groups[group][0];get('aoGroupHint').textContent=groups[group][1];get('aoListStatus').textContent='Chargement des commandes…';
  root.querySelectorAll('[data-order-group]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.orderGroup===group)));controls();
  try{
   const params=new URLSearchParams({group,limit:'10'});if(cursors[page])params.set('before',cursors[page]);
   const data=await request('/api/shop/admin/orders?'+params,{signal:listController.signal});if(seq!==listSeq||!active())return;
   if(!data.orders.length&&page>0){page--;cursors.length=page+1;return loadList({restore});}
   loaded=true;dirty=false;next=data.next_before;get('aoList').replaceChildren(...data.orders.map(row));
   get('aoListStatus').textContent=data.orders.length?(data.orders.length+' commande'+(data.orders.length===1?'':'s')+' sur cette page'):groups[group][2];
   if(!data.orders.length)get('aoList').append(el('li','ao-empty',group==='preparing'?'Les commandes payées et les cadeaux confirmés apparaissent ici.':groups[group][1]));
   get('aoPagination').hidden=!data.orders.length;if(restore)restoreList();
  }catch(e){if(e.name==='AbortError'||seq!==listSeq||!active())return;dirty=true;get('aoListStatus').textContent='Liste indisponible';note('aoListError',e.message);get('aoRetry').hidden=false;}
  finally{if(seq===listSeq){loading=false;get('aoList').setAttribute('aria-busy','false');controls();}}
 }
 function showList({restore=false}={}){
  cancelDetail();selected=null;selectedRef=null;verified=false;get('aoDirectory').hidden=false;get('aoDetail').hidden=true;
  root.querySelector('.page-back').textContent='‹ Administration';if(dirty||!loaded)loadList({restore});else if(restore)restoreList();
 }
 async function openDetail(reference,{refresh=false}={}){
  if(busy){toast('Enregistrement en cours…');return;}
  if(!refresh){scroll=window.scrollY;returnRef=reference;}
  cancelDetail();const seq=detailSeq;detailController=new AbortController();selectedRef=reference;selected=null;verified=false;
  get('aoDirectory').hidden=true;get('aoDetail').hidden=false;root.querySelector('.page-back').textContent='‹ Commandes';
  get('aoDetailBody').replaceChildren(el('p','ao-muted','Chargement de la commande…'));note('aoDetailError','');note('aoDetailStatus','');get('aoCopyFallback').hidden=true;controls();get('aoRefreshDetail').disabled=true;
  if(!refresh)scrollTo({top:0,behavior:'instant'});
  try{
   const data=await request('/api/shop/admin/orders/'+encodeURIComponent(reference),{signal:detailController.signal});if(seq!==detailSeq||!active())return;
   selected=data.order;verified=true;renderDetail();if(!refresh)get('aoDetailBody').querySelector('h1').focus({preventScroll:true});
  }catch(e){if(e.name==='AbortError'||seq!==detailSeq||!active())return;get('aoDetailBody').replaceChildren(el('p','ao-muted','La commande est indisponible.'));note('aoDetailError',e.message);dirty=true;}
  finally{if(seq===detailSeq)get('aoRefreshDetail').disabled=busy;}
 }
 async function copy(text){
  try{await navigator.clipboard.writeText(text);toast('Coordonnées copiées');get('aoCopyFallback').hidden=true;}
  catch{get('aoCopyFallback').hidden=false;get('aoCopyText').value=text;get('aoCopyText').focus();get('aoCopyText').select();}
 }
 function contactField(host,label,value){
  if(!value)return;const item=el('div','ao-contact-field'),text=el('div');text.append(el('span','',label),el('p','',value));
  const b=button('Copier',()=>copy(value),'ao-copy');b.setAttribute('aria-label','Copier : '+label);item.append(text,b);host.append(item);
 }
 function field(label,id,type='text',value=''){
  const wrapper=el('label','',label),input=el('input');input.id=id;input.type=type;input.value=value;wrapper.append(input);return {wrapper,input};
 }
 function action(label,fn,primary=false){const b=button(label,fn,primary?'ao-primary':'ao-secondary');b.dataset.aoMutate='';return b;}
 function formButton(label){const b=el('button','ao-primary',label);b.type='submit';return b;}
 function renderDetail(){
  const o=selected,host=get('aoDetailBody');host.replaceChildren();
  const header=el('div','ao-detail-heading');header.append(el('span','ao-badge ao-status-'+o.status,status(o)));
  if(o.is_gift)header.append(el('span','gift-order-badge','Cadeau · produit et livraison offerts'));
  const title=el('h1','',person(o));title.tabIndex=-1;header.append(title,el('p','ao-muted',o.reference+' · '+date(o.created_at)));host.append(header);
  const contact=el('section','ao-card');contact.append(el('h2','','Coordonnées de livraison'));
  const c=o.contact,address=[c.address,c.address_extra,[c.postal_code,c.city].filter(Boolean).join(' '),countries[c.country]||c.country].filter(Boolean).join('\n');
  contact.append(button('Copier toutes les coordonnées',()=>copy(person(o)+'\n'+address+'\n'+c.email+'\n'+c.phone),'ao-secondary ao-copy-all'));
  contactField(contact,'Nom et prénom',person(o));contactField(contact,'Adresse',address);contactField(contact,'Email',c.email);contactField(contact,'Téléphone',c.phone);
  if(o.username)contactField(contact,'Pseudo Telegram','@'+o.username);host.append(contact);
  const contents=el('section','ao-card');contents.append(el('h2','','Contenu de la commande'));
  for(const line of o.lines){const item=el('div','ao-product-line'),label=el('div');label.append(el('b','',line.name),el('small','',(line.format?line.format+' · ':'')+'Quantité '+line.quantity));item.append(label,el('strong','',money(line.line_cents)));contents.append(item);}
  for(const [label,amount] of [['Produits',o.subtotal_cents],...(o.discount_cents?[['Réduction',-o.discount_cents]]:[]),['Livraison',o.shipping_cents],['Total de la commande',o.total_cents]]){const line=el('div','ao-total');line.append(el('span','',label),el('strong','',money(amount)));contents.append(line);}host.append(contents);
  if(o.payment_help_requested){const help=el('section','ao-card ao-callout');help.append(el('h2','','Autre paiement demandé'),el('p','',o.status==='awaiting_payment'?'Client à recontacter. Son paiement reste en attente.':'Une demande de contact a été enregistrée.'));
   const username=typeof o.username==='string'&&/^[A-Za-z0-9_]{5,32}$/.test(o.username)?o.username:null,id=String(o.telegram_id||'');
   if(username||/^[0-9]+$/.test(id)){const a=el('a','ao-secondary','Contacter sur Telegram ↗');a.href=username?'https://t.me/'+username:'tg://user?id='+id;a.target='_blank';a.rel='noopener noreferrer';help.append(a);}host.append(help);
  }
  const payment=el('details','ao-card ao-payment-proof');payment.append(el('summary','',o.is_gift?'Commande offerte':'Détails du paiement'));
  for(const p of o.payments||[])payment.append(el('p','ao-evidence','Reçu : '+p.amount+' '+p.coin+'\nVersé : '+p.forwarded_amount+'\nTransaction : '+p.transaction_id));
  if(o.payment_note)payment.append(el('p','',o.payment_note));if(!o.payment_note&&!o.payments?.length)payment.append(el('p','ao-muted',o.is_gift?'Produit et livraison offerts. Aucun paiement à encaisser.':'Aucun paiement reçu à vérifier pour le moment.'));host.append(payment);
  const actions=el('section','ao-card ao-workflow');host.append(actions);
  if(o.status==='awaiting_payment'){
   actions.append(el('h2','','En attente de paiement'),el('p','ao-muted','Le bordereau sera à préparer après réception et validation du paiement.'));
  }else if(o.status==='payment_review'){
   actions.append(el('h2','','Vérifier le paiement'),el('p','ao-muted','Vérifiez le paiement reçu, puis confirmez son montant total en euros.'));
   const form=el('form'),fieldset=el('fieldset');fieldset.dataset.aoMutate='';const amount=field('Montant total reçu (€)','aoReceived'),reference=field('Note de vérification','aoPaymentNote');
   amount.input.inputMode='decimal';amount.input.required=true;amount.input.placeholder='Montant vérifié en euros';reference.input.required=true;reference.input.minLength=3;reference.input.maxLength=300;reference.input.placeholder='Ex. Reçu — référence de transaction';
   fieldset.append(amount.wrapper,reference.wrapper,formButton('Valider le paiement'));form.append(fieldset);
   form.onsubmit=e=>{e.preventDefault();if(busy||!verified||!form.reportValidity())return;const value=amount.input.value.trim().replace(',','.');if(!/^\d+(?:\.\d{1,2})?$/.test(value)){note('aoDetailError','Indiquez un montant en euros avec au maximum deux décimales.');get('aoDetailError').scrollIntoView({block:'start',behavior:'instant'});return;}mutate('confirm-payment',{confirmed_total_cents:Math.round(Number(value)*100),note:reference.input.value.trim()},'Paiement validé. Le bordereau est à faire.','preparing');};actions.append(form);
  }else if(['paid','gifted'].includes(o.status)&&!o.preparation?.prepared){
   actions.append(el('h2','','Bordereau à faire'),el('p','ao-muted','Créez votre étiquette dans Mondial Relay avec les coordonnées ci-dessus. Une fois l’étiquette prête, marquez cette étape comme terminée.'),action('Bordereau fait',()=>mutate('preparation',{prepared:true},'Bordereau enregistré comme fait. Le colis est prêt à envoyer.','ready'),true));
  }else if(['paid','gifted'].includes(o.status)||['shipped','available'].includes(o.status)){
   if(['paid','gifted'].includes(o.status)){actions.append(el('h2','','Prêt à envoyer'),el('p','ao-muted','Bordereau fait'+(o.preparation?.prepared_at?' le '+date(o.preparation.prepared_at):'')+'. Confirmez l’expédition lorsque le colis a été déposé.'));}
   else actions.append(el('h2','','Mettre à jour la livraison'));
   const form=el('form'),fieldset=el('fieldset');fieldset.dataset.aoMutate='';const tracking=field('Numéro de suivi Mondial Relay','aoTracking','text',o.tracking_number||'');tracking.input.required=true;tracking.input.pattern='[A-Za-z0-9-]{4,64}';tracking.input.maxLength=64;tracking.input.autocomplete='off';tracking.input.spellcheck=false;
   let select=null;fieldset.append(tracking.wrapper);
   if(o.status==='shipped'){const label=el('label','','Nouveau statut');select=el('select');select.id='aoShippingStatus';select.required=true;for(const [value,text] of [['','Choisir un statut'],['available','Disponible au point de retrait'],['delivered','Livré']]){const option=el('option','',text);option.value=value;select.append(option);}label.append(select);fieldset.append(label);}
   const label=['paid','gifted'].includes(o.status)?'Confirmer l’expédition':o.status==='available'?'Marquer comme livré':'Enregistrer le statut';fieldset.append(formButton(label));form.append(fieldset);
   form.onsubmit=e=>{e.preventDefault();if(busy||!verified||!form.reportValidity())return;const state=['paid','gifted'].includes(o.status)?'shipped':o.status==='available'?'delivered':select.value;mutate('shipping',{tracking_number:tracking.input.value.trim(),status:state},state==='delivered'?'Commande marquée comme livrée.':'Livraison mise à jour.',state==='delivered'?'history':'shipping');};actions.append(form);
   if(['paid','gifted'].includes(o.status))actions.append(action('Remettre dans les bordereaux à faire',()=>mutate('preparation',{prepared:false},'La commande est de nouveau dans les bordereaux à faire.','preparing')));
  }else{actions.append(el('h2','',o.status_label));if(o.tracking_number)contactField(actions,'Numéro de suivi',o.tracking_number);}
  controls();
 }
 async function mutate(endpoint,payload,message,destination){
  if(busy||!verified||!selected)return;const reference=selected.reference;busy=true;controls();note('aoDetailError','');note('aoDetailStatus','Enregistrement en cours…');
  try{
   const data=await request('/api/shop/admin/orders/'+encodeURIComponent(reference)+'/'+endpoint,{method:'POST',body:JSON.stringify(payload)});dirty=true;
   if(active()&&selectedRef===reference){selected=data.order;verified=true;group=stage(selected);cursors=[null];page=0;next=null;renderDetail();note('aoDetailStatus',data.duplicate||group!==destination?'Commande actualisée : '+status(selected)+'.':message);get('aoDetailStatus').scrollIntoView({block:'start',behavior:'instant'});}
  }catch(e){dirty=true;if(active()&&selectedRef===reference){verified=e.status===400;note('aoDetailStatus','');note('aoDetailError',(e.status?e.message:'La réponse n’a pas été reçue.')+(verified?'':' Actualisez la commande pour vérifier son état avant une nouvelle action.'));get('aoDetailError').scrollIntoView({block:'start',behavior:'instant'});}}
  finally{busy=false;controls();if(active()&&get('aoDetail').hidden)loadList({restore:true});}
 }
 get('aoRefresh').onclick=get('aoRetry').onclick=()=>loadList();get('aoRefreshDetail').onclick=()=>{if(!busy&&selectedRef)openDetail(selectedRef,{refresh:true});};
 get('aoPrevious').onclick=()=>{if(!loading&&!busy&&page>0){page--;loadList();scrollTo({top:0,behavior:'instant'});}};
 get('aoNext').onclick=()=>{if(!loading&&!busy&&next){cursors=cursors.slice(0,page+1);cursors.push(next);page++;loadList();scrollTo({top:0,behavior:'instant'});}};
 root.querySelectorAll('[data-order-group]').forEach(b=>b.onclick=()=>setGroup(b.dataset.orderGroup));
 const previousGo=go;go=function(id){if(id==='adminOrders'&&!me.is_admin){toast('Accès réservé à l’administration');return;}if(active()&&id!=='adminOrders'){cancelList();cancelDetail();dirty=true;}previousGo(id);if(id==='adminOrders')showList();};
 const previousBack=goBack;goBack=function(){if(active()&&!get('aoDetail').hidden){showList({restore:true});return;}previousBack();};root.querySelector('.page-back').onclick=()=>goBack();
})();
