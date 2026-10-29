/* Standalone renderer adapted from this project's earlier cradle UI sketch.
 * Motion and heat map use the synthetic generator's rigid-body coefficients.
 * Display magnification is fixed across before/after; geometry is illustrative.
 */
// Opaque surfaces use a per-pixel depth buffer. Sorting entire long polygons
// by their average depth cannot correctly render a shaft crossing bearings.
window.createDepthLayer = function() {
  const canvas=document.createElement('canvas');
  const gl=canvas.getContext('webgl',{alpha:true,antialias:true,premultipliedAlpha:false,preserveDrawingBuffer:true});
  if(!gl)return null;
  function shader(type,source){
    const s=gl.createShader(type);gl.shaderSource(s,source);gl.compileShader(s);
    if(!gl.getShaderParameter(s,gl.COMPILE_STATUS))throw Error(gl.getShaderInfoLog(s));return s;
  }
  const program=gl.createProgram();
  gl.attachShader(program,shader(gl.VERTEX_SHADER,`attribute vec4 position; attribute vec4 color;
    varying lowp vec4 tint; void main(){gl_Position=position;tint=color;}`));
  gl.attachShader(program,shader(gl.FRAGMENT_SHADER,`precision mediump float;
    varying lowp vec4 tint; void main(){gl_FragColor=tint;}`));
  gl.linkProgram(program);
  if(!gl.getProgramParameter(program,gl.LINK_STATUS))throw Error(gl.getProgramInfoLog(program));
  const buffer=gl.createBuffer(),position=gl.getAttribLocation(program,'position'),color=gl.getAttribLocation(program,'color');
  function draw(vertices,mode){
    if(!vertices.length)return;
    gl.bufferData(gl.ARRAY_BUFFER,new Float32Array(vertices),gl.DYNAMIC_DRAW);
    gl.drawArrays(mode,0,vertices.length/8);
  }
  function render(polys,width,height,dpr){
    if(canvas.width!==Math.round(width*dpr)||canvas.height!==Math.round(height*dpr)){
      canvas.width=Math.round(width*dpr);canvas.height=Math.round(height*dpr);
    }
    gl.viewport(0,0,canvas.width,canvas.height);gl.useProgram(program);
    gl.bindBuffer(gl.ARRAY_BUFFER,buffer);
    for(const [attribute,offset] of [[position,0],[color,16]]){
      gl.enableVertexAttribArray(attribute);gl.vertexAttribPointer(attribute,4,gl.FLOAT,false,32,offset);
    }
    gl.clearColor(0,0,0,0);gl.depthMask(true);gl.clear(gl.COLOR_BUFFER_BIT|gl.DEPTH_BUFFER_BIT);
    gl.enable(gl.DEPTH_TEST);gl.depthFunc(gl.LEQUAL);gl.disable(gl.CULL_FACE);gl.disable(gl.BLEND);
    const near=.1,far=10;
    const vertex=(p,c)=>[(2*p[0]/width-1)*p[2],(1-2*p[1]/height)*p[2],
      (far+near)/(far-near)*p[2]-2*far*near/(far-near),p[2],...c];
    const triangles=poly=>{
      const result=[];
      for(let j=1;j+1<poly.points.length;j++)
        for(const i of [0,j,j+1])result.push(...vertex(poly.points[i],poly.colors?.[i]||poly.color));
      return result;
    };
    const solid=[],glass=[];
    for(const poly of polys){if(poly.color[3]<1)glass.push(poly);else solid.push(...triangles(poly));}
    draw(solid,gl.TRIANGLES);
    // Only the frame is translucent: behind solid metal it fails the depth
    // test; in front it gently tints it. Opaque surfaces always write depth.
    gl.enable(gl.BLEND);gl.blendFuncSeparate(gl.SRC_ALPHA,gl.ONE_MINUS_SRC_ALPHA,gl.ONE,gl.ONE_MINUS_SRC_ALPHA);
    gl.depthMask(false);
    glass.sort((a,b)=>b.points.reduce((s,p)=>s+p[2],0)/b.points.length-a.points.reduce((s,p)=>s+p[2],0)/a.points.length);
    const translucent=[],edges=[];
    for(const poly of glass){
      translucent.push(...triangles(poly));
      if(poly.outline)for(let j=0;j<poly.points.length;j++){
        for(const i of [j,(j+1)%poly.points.length])edges.push(...vertex(poly.points[i],[...(poly.colors?.[i]||poly.color).slice(0,3),.36]));
      }
    }
    draw(translucent,gl.TRIANGLES);draw(edges,gl.LINES);gl.depthMask(true);
    return canvas;
  }
  return {render,canvas};
};
window.createCradle = function(canvas) {
  const ctx=canvas.getContext('2d'), TAU=2*Math.PI, gain=6000;
  const depth=window.createDepthLayer();
  canvas.dataset.renderer=depth?'webgl-depth':'unavailable';
  canvas.dataset.cradleOpacity='0.18';
  const add=(a,b)=>a.map((v,i)=>v+b[i]),sub=(a,b)=>a.map((v,i)=>v-b[i]);
  const mul=(a,k)=>a.map(v=>v*k),dot=(a,b)=>a.reduce((s,v,i)=>s+v*b[i],0);
  const cross=(a,b)=>[a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]];
  const unit=a=>mul(a,1/(Math.hypot(...a)||1)), clamp=(x,a,b)=>Math.max(a,Math.min(b,x));
  const value=(i,t)=>motion.real[i]*Math.cos(t)-motion.imag[i]*Math.sin(t);
  let motion={real:[0,0,0],imag:[0,0,0]}, angle=0,rpm=900,ceiling=1;
  let geometry=null,selected='CW3',candidates=new Set(),planActions=[];
  let azimuth=-.45,elevation=.25,endView=false,w=600,h=380,dpr=1;
  const colors={}, probe=document.createElement('span');probe.hidden=true;document.body.append(probe);
  function palette(){for(const key of ['bg','surface','ink','muted','line','accent','second','metal','wood','ghost']){probe.style.color=`var(--${key})`;colors[key]=getComputedStyle(probe).color;}}
  const rgb=c=>(c.match(/[\d.]+/g)||['0','0','0']).slice(0,3).map(Number);
  const mix=(a,b,t)=>'rgb('+rgb(a).map((v,i)=>Math.round(v+(rgb(b)[i]-v)*t)).join(',')+')';
  const amplitude=(i)=>Math.hypot(motion.real[i],motion.imag[i]);
  function accel(p){
    const re=[-p[1]*motion.real[2],motion.real[0]-p[2]*motion.real[1]+p[0]*motion.real[2],p[1]*motion.real[1]];
    const im=[-p[1]*motion.imag[2],motion.imag[0]-p[2]*motion.imag[1]+p[0]*motion.imag[2],p[1]*motion.imag[1]];
    return Math.pow(TAU*rpm/60,2)*Math.sqrt((dot(re,re)+dot(im,im))/2)/9.80665*1000;
  }
  function transform(t){
    const sy=value(0,t)*gain,roll=value(1,t)*gain,yaw=value(2,t)*gain,a=.34,L=.8;
    // Correct second-order pitch/heave so both displayed strings stay taut.
    let p=0,z=0;
    for(let i=0;i<8;i++){
      const cb=Math.cos(p),sb=Math.sin(p),cy=Math.cos(yaw),sY=Math.sin(yaw);
      const D=-Math.sqrt(Math.max(.1,L*L-sy*sy-2*a*a*(1-cy*cb)));
      const f=sy*sY*cb-D*sb,dD=a*a*cy*sb/Math.max(.1,-D);
      const derivative=-sy*sY*sb-dD*sb-D*cb;
      p-=f/(Math.abs(derivative)>1e-8?derivative:1);z=L+D;
    }
    const cr=Math.cos(roll),sr=Math.sin(roll),cp=Math.cos(p),sp=Math.sin(p),cy=Math.cos(yaw),sY=Math.sin(yaw);
    const R=[[cy*cp,cy*sp*sr-sY*cr,cy*sp*cr+sY*sr],[sY*cp,sY*sp*sr+cy*cr,sY*sp*cr-cy*sr],[-sp,cp*sr,cp*cr]];
    return q=>[dot(R[0],q),dot(R[1],q)+sy,dot(R[2],q)+z];
  }
  function projection(){
    const center=[0,0,-.04],eye=add(center,mul([Math.sin(azimuth)*Math.cos(elevation),-Math.cos(azimuth)*Math.cos(elevation),Math.sin(elevation)],3.3));
    const forward=unit(sub(center,eye)),right=unit(cross(forward,[0,0,1])),up=cross(right,forward),scale=Math.min(w*2.7,h*3.1);
    return p=>{const v=sub(p,eye),d=dot(v,forward);return [w/2+dot(v,right)*scale/d,h*.48-dot(v,up)*scale/d,d];};
  }
  let objects=[];
  function face(points,material,center){objects.push({points,material,center});}
  function box(center,size,material){
    const [x,y,z]=size.map(v=>v/2),v=[[-x,-y,-z],[x,-y,-z],[x,y,-z],[-x,y,-z],[-x,-y,z],[x,-y,z],[x,y,z],[-x,y,z]].map(p=>add(center,p));
    for(const ids of [[0,3,2,1],[4,5,6,7],[0,1,5,4],[1,2,6,5],[2,3,7,6],[3,0,4,7]])face(ids.map(i=>v[i]),material,center);
  }
  function cylinder(a,b,r,material,n=14){
    const axis=unit(sub(b,a)),u=unit(cross(axis,Math.abs(axis[2])<.9?[0,0,1]:[0,1,0])),v=cross(axis,u);
    const rings=[a,b].map(c=>Array.from({length:n},(_,i)=>add(c,add(mul(u,r*Math.cos(i*TAU/n)),mul(v,r*Math.sin(i*TAU/n))))));
    face(rings[0].slice().reverse(),material,a);face(rings[1],material,b);
    for(let i=0;i<n;i++)face([rings[0][i],rings[0][(i+1)%n],rings[1][(i+1)%n],rings[1][i]],material,mul(add(a,b),.5));
  }
  function rotor(p){const y=p[1],z=p[2]+.1;return [p[0],y*Math.cos(angle)-z*Math.sin(angle),y*Math.sin(angle)+z*Math.cos(angle)-.1];}
  function counterweight(cw){
    const x=cw.x_mm/1000,center=cw.center_angle_deg*Math.PI/180,arc=cw.half_arc_deg*Math.PI/180;
    const outer=Array.from({length:13},(_,i)=>center-arc+2*arc*i/12);
    const outline=[...outer.map(phi=>[0,-.082*Math.sin(phi),-.1+.082*Math.cos(phi)]),
      ...outer.slice().reverse().map(phi=>[0,-.024*Math.sin(phi),-.1+.024*Math.cos(phi)])];
    const sides=[-.008,.008].map(dx=>outline.map(p=>rotor([x+dx,p[1],p[2]])));
    const material=cw.id===selected?'accent':candidates.has(cw.id)?'second':'ghost';
    const middle=rotor([x,-.055*Math.sin(center),-.1+.055*Math.cos(center)]);
    // An annular sector is concave: split each cap into convex strips so
    // triangulation does not fill the opening or overlap itself.
    for(const side of sides)for(let j=0;j<outer.length-1;j++)
      face([side[j],side[j+1],side[outline.length-2-j],side[outline.length-1-j]],material,middle);
    for(let j=0;j<outline.length;j++)face([sides[0][j],sides[0][(j+1)%outline.length],sides[1][(j+1)%outline.length],sides[1][j]],material,middle);
  }
  function scene(){
    objects=[];
    for(const y of [-.15,.15])box([0,y,-.29],[.8,.05,.09],'heat');
    for(const x of [-.34,.34]){
      box([x,0,-.30],[.085,.35,.055],'heat');
      for(const y of [-.15,.15])box([x,y,-.14],[.065,.05,.30],'heat');
      box([x,0,.015],[.07,.35,.045],'heat');
      box([x,0,-.16],[.095,.14,.11],'metal');
      cylinder([x-.052,0,-.1],[x+.052,0,-.1],.055,'metal',18);
      box([x,.065,-.1],[.045,.035,.02],'ink');
    }
    // Five main journals, joined through the four offset crankpins/cheeks.
    // A continuous rod through every crank throw is not crankshaft geometry.
    for(const [a,b] of [[-.46,-.268],[-.182,-.118],[-.032,.032],[.118,.182],[.268,.46]])
      cylinder([a,0,-.1],[b,0,-.1],.019,'metal');
    for(const [i,x] of [-.225,-.075,.075,.225].entries()){
      const phi=[0,Math.PI,Math.PI,0][i],y=-.06*Math.sin(phi),z=-.1+.06*Math.cos(phi);
      cylinder(rotor([x-.025,y,z]),rotor([x+.025,y,z]),.026,'metal');
      for(const xx of [x-.035,x+.035]){
        cylinder(rotor([xx,0,-.1]),rotor([xx,y,z]),.035,'ghost',10);
      }
    }
    if(geometry)for(const cw of geometry.counterweights)counterweight(cw);
    cylinder([.46,0,-.1],[.49,0,-.1],.145,'metal',32);
    cylinder([-.49,0,-.1],[-.46,0,-.1],.075,'ghost',24);
    // Wide phase stripe on the A-side pulley face, north at index zero.
    const stripe=[[-.494,-.010,-.043],[-.494,.010,-.043],[-.494,.010,-.024],[-.494,-.010,-.024]].map(rotor);
    face(stripe,'second',rotor([-.494,0,-.034]));
  }
  function path(points,project,closed=false){ctx.beginPath();points.forEach((p,i)=>{const q=project(p);if(i)ctx.lineTo(q[0],q[1]);else ctx.moveTo(q[0],q[1]);});if(closed)ctx.closePath();}
  function render(){
    const bounds=canvas.getBoundingClientRect();w=bounds.width;h=bounds.height;dpr=Math.min(2,devicePixelRatio||1);
    if(w<1||h<1)return;
    if(canvas.width!==Math.round(w*dpr)||canvas.height!==Math.round(h*dpr)){canvas.width=Math.round(w*dpr);canvas.height=Math.round(h*dpr);}
    ctx.setTransform(dpr,0,0,dpr,0,0);ctx.clearRect(0,0,w,h);palette();
    const project=projection(),tr=transform(angle);ctx.lineJoin='round';ctx.lineCap='round';
    ctx.strokeStyle=colors.line;ctx.lineWidth=1;
    for(let i=-3;i<=3;i++){path([[-.7,i*.15,-.36],[.7,i*.15,-.36]],project);ctx.stroke();}
    ctx.strokeStyle=colors.ghost;ctx.lineWidth=6;path([[-.55,0,.8],[.55,0,.8]],project);ctx.stroke();
    ctx.strokeStyle=colors.muted;ctx.lineWidth=1.5;
    for(const x of [-.34,.34]){path([[x,0,.8],tr([x,0,0])],project);ctx.stroke();}
    scene();
    const polys=[];
    const light=unit([-.3,-.6,1]);
    for(const o of objects){
      const world=o.points.map(tr);
      const normal=unit(cross(sub(world[1],world[0]),sub(world[2],world[0]))),shade=.7+.3*Math.max(0,dot(normal,light));
      const c=o.material==='heat'?mix(colors.accent,colors.second,clamp(accel(o.center)/ceiling,0,1)):colors[o.material];
      const vertexColors=o.material==='heat'?o.points.map(p=>[
        ...rgb(mix(colors.accent,colors.second,clamp(accel(p)/ceiling,0,1))).map(v=>v*shade/255),.18]):null;
      polys.push({points:world.map(project),color:[...rgb(c).map(v=>v*shade/255),o.material==='heat'?.18:1],
        colors:vertexColors,outline:o.material==='heat'});
    }
    // Labels are screen-space annotations. Hide a correction symbol if its
    // anchor is behind solid metal (perspective-correct triangle depth).
    function hidden(q){
      for(const poly of polys){
        if(poly.color[3]<1)continue;
        for(let j=1;j+1<poly.points.length;j++){
          const [a,b,c]=[poly.points[0],poly.points[j],poly.points[j+1]];
          const d=(b[1]-c[1])*(a[0]-c[0])+(c[0]-b[0])*(a[1]-c[1]);
          if(Math.abs(d)<1e-8)continue;
          const u=((b[1]-c[1])*(q[0]-c[0])+(c[0]-b[0])*(q[1]-c[1]))/d;
          const v=((c[1]-a[1])*(q[0]-c[0])+(a[0]-c[0])*(q[1]-c[1]))/d;
          if(u>=0&&v>=0&&u+v<=1&&1/(u/a[2]+v/b[2]+(1-u-v)/c[2])<q[2]-.0005)return true;
        }
      }
      return false;
    }
    const markers=[];
    for(const action of planActions){
      const phi=action.removal_angle_deg*Math.PI/180,r=action.radius_mm/1000;
      const q=project(tr(rotor([action.x_mm/1000-.009,-r*Math.sin(phi),-.1+r*Math.cos(phi)])));
      if(!hidden(q))markers.push(q);
    }
    if(depth)ctx.drawImage(depth.render(polys,w,h,dpr),0,0,w,h);
    else {ctx.fillStyle=colors.ink;ctx.font='14px system-ui';ctx.fillText('Для 3D включите WebGL в браузере.',15,h/2);return;}
    for(const q of markers){
      ctx.fillStyle=colors.surface;ctx.strokeStyle=colors.ink;ctx.lineWidth=1.5;
      ctx.beginPath();ctx.arc(q[0],q[1],5,0,TAU);ctx.fill();ctx.stroke();
      ctx.beginPath();ctx.moveTo(q[0]-3,q[1]);ctx.lineTo(q[0]+3,q[1]);ctx.moveTo(q[0],q[1]-3);ctx.lineTo(q[0],q[1]+3);ctx.stroke();
    }
    for(const [i,x] of [-.34,.34].entries()){
      const p=[x,.065,-.1],orbit=Array.from({length:65},(_,j)=>transform(TAU*j/64)(p));
      ctx.strokeStyle=i?colors.second:colors.accent;ctx.lineWidth=2;path(orbit,project);ctx.stroke();
      const q=project(tr([x,0,.07]));ctx.font='600 15px system-ui';ctx.textAlign='center';ctx.fillStyle=colors.ink;
      ctx.fillText(i?'B':'A',clamp(q[0]+(endView?(i?18:-18):0),15,w-15),clamp(q[1],25,h-15));
    }
    function callout(caption,p,dx,dy){
      const q=project(tr(p));ctx.font='600 12px system-ui';
      const tw=ctx.measureText(caption).width,tx=clamp(q[0]+dx,tw/2+5,w-tw/2-5),ty=clamp(q[1]+dy,30,h-20);
      ctx.strokeStyle=colors.second;ctx.lineWidth=1;ctx.beginPath();ctx.moveTo(q[0],q[1]);ctx.lineTo(tx,ty+4);ctx.stroke();
      ctx.fillStyle=colors.surface;ctx.fillRect(tx-tw/2-3,ty-12,tw+6,17);ctx.fillStyle=colors.ink;ctx.textAlign='center';ctx.fillText(caption,tx,ty);
    }
    callout('Полоска 0°',rotor([-.494,0,-.024]),-30,-42);
    const cw=geometry?.counterweights.find(w=>w.id===selected);
    if(cw){const phi=cw.center_angle_deg*Math.PI/180;callout(cw.id,rotor([cw.x_mm/1000,-.082*Math.sin(phi),-.1+.082*Math.cos(phi)]),25,45);}
  }
  let drag=null;
  canvas.addEventListener('pointerdown',e=>{drag={x:e.clientX,y:e.clientY,a:azimuth,b:elevation};canvas.setPointerCapture(e.pointerId);});
  canvas.addEventListener('pointermove',e=>{if(drag){azimuth=drag.a+(e.clientX-drag.x)*.008;elevation=clamp(drag.b+(e.clientY-drag.y)*.006,-.1,.8);render();}});
  for(const event of ['pointerup','pointercancel'])canvas.addEventListener(event,()=>{drag=null;});
  new ResizeObserver(render).observe(canvas);matchMedia('(prefers-color-scheme: dark)').addEventListener('change',render);
  return {set(data,newRpm,limit,newGeometry){motion={real:data.motion_real,imag:data.motion_imag};rpm=newRpm;ceiling=Math.max(.001,limit);geometry=newGeometry||geometry;planActions=data.removal_plan?.actions||[];candidates=new Set(planActions.map(a=>a.counterweight));render();},
    select(id){selected=id;render();},
    frame(a){angle=a;render();},toggleView(){endView=!endView;azimuth=endView?-Math.PI/2:-.45;elevation=endView?.08:.25;render();return endView;},
    transform, amplitude};
};
