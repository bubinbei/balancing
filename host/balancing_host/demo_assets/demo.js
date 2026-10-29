(() => {
  const $=id=>document.getElementById(id), root=$('app'), renderer=createCradle($('model'));
  const fmt=(v,d=2)=>Number(v).toLocaleString('ru-RU',{minimumFractionDigits:d,maximumFractionDigits:d});
  const state={scenario:'asymmetric',stage:'before',playing:false,animation:0}, reduced=matchMedia('(prefers-reduced-motion: reduce)');
  let data=null;
  const el=(tag,attrs={},content='')=>{const e=document.createElementNS('http://www.w3.org/2000/svg',tag);for(const [k,v] of Object.entries(attrs))e.setAttribute(k,v);e.textContent=content;return e;};
  function polar(id,plane){
    const svg=$(id);svg.setAttribute('viewBox','0 0 155 155');svg.replaceChildren();
    svg.append(el('circle',{cx:77.5,cy:77.5,r:52,fill:'none',stroke:'var(--line)'}));
    for(const [angle,label] of [[0,'0°'],[90,'90°'],[180,'180°'],[270,'270°']]){
      const rad=angle*Math.PI/180,x=77.5+66*Math.sin(rad),y=77.5-66*Math.cos(rad);
      svg.append(el('text',{x,y:y+4,'text-anchor':'middle','font-size':11,fill:'var(--muted)'},label));
    }
    function arrow(angle,color,dashed){
      const rad=angle*Math.PI/180,x=77.5+48*Math.sin(rad),y=77.5-48*Math.cos(rad);
      svg.append(el('line',{x1:77.5,y1:77.5,x2:x,y2:y,stroke:color,'stroke-width':2,'stroke-dasharray':dashed?'4 3':'none'}));
      const pts=[[-4,9],[0,0],[4,9]].map(([a,b])=>`${x+a*Math.cos(rad)-b*Math.sin(rad)},${y+a*Math.sin(rad)+b*Math.cos(rad)}`).join(' ');
      svg.append(el('polyline',{points:pts,fill:'none',stroke:color,'stroke-width':2}));
    }
    arrow(plane.heavy_angle_deg,'var(--ink)',false);arrow(plane.addition_angle_deg,'var(--accent)',true);
    svg.append(el('circle',{cx:77.5,cy:77.5,r:3,fill:'var(--ink)'}));
  }
  function currentScenario(){return data.scenarios.find(s=>s.id===state.scenario);}
  function stop(){state.playing=false;cancelAnimationFrame(state.animation);$('play').textContent=reduced.matches?'Следующая фаза':'Показать движение';}
  function update(){
    stop();const scenario=currentScenario(),run=scenario[state.stage];
    for(const [i,key] of ['a','b'].entries()){
      const p=run.planes[i];$('mass-'+key).textContent=fmt(p.equivalent_mass_g,3)+' г';
      $('unbalance-'+key).textContent=fmt(p.unbalance_gmm)+' г·мм';
      $('correction-'+key).textContent='Добавить '+fmt(p.equivalent_mass_g,3)+' г при '+fmt(p.addition_angle_deg,1)+'°';
      polar('polar-'+key,p);
    }
    $('comparison').replaceChildren();
    for(let i=0;i<2;i++){
      const tr=document.createElement('tr');
      for(const value of [i?'B':'A',fmt(scenario.before.planes[i].unbalance_gmm),fmt(scenario.after.planes[i].unbalance_gmm),state.stage==='before'?'До коррекции':'После коррекции']){const td=document.createElement('td');td.textContent=value;tr.append(td);}
      $('comparison').append(tr);
    }
    const ceiling=Math.max(...scenario.before.accel_rms_mg)*1.7;
    renderer.set(run,data.rpm,ceiling);renderer.frame(0);
    $('color-legend').textContent='Ускорение RMS · 0–'+fmt(ceiling,1)+' mg · шкала до/после общая';
    $('before').setAttribute('aria-pressed',String(state.stage==='before'));$('after').setAttribute('aria-pressed',String(state.stage==='after'));
    $('status').textContent='ДЕМО · '+(state.stage==='before'?'Исходный синтетический прогон':'Контрольный синтетический прогон после коррекции')+' · физическая точность не подтверждена';
    root.dataset.stage=state.stage;root.dataset.scenario=state.scenario;
  }
  $('scenario').addEventListener('change',e=>{if(data){state.scenario=e.target.value;state.stage='before';update();}});
  for(const stage of ['before','after'])$(stage).addEventListener('click',()=>{if(data){state.stage=stage;update();}});
  $('view').addEventListener('click',()=>{$('view').textContent=renderer.toggleView()?'Общий вид':'Вид с торца';});
  $('play').addEventListener('click',()=>{
    if(!data)return;if(state.playing){stop();return;}
    if(reduced.matches){state.angle=(state.angle||0)+Math.PI/4;renderer.frame(state.angle);return;}
    state.playing=true;$('play').textContent='Пауза';const start=performance.now();
    function tick(now){if(!state.playing)return;const progress=Math.min(1,(now-start)/8000);renderer.frame(progress*2*Math.PI);if(progress<1)state.animation=requestAnimationFrame(tick);else stop();}
    state.animation=requestAnimationFrame(tick);
  });
  document.addEventListener('visibilitychange',()=>{if(document.hidden)stop();});
  fetch('/api/demo').then(r=>{if(!r.ok)throw new Error('HTTP '+r.status);return r.json();}).then(value=>{
    if(value.data_kind!=='synthetic'||value.hardware_connected!==false)throw new Error('Ожидались синтетические данные');
    data=value;$('scenario').replaceChildren();
    for(const scenario of data.scenarios){const option=document.createElement('option');option.value=scenario.id;option.textContent=scenario.label;$('scenario').append(option);}
    $('scenario').disabled=false;$('run-info').textContent=data.rpm+' об/мин · '+data.seconds+' с · '+data.sample_rate_hz+' отсчётов/с';
    update();root.dataset.ready='true';if(!reduced.matches)$('play').click();
  }).catch(error=>{$('status').textContent='Демо не загрузилось: '+error.message;root.dataset.ready='error';});
})();
