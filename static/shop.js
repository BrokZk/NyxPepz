/* Commerce UI. The server owns prices, rewards, stock and payment state. */
(()=>{
 const money=c=>new Intl.NumberFormat('fr-FR',{style:'currency',currency:'EUR'}).format((c||0)/100);
 let settings=null,cart=[],cartOwner=null,lastQuote=null,checkoutKey=null,checkoutPayload=null,checkoutChoice=null,busy=false;
 let appliedGift=null,giftCheckoutKey=null,giftCheckoutPayload=null;
 const originalGo=go,originalRender=renderCatalog;
 const statusText={awaiting_payment:'En attente de paiement',payment_review:'Paiement reçu — vérification',paid:'Payée',gifted:'Offerte',shipped:'Expédiée',available:'Disponible au point de retrait',delivered:'Livrée',cancelled:'Annulée',expired:'Réservation expirée'};
 const $id=id=>document.getElementById(id);
 function loadCart(){
  const owner=me.telegram_id;if(!owner||owner===cartOwner)return;
  cartOwner=owner;
  try{const saved=JSON.parse(localStorage.getItem('nyx-cart-'+owner)||'[]');cart=Array.isArray(saved)?saved.filter(x=>((Number.isInteger(x.product_id)&&x.product_id>0&&!('pack_id' in x))||(Number.isInteger(x.pack_id)&&x.pack_id>0&&!('product_id' in x)))&&Number.isInteger(x.quantity)&&x.quantity>0&&x.quantity<=99):[];}catch{cart=[];}
 }
 function saveCart(){
  clearGift();
  if(cartOwner)try{localStorage.setItem('nyx-cart-'+cartOwner,JSON.stringify(cart));}catch{}
  lastQuote=null;checkoutKey=null;checkoutPayload=null;checkoutChoice=null;updateBadge();
 }
 function updateBadge(){const count=cart.reduce((sum,x)=>sum+x.quantity,0);$id('cartCount').textContent=count||'';$id('cartCount').hidden=!count;}
 function updateLoyalty(){
  const points=Number(me.loyalty_points||0),tiers=[150,300,500,750],next=tiers.find(t=>t>points);
  const small=document.querySelector('.loyal small');
  if(small)small.innerHTML=next?`Encore <span id="remaining">${next-points}</span> points jusqu’au prochain palier`:'<span id="remaining">Récompenses disponibles</span> · Voir mes avantages';
  if($id('progressbar'))$id('progressbar').style.width=Math.min(100,points/(next||750)*100)+'%';
  $id('loyaltyBalance').textContent=points+' points';
  const rewards=settings?.rewards||[{points:150,discount_cents:1000},{points:300,discount_cents:2500},{points:500,discount_cents:5000},{points:750,discount_cents:8000}];
  $id('rewardTiers').innerHTML=rewards.map(r=>`<div class="reward-tier ${points>=r.points?'unlocked':''}"><b>${r.points} points</b><strong>${money(r.discount_cents)}</strong><small>${points>=r.points?'Disponible':r.points-points+' points restants'}</small></div>`).join('');
 }
 async function freshAccount(){try{me=await api('/api/me');$id('points').textContent=me.loyalty_points;$id('profilePoints').textContent=me.loyalty_points;$id('refpoints2').textContent=me.referral_points;updateLoyalty();}catch{}}
 renderCatalog=function(...args){originalRender(...args);loadCart();updateBadge();updateLoyalty();
  document.querySelectorAll('#products .product').forEach((el,i)=>{
   const kind=el.hasAttribute('data-pack-id')?'pack':'product';
   const id=Number(el.dataset.packId||el.dataset.productId);
   const product=catalogItems().find(p=>p.kind===kind&&p.id===id);if(!product)return;
   const key=kind==='pack'?'pack_id':'product_id';
   const button=document.createElement('button');button.className='add-to-cart';button.type='button';button.disabled=product.stock<=0;button.textContent=product.stock>0?'＋ Ajouter au panier':'Indisponible';
   button.onclick=()=>{loadCart();const item=cart.find(x=>x[key]===product.id);if((item?.quantity||0)>=Math.min(product.stock,99)){toast('Stock disponible atteint');return;}if(item)item.quantity++;else cart.push({[key]:product.id,quantity:1});saveCart();toast('Produit ajouté au panier');};el.append(button);
  });
 };
 go=function(id){if(busy&&$id('cart').classList.contains('active')){toast('Enregistrement en cours…');return;}originalGo(id);if(id==='cart'){loadCart();renderCart();loadCheckoutProfile();}if(id==='loyalty'){freshAccount();updateLoyalty();}if(id==='orders'||id==='parcels')loadOrders(id);};
 const originalBack=goBack;goBack=function(){if(busy&&$id('cart').classList.contains('active')){toast('Enregistrement en cours…');return;}originalBack();};$id('cart').querySelector('.page-back').onclick=()=>goBack();
 function linesHTML(lines){return lines.map(x=>`<div class="checkout-line"><span><b>${escapeHTML(x.name)}</b><small>${escapeHTML(x.format||'')} · Quantité ${x.quantity}</small></span><strong>${money(x.line_cents)}</strong></div>`).join('');}
 function summaryHTML(q){if(q.is_gift)return `<div class="total-row"><span>Produits</span><b>Offerts</b></div><div class="total-row"><span>Livraison</span><b>Offerte</b></div><div class="total-row grand-total"><span>Total de la commande</span><strong>${money(0)}</strong></div>`;return `<div class="total-row"><span>Produits</span><b>${money(q.subtotal_cents)}</b></div>${q.discount_cents?`<div class="total-row reward-saving"><span>Récompense (${q.reward_points} points)</span><b>− ${money(q.discount_cents)}</b></div>`:''}<div class="total-row"><span>Livraison</span><b>${money(q.shipping_cents)}</b></div><div class="total-row grand-total"><span>Total à payer</span><strong>${money(q.total_cents)}</strong></div>`;}
 function paymentGuideHTML(expanded=false){return `<details class="payment-guide" ${expanded?'open':''}><summary>Comment payer avec PayGate ?</summary><p class="payment-intro">Votre paiement par carte passe par un prestataire externe qui le convertit en cryptomonnaie pour régler la commande.</p><ol class="payment-steps"><li><b>Ouvrez PayGate</b><span>Vérifiez le montant de votre commande en euros.</span></li><li><b>Choisissez votre prestataire</b><span>Si Coinbase est proposé et que vous avez déjà un compte vérifié, il peut être pratique. Banxa est une autre option lorsqu’il apparaît. Comparez les frais et le total affichés.</span></li><li><b>Connectez-vous ou renseignez vos coordonnées</b><span>Avec Coinbase, connectez-vous ou créez votre compte. Avec Banxa, suivez les étapes et renseignez les informations demandées.</span></li><li><b>Vérifiez votre identité (KYC)</b><span>Suivez les instructions du prestataire si une vérification est demandée : pièce d’identité et, parfois, selfie. Ces documents se transmettent uniquement sur son site.</span></li><li><b>Payez avec votre carte personnelle</b><span>Vérifiez le montant final, confirmez le paiement et validez la demande de votre banque si elle apparaît. Revenez ensuite dans « Mes commandes » pour suivre la validation.</span></li></ol><p class="payment-footnote">Les options et les frais dépendent notamment du pays, du montant et du prestataire. Une commande est payée après réception et validation du paiement.</p><div class="payment-sources"><a href="https://help.coinbase.com/en/coinbase/trading-and-funding/coinbase-pay/using-onramp" target="_blank" rel="noopener noreferrer">Aide Coinbase ↗</a><a href="https://support.banxa.com/en/support/solutions/articles/44002201291-banxa-customer-journey" target="_blank" rel="noopener noreferrer">Aide Banxa ↗</a></div></details>`;}
 function updatePaymentChoices(){
  updateGiftView();
  $id('confirmOrder').disabled=busy||!(settings?.enabled&&settings?.payment_enabled)||(checkoutChoice!==null&&checkoutChoice!=='paygate');
  $id('requestOtherPayment').disabled=busy||!(settings?.enabled&&settings?.payment_help_available)||(checkoutChoice!==null&&checkoutChoice!=='contact');
  $id('otherPaymentNotice').textContent=settings?.payment_help_available?'Enregistrez votre commande et demandez à être recontacté sur Telegram ou avec vos coordonnées. Aucun paiement n’est effectué par ce bouton.':'La demande de contact est momentanément indisponible.';
 }
 function paymentHelpHTML(order){
  if(!order.payment_help_requested||!['awaiting_payment','payment_review'].includes(order.status))return '';
  return `<div class="payment-help-status" role="status"><b>Autre moyen de paiement demandé</b><span>${order.status==='awaiting_payment'?'Votre demande est enregistrée. NyxPepz vous recontactera sur Telegram ou avec les coordonnées de votre commande. Le paiement reste à effectuer.':'Une demande de contact a été enregistrée pour cette commande.'}</span></div>`;
 }
 function adminPaymentHelpHTML(order){
  if(!order.payment_help_requested||!['awaiting_payment','payment_review'].includes(order.status))return '';
  const username=typeof order.username==='string'&&/^[A-Za-z0-9_]{5,32}$/.test(order.username)?order.username:null;
  const id=String(order.telegram_id||'');
  const contactURL=username?'https://t.me/'+username:/^[0-9]+$/.test(id)?'tg://user?id='+id:null;
  return `<div class="payment-help-status"><b>Autre moyen de paiement demandé</b><span>${order.status==='awaiting_payment'?'Client à recontacter · paiement en attente.':'Demande de contact enregistrée.'}</span>${contactURL?`<a class="shop-secondary" href="${contactURL}" target="_blank" rel="noopener noreferrer">Contacter le client sur Telegram ↗</a>`:''}</div>`;
 }

 function giftMatches(gift){
  const normalize=items=>items.map(x=>({product_id:x.product_id,quantity:x.quantity})).sort((a,b)=>a.product_id-b.product_id);
  return cart.length===gift.lines.length&&cart.every(x=>Number.isInteger(x.product_id)&&!x.pack_id)&&JSON.stringify(normalize(cart))===JSON.stringify(normalize(gift.lines));
 }
 function clearGift(){appliedGift=null;giftCheckoutKey=null;giftCheckoutPayload=null;updateGiftView();}
 function updateGiftView(){
  const gift=!!appliedGift,form=$id('checkoutForm');
  for(const id of ['checkoutReward','checkoutReferral','checkoutAmbassador'])$id(id).closest('label').hidden=gift;
  const discovery=form.elements.namedItem('discovery');discovery.closest('label').hidden=gift;discovery.required=!gift;
  for(const option of $id('checkoutCountry').options){const labels={FR:'France',BE:'Belgique',ES:'Espagne'};if(labels[option.value])option.textContent=labels[option.value]+(gift?' — offerte':option.value==='ES'?' — 10 €':' — 5 €');}
  $id('checkoutPaymentGuide').hidden=gift;$id('confirmOrder').hidden=gift;$id('requestOtherPayment').closest('.payment-alternative').hidden=gift;
  $id('confirmGiftOrder').hidden=!gift;$id('confirmGiftOrder').disabled=busy;
  $id('reviewOrder').textContent=gift?'Vérifier mon cadeau · 0 €':'Vérifier ma commande';
  $id('cartGiftApply').disabled=busy;$id('cartGiftCode').disabled=busy||gift;$id('cartGiftApply').hidden=gift;$id('cartGiftRemove').hidden=!gift;$id('cartGiftRemove').disabled=busy;
  $id('cartGiftNotice').textContent=gift?'Code appliqué : '+appliedGift.lines.map(x=>x.quantity+' × '+x.name+' '+(x.format||'')).join(', ')+'. Produits et livraison : 0 €.':'Ajoutez le produit gagné au panier, puis saisissez votre code personnel. Le lot et sa livraison seront offerts.';
  $id('cartGiftForm').classList.toggle('gift-applied',gift);
  document.querySelectorAll('#cartList .cart-item').forEach((row,index)=>{
   const item=cart[index],p=item&&catalogItems().find(x=>x.kind===(item.pack_id?'pack':'product')&&x.id===(item.pack_id||item.product_id));
   row.querySelector('strong').textContent=gift?'Offert · '+money(0):p?money(p.price*100*item.quantity):'—';
   row.querySelectorAll('[data-change],[data-remove]').forEach(b=>{b.disabled=busy||(b.dataset.change==='1'&&(!p||item.quantity>=p.stock||item.quantity>=99));});
  });
  if(gift)$id('shippingHint').textContent='Livraison offerte · Total de votre cadeau : 0 €';
 }
 async function applyGift(code){
  if(busy)return;loadCart();busy=true;updateGiftView();
  try{
   const data=await api('/api/shop/gifts/lookup',{method:'POST',body:JSON.stringify({code:code.trim()})});
   if(data.gift.status==='claimed')throw Error('Ce cadeau a déjà été utilisé. Retrouvez la commande dans Mes commandes.');
   if(!data.gift.can_claim)throw Error('Ce code cadeau n’est pas utilisable actuellement.');
   if(!giftMatches(data.gift))throw Error('Ce code offre uniquement : '+data.gift.lines.map(x=>x.quantity+' × '+x.name+' '+(x.format||'')).join(', ')+'. Ajustez votre panier avec ces produits et quantités, sans autre article.');
   appliedGift=data.gift;giftCheckoutKey=null;giftCheckoutPayload=null;lastQuote=null;$id('checkoutReview').hidden=true;$id('cartGiftCode').value=data.gift.code;toast('Lot et livraison offerts : 0 €');
  }catch(e){$id('cartGiftNotice').textContent=e.message;throw e;}
  finally{busy=false;const message=$id('cartGiftNotice').textContent;updateGiftView();if(!appliedGift)$id('cartGiftNotice').textContent=message;}
 }
 $id('cartGiftForm').onsubmit=e=>{e.preventDefault();applyGift($id('cartGiftCode').value).catch(()=>{});};
 $id('cartGiftRemove').onclick=()=>{if(busy)return;clearGift();$id('checkoutReview').hidden=true;updateShipping();};
 $id('confirmGiftOrder').onclick=async()=>{
  if(busy||!appliedGift||!giftCheckoutPayload)return;
  busy=true;updatePaymentChoices();$id('reviewOrder').disabled=true;const gift=appliedGift;
  try{
   await api('/api/shop/gifts/'+gift.id+'/claim',{method:'POST',headers:{'Idempotency-Key':giftCheckoutKey},body:JSON.stringify(giftCheckoutPayload)});
   cart=[];saveCart();busy=false;go('orders');toast('Cadeau confirmé. Votre commande est offerte.');
   try{products=await api('/api/catalog');renderCatalog();}catch{}
  }catch(e){toast(e.message+' Vous pouvez réessayer ou vérifier Mes commandes.');$id('reviewNotice').textContent=e.message+' Si la réponse a été interrompue, réessayez : le même cadeau ne peut être commandé qu’une seule fois.';}
  finally{busy=false;$id('reviewOrder').disabled=false;updatePaymentChoices();}
 };
 window.NyxShopGifts={openCode:code=>{go('cart');if(!$id('cart').classList.contains('active'))return;$id('cartGiftCode').value=code;$id('cartGiftForm').scrollIntoView({block:'start',behavior:'instant'});applyGift(code).catch(()=>{});}};

 $id('checkoutPaymentGuide').innerHTML=paymentGuideHTML(true);
 function renderCart(){
  updateBadge();updateGiftView();$id('checkoutReview').hidden=true;$id('checkoutForm').hidden=!cart.length;$id('cartList').innerHTML='';
  if(!cart.length){$id('cartList').innerHTML='<div class="card pad empty-state">Votre panier est vide.<button class="shop-primary" id="startShopping">Découvrir la boutique</button></div>';$id('startShopping').onclick=()=>go('catalog');return;}
  for(const item of cart){
   const p=catalogItems().find(x=>x.kind===(item.pack_id?'pack':'product')&&x.id===(item.pack_id||item.product_id));const el=document.createElement('article');el.className='cart-item card';
   el.innerHTML=`<div><h2>${escapeHTML(p?.name||'Produit indisponible')}</h2><p>${escapeHTML(p?.format||'')}</p><strong>${p?money(p.price*100*item.quantity):'—'}</strong>${!p||p.stock<item.quantity?'<small class="shop-error">Quantité indisponible : modifiez votre panier.</small>':''}</div><div class="quantity-control"><button type="button" data-change="-1" aria-label="Diminuer la quantité">−</button><span>${item.quantity}</span><button type="button" data-change="1" aria-label="Augmenter la quantité" ${!p||item.quantity>=p.stock||item.quantity>=99?'disabled':''}>＋</button><button type="button" data-remove aria-label="Retirer le produit">Retirer</button></div>`;
   el.querySelectorAll('[data-change]').forEach(b=>b.onclick=()=>{if(busy)return;item.quantity+=Number(b.dataset.change);cart=cart.filter(x=>x.quantity>0);saveCart();renderCart();});el.querySelector('[data-remove]').onclick=()=>{if(busy)return;cart=cart.filter(x=>x!==item);saveCart();renderCart();};$id('cartList').append(el);
  }
  renderRewardOptions();updateShipping();
 }
 function renderRewardOptions(){const selected=$id('checkoutReward').value;$id('checkoutReward').innerHTML='<option value="0">Conserver mes points</option>'+(settings?.rewards||[]).map(r=>`<option value="${r.points}" ${Number(me.loyalty_points||0)<r.points?'disabled':''}>${r.points} points → ${money(r.discount_cents)} de réduction</option>`).join('');if([...$id('checkoutReward').options].some(x=>x.value===selected&&!x.disabled))$id('checkoutReward').value=selected;}
 function updateShipping(){const code=$id('checkoutCountry').value;const fee=settings?.countries?.find(c=>c.code===code)?.shipping_cents??({FR:500,BE:500,ES:1000}[code]);$id('shippingHint').textContent=fee==null?'Choisissez votre pays de livraison.':'Frais d’envoi : '+money(fee);lastQuote=null;$id('checkoutReview').hidden=true;updateGiftView();}
 async function loadCheckoutProfile(){try{const data=await api('/api/shop/profile');const form=$id('checkoutForm');for(const [key,value] of Object.entries(data.contact||{})){const input=form.elements.namedItem(key);if(input&&!input.value)input.value=value;}if(data.has_referrer){$id('checkoutReferral').value='';$id('checkoutReferral').disabled=true;$id('referralHint').textContent='Votre parrain est déjà associé à votre compte.';}else{$id('checkoutReferral').disabled=false;$id('referralHint').textContent='Facultatif : vous pouvez commander sans parrain.';}updateShipping();}catch(e){$id('checkoutNotice').textContent=e.message;}}
 $id('checkoutCountry').addEventListener('change',updateShipping);
 $id('checkoutReward').addEventListener('change',()=>{$id('checkoutReview').hidden=true;lastQuote=null;});
 $id('checkoutForm').addEventListener('input',()=>{$id('checkoutReview').hidden=true;lastQuote=null;});
 $id('checkoutForm').addEventListener('submit',async event=>{
  event.preventDefault();if(busy)return;busy=true;$id('reviewOrder').disabled=true;
  try{
   const form=$id('checkoutForm'),contact=Object.fromEntries(new FormData(form));delete contact.referral_code;delete contact.reward_points;
   if(appliedGift){
    if(!giftMatches(appliedGift))throw Error('Le panier doit contenir uniquement les produits et quantités du lot offert.');
    contact.discovery='Lot offert / concours';
    const payload={items:cart.map(x=>({...x})),contact};
    if(JSON.stringify(payload)!==JSON.stringify(giftCheckoutPayload)){giftCheckoutKey=crypto.randomUUID();giftCheckoutPayload=payload;}
    $id('reviewContent').innerHTML=linesHTML(appliedGift.lines.map(x=>({...x,line_cents:0})))+summaryHTML({is_gift:true})+`<p class="delivery-summary">${escapeHTML(contact.first_name)} ${escapeHTML(contact.last_name)}<br>${escapeHTML(contact.address)}<br>${escapeHTML(contact.postal_code)} ${escapeHTML(contact.city)} · ${escapeHTML(contact.country)}</p>`;
    $id('reviewNotice').textContent='Votre lot et la livraison sont offerts. Aucun paiement ne sera demandé.';
    $id('checkoutReview').hidden=false;updateGiftView();$id('checkoutReview').scrollIntoView({behavior:'smooth',block:'start'});return;
   }
   const reward=Number($id('checkoutReward').value);
   lastQuote=await api('/api/shop/quote',{method:'POST',body:JSON.stringify({items:cart,country:contact.country,reward_points:reward})});
   const payload={items:cart.map(x=>({...x})),contact,referral_code:$id('checkoutReferral').disabled?'':$id('checkoutReferral').value.trim(),ambassador_code:$id('checkoutAmbassador').value.trim(),reward_points:reward,quote_hash:lastQuote.quote_hash};
   if(JSON.stringify(payload)!==JSON.stringify(checkoutPayload)){checkoutKey=crypto.randomUUID();checkoutPayload=payload;checkoutChoice=null;}
   $id('reviewContent').innerHTML=linesHTML(lastQuote.lines)+summaryHTML(lastQuote)+`<p class="delivery-summary">${escapeHTML(contact.first_name)} ${escapeHTML(contact.last_name)}<br>${escapeHTML(contact.address)}<br>${escapeHTML(contact.postal_code)} ${escapeHTML(contact.city)} · ${escapeHTML(contact.country)}</p>`;
   $id('checkoutReview').hidden=false;$id('reviewNotice').textContent=settings?.enabled?'Votre commande sera réservée pendant une heure, quel que soit votre choix. Les points seront crédités après validation du paiement.':'Les commandes ne sont pas encore ouvertes.';$id('checkoutReview').scrollIntoView({behavior:'smooth',block:'start'});
  }catch(e){toast(e.message);}finally{busy=false;$id('reviewOrder').disabled=false;updatePaymentChoices();}
 });
 async function openPayment(reference){
  const result=await api('/api/shop/orders/'+encodeURIComponent(reference)+'/pay',{method:'POST',body:'{}'});
  const link=new URL(result.url);if(link.protocol!=='https:'||link.hostname!=='checkout.paygate.to')throw Error('Lien de paiement non reconnu');
  if(tg?.openLink)tg.openLink(link.href);else location.assign(link.href);
 }
 async function confirmCheckout(choice){
  if(busy||!lastQuote||!checkoutPayload)return;
  if(checkoutChoice&&checkoutChoice!==choice){toast('Réessayez avec le même choix ou consultez Mes commandes pour retrouver votre demande.');return;}
  checkoutChoice=choice;busy=true;updatePaymentChoices();
  try{
   const data=await api('/api/shop/orders',{method:'POST',headers:{'Idempotency-Key':checkoutKey},body:JSON.stringify({...checkoutPayload,payment_choice:choice})});
   cart=[];saveCart();await freshAccount();busy=false;go('orders');
   if(choice==='contact'){toast('Demande enregistrée. NyxPepz vous recontactera pour le paiement.');return;}
   if(tg?.requestWriteAccess&&!tg?.initDataUnsafe?.user?.allows_write_to_pm)await new Promise(resolve=>tg.requestWriteAccess(()=>resolve()));
   try{await openPayment(data.order.reference);}catch(e){toast(e.message+' Vous pouvez reprendre le paiement dans Mes commandes.');}
  }catch(e){toast(e.message);}finally{busy=false;updatePaymentChoices();}
 }
 $id('confirmOrder').onclick=()=>confirmCheckout('paygate');
 $id('requestOtherPayment').onclick=()=>confirmCheckout('contact');
 async function loadOrders(page='orders'){
  const target=$id(page==='parcels'?'parcelOrders':'orderList');target.innerHTML='<p class="empty-state">Chargement…</p>';
  try{let orders=await api('/api/shop/orders');if(page==='parcels')orders=orders.filter(o=>o.tracking_number);target.innerHTML=orders.length?'':'<div class="card pad empty-state">'+(page==='parcels'?'Aucun colis expédié pour le moment.':'Vous n’avez pas encore de commande.')+'</div>';
   for(const o of orders){const el=document.createElement('article');el.className='order-card card';el.innerHTML=`<small>${escapeHTML(o.reference)}</small><h2>${escapeHTML(o.status_label)}</h2>${o.is_gift?'<span class="gift-order-badge">Cadeau · offert</span>':''}${linesHTML(o.lines)}${summaryHTML(o)}${o.tracking_number?`<p>Suivi : <b>${escapeHTML(o.tracking_number)}</b></p><a target="_blank" rel="noopener" href="https://www.mondialrelay.fr/suivi-de-colis/">Ouvrir le suivi Mondial Relay ↗</a>`:''}<div class="order-actions">${o.can_pay?'<button class="shop-primary" data-pay>Reprendre le paiement</button>':''}${o.status==='awaiting_payment'?'<button class="shop-secondary" data-cancel>Annuler la commande</button>':''}</div>`;
    const actions=el.querySelector('.order-actions');
    if(o.status==='awaiting_payment'&&Number.isFinite(o.expires_at)){const expiry=document.createElement('p');expiry.className='shop-notice';expiry.textContent='Articles réservés jusqu’au '+new Intl.DateTimeFormat('fr-FR',{day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'}).format(new Date(o.expires_at*1000))+'.';actions.before(expiry);}
    const assistance=document.createElement('div');assistance.innerHTML=paymentHelpHTML(o)+(o.can_pay?paymentGuideHTML():'');actions.before(assistance);
    if(o.can_request_payment_help){const help=document.createElement('button');help.type='button';help.className='shop-secondary';help.textContent='Demander un autre moyen de paiement';help.dataset.paymentHelp='';actions.prepend(help);help.onclick=async()=>{help.disabled=true;try{await api('/api/shop/orders/'+encodeURIComponent(o.reference)+'/payment-help',{method:'POST',body:'{}'});await loadOrders(page);toast('Demande enregistrée. NyxPepz vous recontactera.');}catch(e){toast(e.message);}finally{help.disabled=false;}};}
    if(el.querySelector('[data-pay]'))el.querySelector('[data-pay]').onclick=async e=>{e.target.disabled=true;try{await openPayment(o.reference);}catch(err){toast(err.message);}finally{e.target.disabled=false;}};
    if(el.querySelector('[data-cancel]'))el.querySelector('[data-cancel]').onclick=async()=>{if(!confirm('Annuler cette commande en attente ?'))return;try{await api('/api/shop/orders/'+encodeURIComponent(o.reference)+'/cancel',{method:'POST',body:'{}'});await freshAccount();loadOrders(page);}catch(e){toast(e.message);}};target.append(el);
   }
  }catch(e){target.innerHTML='<p class="empty-state">'+escapeHTML(e.message)+'</p>';}
 }
 $id('refreshOrders').onclick=()=>loadOrders();$id('refreshParcels').onclick=()=>loadOrders('parcels');
 $id('parcelManual').onsubmit=e=>{e.preventDefault();const number=$id('parcelNumber').value.trim();if(!/^[A-Za-z0-9-]{4,64}$/.test(number)){toast('Numéro de suivi invalide');return;}$id('parcelManualHint').textContent='Numéro saisi : '+number+' — recopiez-le sur le site Mondial Relay.';$id('parcelExternalLink').hidden=false;};
 $id('allowNotifications').onclick=()=>{if(tg?.requestWriteAccess)tg.requestWriteAccess(allowed=>toast(allowed?'Notifications Telegram autorisées':'Vous pouvez consulter les nouvelles dans Mes commandes.'));else toast('Ouvrez une conversation avec le bot dans Telegram pour recevoir ses messages.');};
 const loyal=document.querySelector('.loyal');loyal.setAttribute('role','button');loyal.tabIndex=0;loyal.setAttribute('aria-label','Voir mes points et mes récompenses');loyal.onclick=()=>go('loyalty');loyal.onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();go('loyalty');}};
 document.addEventListener('visibilitychange',()=>{if(!document.hidden&&$id('orders').classList.contains('active'))loadOrders();});
 api('/api/shop/config').then(data=>{settings=data;updateLoyalty();updatePaymentChoices();$id('checkoutNotice').textContent=data.enabled?'':'La prise de commande est en préparation. Vous pouvez préparer votre panier.';}).catch(()=>{$id('checkoutNotice').textContent='Le service commande est indisponible pour le moment.';updatePaymentChoices();});
})();
