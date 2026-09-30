/* Private, bounded user directory. Mutations retain the existing server rules. */
(()=>{
 const root=document.getElementById('adminPeople');if(!root)return;
 const get=id=>document.getElementById(id);
 const el=(tag,cls,text)=>{const n=document.createElement(tag);if(cls)n.className=cls;if(text!==undefined)n.textContent=text;return n;};
 const button=(label,fn,cls='au-secondary')=>{const b=el('button',cls,label);b.type='button';b.onclick=fn;return b;};
 const number=n=>new Intl.NumberFormat('fr-FR').format(n);
 let page=1,pages=1,total=0,query='',sort='recent',selected=null,selectedId=null;
 let listVersion=0,detailVersion=0,listController,detailController,timer;
 let loading=false,busy=false,verified=false,dirty=true,loaded=false,listScroll=0,returnId=null;
 function active(){return root.classList.contains('active');}
 function notice(id,text){const n=get(id);n.textContent=text;n.hidden=!text;}
 async function request(url,options={}){
  const response=await fetch(url,{credentials:'same-origin',cache:'no-store',...options,
   headers:{'Content-Type':'application/json',...(options.headers||{})}});
  const data=await response.json().catch(()=>({}));
  if(!response.ok){const error=Error(data.error||'Impossible de charger les utilisateurs.');error.status=response.status;throw error;}
  return data;
 }
 function cancelList(){clearTimeout(timer);listVersion++;listController?.abort();}
 function cancelDetail(){detailVersion++;detailController?.abort();}
 function navigation(){
  get('auPrevious').disabled=loading||page<=1;get('auNext').disabled=loading||page>=pages;
  get('auPage').textContent='Page '+page+' sur '+pages;
  get('auPagination').hidden=!loaded||total===0;
 }
 function prepareList(){
  loading=true;notice('auListError','');get('auRetry').hidden=true;
  get('auList').replaceChildren();get('auResults').textContent='Recherche en cours…';
  get('auList').setAttribute('aria-busy','true');navigation();
 }
 function row(user){
  const item=el('li'),b=button('',()=>openUser(user.id),'au-person');b.dataset.userId=user.id;
  b.disabled=busy;
  const avatar=el('span','au-avatar',Array.from(user.name.trim()||'M').slice(0,1).join('').toLocaleUpperCase('fr-FR'));
  avatar.setAttribute('aria-hidden','true');
  const label=el('span','au-person-label');label.append(el('strong','',user.name));
  label.append(el('small','',user.username?'@'+user.username:'ID Telegram · '+user.telegram_id));
  const balance=el('span','au-person-points');balance.append(el('b','',number(user.points)),el('small','','points'));
  const arrow=el('span','au-arrow','›');arrow.setAttribute('aria-hidden','true');
  b.setAttribute('aria-label','Ouvrir la fiche de '+user.name+', ID Telegram '+user.telegram_id+', '+number(user.points)+' points');
  b.append(avatar,label,balance,arrow);item.append(b);return item;
 }
 async function loadList({restore=false}={}){
  cancelList();const version=listVersion;listController=new AbortController();prepareList();
  try{
   const params=new URLSearchParams({q:query,page:String(page),sort});
   const data=await request('/api/admin/users/search?'+params,{signal:listController.signal});
   if(version!==listVersion||!active())return;
   page=data.page;pages=data.pages;total=data.total;loaded=true;dirty=false;
   get('auTotal').textContent=number(data.total_users)+' utilisateur'+(data.total_users===1?'':'s');
   get('auResults').textContent=total?(number((page-1)*data.page_size+1)+'–'+number((page-1)*data.page_size+data.users.length)+' sur '+number(total)+(query?' résultat'+(total===1?'':'s'):'')):(query?'Aucun utilisateur trouvé.':'Aucun utilisateur inscrit.');
   get('auList').replaceChildren(...data.users.map(row));
   if(!data.users.length){const empty=el('li','au-empty',query?'Essaie un autre nom, un pseudo ou son ID Telegram.':'Les comptes apparaîtront ici après leur première ouverture de l’application.');get('auList').append(empty);}
   if(restore)restoreListPosition();
  }catch(error){
   if(error.name==='AbortError'||version!==listVersion||!active())return;
   dirty=true;get('auResults').textContent='Liste indisponible';
   notice('auListError',error.message);get('auRetry').hidden=false;
  }finally{if(version===listVersion){loading=false;get('auList').setAttribute('aria-busy','false');navigation();}}
 }
 function search(){
  cancelList();query=get('auSearch').value.trim();page=1;dirty=true;
  get('auClear').hidden=!get('auSearch').value;prepareList();
  timer=setTimeout(()=>loadList(),250);
 }
 function restoreListPosition(){
  scrollTo({top:listScroll,behavior:'instant'});
  if(returnId){const target=get('auList').querySelector('[data-user-id="'+returnId+'"]');target?.focus({preventScroll:true});}
 }
 function showList({restore=false}={}){
  cancelDetail();selected=null;selectedId=null;verified=false;
  get('auDirectory').hidden=false;get('auDetail').hidden=true;
  root.querySelector('.page-back').textContent='‹ Administration';
  if(dirty||!loaded)loadList({restore});else if(restore)restoreListPosition();
 }
 async function openUser(id,{refresh=false}={}){
  if(busy){toast('Enregistrement en cours…');return;}
  if(!refresh){listScroll=window.scrollY;returnId=id;}
  cancelDetail();const version=detailVersion;detailController=new AbortController();
  selectedId=id;selected=null;verified=false;
  get('auDirectory').hidden=true;get('auDetail').hidden=false;
  root.querySelector('.page-back').textContent='‹ Utilisateurs';
  get('auUserCard').replaceChildren(el('p','au-help','Chargement de la fiche…'));
  get('auPointsCard').hidden=true;get('auAccountActions').hidden=true;
  get('auRefreshUser').disabled=true;notice('auDetailError','');notice('auDetailStatus','');
  if(!refresh)scrollTo({top:0,behavior:'instant'});
  try{
   const user=await request('/api/admin/users/'+id,{signal:detailController.signal});
   if(version!==detailVersion||!active())return;
   selected=user;verified=true;renderUser();
   if(!refresh)get('auUserCard').querySelector('h2').focus({preventScroll:true});
  }catch(error){
   if(error.name==='AbortError'||version!==detailVersion||!active())return;
   get('auUserCard').replaceChildren(el('p','au-help',error.status===404?'Ce compte n’existe plus.':'La fiche n’a pas pu être chargée.'));
   if(error.status===404)dirty=true;
   notice('auDetailError',error.message);
  }finally{if(version===detailVersion)get('auRefreshUser').disabled=busy;}
 }
 function renderUser(){
  if(!selected)return;
  const card=get('auUserCard');card.replaceChildren();
  const badge=el('span','au-avatar au-avatar-large',Array.from(selected.name.trim()||'M').slice(0,1).join('').toLocaleUpperCase('fr-FR'));badge.setAttribute('aria-hidden','true');
  const heading=el('div','au-identity'),title=el('h2','',selected.name);title.tabIndex=-1;heading.append(title);
  if(selected.username)heading.append(el('p','au-handle','@'+selected.username));
  heading.append(el('p','au-id','ID Telegram · '+selected.telegram_id));
  if(selected.is_self)heading.append(el('span','au-self','Votre compte'));
  card.append(badge,heading);
  get('auBalance').textContent=number(selected.points);get('auPointsCard').hidden=false;
  get('auAccountActions').hidden=false;get('auAccountActions').open=false;
  get('auDeleteUser').hidden=selected.is_self;
  get('auDeleteHint').textContent=selected.is_self?'Vous ne pouvez pas supprimer votre propre compte.':'La suppression est définitive. Les comptes liés à des commandes, un parrainage ou un espace ambassadeur sont protégés.';
  controls();
 }
 function controls(){
  get('auList').querySelectorAll('.au-person').forEach(b=>{b.disabled=busy;});
  root.querySelectorAll('[data-au-delta]').forEach(b=>{b.disabled=busy||!verified||!selected||(Number(b.dataset.auDelta)<0&&selected.points===0);});
  get('auDeleteUser').disabled=busy||!verified||!selected;
  get('auRefreshUser').disabled=busy;
 }
 function refreshSelf(user){
  if(!user.is_self)return;
  me.loyalty_points=user.points;
  ['points','profilePoints'].forEach(id=>{get(id).textContent=user.points;});
  get('loyaltyBalance').textContent=number(user.points)+' points';
  const next=[150,300,500,750].find(points=>points>user.points);
  const hint=document.querySelector('.loyal small');
  if(hint){
   const remaining=el('span','',next?String(next-user.points):'Récompenses disponibles');remaining.id='remaining';
   hint.replaceChildren(...(next?['Encore ',remaining,' points jusqu’au prochain palier']:[remaining,' · Voir mes avantages']));
  }
  get('progressbar').style.width=Math.min(100,user.points/(next||750)*100)+'%';
  // The shop refreshes its full reward options on opening the reward screen.
 }
 async function adjust(delta){
  if(busy||!verified||!selected||![-10,-1,1,10].includes(delta))return;
  const user={...selected};busy=true;controls();notice('auDetailError','');notice('auDetailStatus','Mise à jour en cours…');
  try{
   const result=await request('/api/admin/users/'+user.id+'/points',{method:'PATCH',body:JSON.stringify({delta})});
   dirty=true;user.points=result.points;refreshSelf(user);
   if(selectedId===user.id&&active()){
    selected=user;verified=true;get('auBalance').textContent=number(user.points);
    notice('auDetailStatus','Solde enregistré : '+number(user.points)+' points.');
   }
   loadHomeLeaders();loadLeaders();
  }catch(error){
   dirty=true;
   if(selectedId===user.id&&active()){
    verified=false;notice('auDetailStatus','');
    // Do not replay a points change after an ambiguous network failure.
    notice('auDetailError',(error.status?error.message:'La réponse n’a pas été reçue.')+' Actualise la fiche pour vérifier le solde avant une nouvelle modification.');
   }
  }finally{busy=false;controls();if(active()&&get('auDetail').hidden)loadList({restore:true});}
 }
 async function removeUser(){
  if(busy||!verified||!selected||selected.is_self)return;
  const user={...selected};let returnedToList=false;
  if(!confirm('Supprimer définitivement le compte de '+user.name+' ?\nID Telegram : '+user.telegram_id+'\nCette action est irréversible.'))return;
  busy=true;controls();notice('auDetailError','');notice('auDetailStatus','Suppression en cours…');
  try{
   await request('/api/admin/users/'+user.id,{method:'DELETE'});dirty=true;
   if(selectedId===user.id&&active()){listScroll=0;showList();returnedToList=true;scrollTo({top:0,behavior:'instant'});}
   toast('Compte de '+user.name+' supprimé');loadHomeLeaders();loadLeaders();
  }catch(error){
   dirty=true;
   if(selectedId===user.id&&active()){
    notice('auDetailStatus','');
    if(!error.status||error.status===404||error.status>=500){verified=false;notice('auDetailError',error.message+' Actualise la fiche pour vérifier son état.');}
    else notice('auDetailError',error.message);
   }
  }finally{busy=false;controls();if(!returnedToList&&active()&&get('auDetail').hidden)loadList({restore:true});}
 }
 get('auSearch').oninput=search;
 get('auSearchForm').onsubmit=e=>{e.preventDefault();clearTimeout(timer);query=get('auSearch').value.trim();page=1;get('auSearch').blur();loadList();};
 get('auClear').onclick=()=>{get('auSearch').value='';get('auClear').hidden=true;query='';page=1;loadList();get('auSearch').focus();};
 get('auSort').onchange=()=>{sort=get('auSort').value;page=1;loadList();};
 get('auRetry').onclick=get('auRefresh').onclick=()=>loadList();
 get('auPrevious').onclick=()=>{if(!loading&&page>1){page--;loadList();scrollTo({top:0,behavior:'instant'});}};
 get('auNext').onclick=()=>{if(!loading&&page<pages){page++;loadList();scrollTo({top:0,behavior:'instant'});}};
 root.querySelectorAll('[data-au-delta]').forEach(b=>b.onclick=()=>adjust(Number(b.dataset.auDelta)));
 get('auRefreshUser').onclick=()=>{if(!busy&&selectedId)openUser(selectedId,{refresh:true});};
 get('auDeleteUser').onclick=removeUser;
 const originalGo=go;go=function(id){
  if(id==='adminPeople'&&!me.is_admin){toast('Accès réservé à l’administration');return;}
  if(active()&&id!=='adminPeople'){cancelList();cancelDetail();dirty=true;}
  originalGo(id);
  if(id==='adminPeople')showList();
 };
 const originalBack=goBack;goBack=function(){
  if(active()&&!get('auDetail').hidden){showList({restore:true});return;}
  originalBack();
 };
 root.querySelector('.page-back').onclick=()=>goBack();
})();
