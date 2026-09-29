/* Small local SVG icons and a projected, depth-sorted DNA illustration. */
(()=>{
 const icons={
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
 document.querySelectorAll('input:not([type=file])').forEach(el=>{if(!el.hasAttribute('aria-label'))el.setAttribute('aria-label',el.placeholder||el.id)});
 const moon=document.querySelector('.brand-moon');
 if(moon)moon.innerHTML='<svg viewBox="0 0 48 48" aria-hidden="true"><defs><linearGradient id="moonLight" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#e1f9ff"/><stop offset=".35" stop-color="#7abaff"/><stop offset=".7" stop-color="#347aff"/><stop offset="1" stop-color="#1339be"/></linearGradient><mask id="moonCut"><circle cx="24" cy="24" r="20" fill="white"/><circle cx="15" cy="19" r="19.5" fill="black"/></mask></defs><circle cx="24" cy="24" r="20" fill="url(#moonLight)" mask="url(#moonCut)"/></svg>';

 // Decorative light ribbons: a small vector layer, separate from readable content.
 const backdrop=document.querySelector('.bg');
 if(backdrop){
  backdrop.setAttribute('aria-hidden','true');
  backdrop.innerHTML=`<svg class="sapphire-veils" viewBox="0 0 390 844" preserveAspectRatio="xMidYMin slice" focusable="false"><defs>
   <linearGradient id="veilLight" x1="0" y1="1" x2="1" y2="0"><stop stop-color="#1145d4" stop-opacity="0"/><stop offset=".32" stop-color="#315df3" stop-opacity=".5"/><stop offset=".66" stop-color="#428cff"/><stop offset=".82" stop-color="#99dcff" stop-opacity=".7"/><stop offset="1" stop-color="#3878e9" stop-opacity="0"/></linearGradient>
   <linearGradient id="veilSilk" x1="0" y1="1" x2="1" y2="0"><stop stop-color="#17349c" stop-opacity="0"/><stop offset=".55" stop-color="#1641df" stop-opacity=".24"/><stop offset=".78" stop-color="#4387ff" stop-opacity=".32"/><stop offset="1" stop-color="#3468ee" stop-opacity="0"/></linearGradient>
   <filter id="veilBloom" x="-40%" y="-40%" width="180%" height="180%"><feGaussianBlur stdDeviation="9"/></filter>
  </defs><g class="veil-drift">
   <path d="M-90 370 C20 390 57 180 191 181 S300 146 450 36 L450 115 C324 238 277 154 190 207 S45 408-90 417Z" fill="url(#veilSilk)"/>
   <path d="M-80 395 C70 401 75 165 217 195 S344 99 455 59" fill="none" stroke="url(#veilLight)" stroke-width="22" filter="url(#veilBloom)" opacity=".5"/>
   <g fill="none" stroke="url(#veilLight)">
    <path d="M-80 395 C70 401 75 165 217 195 S344 99 455 59" stroke-width="1.1" opacity=".74"/>
    <path d="M-83 401 C63 421 81 176 218 200 S355 96 448 49" stroke-width=".5" opacity=".4"/>
    <path d="M-80 416 C85 418 80 191 230 211 S363 132 462 78" stroke-width=".7" opacity=".23"/>
    <path d="M-66 196 C72 107 182 358 300 262 S385 177 455 223" stroke-width="1" opacity=".27"/>
    <path d="M-66 201 C72 125 182 365 300 270 S385 181 455 230" stroke-width=".5" opacity=".22"/>
   </g>
  </g><g class="veil-drift veil-drift-low" fill="none" stroke="url(#veilLight)">
   <path d="M-105 450 C150 580-120 731 160 850 S400 810 460 710" stroke-width="28" filter="url(#veilBloom)" opacity=".12"/>
   <path d="M-105 450 C150 580-120 731 160 850 S400 810 460 710" stroke-width=".6" opacity=".22"/>
  </g></svg>`;
  document.addEventListener('visibilitychange',()=>backdrop.classList.toggle('is-paused',document.hidden));
 }
 const canvas=document.getElementById('dnaCanvas');if(!canvas)return;
 const scene=canvas.closest('.dna-scene');if(backdrop&&scene)backdrop.append(scene);
 const ctx=canvas.getContext('2d');if(!ctx)return;
 let width=390,height=844,frame=0,last=0,angle=.65,elapsed=3;
 const reducedMotion=window.matchMedia('(prefers-reduced-motion: reduce)');
 const particles=Array.from({length:32},(_,i)=>({x:((i*73+29)%281)/281,y:((i*43+19)%157)/157,r:.45+(i%4)*.25,speed:.04+(i%5)*.012,phase:i*2.1}));
 function resize(){const r=canvas.getBoundingClientRect();if(!r.width||!r.height)return;const dpr=Math.min(devicePixelRatio||1,2);width=r.width;height=r.height;canvas.width=Math.round(width*dpr);canvas.height=Math.round(height*dpr);ctx.setTransform(dpr,0,0,dpr,0,0);draw();}
 function draw(){
  ctx.clearRect(0,0,width,height);
  // A few drifting points, painted behind the helix in the same capped loop.
  for(const p of particles){const x=(p.x*width+Math.sin(angle*.9+p.phase)*7),y=((p.y-angle*p.speed)%1+1)%1*height,alpha=.15+.3*(.5+.5*Math.sin(angle+p.phase));ctx.fillStyle=`rgba(128,190,255,${alpha})`;ctx.shadowColor='#468fff';ctx.shadowBlur=p.r> .8?7:0;ctx.beginPath();ctx.arc(x,y,p.r,0,Math.PI*2);ctx.fill();}
  ctx.shadowBlur=0;
  // The helix extends beyond both viewport edges, with no stop behind the logo.
  const objects=[],step=12,rows=Math.ceil((height+240)/step)+1,radius=Math.min(32,width*.075),scale=1;
  // Sparse shooting stars share the same animation loop as the DNA and particles.
  if(!reducedMotion.matches)for(let n=0;n<2;n++){
   const t=(elapsed+n*6)%12;if(t>1.4)continue;
   const progress=t/1.4,cycle=Math.floor((elapsed+n*6)/12),alpha=Math.sin(progress*Math.PI)*.7;
   const x=width*(.96-progress*.64),y=height*(.08+((cycle+n)%3)*.15)+progress*height*.22;
   const dx=65,dy=-28,g=ctx.createLinearGradient(x+dx,y+dy,x,y);
   g.addColorStop(0,'rgba(110,177,255,0)');g.addColorStop(1,`rgba(192,226,255,${alpha})`);
   ctx.beginPath();ctx.moveTo(x+dx,y+dy);ctx.lineTo(x,y);ctx.strokeStyle=g;ctx.lineWidth=1.3;ctx.stroke();
   ctx.fillStyle=`rgba(232,246,255,${alpha})`;ctx.shadowColor='#87baff';ctx.shadowBlur=8;ctx.beginPath();ctx.arc(x,y,1.3,0,Math.PI*2);ctx.fill();ctx.shadowBlur=0;
  }
  function point(i,side){const a=i*.23+angle+side*Math.PI,z=Math.sin(a)*radius,x=Math.cos(a)*radius,y=-120+i*step,p=240/(240-z);return {x:width*(.86-.70*y/height)+x*p,y:y+x*.27,z};}
  const pts=Array.from({length:rows},(_,i)=>[point(i,0),point(i,1)]);
  pts.forEach((pair,i)=>{
   objects.push({type:'rung',a:pair[0],b:pair[1],z:(pair[0].z+pair[1].z)/2});
   pair.forEach((p,s)=>{if(i)objects.push({type:'strand',a:pts[i-1][s],b:p,z:(pts[i-1][s].z+p.z)/2,s});objects.push({type:'atom',p,z:p.z,s});});
  });
  objects.sort((a,b)=>a.z-b.z);
  for(const obj of objects){
   const depth=(obj.z+radius)/(2*radius);
   const alpha=.10+.43*depth;
   if(obj.type==='atom'){
    const {x,y}=obj.p,r=(1.7+depth*1.05)*scale;
    const g=ctx.createRadialGradient(x-r*.35,y-r*.4,r*.06,x,y,r);
    g.addColorStop(0,`rgba(231,250,255,${alpha})`);g.addColorStop(.3,`rgba(${obj.s?'96,196,255':'107,160,255'},${alpha})`);g.addColorStop(1,`rgba(6,40,104,${alpha})`);
    ctx.beginPath();ctx.arc(x,y,r,0,Math.PI*2);ctx.fillStyle=g;ctx.fill();
   }else{
    const {a,b}=obj;ctx.beginPath();ctx.moveTo(a.x,a.y);ctx.lineTo(b.x,b.y);ctx.lineCap='round';
    if(obj.type==='strand'){ctx.strokeStyle=`rgba(${obj.s?'65,169,244':'72,125,240'},${alpha})`;ctx.lineWidth=(1.6+depth)*scale;ctx.stroke();ctx.lineWidth=.55*scale;ctx.strokeStyle=`rgba(201,231,255,${alpha*.7})`;ctx.stroke();}
    else {const g=ctx.createLinearGradient(a.x,a.y,b.x+.001,b.y);g.addColorStop(0,'rgba(50,112,208,.45)');g.addColorStop(.48,'rgba(149,207,255,.63)');g.addColorStop(.52,'rgba(94,167,244,.63)');g.addColorStop(1,'rgba(26,120,190,.45)');ctx.strokeStyle=g;ctx.lineWidth=1.35*scale;ctx.stroke();}
   }
  }
 }
 function tick(time){
  frame=0;if(document.hidden||reducedMotion.matches)return;
  if(time-last>=33){
   const r=canvas.getBoundingClientRect();
   if(r.width&&r.height&&r.bottom>0&&r.top<innerHeight){const dt=Math.min(time-last,70);angle+=dt*.00045;elapsed+=dt*.001;draw();}
   last=time;
  }
  frame=requestAnimationFrame(tick);
 }
 function resume(){cancelAnimationFrame(frame);frame=0;if(!document.hidden&&!reducedMotion.matches){last=performance.now();frame=requestAnimationFrame(tick);}else draw();}
 // Do not depend on intersection callbacks to restart in an embedded browser.
 if(typeof ResizeObserver==='function')new ResizeObserver(resize).observe(canvas);
 window.addEventListener('resize',resize);
 window.addEventListener('pageshow',()=>{resize();resume();});
 window.addEventListener('focus',resume);
 document.addEventListener('visibilitychange',resume);
 reducedMotion.addEventListener?.('change',resume);
 resize();resume();
})();
