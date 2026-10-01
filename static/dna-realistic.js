/* NyxPepz: self-contained WebGL double helix, original-photo reflections.
   Presentation only. No commerce APIs or stored data. */
(()=>{
 const bg=document.querySelector('.bg');if(!bg||bg.querySelector('.nyx-living-scene'))return;
 const canvas=document.createElement('canvas');canvas.className='nyx-living-scene';canvas.setAttribute('aria-hidden','true');
 canvas.style.cssText='position:absolute;left:50%;top:0;transform:translateX(-50%);width:min(100%,1000px);height:100%;pointer-events:none;z-index:1';
 const gl=canvas.getContext('webgl',{alpha:true,antialias:true,premultipliedAlpha:false,powerPreference:'low-power'});
 if(!gl)return;
 canvas.style.opacity='0';canvas.style.transition='opacity .7s ease';bg.append(canvas);
 const atmosphere=document.createElement('canvas');atmosphere.className='nyx-realistic-atmosphere';atmosphere.setAttribute('aria-hidden','true');atmosphere.style.cssText=canvas.style.cssText+';z-index:2;opacity:1;filter:none';bg.append(atmosphere);
 const ctx=atmosphere.getContext('2d');
 const style=document.createElement('style');style.textContent='.bg.nyx-realistic-ready:before{opacity:0!important;animation:none!important}.bg.nyx-realistic-ready .dna-scene{display:none!important}';document.head.append(style);
 const vertex=`attribute vec3 position;attribute vec3 normal;attribute vec3 tint;attribute float surface;uniform float angle;uniform float aspect;varying vec3 N;varying vec3 P;varying vec3 C;varying float S;
 void main(){float c=cos(angle),s=sin(angle);mat3 rotation=mat3(c,0.,-s,0.,1.,0.,s,0.,c);vec3 p=rotation*position;vec3 n=rotation*normal;float t=.23;mat3 tilt=mat3(cos(t),sin(t),0.,-sin(t),cos(t),0.,0.,0.,1.);p=tilt*p;n=tilt*n;float depth=9./(9.-p.z);gl_Position=vec4(p.x*.28/aspect*depth+.46,-p.y*.28*depth+.15,-p.z*.15,1.);N=n;P=p;C=tint;S=surface;}`;
 const fragment=`
#ifdef GL_FRAGMENT_PRECISION_HIGH
precision highp float;
#else
precision mediump float;
#endif
varying vec3 N;varying vec3 P;varying vec3 C;varying float S;uniform sampler2D environment;uniform float hasTexture;
void main(){
 vec3 n=normalize(N),v=normalize(vec3(0.,0.,9.)-P);
 float facing=max(0.,dot(n,v)),rim=pow(1.-facing,2.8);
 vec3 light=normalize(vec3(-.8,.8,1.7));float diffuse=max(0.,dot(n,light));
 float highlight=pow(max(0.,dot(reflect(-light,n),v)),52.);
 float strip=pow(max(0.,dot(reflect(-normalize(vec3(.8,.3,2.)),n),v)),20.);
 vec3 color=C*(.65+.6*diffuse)+vec3(.035,.57,1.)*rim*1.7;
 color+=vec3(.57,.86,1.)*highlight*.95+vec3(.67,.24,.76)*strip*.34;
 vec2 uv=vec2(.72+n.x*.23,.35-n.y*.22+P.y*.025);
 color+=texture2D(environment,clamp(uv,vec2(.01),vec2(.99))).rgb*hasTexture*.035;
 float fade=1.-smoothstep(2.7,3.3,abs(P.y));float depth=clamp(.88+P.z*.25,.58,1.);
 float alpha=(S>.5?.9:.86)+rim*.1;
 gl_FragColor=vec4(color*depth,alpha*fade);
}`;
 function shader(type,source){const s=gl.createShader(type);gl.shaderSource(s,source);gl.compileShader(s);if(!gl.getShaderParameter(s,gl.COMPILE_STATUS))throw Error('Decorative shader unavailable');return s;}
 let program;try{program=gl.createProgram();gl.attachShader(program,shader(gl.VERTEX_SHADER,vertex));gl.attachShader(program,shader(gl.FRAGMENT_SHADER,fragment));gl.linkProgram(program);if(!gl.getProgramParameter(program,gl.LINK_STATUS))throw Error('Decorative program unavailable');}catch(e){canvas.remove();atmosphere.remove();return;}
 const data=[],TAU=Math.PI*2,blue=[.025,.43,.95],violet=[.57,.12,.9];
 const add=(p,n,c,type=0)=>data.push(...p,...n,...c,type);
 const sub=(a,b)=>a.map((v,i)=>v-b[i]);const norm=a=>{const l=Math.hypot(...a)||1;return a.map(v=>v/l)};const cross=(a,b)=>[a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]];
 function tube(points,r,color,sides=10){
  const rings=points.map((p,i)=>{const tangent=norm(sub(points[Math.min(i+1,points.length-1)],points[Math.max(0,i-1)]));const side=norm(cross(tangent,[0,0,1]));const up=norm(cross(side,tangent));return Array.from({length:sides},(_,j)=>{const a=j/sides*TAU,n=side.map((v,k)=>v*Math.cos(a)+up[k]*Math.sin(a));const irregular=1;return {p:p.map((v,k)=>v+n[k]*r*irregular),n};});});
  for(let i=1;i<rings.length;i++)for(let j=0;j<sides;j++){const k=(j+1)%sides,a=rings[i-1][j],b=rings[i][j],c=rings[i][k],d=rings[i-1][k];for(const v of [a,b,c,a,c,d])add(v.p,v.n,color);}
 }
 function sphere(center,r,color){const lat=16,lon=22;const point=(i,j)=>{const a=i/lat*Math.PI,b=j/lon*TAU,n=[Math.sin(a)*Math.cos(b),Math.cos(a),Math.sin(a)*Math.sin(b)];const rough=1;return {p:center.map((v,k)=>v+n[k]*r*rough),n};};for(let i=0;i<lat;i++)for(let j=0;j<lon;j++){const a=point(i,j),b=point(i+1,j),c=point(i+1,j+1),d=point(i,j+1);for(const v of [a,b,c,a,c,d])add(v.p,v.n,color,1);}}
 function helixPoint(t,strand){const a=t*TAU*3.05+strand*Math.PI;const taper=.76+.24*Math.sin(Math.PI*t);return [Math.cos(a)*.61*taper,(t-.5)*6.5,Math.sin(a)*.61*taper];}
 // Continuous backbone prevents the disconnected pearl-necklace appearance.
 for(let strand=0;strand<2;strand++){
  tube(Array.from({length:280},(_,i)=>helixPoint(i/279,strand)),.049,strand?violet:blue,16);

 }
 for(let i=0;i<35;i++){
  const t=(i+.5)/35,a=helixPoint(t,0),b=helixPoint(t,1),mid=a.map((v,k)=>(v+b[k])*.5);
  const curve=(from,to,phase)=>Array.from({length:8},(_,j)=>{const q=j/7;return from.map((v,k)=>v*(1-q)+to[k]*q+(k===1?.012*Math.sin(q*Math.PI+phase):0));});
  tube(curve(a,mid,0),.013,i%2?violet:blue,8);tube(curve(mid,b,.3),.013,i%2?blue:violet,8);
  
 }
 const count=data.length/10;gl.useProgram(program);const buffer=gl.createBuffer();gl.bindBuffer(gl.ARRAY_BUFFER,buffer);gl.bufferData(gl.ARRAY_BUFFER,new Float32Array(data),gl.STATIC_DRAW);
 for(const [name,offset] of [['position',0],['normal',12],['tint',24],['surface',36]]){const loc=gl.getAttribLocation(program,name);gl.enableVertexAttribArray(loc);gl.vertexAttribPointer(loc,name==='surface'?1:3,gl.FLOAT,false,40,offset);}
 const uniforms={angle:gl.getUniformLocation(program,'angle'),aspect:gl.getUniformLocation(program,'aspect'),hasTexture:gl.getUniformLocation(program,'hasTexture'),hasGlass:gl.getUniformLocation(program,'hasGlass')};
 const texture=gl.createTexture();gl.bindTexture(gl.TEXTURE_2D,texture);gl.texImage2D(gl.TEXTURE_2D,0,gl.RGBA,1,1,0,gl.RGBA,gl.UNSIGNED_BYTE,new Uint8Array([12,40,70,255]));gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MIN_FILTER,gl.LINEAR);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MAG_FILTER,gl.LINEAR);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_S,gl.CLAMP_TO_EDGE);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_T,gl.CLAMP_TO_EDGE);
 gl.uniform1i(gl.getUniformLocation(program,'environment'),0);
 let materialLoaded=true;canvas.style.opacity='1';canvas.style.filter='drop-shadow(0 0 4px #4385ff99) drop-shadow(0 0 10px #4659ff55)';
 const photo=new Image();photo.onload=()=>{gl.activeTexture(gl.TEXTURE0);gl.bindTexture(gl.TEXTURE_2D,texture);gl.texImage2D(gl.TEXTURE_2D,0,gl.RGBA,gl.RGBA,gl.UNSIGNED_BYTE,photo);gl.uniform1f(uniforms.hasTexture,1);};photo.src='/static/neo-dna.webp';
 gl.enable(gl.DEPTH_TEST);gl.enable(gl.BLEND);gl.blendFunc(gl.SRC_ALPHA,gl.ONE_MINUS_SRC_ALPHA);
 let w=0,h=0,time=0,last=0,frame=0,lost=false;
 function resize(){w=Math.min(innerWidth,1000);h=innerHeight;const dpr=Math.min(devicePixelRatio||1,1.5);canvas.width=atmosphere.width=Math.round(w*dpr);canvas.height=atmosphere.height=Math.round(h*dpr);gl.viewport(0,0,canvas.width,canvas.height);gl.uniform1f(uniforms.aspect,w/h);if(ctx)ctx.setTransform(dpr,0,0,dpr,0,0);}
 const particles=Array.from({length:82},(_,i)=>({x:(i*.618034)%1,y:(i*.414214)%1,z:i%7/7,phase:i*1.7}));
 const moleculePoints=[[0,0,0],[18,4,10],[-15,15,-7],[-5,-18,9],[33,-9,-5],[-28,7,12],[3,28,-10]];
 function atomSprite(purple){
  const c=document.createElement('canvas');c.width=c.height=64;const g=c.getContext('2d');
  const grad=g.createRadialGradient(24,20,1,32,32,27);
  grad.addColorStop(0,'rgba(204,234,255,.95)');grad.addColorStop(.23,purple?'rgba(139,68,230,.8)':'rgba(41,120,236,.8)');grad.addColorStop(.7,purple?'rgba(54,15,105,.45)':'rgba(8,35,86,.4)');grad.addColorStop(.88,'rgba(62,180,255,.8)');grad.addColorStop(1,'rgba(32,130,255,0)');
  g.fillStyle=grad;g.beginPath();g.arc(32,32,27,0,TAU);g.fill();g.strokeStyle='rgba(129,222,255,.8)';g.lineWidth=1.1;g.beginPath();g.arc(32,32,24,3.5,5.3);g.stroke();return c;
 }
 const atomSprites=[atomSprite(false),atomSprite(true)];
 function ambient(){if(!ctx)return;ctx.clearRect(0,0,w,h);
  for(const p of particles){
   const x=(p.x*w+Math.sin(time*.15+p.phase)*12+w)%w,y=(p.y*h-time*(2+p.z*6)+h*100)%h,r=.55+p.z*1.8,alpha=.18+p.z*.28;
   ctx.fillStyle=p.phase%3>1?`rgba(171,115,255,${alpha})`:`rgba(86,181,255,${alpha})`;ctx.beginPath();ctx.arc(x,y,r,0,TAU);ctx.fill();
   if(p.z>.78){ctx.strokeStyle=`rgba(112,198,255,${alpha*.28})`;ctx.lineWidth=.5;ctx.beginPath();ctx.moveTo(x-4,y);ctx.lineTo(x+4,y);ctx.moveTo(x,y-4);ctx.lineTo(x,y+4);ctx.stroke();}
  }
  for(let k=0;k<6;k++){
   const a=time*(.13+k*.012)+k*2,b=time*.08+k,ca=Math.cos(a),sa=Math.sin(a),cb=Math.cos(b),sb=Math.sin(b);
   const size=.6+(k%3)*.2,cx=w*(.12+(k%3)*.32)+Math.sin(time*.09+k)*12,cy=((k*.173+time*.005)%1)*(h+120)-60;
   const points=moleculePoints.map(([x,y,z])=>{const rx=x*ca+z*sa,rz=z*ca-x*sa,ry=y*cb-rz*sb,depth=y*sb+rz*cb,scale=180/(180-depth);return{x:cx+rx*scale*size,y:cy+ry*scale*size,z:depth,r:(3.3+k%2)*scale*size};});
   for(const [i,j] of [[0,1],[0,2],[0,3],[1,4],[2,5],[2,6]]){
    const p=points[i],q=points[j],g=ctx.createLinearGradient(p.x,p.y,q.x,q.y);g.addColorStop(0,'rgba(45,127,238,.3)');g.addColorStop(.5,'rgba(123,169,255,.5)');g.addColorStop(1,'rgba(153,64,224,.32)');ctx.strokeStyle=g;ctx.lineWidth=1.25*size;ctx.beginPath();ctx.moveTo(p.x,p.y);ctx.lineTo(q.x,q.y);ctx.stroke();
   }
   points.sort((p,q)=>p.z-q.z).forEach((p,i)=>{ctx.globalAlpha=.5+(p.z+40)/210;ctx.drawImage(atomSprites[(i+k)%3===0?1:0],p.x-p.r*1.2,p.y-p.r*1.2,p.r*2.4,p.r*2.4);ctx.globalAlpha=1;});
  }
 }
 function draw(now){frame=0;if(document.hidden||lost)return;if(now-last<33){frame=requestAnimationFrame(draw);return;}time+=last?Math.min((now-last)/1000,.1):0;last=now;gl.clearColor(0,0,0,0);gl.clear(gl.COLOR_BUFFER_BIT|gl.DEPTH_BUFFER_BIT);gl.uniform1f(uniforms.angle,time*TAU/32+.7);gl.drawArrays(gl.TRIANGLES,0,count);ambient();if(materialLoaded)bg.classList.add('nyx-realistic-ready');frame=requestAnimationFrame(draw);}
 canvas.addEventListener('webglcontextlost',e=>{e.preventDefault();lost=true;cancelAnimationFrame(frame);bg.classList.remove('nyx-realistic-ready');atmosphere.style.display='none';});
 canvas.addEventListener('webglcontextrestored',()=>{canvas.remove();atmosphere.remove();bg.classList.remove('nyx-living-ready');});
 document.addEventListener('visibilitychange',()=>{if(document.hidden){cancelAnimationFrame(frame);frame=0;}else{last=0;if(!frame&&!lost)frame=requestAnimationFrame(draw);}});
 addEventListener('resize',resize,{passive:true});resize();frame=requestAnimationFrame(draw);
})();
