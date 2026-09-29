/* Faithful transcription of owner-supplied summaries, kept separate from calculations. */
(()=>{
 const root=document.getElementById('protocols');if(!root)return;
 const browse=document.getElementById('protocolBrowse'),search=document.getElementById('protocolSearch'),categories=document.getElementById('protocolCategories'),list=document.getElementById('protocolList'),detail=document.getElementById('protocolDetail');
 const documentPath=file=>file;
 let data={categories:[],entries:[],sources:[]},selected='',previousScroll=0,opener=null;
 const normalize=value=>String(value||'').normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase().replace(/([a-z])([0-9])/g,'$1 $2').replace(/([0-9])([a-z])/g,'$1 $2').replace(/[^a-z0-9]+/g,' ').trim();
 function el(tag,cls,text){const node=document.createElement(tag);if(cls)node.className=cls;if(text!==undefined)node.textContent=text;return node;}
 function button(label,cls,fn){const node=el('button',cls,label);node.type='button';node.onclick=fn;return node;}
 const viewer=el('dialog','encyclopedia-viewer');viewer.id='protocolSourceViewer';viewer.setAttribute('aria-label','Document source NyxPepz');
 const toolbar=el('div','encyclopedia-viewer-toolbar'),image=el('img'),viewport=el('div','encyclopedia-viewer-scroll');let zoom=0,previousOverflow='';
 function setZoom(width){zoom=Math.max(viewport.clientWidth,Math.min(2400,width));image.style.width=zoom+'px';}
 toolbar.append(el('strong','','Document original'),button('−','',()=>setZoom(zoom/1.4)),button('Ajuster','',()=>setZoom(viewport.clientWidth)),button('＋','',()=>setZoom(zoom*1.4)),button('Fermer','',()=>viewer.close()));
 toolbar.children[1].setAttribute('aria-label','Réduire le document');toolbar.children[3].setAttribute('aria-label','Agrandir le document');viewport.append(image);viewer.append(toolbar,viewport);document.body.append(viewer);
 viewer.addEventListener('close',()=>{document.body.style.overflow=previousOverflow;});
 function showSource(source){
  if(!/^\/static\/protocols\/(?:recapitulatif-[12]|cagrilintide-apercu|cagrilintide-tableau)\.png$/.test(source.file))return;
  image.src=documentPath(source.file);image.alt=source.title;previousOverflow=document.body.style.overflow;viewer.showModal();document.body.style.overflow='hidden';setZoom(viewport.clientWidth);viewport.scrollTo(0,0);
 }
 function render(){
  browse.hidden=false;detail.hidden=true;categories.replaceChildren();list.replaceChildren();
  const query=normalize(search.value),tokens=query.split(' ').filter(Boolean);
  categories.hidden=Boolean(selected||query);
  if(!selected&&!query){
   data.categories.forEach(cat=>{
    const count=data.entries.filter(entry=>entry.category===cat.id).length;
    const card=button('','',()=>{selected=cat.id;render();list.scrollIntoView({block:'start'});});card.dataset.category=cat.id;
    const icon=el('span','category-menu-icon',cat.icon);icon.setAttribute('aria-hidden','true');const label=el('span');label.append(el('b','',cat.label),el('small','',count+' fiches'));card.append(icon,label,el('em','','›'));categories.append(card);
   });
   list.append(el('p','protocol-note','Les fiches reprennent les documents fournis. Les sources originales sont accessibles dans chaque fiche.'));
   return;
  }
  const back=button('‹ Toutes les catégories','shop-secondary',()=>{selected='';search.value='';render();});
  const cat=data.categories.find(cat=>cat.id===selected);
  const shown=data.entries.filter(entry=>(!selected||entry.category===selected)&&tokens.every(token=>normalize([entry.title,entry.reference,entry.aliases].join(' ')).includes(token)));
  const head=el('div','protocol-list-head');head.append(back,el('h2','',cat?cat.label:'Résultats de recherche'),el('p','protocol-note',shown.length+' fiche'+(shown.length!==1?'s':'')));list.append(head);
  if(!shown.length){list.append(el('p','card pad','Aucune fiche trouvée. Essayez un autre nom ou revenez à toutes les catégories.'));return;}
  const grid=el('div','protocol-products');
  shown.forEach(entry=>{
   const card=button('','protocol-product card',()=>open(entry,card));card.dataset.protocol=entry.id;
   const glyph=el('span','protocol-vial');glyph.setAttribute('aria-hidden','true');
   const parts=entry.title.match(/^(.*?)\s+(\d+(?:[.,]\d+)?(?:\+\d+(?:[.,]\d+)?)?\s*mg)$/i);
   glyph.innerHTML=vial({name:parts?parts[1]:entry.title,format:parts?parts[2]:''});
   const text=el('span','protocol-product-copy');text.append(el('strong','',entry.title),el('small','','Réf. '+entry.reference),el('span','protocol-read','Consulter la fiche ›'));card.append(glyph,text);grid.append(card);
  });list.append(grid);
 }
 function open(entry,trigger){
  previousScroll=window.scrollY;opener=trigger;browse.hidden=true;detail.hidden=false;detail.replaceChildren();
  const back=button('‹ Retour aux produits','shop-secondary',()=>{detail.hidden=true;browse.hidden=false;window.scrollTo(0,previousScroll);opener?.focus({preventScroll:true});});
  const cat=data.categories.find(cat=>cat.id===entry.category),sources=data.sources.filter(source=>entry.sourceIds?entry.sourceIds.includes(source.id):source.page!==undefined&&source.page===entry.sourcePage);
  const title=el('h2','protocol-title',entry.title);title.tabIndex=-1;
  detail.append(back,el('p','eyebrow protocol-category',cat?.fullLabel||''),title,el('p','protocol-note','Réf. '+entry.reference+' · '+(entry.sourceLabel||sources[0]?.title||'Document NyxPepz')));
  const notice=el('div','protocol-source-note');notice.append(el('b','','Récapitulatif du document fourni'),el('p','',entry.notice||'Transcription du guide NyxPepz, sans validation médicale. Ce résumé ne remplace pas un avis médical personnalisé ni la fiche complète du produit, non fournie ici.'));detail.append(notice);
  const blocks=[['01','Flacon → mélange',entry.mix+(entry.concentration?'\n'+entry.concentration:'')],['02','Dose de départ',entry.start],['03','Ensuite',entry.then],['04','Rythme & moment',entry.rhythm]];
  blocks.forEach(([number,label,text])=>{const card=el('article','card protocol-block');const heading=el('h3');heading.append(el('span','protocol-step',number),document.createTextNode(label));card.append(heading,el('p','',text));detail.append(card);});
  detail.append(el('p','protocol-note','Notation du document : U = unités sur une seringue U-100 (100 U = 1 mL).'));
  const footnote=el('details','protocol-footnote');footnote.append(el('summary','','Notes du document fourni'));
  (entry.notes||['Les « max » de ce tableau sont des limites, pas des objectifs. La plupart des gens trouvent leur équilibre à la dose cible, et n’ont aucun intérêt à viser le maximum.']).forEach(note=>{const paragraph=el('p','',note);paragraph.style.whiteSpace='pre-line';footnote.append(paragraph);});detail.append(footnote);
  sources.forEach(source=>detail.append(button(source.page?'Voir le tableau original · page '+source.page:'Voir l’original : '+source.title,'shop-secondary protocol-original',()=>showSource(source))));
  window.scrollTo(0,root.offsetTop);title.focus({preventScroll:true});
 }
 search.addEventListener('input',render);
 function load(){
  list.textContent='Chargement des fiches…';
  fetch('/static/protocols.json?v=11.8').then(response=>{if(!response.ok)throw Error('load');return response.json();}).then(result=>{
   if(!Array.isArray(result.categories)||!Array.isArray(result.entries)||!Array.isArray(result.sources))throw Error('format');
   data=result;render();
  }).catch(()=>{list.replaceChildren(el('p','protocol-note','Les fiches n’ont pas pu être chargées.'),button('Réessayer','shop-secondary',load));});
 }
 load();
})();
