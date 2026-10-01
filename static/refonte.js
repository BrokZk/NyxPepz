/* Presentation only: shortcuts open existing catalogue categories. */
(()=>{
 document.querySelectorAll('[data-catalog-category]').forEach(button=>button.addEventListener('click',()=>{
  go('catalog');renderCatalog(button.dataset.catalogCategory);scrollTo({top:0,behavior:'instant'});
 }));

 const select=document.getElementById('checkoutAmbassador');
 const hint=document.getElementById('checkoutAmbassadorHint');
 const retry=document.getElementById('checkoutAmbassadorRetry');
 let loading=false,requested=false;
 async function loadAmbassadors(){
  if(!select||loading)return;
  loading=true;select.disabled=true;retry.hidden=true;hint.textContent='Chargement des ambassadeurs…';
  const selected=select.value;
  try{
   const data=await api('/api/ambassador/choices');
   const options=[new Option('Sans code ambassadeur','')];
   for(const ambassador of data.ambassadors||[])options.push(new Option(ambassador.name+' · '+ambassador.code,ambassador.code));
   select.replaceChildren(...options);
   if(data.locked&&options.length===2)select.value=options[1].value;
   else if(options.some(option=>option.value===selected))select.value=selected;
   select.disabled=!!data.locked||options.length===1;
   hint.textContent=data.notice||(options.length===1?'Aucun ambassadeur disponible. Vous pouvez commander sans code.':'Choisissez votre ambassadeur. Ce choix ne change pas le prix.');
  }catch{
   select.replaceChildren(new Option('Sans code ambassadeur',''));select.disabled=true;
   hint.textContent='La liste est indisponible. Réessayez ou continuez sans code ambassadeur.';retry.hidden=false;
  }finally{loading=false;}
 }
 if(select){
  select.addEventListener('change',()=>{document.getElementById('checkoutReview').hidden=true;});
  retry.addEventListener('click',loadAmbassadors);
  const cart=document.getElementById('cart');
  const picker=document.getElementById('nyxAmbassadorPicker');
  const cartList=document.getElementById('cartList');
  const showPicker=()=>{picker.hidden=!cartList.querySelector('.cart-item');};
  new MutationObserver(showPicker).observe(cartList,{childList:true,subtree:true});
  showPicker();
  new MutationObserver(()=>{
   if(cart.classList.contains('active')){if(!requested){requested=true;loadAmbassadors();}}
   else requested=false;
  }).observe(cart,{attributes:true,attributeFilter:['class']});
  if(cart.classList.contains('active')){requested=true;loadAmbassadors();}
 }
})();
