/* Original owner-supplied reports, matched by product AND labelled format. */
(()=>{
 const manifestURL='/static/coa.json?v=1';
 const normalizeName=value=>String(value||'').normalize('NFKC').toLowerCase().replace(/[‐‑–—]/g,'-').replace(/\s+/g,' ').trim();
 const normalizeFormat=value=>{
  const match=String(value||'').trim().match(/^(\d+(?:[.,]\d+)?)\s*mg$/i);
  return match?Number(match[1].replace(',','.'))+' mg':null;
 };
 let reports=[],opener=null,previousOverflow='',zoomFactor=1,currentReport=null;
 const make=(tag,className,text)=>{const node=document.createElement(tag);if(className)node.className=className;if(text!==undefined)node.textContent=text;return node;};
 const button=(id,label,action)=>{const node=make('button','',label);node.id=id;node.type='button';node.onclick=action;return node;};
 const viewer=make('dialog','coa-viewer');viewer.id='coaViewer';viewer.setAttribute('aria-labelledby','coaTitle');viewer.setAttribute('aria-describedby','coaMeta');
 const heading=make('div','coa-heading'),title=make('h2','','Certificat d’analyse');title.id='coaTitle';
 const close=button('coaClose','Fermer',()=>viewer.close());close.setAttribute('aria-label','Fermer le COA');heading.append(title,close);
 const meta=make('p','coa-meta');meta.id='coaMeta';
 const tools=make('div','coa-tools'),zoomOut=button('coaZoomOut','−',()=>setZoom(zoomFactor/1.4)),fit=button('coaFit','Ajuster',()=>{setZoom(1);viewport.scrollTo(0,0);}),zoomIn=button('coaZoomIn','＋',()=>setZoom(zoomFactor*1.4));
 zoomOut.setAttribute('aria-label','Réduire le COA');zoomIn.setAttribute('aria-label','Agrandir le COA');
 const download=make('a','coa-download','Télécharger');download.id='coaDownload';download.setAttribute('download','');
 tools.append(zoomOut,fit,zoomIn,download);
 const status=make('p','coa-status');status.id='coaStatus';status.setAttribute('role','status');
 const retry=button('coaRetry','Réessayer',()=>loadImage());retry.hidden=true;
 const viewport=make('div','coa-viewport'),image=make('img');image.id='coaImage';image.draggable=false;viewport.append(image);
 viewer.append(heading,meta,tools,status,retry,viewport);document.body.append(viewer);
 function setZoom(factor){
  zoomFactor=Math.max(1,Math.min(4,factor));
  image.style.width=Math.round(viewport.clientWidth*zoomFactor)+'px';
  zoomOut.disabled=zoomFactor<=1;zoomIn.disabled=zoomFactor>=4;
 }
 function loadImage(){
  if(!currentReport)return;
  status.hidden=false;status.textContent='Chargement du COA…';retry.hidden=true;image.hidden=true;
  image.src=currentReport.file;
 }
 image.onload=()=>{status.hidden=true;retry.hidden=true;image.hidden=false;setZoom(zoomFactor);};
 image.onerror=()=>{status.hidden=false;status.textContent='Le document n’a pas pu être chargé. Réessayez.';retry.hidden=false;image.hidden=true;};
 viewer.addEventListener('close',()=>{document.body.style.overflow=previousOverflow;opener?.focus({preventScroll:true});currentReport=null;});
 window.addEventListener('resize',()=>{if(viewer.open)setZoom(zoomFactor);});
 function openReport(report,trigger){
  currentReport=report;opener=trigger;title.textContent=report.title+' · COA';
  meta.textContent='Rapport n° '+report.report+' · Lot du rapport : '+report.batch+' · Analyse du '+report.analysis_date;
  image.alt='Rapport d’analyse '+report.title+' — lot '+report.batch;
  download.href=report.file;download.download=report.file.split('/').pop();
  previousOverflow=document.body.style.overflow;viewer.showModal();document.body.style.overflow='hidden';setZoom(1);viewport.scrollTo(0,0);loadImage();close.focus();
 }
 function addButtons(){
  document.querySelectorAll('#products .product[data-product-id]').forEach(card=>{
   if(card.querySelector('.coa-button'))return;
   const product=products.find(item=>String(item.id)===card.dataset.productId);if(!product)return;
   const format=normalizeFormat(product.format);if(!format)return;
   const report=reports.find(item=>normalizeFormat(item.format)===format&&item.names.some(name=>normalizeName(name)===normalizeName(product.name)));
   if(!report)return;
   const link=button('','Voir le COA',()=>openReport(report,link));link.removeAttribute('id');link.className='coa-button';link.dataset.coa=report.id;link.setAttribute('aria-label','Voir le COA — '+report.title);card.append(link);
  });
 }
 const originalRender=renderCatalog;
 renderCatalog=function(...args){originalRender(...args);addButtons();};
 fetch(manifestURL).then(response=>{if(!response.ok)throw Error('manifest');return response.json();}).then(result=>{
  if(!Array.isArray(result))throw Error('manifest');
  reports=result.filter(item=>Array.isArray(item.names)&&item.names.length&&normalizeFormat(item.format)&&/^\/static\/coa\/[a-z0-9-]+\.png$/.test(item.file));addButtons();
 }).catch(()=>{/* A missing report list must not interrupt shopping. */});
})();
