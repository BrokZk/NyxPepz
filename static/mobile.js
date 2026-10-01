/* Small local SVG icons and a projected, depth-sorted DNA illustration. */
(()=>{
 const icons={
 calendar:'<rect x="3" y="5" width="18" height="16" rx="3"/><path d="M7 2v6M17 2v6M3 11h18M7 15h2M13 15h2M7 18h2"/>',
 cart:'<path d="M2 3h3l3 12h11l3-9H6M9 19h.01M18 19h.01"/><circle cx="9" cy="20" r="1"/><circle cx="18" cy="20" r="1"/>',
 parcel:'<path d="m3 7 9-5 9 5v11l-9 5-9-5V7Zm0 0 9 5 9-5M12 12v11M7 5l10 5"/>',
 bag:'<path d="M5 7h14l1 14H4L5 7Z"/><path d="M8 8V6a4 4 0 0 1 8 0v2"/>',
 book:'<path d="M12 5C9 2 5 3 2 4v16c4-2 7-1 10 1 3-2 6-3 10-1V4c-3-1-7-2-10 1Z"/><path d="M12 5v16"/>',
 trophy:'<path d="M7 3h10v6a5 5 0 0 1-10 0V3ZM12 14v4M8 21v-3h8v3H8Z"/><path d="M7 5H3v3a4 4 0 0 0 4 4M17 5h4v3a4 4 0 0 1-4 4"/>',
 cap:'<path d="m2 8 10-5 10 5-10 5-10-5ZM6 10v7c4 3 8 3 12 0v-7M22 8v8"/>',
 users:'<circle cx="9" cy="7" r="4"/><path d="M2 21v-3a7 7 0 0 1 14 0v3H2ZM17 3a4 4 0 0 1 0 8M19 14a6 6 0 0 1 3 5v2h-3"/>',
 chart:'<path d="M5 20V12M12 20V7M19 20V2"/>',
 calculator:'<rect x="5" y="2" width="14" height="20" rx="3"/><path d="M8 6h8v4H8zM8 14h1M12 14h1M16 14h.01M8 18h1M12 18h1M16 17v2"/>',
 trend:'<path d="M3 3v18h18M6 9l5 4 4-6 6 3"/><circle cx="11" cy="13" r="1"/><circle cx="15" cy="7" r="1"/>',
 protocol:'<rect x="5" y="4" width="14" height="18" rx="2"/><rect x="9" y="2" width="6" height="4" rx="1"/><path d="m8 11 1 1 2-2M13 11h3m-8 6 1 1 2-2M13 17h3"/>',
 home:'<path d="m3 10 9-8 9 8v11h-6v-7H9v7H3V10Z"/>',
 user:'<circle cx="12" cy="7" r="4"/><path d="M4 21v-2a8 8 0 0 1 16 0v2H4Z"/>',
 star:'<path d="m12 2 3 6 7 1-5 5 1 7-6-3-6 3 1-7-5-5 7-1 3-6Z"/>',
 gift:'<path d="M3 11h18V7H3v4ZM5 11v10h14V11M12 7v14"/><path d="M12 7C4 8 4 1 8 2c2 0 4 5 4 5ZM12 7c8 1 8-6 4-5-2 0-4 5-4 5Z"/>'
 };
 document.querySelectorAll('[data-icon]').forEach(el=>{el.innerHTML=`<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">${icons[el.dataset.icon]||icons.star}</svg>`});
 document.querySelectorAll('input:not([type=file])').forEach(el=>{if(!el.hasAttribute('aria-label')&&!el.closest('label'))el.setAttribute('aria-label',el.placeholder||el.id)});
 const moon=document.querySelector('.brand-moon');
 if(moon)moon.innerHTML='<svg viewBox="0 0 48 48" aria-hidden="true"><defs><linearGradient id="moonLight" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#e1f9ff"/><stop offset=".35" stop-color="#7abaff"/><stop offset=".7" stop-color="#347aff"/><stop offset="1" stop-color="#1339be"/></linearGradient><mask id="moonCut"><circle cx="24" cy="24" r="20" fill="white"/><circle cx="15" cy="19" r="19.5" fill="black"/></mask></defs><circle cx="24" cy="24" r="20" fill="url(#moonLight)" mask="url(#moonCut)"/></svg>';

 // Decorative light ribbons: a small vector layer, separate from readable content.
 const backdrop=document.querySelector('.bg');
 if(backdrop){
  backdrop.setAttribute('aria-hidden','true');
  backdrop.innerHTML='<div class="sapphire-veils"><img class="veil-drift veil-image" src="/static/aurora-upper.svg?v=1" alt="" draggable="false"><img class="veil-drift veil-drift-low veil-image" src="/static/aurora-lower.svg?v=1" alt="" draggable="false"></div>';
 }
 const canvas=document.getElementById('dnaCanvas');if(!canvas)return;
 const scene=canvas.closest('.dna-scene');if(backdrop&&scene)backdrop.append(scene);
 const veils=backdrop&&backdrop.querySelector('.sapphire-veils');
 const ctx=canvas.getContext('2d');if(!ctx)return;
 document.documentElement.dataset.nyxMotion='on';

 // One display-synchronised loop. Only the decorative bitmap is resolution-capped;
 // text, product photographs and UI retain the screen's full resolution.
 let width=0,height=0,frame=null,last=null,angle=.65,elapsed=3;
 let needsResize=true,drawable=false,pageActive=true;
 let points=[],objects=[];
 const TAU=Math.PI*2,SPRITE_DPR=2;
 const particles=Array.from({length:16},(_,i)=>({x:((i*73+29)%281)/281,y:((i*43+19)%157)/157,size:i%4,speed:.06+(i%5)*.014,phase:i*2.1}));
 function texture(w,h,paint){
  const image=document.createElement('canvas');image.width=w*SPRITE_DPR;image.height=h*SPRITE_DPR;
  const brush=image.getContext('2d');brush.scale(SPRITE_DPR,SPRITE_DPR);paint(brush,w,h);return image;
 }
 // Tiny textures are painted once. No gradients or shadow blurs are allocated in draw().
 const sparkles=Array.from({length:4},(_,i)=>texture(32,32,(c)=>{
  c.fillStyle='#99ceff';c.shadowColor='#468fff';c.shadowBlur=i?14:0;
  c.beginPath();c.arc(16,16,.65+i*.3,0,TAU);c.fill();
 }));
 const atoms=[0,1].map(side=>texture(24,24,c=>{
  const r=12,g=c.createRadialGradient(r-r*.35,r-r*.4,r*.06,r,r,r);
  g.addColorStop(0,'#e7faff');g.addColorStop(.3,side?'#60c4ff':'#6ba0ff');g.addColorStop(1,'#062868');
  c.fillStyle=g;c.beginPath();c.arc(r,r,r,0,TAU);c.fill();
 }));
 const rung=texture(64,4,c=>{
  const g=c.createLinearGradient(0,0,64,0);
  g.addColorStop(0,'rgba(50,112,208,.45)');g.addColorStop(.48,'rgba(149,207,255,.63)');
  g.addColorStop(.52,'rgba(94,167,244,.63)');g.addColorStop(1,'rgba(26,120,190,.45)');
  c.fillStyle=g;c.fillRect(0,0,64,4);
 });
 function rebuildGeometry(){
  points=[];objects=[];
  // Keep the original helix phase but omit rows entirely outside the viewport.
  const start=8,end=Math.ceil((height+136)/12);
  for(let i=start;i<=end;i++){
   const row=[];
   for(let side=0;side<2;side++)row.push({x:0,y:0,z:0,baseY:-120+i*12,sin:Math.sin(i*.23),cos:Math.cos(i*.23),side});
   points.push(row);
   objects.push({type:0,a:row[0],b:row[1],z:0});
   for(let side=0;side<2;side++){
    if(points.length>1)objects.push({type:1,a:points[points.length-2][side],b:row[side],side,z:0});
    objects.push({type:2,a:row[side],side,z:0});
   }
  }
 }
 function resize(){
  needsResize=false;
  const rect=canvas.getBoundingClientRect();
  drawable=rect.width>0&&rect.height>0;if(!drawable)return;
  const nextWidth=rect.width,nextHeight=rect.height;
  const density=Math.min(window.devicePixelRatio||1,1.5,Math.sqrt(900000/(nextWidth*nextHeight)));
  const pixelsX=Math.max(1,Math.round(nextWidth*density)),pixelsY=Math.max(1,Math.round(nextHeight*density));
  if(nextWidth===width&&nextHeight===height&&canvas.width===pixelsX&&canvas.height===pixelsY)return;
  const changed=nextWidth!==width||nextHeight!==height;
  width=nextWidth;height=nextHeight;
  if(canvas.width!==pixelsX)canvas.width=pixelsX;
  if(canvas.height!==pixelsY)canvas.height=pixelsY;
  ctx.setTransform(pixelsX/width,0,0,pixelsY/height,0,0);
  ctx.lineCap='round';
  if(changed){
   rebuildGeometry();
   if(veils){
    const rect=veils.getBoundingClientRect(),padding=60*Math.max(rect.width/390,rect.height/844);
    veils.style.setProperty('--veil-padding',padding+'px');
   }
  }
 }
 function draw(){
  ctx.clearRect(0,0,width,height);
  for(const p of particles){
   const x=p.x*width+Math.sin(angle*.9+p.phase)*12;
   const y=(((p.y-angle*p.speed)%1+1)%1)*(height+32)-16;
   ctx.globalAlpha=.5+.2*Math.sin(angle+p.phase);
   ctx.drawImage(sparkles[p.size],x-16,y-16,32,32);
  }
  const radius=Math.min(32,width*.075),sin=Math.sin(angle),cos=Math.cos(angle);
  for(const row of points){
   const phaseCos=row[0].cos*cos-row[0].sin*sin,phaseSin=row[0].sin*cos+row[0].cos*sin;
   for(const p of row){
    const sign=p.side?-1:1,xx=phaseCos*radius*sign;
    p.z=phaseSin*radius*sign;p.x=width*(.86-.70*p.baseY/height)+xx*240/(240-p.z);p.y=p.baseY+xx*.27;
   }
  }
  for(const obj of objects)obj.z=obj.b?(obj.a.z+obj.b.z)/2:obj.a.z;
  objects.sort((a,b)=>a.z-b.z);
  for(const obj of objects){
   const a=obj.a,b=obj.b;
   if(b?(Math.max(a.y,b.y)<-4||Math.min(a.y,b.y)>height+4):(a.y<-4||a.y>height+4))continue;
   const depth=(obj.z+radius)/(2*radius),alpha=.10+.43*depth;
   if(obj.type===2){
    const r=1.7+depth*1.05;ctx.globalAlpha=alpha;ctx.drawImage(atoms[obj.side],a.x-r,a.y-r,r*2,r*2);
   }else if(obj.type===1){
    ctx.globalAlpha=alpha;ctx.beginPath();ctx.moveTo(a.x,a.y);ctx.lineTo(b.x,b.y);
    ctx.strokeStyle=obj.side?'#41a9f4':'#487df0';ctx.lineWidth=1.6+depth;ctx.stroke();
    ctx.globalAlpha=alpha*.7;ctx.lineWidth=.55;ctx.strokeStyle='#c9e7ff';ctx.stroke();
   }else{
    const dx=b.x-a.x,dy=b.y-a.y,length=Math.sqrt(dx*dx+dy*dy);if(length<.01)continue;
    ctx.globalAlpha=1;ctx.save();ctx.translate(a.x,a.y);ctx.rotate(Math.atan2(dy,dx));
    ctx.drawImage(rung,0,-.675,length,1.35);ctx.restore();
   }
  }
  ctx.globalAlpha=1;
 }
 const reducedMotion=window.matchMedia('(prefers-reduced-motion: reduce)');
 function running(){return pageActive&&!document.hidden&&!reducedMotion.matches;}
 reducedMotion.addEventListener('change',()=>{needsResize=true;if(reducedMotion.matches){resize();if(drawable)draw();}resume();});
 function tick(time){
  frame=null;if(!running())return;
  if(needsResize)resize();
  // No 33 ms gate: every display frame is used, including 90/120 Hz screens.
  // Reset after a real pause and cap a long stall so resuming cannot teleport stars.
  const dt=last===null?0:Math.min(Math.max(time-last,0),50);last=time;
  if(drawable){angle+=dt*.00012;elapsed+=dt*.001;draw();}
  frame=requestAnimationFrame(tick);
 }
 function resume(){
  const active=running();if(backdrop)backdrop.classList.toggle('is-paused',!active);
  if(!active){if(frame!==null)cancelAnimationFrame(frame);frame=null;last=null;return;}
  if(frame===null){last=null;frame=requestAnimationFrame(tick);}
 }
 function queueResize(){needsResize=true;if(reducedMotion.matches){resize();if(drawable)draw();}resume();}
 if(typeof ResizeObserver==='function')new ResizeObserver(queueResize).observe(canvas);
 window.addEventListener('resize',queueResize);
 window.addEventListener('pageshow',()=>{pageActive=true;queueResize();});
 window.addEventListener('pagehide',()=>{pageActive=false;resume();});
 window.addEventListener('focus',queueResize);
 document.addEventListener('visibilitychange',()=>{if(!document.hidden)needsResize=true;resume();});
 if(reducedMotion.matches){resize();if(drawable)draw();}
 resume();
})();
