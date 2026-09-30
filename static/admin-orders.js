/* Private order workflow. Payment and delivery transitions remain server-owned. */
(()=>{
 const root=document.getElementById('adminOrders');if(!root)return;
 const get=id=>document.getElementById(id);
 const el=(tag,cls,text)=>{const n=document.createElement(tag);if(cls)n.className=cls;if(text!==undefined)n.textContent=text;return n;};
 const button=(label,fn,cls='ao-secondary')=>{const b=el('button',cls,label);b.type='button';b.onclick=fn;return b;};
 const money=c=>new Intl.NumberFormat('fr-FR',{style:'currency',currency:'EUR'}).format((c||0)/100);
 const date=t=>new Intl.DateTimeFormat('fr-FR',{dateStyle:'medium',timeStyle:'short'}).format(new Date(t*1000));
 const countries={FR:'France',BE:'Belgique',ES:'Espagne'};
 const groups={preparing:['Bordereaux à faire','Commandes payées ou offertes : préparez les étiquettes Mondial Relay avec les coordonnées de chaque commande.','Aucun bordereau à faire.'],payments:['Paiements','Vérifiez un paiement reçu et validez-le ici, y compris par un autre moyen que PayGate.','Aucun paiement en attente ou à vérifier.'],ready:['Prêts à envoyer','Les bordereaux sont faits. Marquez les colis expédiés après leur dépôt.','Aucun colis prêt à envoyer.'],shipping:['En livraison','Colis expédiés ou disponibles au point de retrait.','Aucun colis en livraison.'],history:['Historique','Toutes les commandes payées ou offertes, avec leur état actuel.','Aucune commande payée ou offerte dans l’historique.'],expired:['Expirées','Si vous avez reçu un paiement après expiration, ouvrez la commande pour le valider. Le stock sera vérifié à nouveau.','Aucune réservation expirée.']};
 const paymentMethods={crypto:'Cryptomonnaie',bank_transfer:'Virement bancaire',paypal:'PayPal',cash:'Espèces',other:'Autre'};
 const paid=o=>!o.is_gift&&['paid','shipped','available','delivered'].includes(o.status);
 const helpPending=o=>!o.is_gift&&['awaiting_payment','payment_review'].includes(o.status)&&(o.payment_help_pending??o.payment_help_requested);
 const paymentRecord=o=>o.payment_record||{method:o.payments?.length?'crypto':'unknown',label:o.payments?.length?'Cryptomonnaie':'Moyen non renseigné',note:o.payment_note||'',revision:0};
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
  b.append(top,middle,bottom);if(helpPending(o))b.append(el('small','ao-help-request','Autre paiement demandé'));
  if(paid(o)&&paymentRecord(o).method!=='unknown')b.append(el('small','ao-payment-method-label','Paiement : '+paymentRecord(o).label));
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
 function phoneParts(value,country){
  // Formatting for a separate calling-code field, not phone-number validation.
  // An explicit international prefix always takes priority over the address.
  const compact=String(value||'').trim().replace(/[\s.()\-]/g,'');
  if(!/^(?:\+|00)?\d+$/.test(compact))return null;
  const rules={FR:{code:'33',national:/^[1-9]\d{8}$/,trunk:true},BE:{code:'32',national:/^[1-9]\d{7,8}$/,trunk:true},ES:{code:'34',national:/^[6-9]\d{8}$/,trunk:false}};
  let rule,number=compact;
  if(compact.startsWith('+')||compact.startsWith('00')){
   const international=compact.replace(/^(?:\+|00)/,'');
   rule=Object.values(rules).find(r=>international.startsWith(r.code));
   if(!rule)return null;number=international.slice(rule.code.length);
  }else rule=rules[country];
  if(!rule)return null;
  if(rule.trunk&&number.startsWith('0'))number=number.slice(1);
  return rule.national.test(number)?{prefix:'+'+rule.code,number}:null;
 }
 function phoneField(host,contact){
  const parts=phoneParts(contact.phone,contact.country);
  if(!parts){contactField(host,'Téléphone',contact.phone);return;}
  const item=el('div','ao-contact-field ao-phone-field'),text=el('div');text.append(el('span','','Téléphone'));
  const number=el('div','ao-phone-number'),prefix=el('span','ao-phone-prefix',parts.prefix);
  prefix.setAttribute('aria-label','Indicatif '+parts.prefix);number.append(prefix,el('strong','',parts.number));
  text.append(number,el('small','ao-phone-hint','Sélectionnez '+parts.prefix+' dans Mondial Relay. Copie du numéro seul.'),el('small','ao-phone-original','Saisi : '+contact.phone));
  const b=button('Copier',()=>copy(parts.number),'ao-copy');b.setAttribute('aria-label','Copier le téléphone sans indicatif');item.append(text,b);host.append(item);
 }
 function field(label,id,type='text',value=''){
  const wrapper=el('label','',label),input=el('input');input.id=id;input.type=type;input.value=value;wrapper.append(input);return {wrapper,input};
 }
 function action(label,fn,primary=false){const b=button(label,fn,primary?'ao-primary':'ao-secondary');b.dataset.aoMutate='';return b;}
 function formButton(label){const b=el('button','ao-primary',label);b.type='submit';return b;}
 function methodField(id,value){
  const wrapper=el('label','','Moyen de paiement'),input=el('select');input.id=id;input.required=true;
  const empty=el('option','','Choisir le moyen utilisé');empty.value='';input.append(empty);
  for(const [code,label] of Object.entries(paymentMethods)){const option=el('option','',label);option.value=code;input.append(option);}
  input.value=Object.prototype.hasOwnProperty.call(paymentMethods,value)?value:'';wrapper.append(input);return {wrapper,input};
 }
 function paymentEditor(o){
  const record=paymentRecord(o),card=el('section','ao-card ao-payment-record');
  card.append(el('h2','','Paiement validé'),el('p','ao-method-value',record.label||'Moyen non renseigné'));
  if(record.note)card.append(el('p','ao-record-note',record.note));
  if(record.recorded_at)card.append(el('p','ao-muted','Moyen enregistré le '+date(record.recorded_at)));
  const editor=el('details','ao-payment-editor');editor.id='aoEditPayment';editor.append(el('summary','','Modifier le moyen de paiement'),el('p','ao-muted','Précisez comment cette commande a été payée. Le montant, les points et le chiffre d’affaires restent inchangés.'));
  const form=el('form'),fieldset=el('fieldset');fieldset.dataset.aoMutate='';
  const method=methodField('aoEditMethod',record.method),reference=field('Note / référence','aoEditNote','text',record.note||'');
  reference.input.required=true;reference.input.minLength=3;reference.input.maxLength=300;reference.input.placeholder='Ex. Reçu en crypto via PayGate';
  fieldset.append(method.wrapper,reference.wrapper,formButton('Enregistrer le moyen de paiement'));form.append(fieldset);editor.append(form);card.append(editor);
  form.onsubmit=e=>{e.preventDefault();if(busy||!verified||!form.reportValidity())return;mutate('payment-method',{payment_method:method.input.value,note:reference.input.value.trim(),expected_revision:record.revision},'Moyen de paiement mis à jour.',stage(o));};
  return card;
 }
 function confirmationForm(o,host){
  host.append(el('h2','',o.status==='expired'?'Paiement reçu après expiration':'Valider un paiement reçu'),el('p','ao-muted','Indiquez le moyen utilisé et le montant que vous avez réellement reçu. Vous pouvez valider vous-même, sans attendre de confirmation de PayGate.'));
  if(o.status==='expired')host.append(el('p','ao-late-payment','La réservation a expiré. Le paiement ne pourra être validé que si les produits et les points utilisés sont encore disponibles.'));
  const form=el('form'),fieldset=el('fieldset');fieldset.dataset.aoMutate='';
  const method=methodField('aoPaymentMethod',o.payments?.length?'crypto':''),amount=field('Montant total reçu (€)','aoReceived'),reference=field('Note / référence','aoPaymentNote');
  amount.input.inputMode='decimal';amount.input.required=true;amount.input.placeholder='Montant vérifié en euros';reference.input.required=true;reference.input.minLength=3;reference.input.maxLength=300;reference.input.placeholder='Ex. Virement reçu sur Revolut';
  fieldset.append(method.wrapper,amount.wrapper,reference.wrapper,formButton('Valider le paiement'));form.append(fieldset);
  form.onsubmit=e=>{e.preventDefault();if(busy||!verified||!form.reportValidity())return;const value=amount.input.value.trim().replace(',','.');if(!/^\d+(?:\.\d{1,2})?$/.test(value)){note('aoDetailError','Indiquez un montant en euros avec au maximum deux décimales.');get('aoDetailError').scrollIntoView({block:'start',behavior:'instant'});return;}
   const [euros,cents='']=value.split('.'),total=Number(euros)*100+Number(cents.padEnd(2,'0'));
   if(!Number.isSafeInteger(total)||total!==o.total_cents){note('aoDetailError','Le montant reçu doit correspondre au total de la commande : '+money(o.total_cents)+'.');get('aoDetailError').scrollIntoView({block:'start',behavior:'instant'});return;}
   mutate('confirm-payment',{confirmed_total_cents:total,payment_method:method.input.value,note:reference.input.value.trim()},'Paiement validé. Le bordereau est à faire.','preparing');};host.append(form);
 }
 function renderDetail(){
  const o=selected,host=get('aoDetailBody');host.replaceChildren();
  const header=el('div','ao-detail-heading');header.append(el('span','ao-badge ao-status-'+o.status,status(o)));
  if(o.is_gift)header.append(el('span','gift-order-badge','Cadeau · produit et livraison offerts'));
  const title=el('h1','',person(o));title.tabIndex=-1;header.append(title,el('p','ao-muted',o.reference+' · '+date(o.created_at)));host.append(header);
  const contact=el('section','ao-card');contact.append(el('h2','','Coordonnées de livraison'));
  const c=o.contact,address=[c.address,c.address_extra,[c.postal_code,c.city].filter(Boolean).join(' '),countries[c.country]||c.country].filter(Boolean).join('\n');
  contact.append(button('Copier toutes les coordonnées',()=>copy(person(o)+'\n'+address+'\n'+c.email+'\n'+c.phone),'ao-secondary ao-copy-all'));
  contactField(contact,'Prénom',c.first_name);contactField(contact,'Nom',c.last_name);contactField(contact,'Adresse',address);contactField(contact,'Email',c.email);phoneField(contact,c);
  if(o.username)contactField(contact,'Pseudo Telegram','@'+o.username);host.append(contact);
  const contents=el('section','ao-card');contents.append(el('h2','','Contenu de la commande'));
  for(const line of o.lines){const item=el('div','ao-product-line'),label=el('div');label.append(el('b','',line.name),el('small','',(line.format?line.format+' · ':'')+'Quantité '+line.quantity));item.append(label,el('strong','',money(line.line_cents)));contents.append(item);}
  for(const [label,amount] of [['Produits',o.subtotal_cents],...(o.discount_cents?[['Réduction',-o.discount_cents]]:[]),['Livraison',o.shipping_cents],['Total de la commande',o.total_cents]]){const line=el('div','ao-total');line.append(el('span','',label),el('strong','',money(amount)));contents.append(line);}host.append(contents);
  if(helpPending(o)){const help=el('section','ao-card ao-callout');help.append(el('h2','','Autre paiement demandé'),el('p','',o.status==='awaiting_payment'?'Client à recontacter. S’il a déjà payé, validez son paiement ci-dessous.':'Vérifiez le moyen finalement utilisé, puis validez le paiement ci-dessous.'));
   const username=typeof o.username==='string'&&/^[A-Za-z0-9_]{5,32}$/.test(o.username)?o.username:null,id=String(o.telegram_id||'');
   if(username||/^[0-9]+$/.test(id)){const a=el('a','ao-secondary','Contacter sur Telegram ↗');a.href=username?'https://t.me/'+username:'tg://user?id='+id;a.target='_blank';a.rel='noopener noreferrer';help.append(a);}host.append(help);
  }
  if(paid(o))host.append(paymentEditor(o));
  const payment=el('details','ao-card ao-payment-proof');payment.append(el('summary','',o.is_gift?'Commande offerte':'Détails du paiement'));
  for(const p of o.payments||[])payment.append(el('p','ao-evidence','Reçu : '+p.amount+' '+p.coin+'\nVersé : '+p.forwarded_amount+'\nTransaction : '+p.transaction_id));
  if(o.payment_note&&!paid(o))payment.append(el('p','',o.payment_note));if(!o.payment_note&&!o.payments?.length)payment.append(el('p','ao-muted',o.is_gift?'Produit et livraison offerts. Aucun paiement à encaisser.':paid(o)?'Aucune transaction automatique enregistrée.':'Aucune transaction automatique enregistrée. Vous pouvez valider un paiement reçu avec le formulaire ci-dessous.'));
  if(o.payment_help_requested&&!helpPending(o))payment.append(el('p','ao-muted','Historique : une demande d’autre moyen de paiement avait été enregistrée.'));
  host.append(payment);
  const actions=el('section','ao-card ao-workflow');host.append(actions);
  if(!o.is_gift&&['awaiting_payment','payment_review','expired'].includes(o.status)){
   confirmationForm(o,actions);
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
