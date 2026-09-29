const tg=window.Telegram?.WebApp;if(tg){tg.ready();tg.expand()}
const $=s=>document.querySelector(s),$$=s=>document.querySelectorAll(s);let me={},products=[],chart,packs=[],promoIndex=0,promoTimer,promoTouchX=0;
const toast=m=>{let t=$("#toast");t.textContent=m;t.style.display="block";setTimeout(()=>t.style.display="none",2200)};
async function api(u,o={}){o.headers={"Content-Type":"application/json",...(o.headers||{})};let r=await fetch(u,o),d=await r.json().catch(()=>({}));if(!r.ok)throw Error(d.error||"Erreur");return d}
function go(id){$$(".page").forEach(x=>x.classList.remove("active"));$("#"+id)?.classList.add("active");$$("nav button").forEach(x=>x.classList.toggle("active",x.dataset.go===id));if(id==="tracking")loadWeights();if(id==="leaderboard")loadLeaders();if(id==="admin")loadAdmin();scrollTo(0,0)}
$$("[data-go]").forEach(b=>b.onclick=()=>go(b.dataset.go));
const meta={"Perte de graisse":["◯","Un corps plus sain, une meilleure sensibilité"],"Régénération":["♧","Des tissus plus forts, une récupération accélérée"],"Beauté · peau":["♙","Un éclat naturel, une régénération visible"],"Nootropiques":["◇","Clarté, concentration et équilibre"],"Performance":["ϟ","Performance et vitalité"],"Longévité":["∞","Longévité / Anti-âge"],"Libido":["♡","Bien-être et vitalité"]};
function vial(p){if(p.image_url)return `<div class="product-photo"><img src="${p.image_url}" alt="${p.name}"></div>`;let tone=p.cat.includes("Beauté")?"violet":"blue";return `<div class="pv ${tone}"><div class="pv-cap"></div><div class="pv-neck"></div><div class="pv-body"><div class="pv-label"><span>☾</span><b>NyxPepz</b><small>${p.name}</small><em>${p.format||"PREMIUM"}</em></div></div></div>`}
async function boot(){try{await api("/api/auth/telegram",{method:"POST",body:JSON.stringify({initData:tg?.initData||""})});me=await api("/api/me");$("#hello").textContent=me.first_name||"Nyx";$("#points").textContent=me.loyalty_points;let mod=me.loyalty_points%200;$("#progressbar").style.width=Math.min(mod/2,100)+"%";$("#remaining").textContent=200-mod;$("#refpoints2").textContent=me.referral_points;$("#refcode").textContent=$("#profileCode").textContent=me.referral_code;$("#filleuls").textContent=me.filleuls;$("#profileName").textContent=me.first_name||me.username||"Membre";$("#profilePoints").textContent=me.loyalty_points;if(me.is_admin){let b=document.createElement("button");b.className="admin-fab";b.textContent="⚙ Admin";b.onclick=()=>go("admin");document.body.appendChild(b)}}catch(e){toast(e.message)}
try{products=await api("/api/catalog");renderCatalog();loadHomeLeaders();loadNews();loadPacks()}catch(e){toast(e.message)}}
function renderCatalog(cat="Tous"){let aliases={"Beauté · peau":"Beauté / Peau","Performance":"Performance / GH","Longévité":"Longévité / Anti-âge"};let cats=["Tous",...new Set(products.map(x=>x.cat))];$("#filters").innerHTML=cats.map(c=>`<button class="${c===cat?"active":""}" data-cat="${c}">${aliases[c]||c}</button>`).join("");$("#filters").querySelectorAll("button").forEach(b=>b.onclick=()=>renderCatalog(b.dataset.cat));let q=($("#search").value||"").toLowerCase(),shown=products.filter(p=>(cat==="Tous"||p.cat===cat)&&(`${p.name} ${p.format}`).toLowerCase().includes(q)),groups=[...new Set(shown.map(x=>x.cat))];$("#products").innerHTML=groups.map((g,i)=>{let m=meta[g]||["◇","Produits NyxPepz"];return `<section class="category"><div class="cat-head"><div class="cat-icon">${m[0]}</div><div><h2><b>${i+1}.</b> ${aliases[g]||g}</h2><p>${m[1]}</p></div><button>Voir tout　›</button></div><div class="product-grid">${shown.filter(p=>p.cat===g).map(p=>`<article class="product">${vial(p)}<h3>${p.name}</h3><p>${p.format||"NyxPepz"}</p><strong>${p.price} €</strong><small class="stock ${p.stock>0?"ok":"out"}">${p.stock>0?p.stock+" en stock":"Rupture"}</small><div class="catalog-only">Voir la fiche</div></article>`).join("")}</div></section>`}).join("")}
$("#search").oninput=()=>renderCatalog();

