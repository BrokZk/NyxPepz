/* Private sales totals. Amounts and payment dates are calculated by the server. */
(()=>{
 const root=document.getElementById('adminSales');if(!root)return;
 const get=id=>document.getElementById(id);
 const money=c=>new Intl.NumberFormat('fr-FR',{style:'currency',currency:'EUR'}).format(c/100);
 const formatDate=(t,options)=>new Intl.DateTimeFormat('fr-FR',{timeZone:'Europe/Paris',...options}).format(new Date(t*1000));
 const active=()=>root.classList.contains('active');
 let period='all',sequence=0,controller=null,page=1;
 function renderAccounting(data){
  const m=data.metrics;
  get('asGross').textContent=money(m.gross_cents);
  get('asFees').textContent=m.verified_orders?money(m.fee_cents):'Indisponibles';
  get('asNet').textContent=m.verified_orders?money(m.net_verified_cents):'Indisponible';
  get('asCoverage').textContent=`${m.verified_orders} / ${m.orders} commandes avec net vérifié. Brut sans net vérifiable : ${money(m.unavailable_gross_cents)}. Les montants indisponibles ne sont pas comptés comme zéro.`;
  function groups(id,title,entries){
   const root=get(id);root.replaceChildren();const h=document.createElement('h3');h.textContent=title;root.append(h);
   for(const [label,item] of Object.entries(entries)){const p=document.createElement('p');p.textContent=`${label} : brut ${money(item.gross_cents)} · net vérifié ${item.verified_orders?money(item.net_verified_cents):'indisponible'} (${item.verified_orders}/${item.orders})`;root.append(p);}
  }
  groups('asMethods','Moyens de paiement',{'Crypto':data.methods.crypto,'Autres moyens':data.methods.other,'Non renseigné':data.methods.unknown});
  groups('asProviders','Prestataires traçables',data.providers);
  const list=get('asPaymentOrders');list.replaceChildren();
  for(const order of data.orders){
   const details=document.createElement('details'),summary=document.createElement('summary');
   summary.textContent=`${order.reference} · brut ${money(order.gross_cents)} · ${order.net_is_verified?money(order.net_cents):order.net_label}`;details.append(summary);
   const p=document.createElement('p');p.textContent=`Moyen : ${order.payment_method} · Prestataire : ${order.payment_provider||'Non traçable'} · Frais : ${order.net_is_verified?money(order.fee_cents):'indisponibles'}`;details.append(p);
   const proof=document.createElement('pre');proof.style.whiteSpace='pre-wrap';proof.style.overflowWrap='anywhere';details.append(proof);
   details.addEventListener('toggle',async()=>{if(!details.open||proof.textContent)return;proof.textContent='Chargement…';try{const r=await fetch('/api/shop/admin/orders/'+encodeURIComponent(order.reference)+'/accounting',{cache:'no-store'});const d=await r.json();if(!r.ok)throw Error(d.error);const p=d.payment;const lines=[p.paid_at?'Paiement validé le '+formatDate(p.paid_at,{day:'2-digit',month:'2-digit',year:'numeric'}):'Date historique indisponible',p.evidence||''];if(d.receipts.length){for(const receipt of d.receipts)lines.push('Crypto : '+receipt.coin,'Reçu : '+receipt.value_coin,'Transféré au marchand : '+receipt.merchant_settled_coin,'Différence en crypto : '+receipt.settlement_difference_coin,'Transaction entrante : '+receipt.txid_in,'Transaction sortante : '+(receipt.txid_out||'indisponible'));}else if(p.coin){lines.push('Ancienne preuve : '+p.coin,'Reçu : '+(p.value_coin||'indisponible'),'Transaction : '+(p.txid_in||p.txid_out||'indisponible'));}proof.textContent=lines.filter(Boolean).join('\n');}catch(e){proof.textContent=e.message;}});
   list.append(details);
  }
  get('asPage').textContent=` ${data.page} / ${Math.max(1,data.pages)} `;get('asPrevious').disabled=page<=1;get('asNext').disabled=page>=data.pages;
 }
 function cancel(){sequence++;controller?.abort();}
 function periodLabel(data){
  if(data.period==='all')return 'Depuis la première commande dans l’app';
  if(data.period==='today')return formatDate(data.generated_at,{day:'numeric',month:'long',year:'numeric'});
  if(data.period==='month')return formatDate(data.generated_at,{month:'long',year:'numeric'});
  return 'Année '+formatDate(data.generated_at,{year:'numeric'});
 }
 function render(data){
  const m=data.metrics;
  get('asProducts').textContent=get('asProductsDetail').textContent=money(m.products_cents);
  get('asShipping').textContent=money(m.shipping_cents);
  get('asTotal').textContent=money(m.total_cents);
  get('asOrders').textContent=new Intl.NumberFormat('fr-FR').format(m.orders);
  get('asAverage').textContent=money(m.average_cents);
  get('asDiscounts').textContent=money(m.discount_cents);
  get('asPeriodLabel').textContent=periodLabel(data);
  get('asEmpty').hidden=m.orders!==0;
  get('asUndated').hidden=!data.undated_orders;
  if(data.undated_orders)get('asUndated').textContent=data.undated_orders+' commande'+(data.undated_orders===1?' payée n’a':'s payées n’ont')+' pas de date de validation enregistrée. '+(data.undated_orders===1?'Elle est incluse':'Elles sont incluses')+' dans « Tout », mais pas dans les autres périodes.';
  get('asUpdated').textContent='Actualisé le '+formatDate(data.generated_at,{day:'2-digit',month:'2-digit',year:'numeric',hour:'2-digit',minute:'2-digit'})+' · heure de Paris';
  get('asResults').hidden=false;
 }
 async function load(){
  cancel();const seq=sequence;controller=new AbortController();const currentController=controller;
  get('asResults').hidden=true;get('asUpdated').textContent='';get('asError').hidden=true;get('asRetry').hidden=true;
  get('asLoading').hidden=false;root.setAttribute('aria-busy','true');get('asRefresh').disabled=true;
  root.querySelectorAll('[data-sales-period]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.salesPeriod===period)));
  let timedOut=false;const timer=setTimeout(()=>{timedOut=true;currentController.abort();},15000);
  try{
   const [response,accounting]=await Promise.all([fetch('/api/shop/admin/sales?period='+encodeURIComponent(period),{credentials:'same-origin',cache:'no-store',signal:currentController.signal}),fetch('/api/shop/admin/sales/real?period='+encodeURIComponent(period)+'&page='+page,{credentials:'same-origin',cache:'no-store',signal:currentController.signal})]);
   const data=await response.json().catch(()=>({}));
   if(seq!==sequence||!active())return;
   if(!response.ok)throw Error(data.error||'Les ventes ne sont pas disponibles pour le moment.');
   if(data.period!==period||!data.metrics||!['orders','products_cents','shipping_cents','total_cents','discount_cents','average_cents'].every(k=>Number.isSafeInteger(data.metrics[k])&&data.metrics[k]>=0)||!Number.isFinite(data.generated_at))throw Error('Les montants n’ont pas pu être vérifiés. Réessayez.');
   const financial=await accounting.json();if(seq!==sequence||!active())return;if(!accounting.ok)throw Error(financial.error||'Comptabilité indisponible');
   renderAccounting(financial);render(data);
  }catch(error){
   if(seq!==sequence||!active()||(error.name==='AbortError'&&!timedOut))return;
   get('asError').textContent=timedOut?'Le chargement prend trop de temps. Réessayez.':error.name==='TypeError'?'Connexion interrompue. Réessayez pour afficher vos ventes.':error.message;
   get('asError').hidden=false;get('asRetry').hidden=false;
  }finally{
   clearTimeout(timer);
   if(seq===sequence){get('asLoading').hidden=true;root.setAttribute('aria-busy','false');get('asRefresh').disabled=false;}
  }
 }
 root.querySelectorAll('[data-sales-period]').forEach(b=>b.onclick=()=>{period=b.dataset.salesPeriod;page=1;load();});
 get('asPrevious').onclick=()=>{page--;load();};get('asNext').onclick=()=>{page++;load();};
 get('asRefresh').onclick=get('asRetry').onclick=()=>load();
 const previousGo=go;go=function(id){
  if(id==='adminSales'&&!me.is_admin){toast('Accès réservé à l’administration');return;}
  if(active()&&id!=='adminSales'){cancel();get('asResults').hidden=true;}
  previousGo(id);if(id==='adminSales')load();
 };
 root.querySelector('.page-back').textContent='‹ Administration';
 root.querySelector('.page-back').onclick=()=>goBack();
})();
