/* Source documents are supplied by the owner; no generated treatment protocols. */
(()=>{
 const root=document.getElementById('encyclopedia');if(!root)return;
 const search=document.getElementById('encyclopediaSearch'),filters=document.getElementById('encyclopediaFilters'),list=document.getElementById('encyclopediaList'),detail=document.getElementById('encyclopediaDetail');
 let entries=[],category='Toutes';
 const documentPath=file=>file;
 const viewer=document.createElement('dialog');viewer.className='encyclopedia-viewer';
 viewer.innerHTML='<div class="encyclopedia-viewer-toolbar"><strong>Document original</strong><button type="button" data-zoom-out aria-label="Réduire">−</button><button type="button" data-zoom-fit>Ajuster</button><button type="button" data-zoom-in aria-label="Agrandir">＋</button><button type="button" data-zoom-close aria-label="Fermer la fiche">✕</button></div><div class="encyclopedia-viewer-scroll"><img alt=""></div>';
 document.body.append(viewer);const fullImage=viewer.querySelector('img'),viewport=viewer.querySelector('.encyclopedia-viewer-scroll');
 let zoomWidth=0,previousOverflow='';
 function setZoom(width){zoomWidth=Math.max(viewport.clientWidth,Math.min(2400,width));fullImage.style.width=zoomWidth+'px';}
 viewer.querySelector('[data-zoom-in]').onclick=()=>setZoom(zoomWidth*1.4);
 viewer.querySelector('[data-zoom-out]').onclick=()=>setZoom(zoomWidth/1.4);
 viewer.querySelector('[data-zoom-fit]').onclick=()=>setZoom(viewport.clientWidth);
 viewer.querySelector('[data-zoom-close]').onclick=()=>viewer.close();
 viewer.addEventListener('close',()=>{document.body.style.overflow=previousOverflow;});
 function enlarge(entry){fullImage.src=documentPath(entry.file);fullImage.alt='Fiche '+entry.title;previousOverflow=document.body.style.overflow;document.body.style.overflow='hidden';viewer.showModal();setZoom(viewport.clientWidth);viewport.scrollTop=0;viewport.scrollLeft=0;}
 const normalize=s=>String(s||'').normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase();
 function render(){
  detail.hidden=true;list.hidden=false;
  root.querySelector('.calculator-intro').textContent=entries.length?`${entries.length} fiches de référence · Rechercher ou choisir une catégorie.`:'Retrouvez les documents et fiches de référence.';
  const categories=['Toutes',...new Set(entries.map(x=>x.category).filter(Boolean))];filters.replaceChildren();
  categories.forEach(name=>{const b=document.createElement('button');b.type='button';b.textContent=name;b.setAttribute('aria-pressed',String(name===category));b.onclick=()=>{category=name;render();};filters.append(b);});
  const q=normalize(search.value),shown=entries.filter(x=>(category==='Toutes'||x.category===category)&&normalize([x.title,x.summary,...(x.tags||[])].join(' ')).includes(q));
  list.replaceChildren();
  if(!shown.length){const p=document.createElement('p');p.className='card pad empty-state';p.textContent=entries.length?'Aucune fiche ne correspond à votre recherche.':'Les fiches de l’encyclopédie seront disponibles ici prochainement.';list.append(p);return;}
  shown.forEach(entry=>{const card=document.createElement('article');card.className='card encyclopedia-card';const title=document.createElement('h2');title.textContent=entry.title;const p=document.createElement('p');p.textContent=entry.summary||entry.category||'';const b=document.createElement('button');b.className='shop-secondary';b.type='button';b.textContent='Lire la fiche';b.onclick=()=>open(entry);card.append(title,p,b);list.append(card);});
 }
 function open(entry){
  list.hidden=true;detail.hidden=false;detail.replaceChildren();
  const back=document.createElement('button');back.type='button';back.className='shop-secondary';back.textContent='‹ Retour aux fiches';back.onclick=render;
  const title=document.createElement('h2');title.textContent=entry.title;detail.append(back,title);
  if(entry.source){const source=document.createElement('p');source.className='shop-notice';source.textContent='Source : '+entry.source;detail.append(source);}
  for(const section of entry.sections||[]){const article=document.createElement('article');article.className='card pad';const h=document.createElement('h3');h.textContent=section.title||'';const text=document.createElement('p');text.textContent=section.text||'';text.style.whiteSpace='pre-wrap';article.append(h,text);detail.append(article);}
  if(typeof entry.file==='string'&&/^\/static\/encyclopedia\/[a-zA-Z0-9_-]+\.(pdf|png|jpg|jpeg|webp)$/.test(entry.file)){
   const note=document.createElement('p');note.className='shop-notice';note.textContent='Fiche fournie par NyxPepz. Son contenu et ses protocoles n’ont pas été validés médicalement dans cette application.';detail.append(note);
   if(/\.(png|jpg|jpeg|webp)$/.test(entry.file)){
    const image=document.createElement('img');image.className='encyclopedia-original';image.src=documentPath(entry.file);image.alt='Document original : '+entry.title;image.loading='lazy';
    const button=document.createElement('button');button.className='shop-primary encyclopedia-document';button.type='button';button.textContent='Agrandir la fiche';button.onclick=()=>enlarge(entry);detail.append(button,image);
   }else{
    const link=document.createElement('a');link.className='shop-primary encyclopedia-document';link.href=documentPath(entry.file);link.target='_blank';link.rel='noopener';link.textContent='Ouvrir le document original';detail.append(link);
   }
  }
  const note=document.createElement('p');note.className='shop-notice';note.textContent='Document informatif fourni à titre de référence. Il ne remplace pas un avis médical personnalisé.';detail.append(note);detail.scrollIntoView({block:'start',behavior:'smooth'});
 }
 search.oninput=render;
 fetch('/static/encyclopedia.json?v=11.0').then(r=>{if(!r.ok)throw Error();return r.json();}).then(data=>{entries=Array.isArray(data)?data.filter(x=>x&&typeof x.title==='string'):[];render();}).catch(()=>{list.textContent='Les fiches sont momentanément indisponibles. Réouvrez l’app pour réessayer.';});
})();