function promoSlide(x){
 let img=x.image_url?`<img class="promo-img" src="${x.image_url}" alt="">`:"";
 return `<article class="promo-slide"><div class="promo-copy"><small>PACK & PROMO</small><h2>${x.title}</h2><p>${x.subtitle||""}</p><strong>${x.price?x.price+" €":"Offre à venir"}</strong><button data-go="catalog">Voir le catalogue　›</button></div>${img}<div class="promo-wave"></div></article>`
}
function setPromo(i,user=false){
 if(!packs.length)return;promoIndex=(i+packs.length)%packs.length;
 $("#promoTrack").style.transform=`translateX(-${promoIndex*100}%)`;
 $$("#promoDots button").forEach((b,k)=>b.classList.toggle("active",k===promoIndex));
 if(user)restartPromo();
}
function restartPromo(){clearInterval(promoTimer);if(packs.length>1)promoTimer=setInterval(()=>setPromo(promoIndex+1),5200)}
async function loadPacks(){
 try{packs=await api("/api/packs")}catch{packs=[]}
 if(!packs.length)packs=[{title:"Pack Reta 10 + GHK-CU",subtitle:"Retatrutide 10 mg + GHK-CU",price:110,image_url:"/static/reta10-pack.webp"},{title:"Pack Reta 15 + Cagri",subtitle:"Retatrutide 15 mg + Cagrilintide",price:200,image_url:"/static/reta15-pack.webp"}];
 $("#promoTrack").innerHTML=packs.map(promoSlide).join("");
 $("#promoDots").innerHTML=packs.map((_,i)=>`<button aria-label="Promo ${i+1}" class="${i===0?"active":""}"></button>`).join("");
 $$("#promoDots button").forEach((b,i)=>b.onclick=()=>setPromo(i,true));
 $("#promoTrack").querySelectorAll("[data-go]").forEach(b=>b.onclick=()=>go(b.dataset.go));
 let c=$("#promoCarousel");c.ontouchstart=e=>promoTouchX=e.touches[0].clientX;c.ontouchend=e=>{let d=e.changedTouches[0].clientX-promoTouchX;if(Math.abs(d)>38)setPromo(promoIndex+(d<0?1:-1),true)};
 restartPromo()
}

async function loadNews(){try{let a=await api("/api/news");$("#newsList").innerHTML=(a.length?a:[{title:"GHK-CU",subtitle:"Poudre pure",image_url:"/static/ghk.webp"},{title:"AHK-CU",subtitle:"Poudre pure",image_url:"/static/glow.webp"}]).slice(0,2).map(n=>`<article>${n.image_url?`<img class="news-photo" src="${n.image_url}">`:""}<h3>${n.title}</h3><p>${n.subtitle||""}</p><em>›</em></article>`).join("")}catch{}}
async function loadLeaders(){try{let a=await api("/api/leaderboard");$("#leaders").innerHTML=a.map((x,i)=>`<div class="leader"><span>${i+1}. ${x.name}</span><b>${x.points} pts</b></div>`).join("")||"Aucun classement."}catch(e){toast(e.message)}}
async function loadHomeLeaders(){try{let a=(await api("/api/leaderboard")).slice(0,3);$("#homeLeaders").innerHTML=[0,1,2].map(i=>`<div><b>${["🥇","🥈","🥉"][i]}</b><span>${a[i]?.name||["Luna","Nox","Nyx"][i]}<small>${a[i]?.points||[452,389,321][i]} points</small></span></div>`).join("")}catch{}}
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
async function loadAdmin(){if(!me.is_admin)return;try{await loadAdminUsers();
 let ps=await api("/api/admin/products");
 $("#adminProducts").innerHTML=ps.map(p=>`<div class="admin-row admin-edit card"><div><b>${p.name}</b><small>${p.format||""} · ${p.cat} · ${p.price} € · Stock ${p.stock??0}</small></div><button onclick='editProduct(${JSON.stringify(p)})'>Modifier</button><label class="mini-upload">📷<input type="file" accept="image/png,image/jpeg,image/webp" onchange="changeProductPhoto(${p.id},this)"></label><button onclick="toggleProduct(${p.id},${!p.active})">${p.active?"Masquer":"Afficher"}</button><button class="danger" onclick="deleteProduct(${p.id})">Supprimer</button></div>`).join("");
 let pk=await api("/api/admin/packs");
 $("#adminPacks").innerHTML=pk.map(x=>`<div class="admin-row admin-edit card"><div><b>${x.title}</b><small>${x.subtitle||""} · ${x.price} € · ordre ${x.sort_order}</small></div><button onclick='editPack(${JSON.stringify(x)})'>Modifier</button><label class="mini-upload">📷<input type="file" accept="image/png,image/jpeg,image/webp" onchange="changePackPhoto(${x.id},this)"></label><button onclick="togglePack(${x.id},${!x.active})">${x.active?"Masquer":"Afficher"}</button><button class="danger" onclick="deletePack(${x.id})">Supprimer</button></div>`).join("");
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

async function loadAdminUsers(){
  try{
    const users = await api("/api/admin/users");
    const box = $("#adminUsers");
    if(!box) return;

    box.innerHTML = users.map(u => `
      <div class="admin-row card">
        <div>
          <b>${u.name}</b>
          <small>ID Telegram : ${u.telegram_id} · ${u.points} point(s)</small>
        </div>
        <button onclick="deleteAdminUser(${u.id})">🗑 Supprimer</button>
      </div>
    `).join("");
  }catch(e){
    console.error("Erreur utilisateurs admin :", e);
  }
}

async function deleteAdminUser(id){
  if(!confirm("Supprimer définitivement cet utilisateur ?")) return;
  try{
    await api("/api/admin/users/" + id, {method:"DELETE"});
    toast("Utilisateur supprimé");
    await loadAdminUsers();
    await loadLeaders();
    await loadHomeLeaders();
  }catch(e){
    toast(e.message || "Suppression impossible");
  }
}
