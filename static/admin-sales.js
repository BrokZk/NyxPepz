/* Private sales totals. Amounts and payment dates are calculated by the server. */
(()=>{
 const root=document.getElementById('adminSales');if(!root)return;
 const get=id=>document.getElementById(id);
 const money=c=>new Intl.NumberFormat('fr-FR',{style:'currency',currency:'EUR'}).format(c/100);
 const formatDate=(t,options)=>new Intl.DateTimeFormat('fr-FR',{timeZone:'Europe/Paris',...options}).format(new Date(t*1000));
 const active=()=>root.classList.contains('active');
 let period='all',sequence=0,controller=null;
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
   const response=await fetch('/api/shop/admin/sales?period='+encodeURIComponent(period),{credentials:'same-origin',cache:'no-store',signal:currentController.signal});
   const data=await response.json().catch(()=>({}));
   if(seq!==sequence||!active())return;
   if(!response.ok)throw Error(data.error||'Les ventes ne sont pas disponibles pour le moment.');
   if(data.period!==period||!data.metrics||!['orders','products_cents','shipping_cents','total_cents','discount_cents','average_cents'].every(k=>Number.isSafeInteger(data.metrics[k])&&data.metrics[k]>=0)||!Number.isFinite(data.generated_at))throw Error('Les montants n’ont pas pu être vérifiés. Réessayez.');
   render(data);
  }catch(error){
   if(seq!==sequence||!active()||(error.name==='AbortError'&&!timedOut))return;
   get('asError').textContent=timedOut?'Le chargement prend trop de temps. Réessayez.':error.name==='TypeError'?'Connexion interrompue. Réessayez pour afficher vos ventes.':error.message;
   get('asError').hidden=false;get('asRetry').hidden=false;
  }finally{
   clearTimeout(timer);
   if(seq===sequence){get('asLoading').hidden=true;root.setAttribute('aria-busy','false');get('asRefresh').disabled=false;}
  }
 }
 root.querySelectorAll('[data-sales-period]').forEach(b=>b.onclick=()=>{period=b.dataset.salesPeriod;load();});
 get('asRefresh').onclick=get('asRetry').onclick=()=>load();
 const previousGo=go;go=function(id){
  if(id==='adminSales'&&!me.is_admin){toast('Accès réservé à l’administration');return;}
  if(active()&&id!=='adminSales'){cancel();get('asResults').hidden=true;}
  previousGo(id);if(id==='adminSales')load();
 };
 root.querySelector('.page-back').textContent='‹ Administration';
 root.querySelector('.page-back').onclick=()=>goBack();
})();
