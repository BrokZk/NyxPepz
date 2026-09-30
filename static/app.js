const tg=window.Telegram?.WebApp;if(tg){tg.ready();tg.expand()}
const $=s=>document.querySelector(s),$$=s=>document.querySelectorAll(s);let activeCategory="Tous";let me={},products=[],chart,packs=[],promoIndex=0,promoTimer,promoTouchX=0;
const toast=m=>{let t=$("#toast");t.textContent=m;t.style.display="block";setTimeout(()=>t.style.display="none",2200)};
async function api(u,o={}){o.headers={"Content-Type":"application/json",...(o.headers||{})};let r=await fetch(u,o),d=await r.json().catch(()=>({}));if(!r.ok)throw Error(d.error||"Erreur");return d}
const pageTrail=[];let returningToPage=false;
function go(id){
 const target=$("#"+id);if(!target?.classList.contains('page'))return;
 const current=$('.page.active');
 if(!returningToPage&&current&&current.id!==id){
  if(id==='home')pageTrail.length=0;
  else {pageTrail.push({id:current.id,scroll:window.scrollY,category:activeCategory,query:$('#search').value});if(pageTrail.length>30)pageTrail.shift();}
 }
 $$(".page").forEach(x=>x.classList.remove("active"));target.classList.add("active");
 $$("nav button").forEach(x=>{const active=x.dataset.go===id&&(id!=="catalog"||x.hasAttribute("data-nav-primary"));x.classList.toggle("active",active);if(active)x.setAttribute("aria-current","page");else x.removeAttribute("aria-current")});
 if(id==="catalog"&&!returningToPage){$("#search").value="";renderCatalog("Tous")}
 if(id==="tracking")loadWeights();if(id==="leaderboard")loadLeaders();if(id==="admin")loadAdmin();scrollTo({top:0,behavior:'instant'});
}
function goBack(){
 const dialog=$('dialog[open]');if(dialog){dialog.close();return;}
 const page=$('.page.active');if(!page||page.id==='home')return;
 let internal;
 if(page.id==='catalog')internal=$('#filters .category-back');
 if(page.id==='protocols')internal=!$('#protocolDetail').hidden?$('#protocolDetail > button'):$('#protocolList .protocol-list-head > button');
 if(page.id==='encyclopedia'&&!$('#encyclopediaDetail').hidden)internal=$('#encyclopediaDetail > button');
 if(page.id==='admin'&&(adminProductCategory||$('#adminProductSearch').value)){
  adminProductCategory=null;$('#adminProductSearch').value='';renderAdminProducts();scrollTo({top:0,behavior:'instant'});return;
 }
 if(internal){internal.click();scrollTo({top:0,behavior:'instant'});return;}
 const previous=pageTrail.pop()||{id:'home',scroll:0};returningToPage=true;
 try{go(previous.id);if(previous.id==='catalog'){$('#search').value=previous.query||'';renderCatalog(previous.category||'Tous');}}finally{returningToPage=false;}
 scrollTo({top:previous.scroll||0,behavior:'instant'});
}
$$('.page:not(#home)').forEach(page=>{const back=document.createElement('button');back.type='button';back.className='page-back';back.textContent='‹ Retour';back.setAttribute('aria-label','Revenir en arrière');back.onclick=goBack;page.prepend(back);});
document.body.classList.add('has-page-back');
$$("[data-go]").forEach(b=>b.onclick=()=>go(b.dataset.go));
const meta={"Perte de graisse":["◯","Un corps plus sain, une meilleure sensibilité"],"Régénération":["♧","Des tissus plus forts, une récupération accélérée"],"Beauté · peau":["♙","Un éclat naturel, une régénération visible"],"Nootropiques":["◇","Clarté, concentration et équilibre"],"Performance":["ϟ","Performance et vitalité"],"Longévité":["∞","Longévité / Anti-âge"],"Libido":["♡","Bien-être et vitalité"]};
function vial(p){
 if(p.image_url==='/static/protocols/amino-pack-original.png')return `<div class="product-photo accessory-photo"><svg viewBox="665 255 647 415" role="img" aria-label="10 seringues et 10 tampons alcool"><image href="/static/protocols/amino-pack-original.png" width="1312" height="1199"/></svg></div>`;
 // Custom photos uploaded in Admin remain available. Replace the original
 // bundled catalogue artwork and missing photos with the new label template.
 if(p.image_url&&!p.image_url.startsWith("/static/"))return `<div class="product-photo"><img loading="lazy" src="${escapeHTML(p.image_url)}" alt="${escapeHTML(p.name)}"></div>`;
 const name=String(p.name||"NyxPepz").toUpperCase(),dose=String(p.format||"").trim();
 return `<div class="product-photo branded-photo"><div class="branded-vial" role="img" aria-label="Visuel ${escapeHTML(p.name)} ${escapeHTML(dose)}"><img loading="lazy" src="/static/nyx-vial.png" alt="" width="1024" height="1536"><div class="vial-print" aria-hidden="true"><span class="vial-brand"><b>Nyx</b>Pepz</span><span class="vial-rule"></span><span class="vial-name ${name.length>11?'long-name':''}">${escapeHTML(name)}</span>${dose?`<span class="vial-dose ${dose.length>10?'long-dose':''}">${escapeHTML(dose)}</span>`:''}<span class="vial-bottom-rule"></span></div></div></div>`
}
function includedSupplies(p){
 // Explicit catalogue matches keep accessories, water sold separately and
 // unknown products from inheriting a promise about their contents.
 if(p.kind!=='product'||p.cat==='Accessoires')return '';
 const normalize=value=>String(value||'').normalize('NFKD').replace(/[\u0300-\u036f]/g,'').toLowerCase().replace(/[^a-z0-9]/g,'');
 const name=normalize(p.name),dose=String(p.format||'').trim().match(/^(\d+(?:[.,]\d+)?)\s*mg$/i);
 if(name==='retatrutide'||name==='reta')return dose&&[10,15,20,30].includes(Number(dose[1].replace(',','.')))?'Eau + 5 seringues + 5 tampons alcool inclus':'';
 const withWater=['tesamorelin','cagrilintide','bpc157','wolverinestack','semax','selank','dsip','motsc','klow','klowstack','ghkcu','ahkcu','glow','glowstack','melanotan1','melanotan2','pt141'];
 return withWater.includes(name)?'Eau incluse':'';
}
async function boot(){try{await api("/api/auth/telegram",{method:"POST",body:JSON.stringify({initData:tg?.initData||""})});me=await api("/api/me");$("#hello").textContent=me.first_name||"Nyx";$("#points").textContent=me.loyalty_points;let mod=me.loyalty_points%200;$("#progressbar").style.width=Math.min(mod/2,100)+"%";$("#remaining").textContent=200-mod;$("#refpoints2").textContent=me.referral_points;$("#refcode").textContent=$("#profileCode").textContent=me.referral_code;$("#filleuls").textContent=me.filleuls;$("#profileName").textContent=me.first_name||me.username||"Membre";$("#profilePoints").textContent=me.loyalty_points;if(me.is_admin){let b=document.createElement("button");b.className="admin-fab";b.textContent="⚙ Admin";b.onclick=()=>go("admin");document.body.appendChild(b)}}catch(e){toast(e.message)}
try{products=await api("/api/catalog");await loadPacks();renderCatalog();loadHomeLeaders();loadNews()}catch(e){toast(e.message)}}
const categoryLabels={"Perte de graisse":"Perte de poids","Beauté · peau":"Beauté / Peau","Régénération":"Régénération / Réparation","Nootropiques":"Nootropiques","Performance":"Performance / GH","Longévité":"Longévité / Anti-âge"};
const categoryIcons={"Perte de graisse":"⚖️","Beauté · peau":"✨","Régénération":"💪","Nootropiques":"🧠","Performance":"⚡","Longévité":"🧬","Libido":"♡","Accessoires":"✚"};
function catalogItems(){
 return [...packs.filter(p=>p.price>0).map(p=>({...p,kind:'pack',name:p.title,format:packDescription(p),cat:'Packs & promos'})),...products.map(p=>({...p,kind:'product'}))];
}
function packDescription(p){return p.components?.length?p.components.map(x=>`${x.quantity} × ${x.name} ${x.format||''}`).join(' + '):p.subtitle||'';}
function openPack(id){go('catalog');renderCatalog('Packs & promos');const el=document.querySelector(`[data-pack-id="${id}"]`);if(el){el.classList.add('selected-pack');el.scrollIntoView({block:'center',behavior:'smooth'});}}
function renderCatalog(cat=activeCategory){
 const items=catalogItems();
 activeCategory=cat;
 const q=($("#search").value||"").trim().toLowerCase();
 const order=["Packs & promos","Perte de graisse","Régénération","Beauté · peau","Nootropiques","Libido","Performance","Longévité"]; const cats=[...new Set(items.map(p=>p.cat))].sort((a,b)=>(order.includes(a)?order.indexOf(a):99)-(order.includes(b)?order.indexOf(b):99));
 const landing=cat==="Tous"&&!q;
 const filters=$("#filters"),target=$("#products");
 filters.classList.toggle('category-menu',landing);
 filters.classList.toggle('category-toolbar',!landing);
 if(landing){
  filters.innerHTML=cats.map(c=>`<button data-cat="${escapeHTML(c)}"><span class="category-menu-icon" aria-hidden="true">${categoryIcons[c]||'◇'}</span><span><b>${escapeHTML(categoryLabels[c]||c)}</b><small>${items.filter(p=>p.cat===c).length} produit${items.filter(p=>p.cat===c).length===1?"":"s"}</small></span><em aria-hidden="true">›</em></button>`).join('');
  target.innerHTML=cats.length?'':'<p class="empty-state">Le catalogue sera bientôt disponible.</p>';
  filters.querySelectorAll('[data-cat]').forEach(b=>b.onclick=()=>{renderCatalog(b.dataset.cat);scrollTo(0,0);});
  $('#catalog .catalog-head h1').textContent='Boutique';
  $('#catalog .catalog-head p').textContent='Choisissez une catégorie';
  return;
 }
 const shown=items.filter(p=>(cat==="Tous"||p.cat===cat)&&(`${p.name} ${p.format}`).toLowerCase().includes(q));
 filters.innerHTML='<button class="category-back">‹ Toutes les catégories</button>';
 filters.querySelector('button').onclick=()=>{$('#search').value='';renderCatalog('Tous');scrollTo(0,0);};
 $('#catalog .catalog-head h1').textContent=cat==='Tous'?'Recherche':categoryLabels[cat]||cat;
 $('#catalog .catalog-head p').textContent=`${shown.length} produit${shown.length===1?'':'s'}${q?' trouvé'+(shown.length===1?'':'s'):''}`;
 target.innerHTML=shown.length?`<div class="product-grid">${shown.map(p=>`<article class="product" ${p.kind==='pack'?`data-pack-id="${p.id}"`:`data-product-id="${p.id}"`}>${p.kind==='pack'?`<div class="pack-card-visual">${packVisual(p)}</div>`:vial(p)}<h3>${escapeHTML(p.name)}</h3><p>${escapeHTML(p.format||"NyxPepz")}</p><strong>${escapeHTML(p.price)} €</strong><small class="stock ${p.stock>0?"ok":"out"}">${p.stock>0?escapeHTML(p.stock)+" en stock":"Rupture"}</small>${includedSupplies(p)?`<small class="product-included">${includedSupplies(p)}</small>`:''}<div class="catalog-only">${escapeHTML(categoryLabels[p.cat]||p.cat)}</div></article>`).join('')}</div>`:'<p class="empty-state">Aucun produit ne correspond à votre recherche.</p>';
}
$("#search").oninput=()=>renderCatalog();

