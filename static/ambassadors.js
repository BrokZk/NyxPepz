(()=>{
 const get=id=>document.getElementById(id),money=c=>new Intl.NumberFormat('fr-FR',{style:'currency',currency:'EUR'}).format(c/100);
 const el=(tag,cls,text)=>{const n=document.createElement(tag);if(cls)n.className=cls;if(text!==undefined)n.textContent=text;return n;};
 const button=(label,fn,cls='shop-secondary')=>{const n=el('button',cls,label);n.type='button';n.onclick=fn;return n;};
 const labels={pending:'À décider',first:'Première commande uniquement',all:'Toutes les commandes suivantes'};
 const states={approved:'Validée',pending:'En attente de règle',excluded:'Hors règle',void:'Annulée'};
 let selected=null,busy=false,adminLoad=0,ownLoad=0;
 const notice=(id,text)=>get(id).textContent=text;
 function input(form,label,type,id,value=''){const l=el('label','',label),n=el('input');n.type=type;n.id=id;n.value=value;l.append(n);form.append(l);return n;}
 function stats(data){
  const grid=el('div','amb-stats');
  for(const [title,key] of [['Disponible à verser','available_cents'],['Commissions validées','earned_cents'],['Déjà versé','paid_cents'],['En attente de règle','pending_cents'],['Ventes apportées · produits','sales_cents']]){const card=el('article','card amb-stat');card.append(el('small','',title),el('strong','',money(data[key])));grid.append(card);}
  if(data.adjustment_cents)grid.append(el('p','shop-notice','Ajustement restant à compenser : '+money(data.adjustment_cents)+'. Une commission a été annulée après versement.'));
  return grid;
 }
 function history(data,admin=false){
  const wrap=el('div','amb-history');wrap.append(el('h2','','Ventes et commissions'));
  wrap.append(el('p','journal-caption','Les 500 écritures les plus récentes sont affichées. Les soldes incluent tout l’historique.'));
  if(!data.commissions.length)wrap.append(el('p','card journal-empty','Aucune commission pour le moment.'));
  for(const c of data.commissions){const row=el('article','card amb-row');row.append(el('span','journal-badge '+(c.status==='approved'?'done':'planned'),states[c.status]),el('h3','',c.sale+' · '+new Date(c.date*1000).toLocaleDateString('fr-FR')),el('p','','Produits payés : '+money(c.basis_cents)),el('strong','','Commission à 10 % : '+money(c.amount_cents)),el('p','journal-caption',c.first_order?'Premier achat du client':'Commande suivante'));if(c.reason)row.append(el('p','journal-caption',c.reason));
   if(admin&&c.order_reference)row.append(el('p','journal-caption','Commande : '+c.order_reference));if(admin&&c.status!=='void')row.append(button('Annuler cette commission',()=>voidCommission(data.ambassador.id,c.id),'journal-delete'));wrap.append(row);
  }
  wrap.append(el('h2','','Versements enregistrés'));
  if(!data.payouts.length)wrap.append(el('p','card journal-empty','Aucun versement enregistré.'));
  for(const p of data.payouts){const row=el('article','card amb-row');row.append(el('strong','',money(p.amount_cents)),el('p','','Mois concerné : '+p.period),el('p','journal-caption','Versé le '+new Date(p.date+'T12:00:00').toLocaleDateString('fr-FR')),el('p','journal-caption',p.reference));wrap.append(row);}
  return wrap;
 }
 function header(data){const a=data.ambassador,box=el('div','card amb-row');box.append(el('h2','',a.name),el('p','','Code personnel : '+a.code),el('p','journal-caption','10 % des produits après réduction, hors livraison · '+data.totals.customers+' nouveau(x) client(s)'),el('p','journal-caption','Commandes suivantes : '+labels[a.mode]));return box;}
 async function loadOwn(){
  const token=++ownLoad;get('ambDashboard').replaceChildren();get('ambLogin').hidden=true;get('ambLogout').hidden=true;notice('ambNotice','Chargement…');
  try{const access=await api('/api/ambassador/access');if(token!==ownLoad)return;if(!access.member){notice('ambNotice','Cet espace est réservé aux comptes autorisés par NyxPepz.');return;}if(!access.unlocked){notice('ambNotice','');get('ambLogin').hidden=false;return;}const data=await api('/api/ambassador/dashboard');if(token!==ownLoad)return;get('ambDashboard').append(header(data),stats(data.totals),history(data));get('ambLogout').hidden=false;notice('ambNotice','');}catch(e){if(token===ownLoad)notice('ambNotice',e.message);}
 }
 get('ambLogin').onsubmit=async e=>{e.preventDefault();if(busy)return;busy=true;const b=get('ambLogin').querySelector('button');b.disabled=true;try{await api('/api/ambassador/login',{method:'POST',body:JSON.stringify({password:get('ambPassword').value})});get('ambPassword').value='';await loadOwn();}catch(e){notice('ambNotice',e.message);}finally{busy=false;b.disabled=false;}};
 get('ambRefresh').onclick=loadOwn;get('ambLogout').onclick=async()=>{try{await api('/api/ambassador/logout',{method:'POST',body:'{}'});await loadOwn();}catch(e){notice('ambNotice',e.message);}};
 async function loadAdmin(){
  const token=++adminLoad;selected=null;get('ambAdminDetail').replaceChildren();get('ambAdminList').replaceChildren();get('ambUser').replaceChildren();notice('ambAdminNotice','Chargement…');
  try{const [list,users]=await Promise.all([api('/api/admin/ambassadors'),api('/api/admin/users')]);if(token!==adminLoad)return;get('ambUser').add(new Option('Choisir un compte Telegram',''));for(const u of users)get('ambUser').add(new Option(u.name+' · Telegram '+u.telegram_id,u.id));
   for(const a of list.ambassadors){const card=el('article','card amb-row');card.dataset.ambassadorId=a.id;card.append(el('h2','',a.name),el('p','',a.code+' · '+(a.active?'Actif':'Désactivé')),el('strong','','À verser : '+money(a.totals.available_cents)),button('Ouvrir le tableau',()=>openAdmin(a.id)));get('ambAdminList').append(card);}if(!list.ambassadors.length)get('ambAdminList').append(el('p','journal-caption','Créez le premier espace ci-dessous.'));notice('ambAdminNotice','');
  }catch(e){if(token===adminLoad)notice('ambAdminNotice',e.message);}
 }
 get('ambAdminRefresh').onclick=()=>{if(!busy)loadAdmin();};
 get('ambCreate').onsubmit=async e=>{e.preventDefault();if(busy)return;busy=true;const fieldset=get('ambCreate').querySelector('fieldset');fieldset.disabled=true;try{await api('/api/admin/ambassadors',{method:'POST',body:JSON.stringify({user_id:Number(get('ambUser').value),name:get('ambName').value,code:get('ambCode').value,password:get('ambNewPassword').value})});get('ambCreate').reset();await loadAdmin();toast('Espace ambassadeur créé');}catch(e){notice('ambAdminNotice',e.message);}finally{busy=false;fieldset.disabled=false;}};
 async function change(id,data){await api('/api/admin/ambassadors/'+id,{method:'PATCH',body:JSON.stringify(data)});await openAdmin(id);}
 async function openAdmin(id){
  selected=id;const target=get('ambAdminDetail');target.replaceChildren();notice('ambAdminNotice','Chargement du tableau…');
  try{const data=await api('/api/admin/ambassadors/'+id);if(selected!==id)return;const a=data.ambassador,listCard=get('ambAdminList').querySelector(`[data-ambassador-id="${id}"]`);if(listCard){listCard.querySelector('strong').textContent='À verser : '+money(data.totals.available_cents);listCard.querySelector('p').textContent=a.code+' · '+(a.active?'Actif':'Désactivé');}target.append(button('Fermer la fiche',()=>{selected=null;target.replaceChildren();}),header(data),stats(data.totals));
   const settings=el('div','card journal-form');settings.append(el('h2','','Réglages'));
   const label=el('label','','Commandes suivantes'),select=el('select');select.id='ambMode';for(const [value,text] of Object.entries(labels))select.add(new Option(text,value));select.value=a.mode;label.append(select);settings.append(label,el('p','journal-caption','La première commande payée rapporte 10 %. La règle choisie s’applique aux commandes futures et à celles en attente. Les commissions déjà décidées restent conservées.'));
   settings.append(button('Enregistrer la règle',async()=>{if(busy)return;if(!confirm('Appliquer « '+labels[select.value]+' » ? Commissions actuellement en attente : '+money(data.totals.pending_cents)+'.'))return;busy=true;try{await change(id,{mode:select.value});}catch(e){notice('ambAdminNotice',e.message);}finally{busy=false;}}));
   settings.append(button(a.active?'Désactiver cet accès et le code':'Réactiver cet accès et le code',async()=>{if(busy)return;busy=true;try{await change(id,{active:!a.active});}catch(e){notice('ambAdminNotice',e.message);}finally{busy=false;}}));
   const passwordForm=el('form');const password=input(passwordForm,'Nouveau mot de passe','password','ambResetPassword');password.minLength=12;password.maxLength=128;password.required=true;password.autocomplete='new-password';const reset=el('button','shop-secondary','Remplacer le mot de passe');passwordForm.append(reset);passwordForm.onsubmit=async e=>{e.preventDefault();if(busy)return;busy=true;reset.disabled=true;try{await change(id,{password:password.value});toast('Mot de passe remplacé');}catch(e){notice('ambAdminNotice',e.message);}finally{busy=false;reset.disabled=false;}};settings.append(passwordForm);target.append(settings);
   const payout=el('form','card journal-form');payout.id='ambPayout';payout.append(el('h2','','Enregistrer un versement effectué'),el('p','journal-caption','Envoyez l’argent par votre moyen habituel, puis enregistrez-le ici. Ce bouton ne transfère pas d’argent.'));
   const amount=input(payout,'Montant versé (€)','text','ambPayoutAmount');amount.inputMode='decimal';amount.required=true;
   const now=new Date(),day=`${now.getFullYear()}-${String(now.getMonth()+1).padStart(2,'0')}-${String(now.getDate()).padStart(2,'0')}`;
   const period=input(payout,'Mois concerné','month','ambPayoutMonth',day.slice(0,7));period.required=true;
   const date=input(payout,'Date du versement','date','ambPayoutDate',day);date.required=true;date.max=day;
   const reference=input(payout,'Référence du versement (visible par l’ambassadeur)','text','ambPayoutReference');reference.minLength=3;reference.maxLength=160;reference.required=true;
   const confirmLabel=el('label','amb-check'),confirmed=el('input');confirmed.type='checkbox';confirmed.required=true;confirmed.id='ambPayoutConfirmed';confirmLabel.append(confirmed,document.createTextNode('Je confirme avoir déjà envoyé cette somme.'));payout.append(confirmLabel);const save=el('button','shop-primary','Enregistrer le versement');payout.append(save);const payoutKey=crypto.randomUUID();
   payout.onsubmit=async e=>{e.preventDefault();if(busy)return;busy=true;save.disabled=true;try{await api('/api/admin/ambassadors/'+id+'/payouts',{method:'POST',body:JSON.stringify({amount:amount.value,period:period.value,date:date.value,reference:reference.value,client_id:payoutKey,transfer_confirmed:confirmed.checked})});await openAdmin(id);toast('Versement enregistré');}catch(e){notice('ambAdminNotice',e.message);}finally{busy=false;save.disabled=false;}};
   target.append(payout,history(data,true));notice('ambAdminNotice','');target.scrollIntoView({block:'start'});
  }catch(e){if(selected===id)notice('ambAdminNotice',e.message);}
 }
 async function voidCommission(id,cid){if(busy)return;const reason=prompt('Motif d’annulation de la commission (remboursement, erreur…). Le motif sera visible par l’ambassadeur.');if(reason===null)return;busy=true;try{await api('/api/admin/ambassadors/'+id+'/commissions/'+cid+'/void',{method:'POST',body:JSON.stringify({reason})});await openAdmin(id);}catch(e){notice('ambAdminNotice',e.message);}finally{busy=false;}}
 const previousGo=go;go=function(id){previousGo(id);if(id==='ambassador')loadOwn();if(id==='ambassadorAdmin')loadAdmin();};
 const previousBack=goBack;get('ambassadorAdmin').querySelector('.page-back').onclick=()=>{if(selected!==null){if(!busy){selected=null;get('ambAdminDetail').replaceChildren();get('ambAdminList').scrollIntoView({block:'start'});}return;}previousBack();};
})();
