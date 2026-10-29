/* Standalone renderer adapted from this project's earlier cradle UI sketch.
 * Motion and heat map use the synthetic generator's rigid-body coefficients.
 * Display magnification is fixed across before/after; geometry is illustrative.
 */
window.createCradle = function(canvas) {
  const ctx=canvas.getContext('2d'), TAU=2*Math.PI, gain=6000;
  const add=(a,b)=>a.map((v,i)=>v+b[i]),sub=(a,b)=>a.map((v,i)=>v-b[i]);
  const mul=(a,k)=>a.map(v=>v*k),dot=(a,b)=>a.reduce((s,v,i)=>s+v*b[i],0);
  const cross=(a,b)=>[a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]];
  const unit=a=>mul(a,1/(Math.hypot(...a)||1)), clamp=(x,a,b)=>Math.max(a,Math.min(b,x));
  const value=(i,t)=>motion.real[i]*Math.cos(t)-motion.imag[i]*Math.sin(t);
  let motion={real:[0,0,0],imag:[0,0,0]}, angle=0,rpm=900,ceiling=1;
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
    const center=[0,0,.15],eye=add(center,mul([Math.sin(azimuth)*Math.cos(elevation),-Math.cos(azimuth)*Math.cos(elevation),Math.sin(elevation)],3.3));
    const forward=unit(sub(center,eye)),right=unit(cross(forward,[0,0,1])),up=cross(right,forward),scale=Math.min(w*2.1,h*2.1);
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
  function scene(){
    objects=[];
    for(const y of [-.15,.15])for(let i=0;i<10;i++)box([-.36+i*.08,y,-.29],[.08,.05,.09],'heat');
    for(const x of [-.34,.34]){
      box([x,0,-.30],[.085,.35,.055],'heat');
      for(const y of [-.15,.15])box([x,y,-.14],[.065,.05,.30],'heat');
      box([x,0,.015],[.07,.35,.045],'heat');
      box([x,0,-.16],[.095,.14,.11],'metal');
      cylinder([x-.052,0,-.1],[x+.052,0,-.1],.055,'metal',18);
      box([x,.065,-.1],[.045,.035,.02],'ink');
    }
    cylinder([-.46,0,-.1],[.46,0,-.1],.019,'metal');
    for(const [i,x] of [-.225,-.075,.075,.225].entries()){
      const phi=[0,Math.PI,Math.PI,0][i],y=.06*Math.cos(phi),z=-.1+.06*Math.sin(phi);
      cylinder(rotor([x-.025,y,z]),rotor([x+.025,y,z]),.026,'metal');
      for(const xx of [x-.035,x+.035]){
        cylinder(rotor([xx,0,-.1]),rotor([xx,y,z]),.035,'ghost',10);
        cylinder([xx-.007,0,-.1],[xx+.007,0,-.1],.065,'ghost',16);
      }
    }
    cylinder([.46,0,-.1],[.49,0,-.1],.145,'metal',32);
    cylinder([-.49,0,-.1],[-.46,0,-.1],.075,'ghost',24);
    const mark=rotor([.497,0,.025]);cylinder(add(mark,[-.003,0,0]),add(mark,[.003,0,0]),.009,'second',8);
  }
  function path(points,project,closed=false){ctx.beginPath();points.forEach((p,i)=>{const q=project(p);if(i)ctx.lineTo(q[0],q[1]);else ctx.moveTo(q[0],q[1]);});if(closed)ctx.closePath();}
  function render(){
    const bounds=canvas.getBoundingClientRect();w=bounds.width;h=bounds.height;dpr=Math.min(2,devicePixelRatio||1);
    if(canvas.width!==Math.round(w*dpr)||canvas.height!==Math.round(h*dpr)){canvas.width=Math.round(w*dpr);canvas.height=Math.round(h*dpr);}
    ctx.setTransform(dpr,0,0,dpr,0,0);ctx.clearRect(0,0,w,h);palette();
    const project=projection(),tr=transform(angle);ctx.lineJoin='round';ctx.lineCap='round';
    ctx.strokeStyle=colors.line;ctx.lineWidth=1;
    for(let i=-3;i<=3;i++){path([[-.7,i*.15,-.36],[.7,i*.15,-.36]],project);ctx.stroke();}
    ctx.strokeStyle=colors.ghost;ctx.lineWidth=6;path([[-.55,0,.8],[.55,0,.8]],project);ctx.stroke();
    ctx.strokeStyle=colors.muted;ctx.lineWidth=1.5;
    for(const x of [-.34,.34]){path([[x,0,.8],tr([x,0,0])],project);ctx.stroke();}
    scene();
    const polys=objects.map(o=>({o,world:o.points.map(tr)}));polys.sort((a,b)=>b.world.reduce((s,p)=>s+project(p)[2],0)/b.world.length-a.world.reduce((s,p)=>s+project(p)[2],0)/a.world.length);
    const light=unit([-.3,-.6,1]);
    for(const {o,world} of polys){
      const normal=unit(cross(sub(world[1],world[0]),sub(world[2],world[0]))),shade=.7+.3*Math.max(0,dot(normal,light));
      const c=o.material==='heat'?mix(colors.accent,colors.second,clamp(accel(o.center)/ceiling,0,1)):colors[o.material];
      ctx.fillStyle='rgb('+rgb(c).map(v=>Math.round(v*shade)).join(',')+')';path(world,project,true);ctx.fill();
      ctx.strokeStyle=colors.bg;ctx.lineWidth=.35;ctx.stroke();
    }
    for(const [i,x] of [-.34,.34].entries()){
      const p=[x,.065,-.1],orbit=Array.from({length:65},(_,j)=>transform(TAU*j/64)(p));
      ctx.strokeStyle=i?colors.second:colors.accent;ctx.lineWidth=2;path(orbit,project);ctx.stroke();
      const q=project(tr([x,0,.07]));ctx.font='600 15px system-ui';ctx.textAlign='center';ctx.fillStyle=colors.ink;
      ctx.fillText(i?'B':'A',clamp(q[0]+(endView?(i?18:-18):0),15,w-15),clamp(q[1],25,h-15));
    }
  }
  let drag=null;
  canvas.addEventListener('pointerdown',e=>{drag={x:e.clientX,y:e.clientY,a:azimuth,b:elevation};canvas.setPointerCapture(e.pointerId);});
  canvas.addEventListener('pointermove',e=>{if(drag){azimuth=drag.a+(e.clientX-drag.x)*.008;elevation=clamp(drag.b+(e.clientY-drag.y)*.006,-.1,.8);render();}});
  for(const event of ['pointerup','pointercancel'])canvas.addEventListener(event,()=>{drag=null;});
  new ResizeObserver(render).observe(canvas);matchMedia('(prefers-color-scheme: dark)').addEventListener('change',render);
  return {set(data,newRpm,limit){motion={real:data.motion_real,imag:data.motion_imag};rpm=newRpm;ceiling=Math.max(.001,limit);render();},
    frame(a){angle=a;render();},toggleView(){endView=!endView;azimuth=endView?-Math.PI/2:-.45;elevation=endView?.08:.25;render();return endView;},
    transform, amplitude};
};