function escapeHTML(v){return String(v??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]))}
function packProducts(pack){
 if(pack.components?.length)return pack.components.map(x=>({name:x.name,format:x.format}));
 const normalize=s=>String(s||'').toLowerCase().replace(/[^a-z0-9]/g,'');
 function resolve(text){
  const parts=String(text||'').replace(/^pack\s+/i,'').split('+');
  const found=parts.map(part=>{
   const token=normalize(part);
   const matches=products.filter(p=>{
    const names=[p.name];
    if(normalize(p.name)==='retatrutide')names.push('Reta');
    if(normalize(p.name)==='cagrilintide')names.push('Cagri');
    return names.some(name=>{const n=normalize(name);if(!token.startsWith(n))return false;const dose=token.slice(n.length);return !dose||dose===normalize(p.format)||dose===normalize(p.format).replace(/mg/g,'');});
   });
   return matches.length===1?matches[0]:null;
  });
  return found.length<=3&&found.every(Boolean)?found:[];
 }
 return resolve(pack.subtitle).length?resolve(pack.subtitle):resolve(pack.title);
}
function packVisual(pack){
 // Preserve a deliberately uploaded custom photo. Bundled legacy art uses
 // the same label renderer as the shop, with catalogue-backed dosages.
 if(pack.image_url&&!pack.image_url.startsWith('/static/'))return `<img class="promo-img" src="${escapeHTML(pack.image_url)}" alt="${escapeHTML(pack.title)}">`;
 const items=packProducts(pack);
 return `<div class="promo-vials ${items.length>1?'multiple-vials':''}">${(items.length?items:[{name:'NyxPepz',format:''}]).map(p=>vial({...p,image_url:null})).join('')}</div>`;
}
function promoSlide(x){
 return `<article class="promo-slide"><div class="promo-copy"><small>PACK & PROMO</small><h2>${escapeHTML(x.title)}</h2><p>${escapeHTML(x.subtitle||"")}</p><strong>${x.price?escapeHTML(x.price)+" €":"Offre à venir"}</strong><button data-pack-open="${x.id}">Voir ce pack　›</button></div>${packVisual(x)}<div class="promo-wave"></div></article>`
}
function setPromo(i,user=false){
 if(!packs.length)return;promoIndex=(i+packs.length)%packs.length;
 $("#promoTrack").style.transform=`translateX(-${promoIndex*100}%)`;
 $$("#promoDots button").forEach((b,k)=>b.classList.toggle("active",k===promoIndex));
 if(user)restartPromo();
}
function restartPromo(){clearInterval(promoTimer);if(packs.length>1&&!document.hidden&&!matchMedia("(prefers-reduced-motion: reduce)").matches)promoTimer=setInterval(()=>setPromo(promoIndex+1),5200)}
async function loadPacks(){
 try{packs=await api("/api/packs")}catch{packs=[]}
 if(!packs.length){clearInterval(promoTimer);$("#promoTrack").innerHTML='<article class="promo-slide"><div class="promo-copy"><small>NYXPEPZ</small><h2>Découvrez le catalogue</h2><p>Retrouvez tous nos produits.</p><button data-go="catalog">Voir le catalogue　›</button></div></article>';$("#promoDots").innerHTML="";$("#promoTrack button").onclick=()=>go("catalog");return}

 $("#promoTrack").innerHTML=packs.map(promoSlide).join("");
 $("#promoTrack").querySelectorAll("[data-pack-open]").forEach(b=>b.onclick=()=>openPack(Number(b.dataset.packOpen)));
 $("#promoDots").innerHTML=packs.map((_,i)=>`<button aria-label="Promo ${i+1}" class="${i===0?"active":""}"></button>`).join("");
 $$("#promoDots button").forEach((b,i)=>b.onclick=()=>setPromo(i,true));
 $("#promoTrack").querySelectorAll("[data-go]").forEach(b=>b.onclick=()=>go(b.dataset.go));
 let c=$("#promoCarousel");c.ontouchstart=e=>promoTouchX=e.touches[0].clientX;c.ontouchend=e=>{let d=e.changedTouches[0].clientX-promoTouchX;if(Math.abs(d)>38)setPromo(promoIndex+(d<0?1:-1),true)};
 restartPromo()
}

