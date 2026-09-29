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
 function refresh(){
  result.hidden=true;result.replaceChildren();hint.classList.remove('shop-error');
  const mass=form.elements.mass.value,volume=form.elements.volume.value,dose=form.elements.dose.value;
  if(!mass.trim()||!volume.trim()||!dose.trim()){hint.textContent='Renseignez les trois valeurs pour afficher la conversion.';return;}
  const data=calculate({mass,volume,dose,unit,scale,capacity:form.elements.capacity.value});
  if(data.error){hint.textContent=data.error;hint.classList.add('shop-error');return;}
  hint.textContent='Résultat mathématique : faites valider la concentration, la dose et le matériel par un professionnel de santé.';
  result.innerHTML=`<small>VOLUME CALCULÉ</small><strong>${format(data.volumeMl)} mL</strong><div class="conversion-mark">Repère théorique : <b>${format(data.mark)}</b> sur l’échelle U‑${scale}</div><p>Concentration : ${format(data.concentration)} mg/mL<br>Quantité saisie : ${format(data.doseMg)} mg</p><small>Affichage arrondi à 8 chiffres significatifs. Ne pas arrondir à une graduation de seringue sans validation professionnelle.</small>`;
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
