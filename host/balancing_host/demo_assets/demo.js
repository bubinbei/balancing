(() => {
  const $=id=>document.getElementById(id), root=$('app'), renderer=createCradle($('model'));
  const fmt=(v,d=2)=>Number(v).toLocaleString('ru-RU',{minimumFractionDigits:d,maximumFractionDigits:d});
  const state={scenario:'asymmetric',stage:'before',playing:false,animation:0,selected:'CW3'}, reduced=matchMedia('(prefers-reduced-motion: reduce)');
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
  function counterweights(){
    const geometry=data.geometry,run=currentScenario()[state.stage],plan=run.removal_plan;
    const candidates=new Set(plan.actions.map(a=>a.counterweight));
    const map=$('counterweight-map'),width=map.getBoundingClientRect().width;
    map.setAttribute('viewBox',`0 0 ${width} 155`);map.replaceChildren();
    const label=(text,x,y,anchor='middle')=>map.append(el('text',{x,y,'font-size':12,fill:'var(--ink)','text-anchor':anchor},text));
    map.append(el('line',{x1:18,y1:75,x2:width-18,y2:75,stroke:'var(--metal)','stroke-width':4}));
    label('Север · 0°',width/2,13);label('Юг · 180°',width/2,151);
    label('A',4,79,'start');label('B',width-4,79,'end');
    $('counterweight-buttons').replaceChildren();
    geometry.counterweights.forEach((cw,i)=>{
      const x=25+i*(width-50)/7,north=cw.center_angle_deg===0,y=north?42:108;
      map.append(el('line',{x1:x,y1:75,x2:x,y2:y,stroke:'var(--line)'}));
      map.append(el('circle',{cx:x,cy:y,r:9,fill:cw.id===state.selected?'var(--accent)':candidates.has(cw.id)?'var(--second)':'var(--metal)'}));
      label(cw.id,x,north?28:132);
      const button=document.createElement('button');button.textContent=cw.id;button.dataset.cw=cw.id;
      button.dataset.candidate=String(candidates.has(cw.id));button.setAttribute('aria-pressed',String(cw.id===state.selected));
      button.addEventListener('click',()=>{stop();state.angle=0;state.selected=cw.id;renderer.frame(0);renderer.select(cw.id);root.dataset.phase='zero';counterweights();document.querySelector(`button[data-cw="${cw.id}"]`).focus({preventScroll:true});});
      $('counterweight-buttons').append(button);
    });
    const cw=geometry.counterweights.find(w=>w.id===state.selected);
    $('counterweight-info').textContent=`${cw.id}: ${cw.center_angle_deg===0?'север':'юг'}, x = ${cw.x_mm} мм от середины, условный радиус ${cw.radius_mm} мм. Выбранный противовес подсвечен в 3D.`;
    $('removal-actions').replaceChildren();
    for(const action of plan.actions){
      const tr=document.createElement('tr');
      for(const value of [action.counterweight,fmt(action.mass_g,3),fmt(action.removal_angle_deg,1)+'°',fmt(action.radius_mm,0)]){const td=document.createElement('td');td.textContent=value;tr.append(td);}
      $('removal-actions').append(tr);
    }
    $('removal-table').hidden=plan.actions.length===0;
    $('removal-status').textContent=plan.status==='demo_candidate'?'Условный вариант снятия: '+plan.actions.map(a=>a.counterweight).join(' + ')+'. Реальные зоны обработки не подтверждены.':plan.status==='not_required'?'В модели коррекция не требуется.':'В заданных секторах не найден вариант на двух противовесах. Нельзя просто сверлить ближайший CW: нужен другой набор точек или иной способ коррекции.';
    root.dataset.removal=plan.status;root.dataset.selectedCw=state.selected;
  }
  function update(){
    stop();const scenario=currentScenario(),run=scenario[state.stage];
    for(const [i,key] of ['a','b'].entries()){
      const p=run.planes[i];$('mass-'+key).textContent=fmt(p.equivalent_mass_g,3)+' г';
      $('unbalance-'+key).textContent=fmt(p.unbalance_gmm)+' г·мм';
      $('correction-'+key).textContent='Добавить '+fmt(p.equivalent_mass_g,3)+' г при '+fmt(p.addition_angle_deg,1)+'°';
      const caption=document.createElement('span');caption.className='removal-caption';caption.textContent='Эквивалентное снятие в этой плоскости: '+fmt(p.heavy_angle_deg,1)+'°';
      $('correction-'+key).append(document.createElement('br'),caption);
      polar('polar-'+key,p);
    }
    $('comparison').replaceChildren();
    for(let i=0;i<2;i++){
      const tr=document.createElement('tr');
      for(const value of [i?'B':'A',fmt(scenario.before.planes[i].unbalance_gmm),fmt(scenario.after.planes[i].unbalance_gmm),state.stage==='before'?'До коррекции':'После коррекции']){const td=document.createElement('td');td.textContent=value;tr.append(td);}
      $('comparison').append(tr);
    }
    const ceiling=Math.max(...scenario.before.accel_rms_mg)*1.7;
    renderer.set(run,data.rpm,ceiling,data.geometry);renderer.select(state.selected);renderer.frame(0);root.dataset.phase='zero';counterweights();
    $('color-legend').textContent='Ускорение RMS · 0–'+fmt(ceiling,1)+' mg · шкала до/после общая';
    $('before').setAttribute('aria-pressed',String(state.stage==='before'));$('after').setAttribute('aria-pressed',String(state.stage==='after'));
    $('status').textContent='ДЕМО · '+(state.stage==='before'?'Исходный синтетический прогон':'Контрольный синтетический прогон после коррекции')+' · физическая точность не подтверждена';
    root.dataset.stage=state.stage;root.dataset.scenario=state.scenario;
  }
  $('scenario').addEventListener('change',e=>{if(data){state.scenario=e.target.value;state.stage='before';update();}});
  for(const stage of ['before','after'])$(stage).addEventListener('click',()=>{if(data){state.stage=stage;update();}});
  $('view').addEventListener('click',()=>{$('view').textContent=renderer.toggleView()?'Общий вид':'Вид с торца';});
  $('zero').addEventListener('click',()=>{stop();state.angle=0;renderer.frame(0);root.dataset.phase='zero';});
  new ResizeObserver(()=>{if(data)counterweights();}).observe($('counterweight-map'));
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
    update();root.dataset.ready='true';
  }).catch(error=>{$('status').textContent='Демо не загрузилось: '+error.message;root.dataset.ready='error';});
})();
