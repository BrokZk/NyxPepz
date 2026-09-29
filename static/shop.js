/* Commerce UI. The server owns prices, rewards, stock and payment state. */
(()=>{
 const money=c=>new Intl.NumberFormat('fr-FR',{style:'currency',currency:'EUR'}).format((c||0)/100);
 let settings=null,cart=[],cartOwner=null,lastQuote=null,checkoutKey=null,checkoutPayload=null,busy=false;
 const originalGo=go,originalRender=renderCatalog;
 const statusText={awaiting_payment:'En attente de paiement',payment_review:'Paiement reçu — vérification',paid:'Payée',shipped:'Expédiée',available:'Disponible au point de retrait',delivered:'Livrée',cancelled:'Annulée',expired:'Réservation expirée'};
 const $id=id=>document.getElementById(id);
 function loadCart(){
  const owner=me.telegram_id;if(!owner||owner===cartOwner)return;
  cartOwner=owner;
  try{const saved=JSON.parse(localStorage.getItem('nyx-cart-'+owner)||'[]');cart=Array.isArray(saved)?saved.filter(x=>((Number.isInteger(x.product_id)&&x.product_id>0&&!('pack_id' in x))||(Number.isInteger(x.pack_id)&&x.pack_id>0&&!('product_id' in x)))&&Number.isInteger(x.quantity)&&x.quantity>0&&x.quantity<=99):[];}catch{cart=[];}
 }
 function saveCart(){
  if(cartOwner)try{localStorage.setItem('nyx-cart-'+cartOwner,JSON.stringify(cart));}catch{}
  lastQuote=null;checkoutKey=null;checkoutPayload=null;updateBadge();
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
 go=function(id){originalGo(id);if(id==='cart'){loadCart();renderCart();loadCheckoutProfile();}if(id==='loyalty'){freshAccount();updateLoyalty();}if(id==='orders'||id==='parcels')loadOrders(id);if(id==='admin')loadAdminOrders();};
 function linesHTML(lines){return lines.map(x=>`<div class="checkout-line"><span><b>${escapeHTML(x.name)}</b><small>${escapeHTML(x.format||'')} · Quantité ${x.quantity}</small></span><strong>${money(x.line_cents)}</strong></div>`).join('');}
 function summaryHTML(q){return `<div class="total-row"><span>Produits</span><b>${money(q.subtotal_cents)}</b></div>${q.discount_cents?`<div class="total-row reward-saving"><span>Récompense (${q.reward_points} points)</span><b>− ${money(q.discount_cents)}</b></div>`:''}<div class="total-row"><span>Livraison</span><b>${money(q.shipping_cents)}</b></div><div class="total-row grand-total"><span>Total à payer</span><strong>${money(q.total_cents)}</strong></div>`;}
 function renderCart(){
  updateBadge();$id('checkoutReview').hidden=true;$id('checkoutForm').hidden=!cart.length;$id('cartList').innerHTML='';
  if(!cart.length){$id('cartList').innerHTML='<div class="card pad empty-state">Votre panier est vide.<button class="shop-primary" id="startShopping">Découvrir la boutique</button></div>';$id('startShopping').onclick=()=>go('catalog');return;}
  for(const item of cart){
   const p=catalogItems().find(x=>x.kind===(item.pack_id?'pack':'product')&&x.id===(item.pack_id||item.product_id));const el=document.createElement('article');el.className='cart-item card';
   el.innerHTML=`<div><h2>${escapeHTML(p?.name||'Produit indisponible')}</h2><p>${escapeHTML(p?.format||'')}</p><strong>${p?money(p.price*100*item.quantity):'—'}</strong>${!p||p.stock<item.quantity?'<small class="shop-error">Quantité indisponible : modifiez votre panier.</small>':''}</div><div class="quantity-control"><button type="button" data-change="-1" aria-label="Diminuer la quantité">−</button><span>${item.quantity}</span><button type="button" data-change="1" aria-label="Augmenter la quantité" ${!p||item.quantity>=p.stock||item.quantity>=99?'disabled':''}>＋</button><button type="button" data-remove aria-label="Retirer le produit">Retirer</button></div>`;
   el.querySelectorAll('[data-change]').forEach(b=>b.onclick=()=>{item.quantity+=Number(b.dataset.change);cart=cart.filter(x=>x.quantity>0);saveCart();renderCart();});el.querySelector('[data-remove]').onclick=()=>{cart=cart.filter(x=>x!==item);saveCart();renderCart();};$id('cartList').append(el);
  }
  renderRewardOptions();updateShipping();
 }
 function renderRewardOptions(){const selected=$id('checkoutReward').value;$id('checkoutReward').innerHTML='<option value="0">Conserver mes points</option>'+(settings?.rewards||[]).map(r=>`<option value="${r.points}" ${Number(me.loyalty_points||0)<r.points?'disabled':''}>${r.points} points → ${money(r.discount_cents)} de réduction</option>`).join('');if([...$id('checkoutReward').options].some(x=>x.value===selected&&!x.disabled))$id('checkoutReward').value=selected;}
 function updateShipping(){const code=$id('checkoutCountry').value;const fee=settings?.countries?.find(c=>c.code===code)?.shipping_cents??({FR:500,BE:500,ES:1000}[code]);$id('shippingHint').textContent=fee==null?'Choisissez votre pays de livraison.':'Frais d’envoi : '+money(fee);lastQuote=null;$id('checkoutReview').hidden=true;}
 async function loadCheckoutProfile(){try{const data=await api('/api/shop/profile');const form=$id('checkoutForm');for(const [key,value] of Object.entries(data.contact||{})){const input=form.elements.namedItem(key);if(input&&!input.value)input.value=value;}if(data.has_referrer){$id('checkoutReferral').value='';$id('checkoutReferral').disabled=true;$id('referralHint').textContent='Votre parrain est déjà associé à votre compte.';}else{$id('checkoutReferral').disabled=false;$id('referralHint').textContent='Facultatif : vous pouvez commander sans parrain.';}updateShipping();}catch(e){$id('checkoutNotice').textContent=e.message;}}
 $id('checkoutCountry').addEventListener('change',updateShipping);
 $id('checkoutReward').addEventListener('change',()=>{$id('checkoutReview').hidden=true;lastQuote=null;});
 $id('checkoutForm').addEventListener('input',()=>{$id('checkoutReview').hidden=true;lastQuote=null;});
 $id('checkoutForm').addEventListener('submit',async event=>{
  event.preventDefault();if(busy)return;busy=true;$id('reviewOrder').disabled=true;
  try{
   const form=$id('checkoutForm'),contact=Object.fromEntries(new FormData(form));delete contact.referral_code;delete contact.reward_points;
   const reward=Number($id('checkoutReward').value);
   lastQuote=await api('/api/shop/quote',{method:'POST',body:JSON.stringify({items:cart,country:contact.country,reward_points:reward})});
   const payload={items:cart.map(x=>({...x})),contact,referral_code:$id('checkoutReferral').disabled?'':$id('checkoutReferral').value.trim(),reward_points:reward,quote_hash:lastQuote.quote_hash};
   if(JSON.stringify(payload)!==JSON.stringify(checkoutPayload)){checkoutKey=crypto.randomUUID();checkoutPayload=payload;}
   $id('reviewContent').innerHTML=linesHTML(lastQuote.lines)+summaryHTML(lastQuote)+`<p class="delivery-summary">${escapeHTML(contact.first_name)} ${escapeHTML(contact.last_name)}<br>${escapeHTML(contact.address)}<br>${escapeHTML(contact.postal_code)} ${escapeHTML(contact.city)} · ${escapeHTML(contact.country)}</p>`;
   $id('checkoutReview').hidden=false;$id('confirmOrder').disabled=!(settings?.enabled&&settings?.payment_enabled);$id('reviewNotice').textContent=settings?.enabled&&settings?.payment_enabled?'Votre commande sera réservée pendant une heure. Les points seront crédités après validation du paiement.':'Les commandes et le paiement ne sont pas encore ouverts.';$id('checkoutReview').scrollIntoView({behavior:'smooth',block:'start'});
  }catch(e){toast(e.message);}finally{busy=false;$id('reviewOrder').disabled=false;}
 });
 async function openPayment(reference){
  const result=await api('/api/shop/orders/'+encodeURIComponent(reference)+'/pay',{method:'POST',body:'{}'});
  const link=new URL(result.url);if(link.protocol!=='https:'||link.hostname!=='checkout.paygate.to')throw Error('Lien de paiement non reconnu');
  if(tg?.openLink)tg.openLink(link.href);else location.assign(link.href);
 }
 $id('confirmOrder').onclick=async()=>{
  if(busy||!lastQuote||!checkoutPayload)return;busy=true;$id('confirmOrder').disabled=true;
  try{
   const data=await api('/api/shop/orders',{method:'POST',headers:{'Idempotency-Key':checkoutKey},body:JSON.stringify(checkoutPayload)});
   cart=[];saveCart();await freshAccount();go('orders');
   if(tg?.requestWriteAccess&&!tg?.initDataUnsafe?.user?.allows_write_to_pm)await new Promise(resolve=>tg.requestWriteAccess(()=>resolve()));
   try{await openPayment(data.order.reference);}catch(e){toast(e.message+' Vous pouvez reprendre le paiement dans Mes commandes.');}
  }catch(e){toast(e.message);}finally{busy=false;$id('confirmOrder').disabled=false;}
 };
 async function loadOrders(page='orders'){
  const target=$id(page==='parcels'?'parcelOrders':'orderList');target.innerHTML='<p class="empty-state">Chargement…</p>';
  try{let orders=await api('/api/shop/orders');if(page==='parcels')orders=orders.filter(o=>o.tracking_number);target.innerHTML=orders.length?'':'<div class="card pad empty-state">'+(page==='parcels'?'Aucun colis expédié pour le moment.':'Vous n’avez pas encore de commande.')+'</div>';
   for(const o of orders){const el=document.createElement('article');el.className='order-card card';el.innerHTML=`<small>${escapeHTML(o.reference)}</small><h2>${escapeHTML(o.status_label)}</h2>${linesHTML(o.lines)}${summaryHTML(o)}${o.tracking_number?`<p>Suivi : <b>${escapeHTML(o.tracking_number)}</b></p><a target="_blank" rel="noopener" href="https://www.mondialrelay.fr/suivi-de-colis/">Ouvrir le suivi Mondial Relay ↗</a>`:''}<div class="order-actions">${o.can_pay?'<button class="shop-primary" data-pay>Reprendre le paiement</button>':''}${o.status==='awaiting_payment'?'<button class="shop-secondary" data-cancel>Annuler la commande</button>':''}</div>`;
    if(el.querySelector('[data-pay]'))el.querySelector('[data-pay]').onclick=async e=>{e.target.disabled=true;try{await openPayment(o.reference);}catch(err){toast(err.message);}finally{e.target.disabled=false;}};
    if(el.querySelector('[data-cancel]'))el.querySelector('[data-cancel]').onclick=async()=>{if(!confirm('Annuler cette commande en attente ?'))return;try{await api('/api/shop/orders/'+encodeURIComponent(o.reference)+'/cancel',{method:'POST',body:'{}'});await freshAccount();loadOrders(page);}catch(e){toast(e.message);}};target.append(el);
   }
  }catch(e){target.innerHTML='<p class="empty-state">'+escapeHTML(e.message)+'</p>';}
 }
 $id('refreshOrders').onclick=()=>loadOrders();$id('refreshParcels').onclick=()=>loadOrders('parcels');
 $id('parcelManual').onsubmit=e=>{e.preventDefault();const number=$id('parcelNumber').value.trim();if(!/^[A-Za-z0-9-]{4,64}$/.test(number)){toast('Numéro de suivi invalide');return;}$id('parcelManualHint').textContent='Numéro saisi : '+number+' — recopiez-le sur le site Mondial Relay.';$id('parcelExternalLink').hidden=false;};
 let adminGroup='action',adminCursor=null,adminRequest=0;
 const orderToolbar=document.createElement('div');orderToolbar.className='order-filters';
 orderToolbar.innerHTML=[['action','À traiter'],['shipping','En livraison'],['history','Historique']].map(([id,label])=>`<button type="button" data-order-group="${id}" aria-pressed="${id===adminGroup}">${label}</button>`).join('');
 $id('adminShopOrders').before(orderToolbar);
 orderToolbar.querySelectorAll('button').forEach(b=>b.onclick=()=>{adminGroup=b.dataset.orderGroup;loadAdminOrders();});
 const olderButton=document.createElement('button');olderButton.className='shop-secondary';olderButton.textContent='Afficher la suite';olderButton.hidden=true;olderButton.onclick=()=>loadAdminOrders(true);$id('adminShopOrders').after(olderButton);
 async function loadAdminOrders(append=false){
  const requestId=++adminRequest;
  orderToolbar.querySelectorAll('button').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.orderGroup===adminGroup)));
  olderButton.hidden=true;
  const target=$id('adminShopOrders');if(!append){adminCursor=null;target.innerHTML='<p>Chargement des commandes…</p>';} 
  try{const data=await api('/api/shop/admin/orders?group='+adminGroup+(append&&adminCursor?'&before='+adminCursor:''));if(requestId!==adminRequest)return;const orders=Array.isArray(data)?data:data.orders;adminCursor=data.next_before;olderButton.hidden=!adminCursor;if(!append)target.innerHTML=orders.length?'':'<p>Aucune commande dans cette rubrique.</p>';for(const o of orders){const el=document.createElement('article');el.className='order-card';el.innerHTML=`<small>${escapeHTML(o.reference)}</small><h3>${escapeHTML(o.status_label)} · ${money(o.total_cents)}</h3><p>${escapeHTML(o.contact.first_name)} ${escapeHTML(o.contact.last_name)} ${o.username?'(@'+escapeHTML(o.username)+')':''}<br>${escapeHTML(o.contact.email)} · ${escapeHTML(o.contact.phone)}<br>${escapeHTML(o.contact.address)} ${escapeHTML(o.contact.address_extra)}<br>${escapeHTML(o.contact.postal_code)} ${escapeHTML(o.contact.city)} ${escapeHTML(o.contact.country)}</p>${linesHTML(o.lines)}${summaryHTML(o)}<small>${o.sync_pending} envoi(s) en attente</small>${o.payments.map(x=>`<p class="payment-evidence">Reçu : ${escapeHTML(x.amount)} ${escapeHTML(x.coin)}<br>Versé : ${escapeHTML(x.forwarded_amount)}<br>Transaction : ${escapeHTML(x.transaction_id)}</p>`).join('')}${o.status==='payment_review'?'<button data-confirm class="shop-primary">Vérifier et valider le paiement</button>':''}${['paid','shipped','available'].includes(o.status)?'<button data-shipping class="shop-secondary">Mettre à jour la livraison</button>':''}`;
   if(el.querySelector('[data-confirm]'))el.querySelector('[data-confirm]').onclick=async()=>{const total=prompt('Après vérification chez PayGate, quel montant total le client a-t-il payé en EUR ?');if(total===null)return;const note=prompt('Référence de votre vérification du paiement :');if(!note)return;try{await api('/api/shop/admin/orders/'+encodeURIComponent(o.reference)+'/confirm-payment',{method:'POST',body:JSON.stringify({confirmed_total_cents:Math.round(Number(total.replace(',','.'))*100),note})});toast('Paiement validé');loadAdminOrders();}catch(e){toast(e.message);}};
   if(el.querySelector('[data-shipping]'))el.querySelector('[data-shipping]').onclick=async()=>{const tracking=prompt('Numéro Mondial Relay :',o.tracking_number||'');if(!tracking)return;const status=prompt('Statut : shipped (expédié), available (disponible au retrait), delivered (livré)',o.status==='paid'?'shipped':o.status==='shipped'?'available':'delivered');if(!status)return;try{await api('/api/shop/admin/orders/'+encodeURIComponent(o.reference)+'/shipping',{method:'POST',body:JSON.stringify({tracking_number:tracking,status})});loadAdminOrders();}catch(e){toast(e.message);}};target.append(el);}
  }catch(e){target.textContent=e.message;}
 }
 $id('refreshAdminOrders').onclick=()=>loadAdminOrders();
 $id('allowNotifications').onclick=()=>{if(tg?.requestWriteAccess)tg.requestWriteAccess(allowed=>toast(allowed?'Notifications Telegram autorisées':'Vous pouvez consulter les nouvelles dans Mes commandes.'));else toast('Ouvrez une conversation avec le bot dans Telegram pour recevoir ses messages.');};
 const loyal=document.querySelector('.loyal');loyal.setAttribute('role','button');loyal.tabIndex=0;loyal.setAttribute('aria-label','Voir mes points et mes récompenses');loyal.onclick=()=>go('loyalty');loyal.onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();go('loyalty');}};
 document.addEventListener('visibilitychange',()=>{if(!document.hidden&&$id('orders').classList.contains('active'))loadOrders();});
 api('/api/shop/config').then(data=>{settings=data;updateLoyalty();$id('checkoutNotice').textContent=data.enabled?'':'La prise de commande est en préparation. Vous pouvez préparer votre panier.';}).catch(()=>{$id('checkoutNotice').textContent='Le service commande est indisponible pour le moment.';});
})();
