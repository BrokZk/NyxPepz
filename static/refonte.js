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


/* Decorative 3D reconstruction: double helix rotates around its longitudinal axis.
   No business APIs, storage, form handlers or network dependencies. */
(()=>{
 const bg=document.querySelector('.bg');if(!bg||bg.querySelector('.nyx-living-scene'))return;
 const canvas=document.createElement('canvas');canvas.className='nyx-living-scene';canvas.setAttribute('aria-hidden','true');bg.append(canvas);
 const ctx=canvas.getContext('2d',{alpha:true});if(!ctx){canvas.remove();return;}
 let w=0,h=0,ratio=1,frame=0,last=0,time=0;
 const TAU=Math.PI*2;
 const particles=Array.from({length:48},(_,i)=>({x:(i*.6180339)%1,y:(i*.4142135)%1,z:(i%7)/7,r:.7+(i%4)*.6,phase:i*1.7}));
 const atoms=[[0,0,0],[24,8,10],[-20,14,-8],[5,-23,14],[38,-9,-9],[-34,-8,12]];
 const bonds=[[0,1],[0,2],[0,3],[1,4],[2,5]];
 // Fixed glass microtexture, rendered once and reused at every projected depth.
 function glassSprite(violet){
  const c=document.createElement('canvas');c.width=c.height=128;const g=c.getContext('2d');
  const base=violet?'114,99,242':'38,154,232';
  let grad=g.createRadialGradient(45,35,3,64,64,59);
  grad.addColorStop(0,'rgba(223,249,255,.92)');grad.addColorStop(.2,`rgba(${base},.46)`);grad.addColorStop(.55,'rgba(13,48,102,.24)');grad.addColorStop(.85,`rgba(${base},.58)`);grad.addColorStop(.97,'rgba(165,224,255,.8)');grad.addColorStop(1,'rgba(18,57,130,0)');
  g.fillStyle=grad;g.beginPath();g.arc(64,64,59,0,TAU);g.fill();
  g.save();g.beginPath();g.arc(64,64,56,0,TAU);g.clip();
  for(let i=0;i<75;i++){const x=14+(i*37.73)%100,y=14+(i*61.39)%100,r=.8+(i%6)*.6;g.strokeStyle=`rgba(146,216,255,${.11+(i%4)*.045})`;g.lineWidth=.7;g.beginPath();g.arc(x,y,r,0,TAU);g.stroke();}
  for(let i=0;i<9;i++){g.strokeStyle='rgba(113,203,255,.11)';g.lineWidth=.8;g.beginPath();g.ellipse(64,64,18+i*4,52,.3+i*.17,0,TAU);g.stroke();}
  g.restore();g.strokeStyle='rgba(219,249,255,.82)';g.lineWidth=2.1;g.beginPath();g.arc(64,64,53,3.55,5.05);g.stroke();
  g.strokeStyle='rgba(94,194,255,.4)';g.lineWidth=2;g.beginPath();g.arc(64,64,48,.15,1.4);g.stroke();
  grad=g.createRadialGradient(43,29,0,43,29,12);grad.addColorStop(0,'rgba(246,255,255,.88)');grad.addColorStop(1,'rgba(192,241,255,0)');g.fillStyle=grad;g.fillRect(28,14,30,30);
  return c;
 }
 const sprites=[glassSprite(false),glassSprite(true)];
 function resize(){w=Math.min(innerWidth,1000);h=innerHeight;ratio=Math.min(devicePixelRatio||1,1.5);canvas.width=Math.round(w*ratio);canvas.height=Math.round(h*ratio);ctx.setTransform(ratio,0,0,ratio,0,0);}
 function project(x,y,z){
  // Tilt the axis, then project perspective. Rotation occurs before this tilt.
  const tilt=.24,rx=x*Math.cos(tilt)-y*Math.sin(tilt),ry=x*Math.sin(tilt)+y*Math.cos(tilt);
  const depth=900/(900-z);return{x:w*.76+rx*depth,y:h*.43+ry*depth,z,scale:depth};
 }
 function cylinder(a,b,width,violet,alpha){
  const dx=b.x-a.x,dy=b.y-a.y,len=Math.hypot(dx,dy);if(len<.01)return;
  const nx=-dy/len*width*.5,ny=dx/len*width*.5;
  const g=ctx.createLinearGradient((a.x+b.x)*.5-nx,(a.y+b.y)*.5-ny,(a.x+b.x)*.5+nx,(a.y+b.y)*.5+ny);
  g.addColorStop(0,violet?'#382b89':'#06396a');g.addColorStop(.3,violet?'#8756df':'#228dd3');g.addColorStop(.46,'#c5eeff');g.addColorStop(.63,violet?'#794fe0':'#54baff');g.addColorStop(1,'#061a39');
  ctx.globalAlpha=alpha;ctx.lineWidth=width;ctx.strokeStyle=g;ctx.lineCap='round';ctx.beginPath();ctx.moveTo(a.x,a.y);ctx.lineTo(b.x,b.y);ctx.stroke();ctx.globalAlpha=1;
 }
 function helix(){
  const radius=Math.min(w*.185,102),length=Math.min(h*1.38,1120),count=62,items=[],strands=[[],[]];
  const rotation=time*TAU/28;
  for(let i=0;i<count;i++){
   const t=i/(count-1),y=(t-.5)*length,phase=t*TAU*3.45+rotation;
   // Ends retain the natural tapered, fading silhouette of the reference.
   const taper=.7+.3*Math.sin(Math.PI*t),fade=Math.min(1,t*9,(1-t)*9);
   for(let strand=0;strand<2;strand++){
    const a=phase+strand*Math.PI,p=project(Math.cos(a)*radius*taper,y,Math.sin(a)*radius*taper);
    p.r=(Math.min(18,w*.046))*taper*p.scale;p.alpha=fade*(.44+.36*(p.z/radius+1)/2);p.violet=strand===1&&i%5<2;
    strands[strand].push(p);items.push({z:p.z,type:'sphere',p});
    if(i){const prev=strands[strand][i-1];items.push({z:(p.z+prev.z)/2,type:'bond',a:prev,b:p,width:p.r*.64,violet:p.violet,alpha:fade*.6});}
   }
   if(i%2===0){const a=strands[0][i],b=strands[1][i];items.push({z:(a.z+b.z)/2,type:'bond',a,b,width:Math.max(2.5,Math.min(5,w*.012)),violet:true,alpha:fade*.64});}
  }
  items.sort((a,b)=>a.z-b.z).forEach(item=>{
   if(item.type==='bond')cylinder(item.a,item.b,item.width,item.violet,item.alpha);
   else{const p=item.p;ctx.globalAlpha=p.alpha;ctx.drawImage(sprites[p.violet?1:0],p.x-p.r,p.y-p.r,p.r*2,p.r*2);ctx.globalAlpha=1;}
  });
 }
 function sphere(x,y,r,opacity){const g=ctx.createRadialGradient(x-r*.3,y-r*.35,r*.08,x,y,r);g.addColorStop(0,`rgba(219,246,255,${opacity})`);g.addColorStop(.32,`rgba(83,191,255,${opacity*.85})`);g.addColorStop(.72,`rgba(21,76,152,${opacity*.65})`);g.addColorStop(1,`rgba(110,191,255,${opacity*.35})`);ctx.fillStyle=g;ctx.beginPath();ctx.arc(x,y,r,0,TAU);ctx.fill();}
 function molecule(index){
  const a=time*.19+index*2.4,b=time*.11+index,ca=Math.cos(a),sa=Math.sin(a),cb=Math.cos(b),sb=Math.sin(b);
  const centerX=w*(.15+index*.28)+Math.sin(time*.12+index)*18,centerY=((index*.34+time*.012)%1)*(h+160)-80;
  const points=atoms.map(([x,y,z])=>{const rx=x*ca+z*sa,rz=z*ca-x*sa,ry=y*cb-rz*sb,depth=y*sb+rz*cb,scale=200/(200-depth);return{x:centerX+rx*scale,y:centerY+ry*scale,z:depth,r:(index===1?6:4.5)*scale};});
  for(const [i,j] of bonds)cylinder(points[i],points[j],2.3,false,.38);
  points.sort((p,q)=>p.z-q.z).forEach(p=>sphere(p.x,p.y,p.r,.25+(p.z+40)/220));
 }
 function draw(now){
  frame=0;if(document.hidden)return;
  if(now-last<33){frame=requestAnimationFrame(draw);return;}
  time+=last?Math.min((now-last)/1000,.1):0;last=now;ctx.clearRect(0,0,w,h);
  helix();
  for(const p of particles){const x=(p.x*w+Math.sin(time*.19+p.phase)*18+w)%w,y=(p.y*h-time*(3+p.z*7)+h*100)%h,r=p.r*(.7+p.z),alpha=.18+.2*(.5+.5*Math.sin(time*.8+p.phase));ctx.fillStyle=`rgba(111,203,255,${alpha})`;ctx.beginPath();ctx.arc(x,y,r,0,TAU);ctx.fill();if(p.z>.7){ctx.strokeStyle=`rgba(103,181,255,${alpha*.35})`;ctx.lineWidth=.6;ctx.beginPath();ctx.moveTo(x-5,y);ctx.lineTo(x+5,y);ctx.moveTo(x,y-5);ctx.lineTo(x,y+5);ctx.stroke();}}
  for(let i=0;i<3;i++)molecule(i);
  bg.classList.add('nyx-living-ready');frame=requestAnimationFrame(draw);
 }
 addEventListener('resize',resize,{passive:true});
 document.addEventListener('visibilitychange',()=>{if(document.hidden){cancelAnimationFrame(frame);frame=0;}else{last=0;if(!frame)frame=requestAnimationFrame(draw);}});
 resize();frame=requestAnimationFrame(draw);
})();
