/* Offline WebGL renderer for the actual GLB; localhost polling is read-only. */
(()=>{
'use strict';
const canvas=document.getElementById('model');
const status=document.getElementById('live-status');
const gl=canvas.getContext('webgl',{antialias:true,preserveDrawingBuffer:true});
if(!gl){status.textContent='WebGL no disponible en este navegador';return;}
const vs=`attribute vec3 pos;attribute vec3 normal;uniform mat4 view;uniform mat4 lightView;uniform vec3 shift;varying vec3 n;varying vec4 shadowPos;void main(){n=normal;shadowPos=lightView*vec4(pos+shift,1.);gl_Position=view*vec4(pos+shift,1.);}`;
const fs=`precision highp float;varying vec3 n;varying vec4 shadowPos;uniform vec3 color;uniform vec3 lightDir;uniform sampler2D shadowMap;float unpack(vec4 c){return dot(c,vec4(1.,1./255.,1./65025.,1./16581375.));}void main(){vec3 nn=normalize(n);float key=max(0.,dot(nn,lightDir));vec3 sc=shadowPos.xyz*0.5+0.5;float shadow=0.;float bias=0.00038+0.0003*(1.-key);for(int x=-1;x<=1;x++){for(int y=-1;y<=1;y++){float d=unpack(texture2D(shadowMap,sc.xy+vec2(float(x),float(y))/2048.));shadow+=sc.z-bias>d?0.20:1.;}}shadow/=9.;float fill=max(0.,dot(nn,normalize(vec3(-lightDir.x,-lightDir.y,0.35))));float lit=0.30+0.67*key*shadow+0.15*fill+0.04*max(0.,nn.z);gl_FragColor=vec4(pow(color*lit,vec3(0.85)),1.);}`;
function shader(type,src){const sh=gl.createShader(type);gl.shaderSource(sh,src);gl.compileShader(sh);if(!gl.getShaderParameter(sh,gl.COMPILE_STATUS))throw Error(gl.getShaderInfoLog(sh));return sh;}
const program=gl.createProgram();gl.attachShader(program,shader(gl.VERTEX_SHADER,vs));gl.attachShader(program,shader(gl.FRAGMENT_SHADER,fs));gl.linkProgram(program);if(!gl.getProgramParameter(program,gl.LINK_STATUS))throw Error(gl.getProgramInfoLog(program));gl.useProgram(program);
const loc={};for(const n of ['view','shift','color','lightView','shadowMap','lightDir'])loc[n]=gl.getUniformLocation(program,n);
const ap=gl.getAttribLocation(program,'pos'),an=gl.getAttribLocation(program,'normal');
const depthProgram=gl.createProgram();gl.attachShader(depthProgram,shader(gl.VERTEX_SHADER,'attribute vec3 pos;uniform mat4 view;uniform vec3 shift;void main(){gl_Position=view*vec4(pos+shift,1.);}'));gl.attachShader(depthProgram,shader(gl.FRAGMENT_SHADER,'precision highp float;void main(){vec4 c=fract(gl_FragCoord.z*vec4(1.,255.,65025.,16581375.));c-=c.yzww*vec4(1./255.,1./255.,1./255.,0.);gl_FragColor=c;}'));gl.linkProgram(depthProgram);if(!gl.getProgramParameter(depthProgram,gl.LINK_STATUS))throw Error(gl.getProgramInfoLog(depthProgram));
const depthLoc={pos:gl.getAttribLocation(depthProgram,'pos'),view:gl.getUniformLocation(depthProgram,'view'),shift:gl.getUniformLocation(depthProgram,'shift')};
const shadowTexture=gl.createTexture();gl.bindTexture(gl.TEXTURE_2D,shadowTexture);gl.texImage2D(gl.TEXTURE_2D,0,gl.RGBA,2048,2048,0,gl.RGBA,gl.UNSIGNED_BYTE,null);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MIN_FILTER,gl.NEAREST);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MAG_FILTER,gl.NEAREST);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_S,gl.CLAMP_TO_EDGE);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_T,gl.CLAMP_TO_EDGE);
const shadowBuffer=gl.createFramebuffer();gl.bindFramebuffer(gl.FRAMEBUFFER,shadowBuffer);gl.framebufferTexture2D(gl.FRAMEBUFFER,gl.COLOR_ATTACHMENT0,gl.TEXTURE_2D,shadowTexture,0);const depthBuffer=gl.createRenderbuffer();gl.bindRenderbuffer(gl.RENDERBUFFER,depthBuffer);gl.renderbufferStorage(gl.RENDERBUFFER,gl.DEPTH_COMPONENT16,2048,2048);gl.framebufferRenderbuffer(gl.FRAMEBUFFER,gl.DEPTH_ATTACHMENT,gl.RENDERBUFFER,depthBuffer);if(gl.checkFramebufferStatus(gl.FRAMEBUFFER)!==gl.FRAMEBUFFER_COMPLETE)throw Error('No se pudo crear la iluminación');gl.bindFramebuffer(gl.FRAMEBUFFER,null);
let shadowDirty=true;
function cameraMatrix(yaw,pitch,sx,sy){const c=Math.cos(yaw),s=Math.sin(yaw),cp=Math.cos(pitch),sp=Math.sin(pitch);return new Float32Array([c/sx,-s*sp/sy,-s*cp/250,0,s/sx,c*sp/sy,c*cp/250,0,0,cp/sy,-sp/250,0,0,0,0,1]);}
const lightYaw=-0.55;
const lightMatrix=cameraMatrix(lightYaw,0.65,125,125);
let objects=[],bounds=[[-44,-74,0],[44,74,71]];
let yaw=0.72,pitch=0.46,zoom=1.25,visible={upper:true,table:true,lower:true};
const identity=()=>[1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1];
function multiply(a,b){const c=new Array(16).fill(0);for(let j=0;j<4;j++)for(let i=0;i<4;i++)for(let k=0;k<4;k++)c[j*4+i]+=a[k*4+i]*b[j*4+k];return c;}
function nodeMatrix(n){if(n.matrix)return n.matrix;const [x,y,z,w]=n.rotation||[0,0,0,1],s=n.scale||[1,1,1],t=n.translation||[0,0,0];return [(1-2*y*y-2*z*z)*s[0],(2*x*y+2*z*w)*s[0],(2*x*z-2*y*w)*s[0],0,(2*x*y-2*z*w)*s[1],(1-2*x*x-2*z*z)*s[1],(2*y*z+2*x*w)*s[1],0,(2*x*z+2*y*w)*s[2],(2*y*z-2*x*w)*s[2],(1-2*x*x-2*y*y)*s[2],0,...t,1];}
function decodeGLB(buffer){
  const dv=new DataView(buffer);if(dv.getUint32(0,true)!==0x46546c67||dv.getUint32(4,true)!==2)throw Error('El archivo debe ser GLB 2');
  let json,bin;for(let p=12;p<buffer.byteLength;){const len=dv.getUint32(p,true),type=dv.getUint32(p+4,true);if(type===0x4e4f534a)json=JSON.parse(new TextDecoder().decode(new Uint8Array(buffer,p+8,len)));if(type===0x004e4942)bin=buffer.slice(p+8,p+8+len);p+=8+len;}
  if(!json||!bin)throw Error('GLB incompleto');
  function accessor(index){const a=json.accessors[index];if(a.sparse)throw Error('Accesor sparse no compatible');const b=json.bufferViews[a.bufferView],dim={SCALAR:1,VEC2:2,VEC3:3,VEC4:4,MAT4:16}[a.type];const types={5120:[1,'getInt8'],5121:[1,'getUint8'],5122:[2,'getInt16'],5123:[2,'getUint16'],5125:[4,'getUint32'],5126:[4,'getFloat32']};const [bytes,get]=types[a.componentType],stride=b.byteStride||dim*bytes,start=(b.byteOffset||0)+(a.byteOffset||0),data=new DataView(bin);const out=new Float64Array(a.count*dim);for(let i=0;i<a.count;i++)for(let k=0;k<dim;k++)out[i*dim+k]=data[get](start+i*stride+k*bytes,true);return out;}
  const result=[];const box=[[Infinity,Infinity,Infinity],[-Infinity,-Infinity,-Infinity]];
  function visit(ni,parent){const node=json.nodes[ni],mat=multiply(parent,nodeMatrix(node));if(node.mesh!==undefined){const mesh=json.meshes[node.mesh];for(const prim of mesh.primitives){if(prim.mode!==undefined&&prim.mode!==4)continue;const points=accessor(prim.attributes.POSITION),indices=prim.indices===undefined?Array.from({length:points.length/3},(_,i)=>i):accessor(prim.indices);const flat=new Float32Array(indices.length*6);for(let i=0;i<indices.length;i+=3){const tri=[];for(let j=0;j<3;j++){const k=indices[i+j]*3,x=points[k],y=points[k+1],z=points[k+2];const p=[(mat[0]*x+mat[4]*y+mat[8]*z+mat[12])*1000,(mat[1]*x+mat[5]*y+mat[9]*z+mat[13])*1000,(mat[2]*x+mat[6]*y+mat[10]*z+mat[14])*1000];tri.push(p);for(let a=0;a<3;a++){box[0][a]=Math.min(box[0][a],p[a]);box[1][a]=Math.max(box[1][a],p[a]);}}const a=tri[0],b=tri[1],c=tri[2],u=b.map((v,k)=>v-a[k]),v=c.map((v,k)=>v-a[k]);let n=[u[1]*v[2]-u[2]*v[1],u[2]*v[0]-u[0]*v[2],u[0]*v[1]-u[1]*v[0]],l=Math.hypot(...n)||1;n=n.map(x=>x/l);for(let j=0;j<3;j++){flat.set(tri[j],(i+j)*6);flat.set(n,(i+j)*6+3);}}
      const name=node.name||mesh.name||'Modelo',layer=name.startsWith('Respiradero')?'lower':name.startsWith('Mesa')?'table':'upper';
      result.push({name,flat,count:indices.length,layer,color:layer==='table'?[0.67,0.57,0.40]:layer==='lower'?[0.77,0.67,0.49]:[0.82,0.73,0.56]});
  }}for(const child of node.children||[])visit(child,mat);}
  const root=json.scenes[json.scene||0];for(const ni of root.nodes)visit(ni,identity());if(!result.length)throw Error('El GLB no contiene triángulos');return {objects:result,bounds:box};
}
function render(){
 const ratio=Math.min(devicePixelRatio,2),w=Math.round(canvas.clientWidth*ratio),h=Math.round(canvas.clientHeight*ratio);
 if(canvas.width!==w||canvas.height!==h){canvas.width=w;canvas.height=h;}
 const shift=bounds[0].map((v,i)=>-(v+bounds[1][i])/2);
 gl.enable(gl.DEPTH_TEST);gl.disable(gl.CULL_FACE);
 if(shadowDirty || objects.length){
  gl.bindFramebuffer(gl.FRAMEBUFFER,shadowBuffer);gl.viewport(0,0,2048,2048);gl.clearColor(1,1,1,1);gl.clear(gl.COLOR_BUFFER_BIT|gl.DEPTH_BUFFER_BIT);gl.useProgram(depthProgram);gl.uniformMatrix4fv(depthLoc.view,false,lightMatrix);gl.uniform3fv(depthLoc.shift,shift);gl.enableVertexAttribArray(depthLoc.pos);
  for(const o of objects){if(!visible[o.layer])continue;gl.bindBuffer(gl.ARRAY_BUFFER,o.buffer);gl.vertexAttribPointer(depthLoc.pos,3,gl.FLOAT,false,24,0);gl.drawArrays(gl.TRIANGLES,0,o.count);}
  gl.bindFramebuffer(gl.FRAMEBUFFER,null);shadowDirty=false;
 }
 gl.useProgram(program);gl.viewport(0,0,w,h);gl.clearColor(0,0,0,0);gl.clear(gl.COLOR_BUFFER_BIT|gl.DEPTH_BUFFER_BIT);const sy=110/zoom;
 gl.uniformMatrix4fv(loc.view,false,cameraMatrix(yaw,pitch,sy*w/h,sy));gl.uniformMatrix4fv(loc.lightView,false,lightMatrix);gl.uniform3fv(loc.shift,shift);gl.activeTexture(gl.TEXTURE0);gl.bindTexture(gl.TEXTURE_2D,shadowTexture);gl.uniform1i(loc.shadowMap,0);gl.uniform3f(loc.lightDir,Math.sin(lightYaw)*Math.cos(0.65),-Math.cos(lightYaw)*Math.cos(0.65),Math.sin(0.65));
 for(const o of objects){if(!visible[o.layer])continue;gl.bindBuffer(gl.ARRAY_BUFFER,o.buffer);gl.enableVertexAttribArray(ap);gl.enableVertexAttribArray(an);gl.vertexAttribPointer(ap,3,gl.FLOAT,false,24,0);gl.vertexAttribPointer(an,3,gl.FLOAT,false,24,12);gl.uniform3fv(loc.color,o.color);gl.drawArrays(gl.TRIANGLES,0,o.count);}
 window.PASO_READY=objects.length>0;
}
let key='',busy=false,reloads=0;
async function check(){if(busy||document.hidden)return;busy=true;try{const response=await fetch('/estado',{cache:'no-store'});if(!response.ok)throw Error('Servidor no disponible');const s=await response.json();if(s.key!==key){status.textContent='Actualizando modelo…';const res=await fetch('paso_completo.glb?t='+encodeURIComponent(s.key),{cache:'no-store'});if(!res.ok)throw Error('Archivo 3D no disponible');const decoded=decodeGLB(await res.arrayBuffer());const next=decoded.objects.map(o=>{const buffer=gl.createBuffer();gl.bindBuffer(gl.ARRAY_BUFFER,buffer);gl.bufferData(gl.ARRAY_BUFFER,o.flat,gl.STATIC_DRAW);delete o.flat;return {...o,buffer};});for(const o of objects)gl.deleteBuffer(o.buffer);objects=next;bounds=decoded.bounds;shadowDirty=true;key=s.key;reloads++;const dims=bounds[1].map((v,i)=>v-bounds[0][i]);document.getElementById('height').textContent=dims[2].toFixed(1).replace('.',',');document.getElementById('measurements').textContent=[dims[1],dims[0],dims[2]].map(x=>x.toFixed(1).replace('.',',')).join(' × ');render();document.getElementById('updated').textContent=new Date().toLocaleTimeString('es-ES',{hour:'2-digit',minute:'2-digit',second:'2-digit'});}status.textContent='● Conectado · Cambios automáticos';status.dataset.state='ok';}catch(error){status.textContent=objects.length?'● Reconectando · Se conserva la última vista':'No se pudo cargar el modelo: '+error.message;status.dataset.state='error';}finally{busy=false;}}
let dragging=false,lastX=0,lastY=0;canvas.addEventListener('pointerdown',e=>{dragging=true;lastX=e.clientX;lastY=e.clientY;canvas.setPointerCapture(e.pointerId);canvas.style.cursor='grabbing';});canvas.addEventListener('pointermove',e=>{if(!dragging)return;yaw-=(e.clientX-lastX)*0.008;pitch=Math.max(-1.5,Math.min(1.57,pitch+(e.clientY-lastY)*0.008));lastX=e.clientX;lastY=e.clientY;document.querySelectorAll('[data-view]').forEach(b=>b.setAttribute('aria-pressed','false'));render();});canvas.addEventListener('pointerup',()=>{dragging=false;canvas.style.cursor='grab';});canvas.addEventListener('pointercancel',()=>{dragging=false;});canvas.addEventListener('wheel',e=>{e.preventDefault();zoom=Math.max(0.55,Math.min(3,zoom*Math.exp(-e.deltaY*0.001)));render();},{passive:false});
const views={perspectiva:[0.72,0.46],frente:[0,0],lateral:[Math.PI/2,0],planta:[0,Math.PI/2]};document.querySelectorAll('[data-view]').forEach(b=>b.addEventListener('click',()=>{[yaw,pitch]=views[b.dataset.view];zoom=b.dataset.view==='frente'?1.75:1.25;document.querySelectorAll('[data-view]').forEach(x=>x.setAttribute('aria-pressed',String(x===b)));render();}));document.querySelectorAll('[data-layer]').forEach(c=>c.addEventListener('change',()=>{visible[c.dataset.layer]=c.checked;shadowDirty=true;render();}));window.addEventListener('resize',render);document.addEventListener('visibilitychange',()=>{if(!document.hidden)check();});
window.PASO_VIEW={render,get:()=>({yaw,pitch,zoom,visible,reloads,objects:objects.length,bounds}),set:(y,p,z)=>{yaw=y;pitch=p;zoom=z;render();}};
render();check();setInterval(check,1000);
})();