async function loadNews(){try{let a=await api("/api/news");$("#newsList").innerHTML=a.slice(0,2).map(n=>`<article>${n.image_url?`<img class="news-photo" loading="lazy" alt="${escapeHTML(n.title)}" src="${n.image_url}">`:""}<h3>${n.title}</h3><p>${n.subtitle||""}</p><em>›</em></article>`).join("")}catch{}}
async function loadLeaders(){try{let a=await api("/api/leaderboard");$("#leaders").innerHTML=a.map((x,i)=>`<div class="leader"><span>${i+1}. ${escapeHTML(x.name)}</span><b>${x.points} pts</b></div>`).join("")||"Aucun classement."}catch(e){toast(e.message)}}
async function loadHomeLeaders(){try{let a=(await api("/api/leaderboard")).slice(0,3);$("#homeLeaders").innerHTML=a.map((x,i)=>`<div class="podium-member"><span class="podium-medal" aria-label="Place ${i+1}">${["🥇","🥈","🥉"][i]}</span><b>${escapeHTML(x.name)}</b><span class="podium-points">${Number(x.points)||0} points</span></div>`).join("")||'<p class="empty-state">Le classement apparaîtra avec les premiers membres.</p>'}catch(e){$("#homeLeaders").innerHTML='<p class="empty-state">Classement momentanément indisponible.</p>'}}
$("#copyCode").onclick=async()=>{try{await navigator.clipboard.writeText(me.referral_code);toast("Code copié")}catch{toast(me.referral_code||"Code indisponible")}};
$("#applyReferral").onclick=async()=>{try{await api("/api/referral/apply",{method:"POST",body:JSON.stringify({code:$("#applyCode").value})});toast("Parrain enregistré")}catch(e){toast(e.message)}};
async function loadWeights(){try{let a=await api("/api/weights");chart?.destroy();chart=new Chart($("#weightChart"),{type:"line",data:{labels:a.map(x=>new Date(x.date).toLocaleDateString("fr-FR")),datasets:[{label:"Poids (kg)",data:a.map(x=>x.weight),tension:.35}]},options:{responsive:true,maintainAspectRatio:false}})}catch(e){toast(e.message)}}
$("#addWeight").onclick=async()=>{try{await api("/api/weights",{method:"POST",body:JSON.stringify({weight:$("#weight").value})});$("#weight").value="";loadWeights()}catch(e){toast(e.message)}};
async function uploadPhoto(input){
 let f=input?.files?.[0];if(!f)return "";
 let fd=new FormData();fd.append("file",f);
 let r=await fetch("/api/admin/upload",{method:"POST",body:fd}),d=await r.json().catch(()=>({}));
 if(!r.ok)throw Error(d.error||"Upload impossible");return d.url
}
function editProduct(p){
 let name=prompt("Nom",p.name);if(name===null)return;
 let format=prompt("Format",p.format||"");if(format===null)return;
 let price=prompt("Prix €",p.price);if(price===null)return;
 let stock=prompt("Stock",p.stock??0);if(stock===null)return;
 let cat=prompt("Catégorie",p.cat);if(cat===null)return;
 let image=prompt("URL image",p.image_url||"");if(image===null)return;
 api("/api/admin/products/"+p.id,{method:"PATCH",body:JSON.stringify({name,format,price:+price,stock:+stock,cat,image_url:image})}).then(async()=>{toast("Produit modifié");loadAdmin();products=await api("/api/catalog");renderCatalog()}).catch(e=>toast(e.message))
}
function editPack(p){
 let title=prompt("Titre",p.title);if(title===null)return;
 let subtitle=prompt("Sous-titre",p.subtitle||"");if(subtitle===null)return;
 let price=prompt("Prix €",p.price);if(price===null)return;
 let order=prompt("Ordre",p.sort_order||0);if(order===null)return;
 let image=prompt("URL image",p.image_url||"");if(image===null)return;
 api("/api/admin/packs/"+p.id,{method:"PATCH",body:JSON.stringify({title,subtitle,price:+price,sort_order:+order,image_url:image})}).then(()=>{toast("Pack modifié");loadAdmin();loadPacks()}).catch(e=>toast(e.message))
}
async function changeProductPhoto(id,input){try{let url=await uploadPhoto(input);if(!url)return;await api("/api/admin/products/"+id,{method:"PATCH",body:JSON.stringify({image_url:url})});toast("Photo modifiée");loadAdmin();products=await api("/api/catalog");renderCatalog()}catch(e){toast(e.message)}}
async function changePackPhoto(id,input){try{let url=await uploadPhoto(input);if(!url)return;await api("/api/admin/packs/"+id,{method:"PATCH",body:JSON.stringify({image_url:url})});toast("Photo modifiée");loadAdmin();loadPacks()}catch(e){toast(e.message)}}
let adminProductItems=[],adminProductCategory=null;
const adminProductSearch=value=>String(value||'').normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase().replace(/([a-z])([0-9])/g,'$1 $2').replace(/([0-9])([a-z])/g,'$1 $2').replace(/[^a-z0-9]+/g,' ').trim();
const adminProductCategoryOf=p=>String(p.cat||'').trim()||'Sans catégorie';
function renderAdminProducts(){
 const menu=$('#adminProductCategories'),list=$('#adminProducts'),toolbar=$('#adminProductToolbar'),search=$('#adminProductSearch');
 if(!menu||!list||!toolbar||!search)return;
 const label=cat=>cat==='Beauté · peau'?'Beauté de la peau':categoryLabels[cat]||cat;
 const order=['Perte de graisse','Nootropiques','Beauté · peau','Régénération','Performance','Longévité','Libido'];
 const collator=new Intl.Collator('fr',{numeric:true,sensitivity:'base'});
 const cats=[...new Set(adminProductItems.map(adminProductCategoryOf))].sort((a,b)=>{const rank=c=>order.includes(c)?order.indexOf(c):99;return rank(a)-rank(b)||collator.compare(a,b);});
 if(adminProductCategory&&!cats.includes(adminProductCategory))adminProductCategory=null;
 const tokens=adminProductSearch(search.value).split(' ').filter(Boolean),landing=!adminProductCategory&&!tokens.length;
 menu.replaceChildren();toolbar.replaceChildren();list.replaceChildren();menu.hidden=!landing;toolbar.hidden=landing;
 function element(tag,cls,text){const node=document.createElement(tag);if(cls)node.className=cls;if(text!==undefined)node.textContent=text;return node;}
 function button(text,handler,cls=''){const node=element('button',cls,text);node.type='button';node.onclick=handler;return node;}
 if(landing){
  cats.forEach(cat=>{const items=adminProductItems.filter(p=>adminProductCategoryOf(p)===cat),card=button('',()=>{adminProductCategory=cat;renderAdminProducts();$('#adminProductHeading').focus({preventScroll:true});});card.dataset.adminCategory=cat;
   const icon=element('span','category-menu-icon',categoryIcons[cat]||'◇');icon.setAttribute('aria-hidden','true');const copy=element('span');copy.append(element('b','',label(cat)),element('small','',items.length+' produit'+(items.length>1?'s':'')));const arrow=element('em','','›');arrow.setAttribute('aria-hidden','true');card.append(icon,copy,arrow);menu.append(card);
  });
  if(!cats.length)list.append(element('p','empty-state','Aucun produit pour le moment. Utilisez « Ajouter un produit ».'));
  return;
 }
 const back=button('‹ Toutes les catégories',()=>{adminProductCategory=null;search.value='';renderAdminProducts();menu.querySelector('button')?.focus({preventScroll:true});},'shop-secondary');
 const shown=adminProductItems.filter(p=>(!adminProductCategory||adminProductCategoryOf(p)===adminProductCategory)&&tokens.every(token=>adminProductSearch(`${p.name} ${p.format} ${label(adminProductCategoryOf(p))}`).includes(token))).sort((a,b)=>collator.compare(a.name,b.name)||collator.compare(a.format||'',b.format||'')||a.id-b.id);
 const heading=element('h3','',adminProductCategory?label(adminProductCategory):'Résultats de recherche');heading.id='adminProductHeading';heading.tabIndex=-1;
 toolbar.append(back,heading,element('p','admin-note',shown.length+' produit'+(shown.length!==1?'s':'')));
 if(!shown.length)list.append(element('p','empty-state','Aucun produit ne correspond à cette recherche.'));
 shown.forEach(p=>{
  const row=element('article','admin-row admin-edit card');row.dataset.adminProductId=p.id;
  const copy=element('div'),name=element('b','',`${p.name} ${p.format||''}`.trim());copy.append(name,element('small','',`${p.price} € · Stock ${p.stock??0} · ${p.active?'Visible':'Masqué'}`));
  const photo=element('label','mini-upload','📷');photo.setAttribute('aria-label','Changer la photo de '+p.name+' '+(p.format||''));const input=element('input');input.type='file';input.accept='image/png,image/jpeg,image/webp';input.onchange=()=>changeProductPhoto(p.id,input);photo.append(input);
  const actions=element('div','admin-product-actions');
  const editor=element('form','admin-stock-editor');editor.hidden=true;editor.noValidate=true;
  const stockId='admin-stock-'+p.id,label=element('label','','Nouvelle quantité en stock'),quantity=element('input');quantity.id=stockId;quantity.type='text';quantity.inputMode='numeric';quantity.autocomplete='off';quantity.maxLength=10;quantity.value=String(p.stock??0);label.htmlFor=stockId;
  const help=element('p','admin-note','Saisissez la quantité totale disponible, pas la quantité à ajouter.');help.id=stockId+'-help';quantity.setAttribute('aria-describedby',help.id+' '+stockId+'-status');
  const status=element('p','admin-stock-status');status.id=stockId+'-status';status.setAttribute('role','status');status.setAttribute('aria-live','polite');
  const stock=button('Stock',()=>{editor.hidden=!editor.hidden;stock.setAttribute('aria-expanded',String(!editor.hidden));if(!editor.hidden){quantity.value=String(p.stock??0);status.textContent='';quantity.removeAttribute('aria-invalid');quantity.focus();quantity.select();}},'admin-stock-open');stock.setAttribute('aria-expanded','false');editor.id=stockId+'-editor';stock.setAttribute('aria-controls',editor.id);
  const save=element('button','admin-stock-save','Enregistrer');save.type='submit';
  const cancel=button('Annuler',()=>{editor.hidden=true;stock.setAttribute('aria-expanded','false');stock.focus();});
  const formActions=element('div','admin-stock-actions');formActions.append(save,cancel);editor.append(label,quantity,help,status,formActions);
  let saving=false;
  editor.onsubmit=async event=>{
   event.preventDefault();if(saving)return;
   const raw=quantity.value.trim(),value=Number(raw);
   if(!/^\d+$/.test(raw)||!Number.isSafeInteger(value)||value>2147483647){status.textContent='Indiquez un nombre entier positif ou zéro.';quantity.setAttribute('aria-invalid','true');quantity.focus();return;}
   saving=true;quantity.removeAttribute('aria-invalid');status.textContent='Enregistrement…';save.disabled=cancel.disabled=quantity.disabled=true;actions.querySelectorAll('button,input').forEach(control=>control.disabled=true);
   try{
    const updated=await api('/api/admin/products/'+p.id,{method:'PATCH',body:JSON.stringify({stock:value})});
    p.stock=updated.stock??value;const cached=adminProductItems.find(item=>item.id===p.id);if(cached)cached.stock=p.stock;
    copy.querySelector('small').textContent=`${p.price} € · Stock ${p.stock} · ${p.active?'Visible':'Masqué'}`;
    status.textContent='Stock enregistré.';editor.hidden=true;stock.setAttribute('aria-expanded','false');toast('Stock enregistré : '+p.stock);
    // Refresh the storefront independently: a refresh failure must not suggest the save failed.
    api('/api/catalog').then(items=>{products=items;renderCatalog();}).catch(()=>{});
   }catch(error){status.textContent=error.message||'Impossible d’enregistrer le stock. Réessayez.';}
   finally{saving=false;save.disabled=cancel.disabled=quantity.disabled=false;actions.querySelectorAll('button,input').forEach(control=>control.disabled=false);if(editor.hidden&&row.isConnected)stock.focus({preventScroll:true});}
  };
  actions.append(stock,button('Modifier',()=>editProduct(p)),photo,button(p.active?'Masquer':'Afficher',()=>toggleProduct(p.id,!p.active)),button('Supprimer',()=>deleteProduct(p.id),'danger'));
  row.append(copy,actions,editor);list.append(row);
 });
}
$('#adminProductSearch')?.addEventListener('input',renderAdminProducts);
async function loadAdmin(){if(!me.is_admin)return;try{
 let ps=await api("/api/admin/products");
 adminProductItems=ps;renderAdminProducts();
 let pk=await api("/api/admin/packs");
 $("#adminPacks").innerHTML=pk.map(x=>`<div class="admin-row admin-edit card"><div><b>${x.title}</b><small>${x.subtitle||""} · ${x.price} € · ordre ${x.sort_order}</small></div><button onclick='editPack(${escapeHTML(JSON.stringify(x))})'>Modifier</button><button onclick="editPackComposition(${x.id})">Composition</button><label class="mini-upload">📷<input type="file" accept="image/png,image/jpeg,image/webp" onchange="changePackPhoto(${x.id},this)"></label><button onclick="togglePack(${x.id},${!x.active})">${x.active?"Masquer":"Afficher"}</button><button class="danger" onclick="deletePack(${x.id})">Supprimer</button></div>`).join("");
 let ns=await api("/api/admin/news");$("#adminNews").innerHTML=ns.map(n=>`<div class="admin-row card"><div><b>${n.title}</b><small>${n.subtitle||""}</small></div><button class="danger" onclick="deleteNews(${n.id})">Supprimer</button></div>`).join("")
 }catch(e){toast(e.message)}
}
async function toggleProduct(id,active){await api("/api/admin/products/"+id,{method:"PATCH",body:JSON.stringify({active})});loadAdmin();products=await api("/api/catalog");renderCatalog()}
async function deleteProduct(id){if(!confirm("Supprimer ce produit ?"))return;await api("/api/admin/products/"+id,{method:"DELETE"});loadAdmin();products=await api("/api/catalog");renderCatalog()}
async function togglePack(id,active){await api("/api/admin/packs/"+id,{method:"PATCH",body:JSON.stringify({active})});loadAdmin();loadPacks()}
async function deletePack(id){if(!confirm("Supprimer ce pack ?"))return;await api("/api/admin/packs/"+id,{method:"DELETE"});loadAdmin();loadPacks()}
async function deleteNews(id){if(!confirm("Supprimer cette nouveauté ?"))return;await api("/api/admin/news/"+id,{method:"DELETE"});loadAdmin();loadNews()}
$("#aAdd").onclick=async()=>{try{let image=$("#aImage").value;if($("#aFile").files[0])image=await uploadPhoto($("#aFile"));await api("/api/admin/products",{method:"POST",body:JSON.stringify({name:$("#aName").value,format:$("#aFormat").value,price:+$("#aPrice").value,stock:+$("#aStock").value||0,cat:$("#aCat").value,image_url:image})});toast("Produit ajouté");loadAdmin();products=await api("/api/catalog");renderCatalog()}catch(e){toast(e.message)}};
$("#pAdd").onclick=async()=>{try{let image=$("#pImage").value;if($("#pFile").files[0])image=await uploadPhoto($("#pFile"));await api("/api/admin/packs",{method:"POST",body:JSON.stringify({title:$("#pTitle").value,subtitle:$("#pSubtitle").value,price:+$("#pPrice").value,image_url:image,sort_order:+$("#pOrder").value||0})});toast("Pack ajouté");loadAdmin();loadPacks()}catch(e){toast(e.message)}};
$("#nAdd").onclick=async()=>{try{let image=$("#nImage").value;if($("#nFile").files[0])image=await uploadPhoto($("#nFile"));await api("/api/admin/news",{method:"POST",body:JSON.stringify({title:$("#nTitle").value,subtitle:$("#nSubtitle").value,image_url:image})});toast("Nouveauté publiée");loadAdmin();loadNews()}catch(e){toast(e.message)}};
go("home");boot();

document.addEventListener("visibilitychange",restartPromo);

async function editPackComposition(id){
 try{
 const [all,entries]=await Promise.all([api('/api/admin/products'),api('/api/admin/packs')]);
 const pack=entries.find(p=>p.id===id);if(!pack)return;
 const labels=all.map(p=>`${p.id} : ${p.name} ${p.format||''}`).join('\n');
 const value=prompt('Produits inclus dans UN pack. Saisissez numéro:quantité, séparés par une virgule. Exemple : 1:1, 14:1\n\n'+labels,(pack.components||[]).map(p=>`${p.product_id}:${p.quantity}`).join(', '));
 if(value===null)return;
 const components=value.trim()?value.split(',').map(entry=>{const match=entry.trim().match(/^(\d+):(\d+)$/);if(!match)throw Error('Format attendu : numéro:quantité');return {product_id:Number(match[1]),quantity:Number(match[2])};}):[];
 await api('/api/admin/packs/'+id,{method:'PATCH',body:JSON.stringify({components})});await loadPacks();loadAdmin();toast('Composition enregistrée');
 }catch(e){toast(e.message);}
}
