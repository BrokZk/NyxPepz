/* Arithmetic conversion only; no suggested dose, schedule or reconstitution protocol. */
(function(){
 'use strict';
 function decimal(value){
  const text=String(value??'').trim().replace(',','.');
  if(!/^(?:\d+(?:\.\d*)?|\.\d+)$/.test(text))return NaN;
  return Number(text);
 }
 function calculate({mass,volume,dose,unit,scale,capacity}){
  const values=[mass,volume,dose].map(decimal),[mg,ml,amount]=values;
  if(values.some(n=>!Number.isFinite(n)||n<=0||n>1000000))return {error:'Saisissez trois valeurs positives valides.'};
  if(!['mcg','mg'].includes(unit)||![100,50,40].includes(Number(scale)))return {error:'Vérifiez les unités sélectionnées.'};
  const doseMg=unit==='mcg'?amount/1000:amount;
  if(doseMg>mg)return {error:'La quantité demandée dépasse la quantité totale du flacon.'};
  const concentration=mg/ml,volumeMl=doseMg/concentration,mark=volumeMl*Number(scale);
  if(![concentration,volumeMl,mark].every(n=>Number.isFinite(n)&&n>=1e-8))return {error:'Valeurs hors de la précision de ce calculateur.'};
  if(capacity!==''&&capacity!=null){
   const max=decimal(capacity);
   if(![0.3,0.5,1].includes(max))return {error:'Capacité de seringue invalide.'};
   if(volumeMl>max+1e-12)return {error:'Le volume calculé dépasse la capacité de la seringue sélectionnée. Faites vérifier les valeurs.'};
  }
  return {concentration,volumeMl,mark,doseMg,scale:Number(scale)};
 }
 if(typeof module!=='undefined'&&module.exports)module.exports={calculate,decimal};
 if(typeof document==='undefined')return;
 const form=document.getElementById('conversionForm');if(!form)return;
 const result=document.getElementById('conversionResult'),hint=document.getElementById('conversionHint');
 const format=n=>new Intl.NumberFormat('fr-FR',{maximumSignificantDigits:8}).format(n);
 let unit='mcg',scale=100;
 const syringe=document.createElement('div');syringe.className='syringe-preview';
 syringe.innerHTML='<div class="syringe-heading"><strong>Seringue graduée</strong><span data-syringe-size></span></div><svg viewBox="0 0 480 160" role="img" aria-label="Seringue vide"><defs><linearGradient id="syringe-liquid" x2="0" y2="1"><stop stop-color="#72ddff"/><stop offset="1" stop-color="#387aff"/></linearGradient></defs><path d="M8 84H52" stroke="#b5c8e0" stroke-width="3"/><path d="M52 77H70V91H52Z" fill="#c88442"/><rect x="70" y="58" width="300" height="52" rx="5" fill="#081427" stroke="#8aa5cb" stroke-width="2"/><rect data-syringe-liquid x="70" y="60" width="300" height="48" fill="url(#syringe-liquid)"/><g data-syringe-ticks></g><path d="M376 47V121" stroke="#8aa5cb" stroke-width="7" stroke-linecap="round"/><g data-syringe-piston><rect x="71" y="62" width="8" height="44" rx="2" fill="#e5efff"/><path d="M79 84H134M134 65V103" stroke="#91b4e3" stroke-width="6" stroke-linecap="round"/></g><text x="220" y="147" text-anchor="middle" fill="#a9c1e5" font-size="14">Graduations en unités</text></svg><p data-syringe-reading role="status" aria-live="polite"></p><small>Schéma indicatif : vérifiez les graduations réelles de votre matériel.</small>';
 result.after(syringe);
 const drawing=syringe.querySelector('svg'),liquid=syringe.querySelector('[data-syringe-liquid]'),piston=syringe.querySelector('[data-syringe-piston]'),ticks=syringe.querySelector('[data-syringe-ticks]'),reading=syringe.querySelector('[data-syringe-reading]');
 let drawnScale='';
 function renderSyringe(data){
  const capacity=decimal(form.elements.capacity.value||'1'),max=capacity*scale,key=scale+':'+capacity;
  syringe.querySelector('[data-syringe-size]').textContent=`U‑${scale} · ${format(capacity)} mL · ${format(max)} unités`;
  if(drawnScale!==key){
   const minor=max>=100?2:1,step=max>=100?10:max>=30?5:2;
   drawnScale=key;ticks.innerHTML=Array.from({length:Math.round(max/minor)+1},(_,i)=>{const value=i*minor,x=70+value/max*300,major=value%step===0||value===max;return `<line x1="${x}" x2="${x}" y1="58" y2="${major?77:67}" stroke="#b8cce7" stroke-width="${major?1.5:1}"/>${major?`<text x="${x}" y="44" text-anchor="middle" fill="#cdddf4" font-size="14">${format(value)}</text>`:''}`;}).join('');
  }
  const overflow=data&&!data.error&&data.volumeMl>capacity+1e-12;
  const valid=data&&!data.error&&!overflow;
  const fraction=valid?Math.min(1,data.volumeMl/capacity):0;
  liquid.style.transform=`scaleX(${fraction})`;piston.style.transform=`translateX(${fraction*300}px)`;
  syringe.classList.toggle('syringe-invalid',Boolean(data?.error||overflow));
  reading.textContent=overflow?'Le volume dépasse cette seringue : aucun remplissage représenté.':data?.error?'Vérifiez les valeurs pour afficher le remplissage.':valid?`${format(data.mark)} unités = ${format(data.volumeMl)} mL`:'Le remplissage apparaîtra avec votre calcul.';
  drawing.setAttribute('aria-label',valid?`Seringue U-${scale} de ${format(capacity)} mL, repère théorique ${format(data.mark)} unités`:'Seringue sans résultat valide');
  syringe.dataset.fraction=String(fraction);
 }
 function refresh(){
  result.hidden=true;result.replaceChildren();hint.classList.remove('shop-error');
  const mass=form.elements.mass.value,volume=form.elements.volume.value,dose=form.elements.dose.value;
  if(!mass.trim()||!volume.trim()||!dose.trim()){hint.textContent='Renseignez les trois valeurs pour afficher la conversion.';renderSyringe(null);return;}
  const data=calculate({mass,volume,dose,unit,scale,capacity:form.elements.capacity.value});
  renderSyringe(data);
  if(data.error){hint.textContent=data.error;hint.classList.add('shop-error');return;}
  hint.textContent='Résultat mathématique : faites valider la concentration, la dose et le matériel par un professionnel de santé.';
  result.innerHTML=`<small>VOLUME CALCULÉ</small><strong>${format(data.volumeMl)} mL</strong><div class="conversion-mark">Repère théorique : <b>${format(data.mark)}</b> sur l’échelle U‑${scale}</div><p>Concentration : ${format(data.concentration)} mg/mL<br>Dose saisie : ${format(data.doseMg)} mg</p><small>Affichage arrondi à 8 chiffres significatifs. Ne pas arrondir à une graduation de seringue sans validation professionnelle.</small>`;
  result.hidden=false;
 }
 form.addEventListener('submit',e=>e.preventDefault());form.addEventListener('input',refresh);form.addEventListener('change',refresh);
 document.querySelectorAll('[data-dose-unit]').forEach(b=>b.onclick=()=>{
  const next=b.dataset.doseUnit;
  if(next!==unit){const value=decimal(form.elements.dose.value);if(Number.isFinite(value)&&value>0)form.elements.dose.value=String(Number((next==='mg'?value/1000:value*1000).toPrecision(12)));unit=next;}
  document.querySelectorAll('[data-dose-unit]').forEach(x=>x.setAttribute('aria-pressed',String(x.dataset.doseUnit===unit)));
  document.getElementById('doseUnitLabel').textContent=unit;refresh();
 });
 document.querySelectorAll('[data-syringe-scale]').forEach(b=>b.onclick=()=>{
  scale=Number(b.dataset.syringeScale);document.querySelectorAll('[data-syringe-scale]').forEach(x=>x.setAttribute('aria-pressed',String(Number(x.dataset.syringeScale)===scale)));refresh();
 });
 document.getElementById('conversionReset').onclick=()=>{form.reset();refresh();};
 refresh();
})();
