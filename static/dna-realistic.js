/* NyxPepz: self-contained WebGL double helix, original-photo reflections.
   Presentation only. No commerce APIs or stored data. */
(()=>{
 const bg=document.querySelector('.bg');if(!bg||bg.querySelector('.nyx-living-scene'))return;
 const canvas=document.createElement('canvas');canvas.className='nyx-living-scene';canvas.setAttribute('aria-hidden','true');
 canvas.style.cssText='position:absolute;left:50%;top:0;transform:translateX(-50%);width:min(100%,1000px);height:100%;pointer-events:none;z-index:1';
 const gl=canvas.getContext('webgl',{alpha:true,antialias:true,premultipliedAlpha:false,powerPreference:'low-power'});
 if(!gl)return;
 canvas.style.opacity='0';canvas.style.transition='opacity .7s ease';bg.append(canvas);
 const atmosphere=document.createElement('canvas');atmosphere.className='nyx-realistic-atmosphere';atmosphere.setAttribute('aria-hidden','true');atmosphere.style.cssText=canvas.style.cssText+';z-index:2';bg.append(atmosphere);
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
varying vec3 N;varying vec3 P;varying vec3 C;varying float S;uniform sampler2D environment;uniform float hasTexture;uniform sampler2D glassDetail;uniform float hasGlass;
 float noise(vec3 p){return fract(sin(dot(p,vec3(12.9898,78.233,37.719)))*43758.5453);}
 void main(){vec3 n=normalize(N);vec3 v=normalize(vec3(0.,0.,9.)-P);vec3 l=normalize(vec3(-.65,1.,1.8));float diffuse=max(0.,dot(n,l));float rim=pow(1.-max(0.,dot(n,v)),2.7);float spec=pow(max(0.,dot(reflect(-l,n),v)),72.);float softbox=pow(max(0.,dot(reflect(-normalize(vec3(-1.,.3,2.)),n),v)),18.);float second=pow(max(0.,dot(reflect(normalize(vec3(.9,-.6,-1.)),n),v)),30.);
 float grain=noise(P*78.);float cells=sin(P.x*81.+sin(P.y*57.))*sin(P.y*72.+P.z*59.);float micro=smoothstep(.65,.95,cells)*.035+grain*.02;
 vec2 uv=vec2(.72+n.x*.23,.35-n.y*.22+P.y*.025);vec3 env=texture2D(environment,clamp(uv,vec2(.01),vec2(.99))).rgb;
 vec3 base=C*(.16+.65*diffuse);base+=env*hasTexture*(.14+rim*.32);base+=C*rim*.8+vec3(.85,.95,1.)*spec*2.4+vec3(.25,.4,.8)*second*.23; base+=vec3(.58,.8,1.)*softbox*.65; base+=vec3(.35,.66,.9)*pow(rim,3.)*.25; base+=vec3(.19,.48,.68)*micro;
 if(S>.5&&hasGlass>.5){vec2 glassUV=vec2(.5+n.x*.395,.5-n.y*.395);float blur=max(0.,-P.z)*.015;vec4 glass=(texture2D(glassDetail,glassUV+vec2(blur,0.))+texture2D(glassDetail,glassUV-vec2(blur,0.))+texture2D(glassDetail,glassUV+vec2(0.,blur))+texture2D(glassDetail,glassUV-vec2(0.,blur)))*.25;base=mix(base,glass.rgb*(1.02+.22*diffuse)+vec3(.5,.72,1.)*spec*.32,.92);}
 float fade=(1.-smoothstep(2.65,3.3,abs(P.y)));float fog=clamp(.84+P.z*.42,.45,1.);float alpha=(.84+rim*.1)*fade;gl_FragColor=vec4(base*fog,alpha);}`;
 function shader(type,source){const s=gl.createShader(type);gl.shaderSource(s,source);gl.compileShader(s);if(!gl.getShaderParameter(s,gl.COMPILE_STATUS))throw Error('Decorative shader unavailable');return s;}
 let program;try{program=gl.createProgram();gl.attachShader(program,shader(gl.VERTEX_SHADER,vertex));gl.attachShader(program,shader(gl.FRAGMENT_SHADER,fragment));gl.linkProgram(program);if(!gl.getProgramParameter(program,gl.LINK_STATUS))throw Error('Decorative program unavailable');}catch(e){canvas.remove();atmosphere.remove();return;}
 const data=[],TAU=Math.PI*2,blue=[.13,.55,.85],violet=[.52,.22,.85];
 const add=(p,n,c,type=0)=>data.push(...p,...n,...c,type);
 const sub=(a,b)=>a.map((v,i)=>v-b[i]);const norm=a=>{const l=Math.hypot(...a)||1;return a.map(v=>v/l)};const cross=(a,b)=>[a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]];
 function tube(points,r,color,sides=10){
  const rings=points.map((p,i)=>{const tangent=norm(sub(points[Math.min(i+1,points.length-1)],points[Math.max(0,i-1)]));const side=norm(cross(tangent,[0,0,1]));const up=norm(cross(side,tangent));return Array.from({length:sides},(_,j)=>{const a=j/sides*TAU,n=side.map((v,k)=>v*Math.cos(a)+up[k]*Math.sin(a));const irregular=1+.008*Math.sin(i*1.7+j*2.3);return {p:p.map((v,k)=>v+n[k]*r*irregular),n};});});
  for(let i=1;i<rings.length;i++)for(let j=0;j<sides;j++){const k=(j+1)%sides,a=rings[i-1][j],b=rings[i][j],c=rings[i][k],d=rings[i-1][k];for(const v of [a,b,c,a,c,d])add(v.p,v.n,color);}
 }
 function sphere(center,r,color){const lat=16,lon=22;const point=(i,j)=>{const a=i/lat*Math.PI,b=j/lon*TAU,n=[Math.sin(a)*Math.cos(b),Math.cos(a),Math.sin(a)*Math.sin(b)];const rough=1+.008*Math.sin(b*5+a*7);return {p:center.map((v,k)=>v+n[k]*r*rough),n};};for(let i=0;i<lat;i++)for(let j=0;j<lon;j++){const a=point(i,j),b=point(i+1,j),c=point(i+1,j+1),d=point(i,j+1);for(const v of [a,b,c,a,c,d])add(v.p,v.n,color,1);}}
 function helixPoint(t,strand){const a=t*TAU*3.05+strand*Math.PI;const taper=.76+.24*Math.sin(Math.PI*t);return [Math.cos(a)*.61*taper,(t-.5)*6.5,Math.sin(a)*.61*taper];}
 // Continuous backbone prevents the disconnected pearl-necklace appearance.
 for(let strand=0;strand<2;strand++){
  tube(Array.from({length:220},(_,i)=>helixPoint(i/219,strand)),.077,blue,12);
  for(let i=0;i<54;i++){const t=i/53,r=.133+.004*Math.sin(i*2.1);sphere(helixPoint(t,strand),r,blue);}
 }
 for(let i=0;i<35;i++){
  const t=(i+.5)/35,a=helixPoint(t,0),b=helixPoint(t,1),mid=a.map((v,k)=>(v+b[k])*.5);
  const curve=(from,to,phase)=>Array.from({length:8},(_,j)=>{const q=j/7;return from.map((v,k)=>v*(1-q)+to[k]*q+(k===1?.012*Math.sin(q*Math.PI+phase):0));});
  tube(curve(a,mid,0),.027,i%2?violet:blue,8);tube(curve(mid,b,.3),.027,i%2?blue:violet,8);
  sphere(mid,.038,violet);
 }
 const count=data.length/10;gl.useProgram(program);const buffer=gl.createBuffer();gl.bindBuffer(gl.ARRAY_BUFFER,buffer);gl.bufferData(gl.ARRAY_BUFFER,new Float32Array(data),gl.STATIC_DRAW);
 for(const [name,offset] of [['position',0],['normal',12],['tint',24],['surface',36]]){const loc=gl.getAttribLocation(program,name);gl.enableVertexAttribArray(loc);gl.vertexAttribPointer(loc,name==='surface'?1:3,gl.FLOAT,false,40,offset);}
 const uniforms={angle:gl.getUniformLocation(program,'angle'),aspect:gl.getUniformLocation(program,'aspect'),hasTexture:gl.getUniformLocation(program,'hasTexture'),hasGlass:gl.getUniformLocation(program,'hasGlass')};
 const texture=gl.createTexture();gl.bindTexture(gl.TEXTURE_2D,texture);gl.texImage2D(gl.TEXTURE_2D,0,gl.RGBA,1,1,0,gl.RGBA,gl.UNSIGNED_BYTE,new Uint8Array([12,40,70,255]));gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MIN_FILTER,gl.LINEAR);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MAG_FILTER,gl.LINEAR);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_S,gl.CLAMP_TO_EDGE);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_T,gl.CLAMP_TO_EDGE);
 gl.uniform1i(gl.getUniformLocation(program,'environment'),0);
 const glassTexture=gl.createTexture();gl.activeTexture(gl.TEXTURE1);gl.bindTexture(gl.TEXTURE_2D,glassTexture);gl.texImage2D(gl.TEXTURE_2D,0,gl.RGBA,1,1,0,gl.RGBA,gl.UNSIGNED_BYTE,new Uint8Array([12,40,70,255]));gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MIN_FILTER,gl.LINEAR);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MAG_FILTER,gl.LINEAR);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_S,gl.CLAMP_TO_EDGE);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_T,gl.CLAMP_TO_EDGE);gl.uniform1i(gl.getUniformLocation(program,'glassDetail'),1);
 let materialLoaded=false;const detail=new Image();detail.onload=()=>{gl.activeTexture(gl.TEXTURE1);gl.bindTexture(gl.TEXTURE_2D,glassTexture);const mip=document.createElement('canvas');mip.width=mip.height=512;mip.getContext('2d').drawImage(detail,0,0,512,512);gl.texImage2D(gl.TEXTURE_2D,0,gl.RGBA,gl.RGBA,gl.UNSIGNED_BYTE,mip);gl.generateMipmap(gl.TEXTURE_2D);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MIN_FILTER,gl.LINEAR_MIPMAP_LINEAR);gl.uniform1f(uniforms.hasGlass,1);gl.activeTexture(gl.TEXTURE0);materialLoaded=true;canvas.style.opacity='1';};detail.src='/static/dna-glass-detail.png';
 gl.activeTexture(gl.TEXTURE0);
 const photo=new Image();photo.onload=()=>{gl.activeTexture(gl.TEXTURE0);gl.bindTexture(gl.TEXTURE_2D,texture);gl.texImage2D(gl.TEXTURE_2D,0,gl.RGBA,gl.RGBA,gl.UNSIGNED_BYTE,photo);gl.uniform1f(uniforms.hasTexture,1);};photo.src='/static/neo-dna.webp';
 gl.enable(gl.DEPTH_TEST);gl.enable(gl.BLEND);gl.blendFunc(gl.SRC_ALPHA,gl.ONE_MINUS_SRC_ALPHA);
 let w=0,h=0,time=0,last=0,frame=0,lost=false;
 function resize(){w=Math.min(innerWidth,1000);h=innerHeight;const dpr=Math.min(devicePixelRatio||1,1.5);canvas.width=atmosphere.width=Math.round(w*dpr);canvas.height=atmosphere.height=Math.round(h*dpr);gl.viewport(0,0,canvas.width,canvas.height);gl.uniform1f(uniforms.aspect,w/h);if(ctx)ctx.setTransform(dpr,0,0,dpr,0,0);}
 const particles=Array.from({length:50},(_,i)=>({x:(i*.618034)%1,y:(i*.414214)%1,z:i%5/5,phase:i*1.7}));
 const moleculePoints=[[0,0,0],[24,4,12],[-17,18,-7],[-5,-22,9],[43,-10,-5],[-36,9,12]];
 function orb(x,y,r,a){if(detail.complete&&detail.naturalWidth){ctx.globalAlpha=a;ctx.drawImage(detail,x-r*1.25,y-r*1.25,r*2.5,r*2.5);ctx.globalAlpha=1;return;}const g=ctx.createRadialGradient(x-r*.3,y-r*.4,0,x,y,r);g.addColorStop(0,`rgba(206,238,255,${a})`);g.addColorStop(.3,`rgba(37,117,174,${a*.6})`);g.addColorStop(.8,`rgba(5,25,52,${a*.7})`);g.addColorStop(1,`rgba(80,153,210,${a*.5})`);ctx.fillStyle=g;ctx.beginPath();ctx.arc(x,y,r,0,TAU);ctx.fill();}
 function ambient(){if(!ctx)return;ctx.clearRect(0,0,w,h);
  for(const p of particles){const x=(p.x*w+Math.sin(time*.15+p.phase)*12+w)%w,y=(p.y*h-time*(2+p.z*6)+h*100)%h;const r=.5+p.z*1.8;ctx.fillStyle=`rgba(130,207,251,${.12+p.z*.2})`;ctx.beginPath();ctx.arc(x,y,r,0,TAU);ctx.fill();}
  for(let k=0;k<3;k++){const a=time*.17+k*2,ca=Math.cos(a),sa=Math.sin(a),cx=w*(.16+k*.26),cy=((k*.33+time*.008)%1)*(h+120)-60;const points=moleculePoints.map(([x,y,z])=>{const rx=x*ca+z*sa,rz=z*ca-x*sa,s=180/(180-rz);return{x:cx+rx*s,y:cy+y*s,z:rz,s};});ctx.lineWidth=1.8;ctx.strokeStyle='rgba(100,173,224,.26)';for(const [i,j] of [[0,1],[0,2],[0,3],[1,4],[2,5]]){ctx.beginPath();ctx.moveTo(points[i].x,points[i].y);ctx.lineTo(points[j].x,points[j].y);ctx.stroke();}points.sort((p,q)=>p.z-q.z).forEach(p=>orb(p.x,p.y,6*p.s,.48));}
 }
 function draw(now){frame=0;if(document.hidden||lost)return;if(now-last<33){frame=requestAnimationFrame(draw);return;}time+=last?Math.min((now-last)/1000,.1):0;last=now;gl.clearColor(0,0,0,0);gl.clear(gl.COLOR_BUFFER_BIT|gl.DEPTH_BUFFER_BIT);gl.uniform1f(uniforms.angle,time*TAU/32+.7);gl.drawArrays(gl.TRIANGLES,0,count);ambient();if(materialLoaded)bg.classList.add('nyx-realistic-ready');frame=requestAnimationFrame(draw);}
 canvas.addEventListener('webglcontextlost',e=>{e.preventDefault();lost=true;cancelAnimationFrame(frame);bg.classList.remove('nyx-realistic-ready');atmosphere.style.display='none';});
 canvas.addEventListener('webglcontextrestored',()=>{canvas.remove();atmosphere.remove();bg.classList.remove('nyx-living-ready');});
 document.addEventListener('visibilitychange',()=>{if(document.hidden){cancelAnimationFrame(frame);frame=0;}else{last=0;if(!frame&&!lost)frame=requestAnimationFrame(draw);}});
 addEventListener('resize',resize,{passive:true});resize();frame=requestAnimationFrame(draw);
})();
