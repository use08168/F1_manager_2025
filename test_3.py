import streamlit as st
import json

st.set_page_config(layout="wide", page_title="SVG Race Preview — 20 Cars + Roster Card + Live Params")

st.title("🏁 SVG Race Preview — 20 Cars + Natural Pit-In + Roster Card + Live Params")

u = st.file_uploader("SVG 업로드", type=["svg"])

RAW_SVG = u.getvalue().decode("utf-8", "ignore") if u else ""
VIEWBOX_FALLBACK = "0 0 1200 800"

html = r"""
<style>
  #wrap { display:grid; grid-template-columns: 1fr 360px; gap:16px; margin-top:12px; }
  #left  { background:#fff; border:1px solid #e5e7eb; border-radius:14px; padding:12px; }
  #right { background:#f8fafc; border:1px solid #e5e7eb; border-radius:14px; padding:12px; font-size:13px; color:#334155; }
  #stage { width:100%; height:820px; background:#fff; border-radius:10px; box-shadow:0 6px 24px rgba(0,0,0,.08); user-select:none; }
  .panel h3 { margin:.25rem 0 .5rem; font-size:14px; color:#0f172a; }
  .muted { color:#64748b; font-size:12px; }
  .legend { display:flex; flex-wrap:wrap; gap:8px; margin:8px 0 12px; }
  .chip { font-size:11px; padding:2px 6px; border-radius:999px; border:1px solid #cbd5e1; background:white; }
  .btns { display:flex; gap:8px; margin:8px 0 12px; }
  .btn  { font-size:13px; padding:6px 10px; border-radius:8px; border:1px solid #cbd5e1; background:white; cursor:pointer; }
  .btn.primary { background:#0b5cff; color:#fff; border-color:#0b5cff; }
  .grid2 { display:grid; grid-template-columns: 1fr 1fr; gap:8px; margin:6px 0 12px; }
  .panel label { font-size:12px; color:#0f172a; display:block; }
  .panel input { width:100%; box-sizing:border-box; padding:6px 8px; border-radius:8px; border:1px solid #cbd5e1; background:#fff; font-size:13px; }

  /* 클릭 가능 보장 */
  .car, .carLabel { cursor: pointer; pointer-events: auto; }
</style>

<div id="wrap">
  <div id="left">
    <svg id="stage" viewBox="0 0 1200 800">
      <g id="track"></g>
      <g id="actors"></g>
    </svg>
  </div>
  <div id="right" class="panel">
    <h3>미리보기</h3>
    <div class="legend">
      <span class="chip">메인: 진회색</span>
      <span class="chip">피트: 회색</span>
      <span class="chip">결승선: 빨강선</span>
      <span class="chip">Markers: pitIn/Out/Stop</span>
    </div>

    <div class="grid2">
      <label>Lap (sec)
        <input id="lapSecInput" type="number" min="0.3" step="0.1" value="2.5">
      </label>
      <label>Pit wait (sec)
        <input id="waitSecInput" type="number" min="0" step="0.1" value="3.0">
      </label>
      <label>Transition (ms)
        <input id="transMsInput" type="number" min="50" step="50" value="900">
      </label>
      <label>Pit speed ×
        <input id="pitMulInput" type="number" min="0.1" step="0.1" value="0.6">
      </label>
      <label>Pit-In 대상 차량 (1~20)
        <input id="targetCarInput" type="number" min="1" max="20" step="1" value="1">
      </label>
    </div>

    <div class="btns">
      <button id="play" class="btn primary">▶ Play</button>
      <button id="stop" class="btn">⏹ Stop</button>
      <button id="pitInNow" class="btn">Pit-In (선택 차량)</button>
    </div>
    <div class="muted" id="state">state: idle</div>

    <h3>선수 카드</h3>
    <div id="card" style="display:none; padding:10px; border:1px solid #cbd5e1; border-radius:10px; background:#fff;">
      <div id="cHeader" style="font-weight:600; margin-bottom:6px;">-</div>
      <div class="muted" id="cSub">-</div>
      <div id="cMode" class="muted" style="margin-top:6px;">mode: -</div>
    </div>

    <h3>파싱 결과</h3>
    <div id="report" class="muted"></div>
  </div>
</div>

<script>
(function(){
  const RAW = %%RAW_SVG%%;
  const VIEWBOX_FALLBACK = "%%VIEWBOX%%";
  const stage = document.getElementById('stage');
  const gTrack= document.getElementById('track');
  const gAct  = document.getElementById('actors');
  const report= document.getElementById('report');
  const stateEl=document.getElementById('state');

  // ===== 기본 로스터(예시) =====
  const roster = Array.from({length:20}, (_,i)=>({
    num: i+1,
    name: `Driver ${i+1}`,
    team: `Team ${String.fromCharCode(65 + (i%5))}`
  }));

  // Live parameters
  const params = {
    lapSec: 2.5,
    waitSec: 3.0,
    transMs: 900,
    pitMul: 0.6,
    targetCar: 1
  };
  const lapIn  = document.getElementById('lapSecInput');
  const waitIn = document.getElementById('waitSecInput');
  const transIn= document.getElementById('transMsInput');
  const pitMulIn=document.getElementById('pitMulInput');
  const carIn  = document.getElementById('targetCarInput');

  function bindLive(inputEl, key, mapFn){
    inputEl.addEventListener('input', ()=>{
      const v = mapFn ? mapFn(inputEl.value) : parseFloat(inputEl.value);
      if (Number.isFinite(v)) {
        params[key] = v;
        if (key==='targetCar') selectCar(v-1, false); // UI 동기화
      }
    });
  }
  bindLive(lapIn,  'lapSec',  v=>Math.max(0.1, parseFloat(v)));
  bindLive(waitIn, 'waitSec', v=>Math.max(0, parseFloat(v)));
  bindLive(transIn,'transMs', v=>Math.max(50, parseInt(v||"0",10)));
  bindLive(pitMulIn,'pitMul', v=>Math.max(0.1, parseFloat(v)));
  bindLive(carIn,  'targetCar', v=>Math.min(20, Math.max(1, parseInt(v||"1",10))));

  // ---------------- SVG helpers ----------------
  const colors=['#ff6b00','#00a3ff','#ffd400','#5ad469','#c86bff','#ff4d6d','#3bc9db','#fab005','#9b59b6','#2ecc71',
                '#e67e22','#3498db','#f1c40f','#1abc9c','#e84393','#16a085','#c0392b','#8e44ad','#2980b9','#2ecc71'];
  function text(x,y,str,size=10,fill='#0f172a'){const t=document.createElementNS(stage.namespaceURI,'text');t.setAttribute('x',x);t.setAttribute('y',y);t.setAttribute('font-size',String(size));t.setAttribute('fill',fill);t.textContent=str;return t;}
  function ptOn(path,s){const L=Math.max(1,path.getTotalLength()); const c=Math.max(0,Math.min(1,s)); const q=path.getPointAtLength(c*L); return {x:q.x,y:q.y};}
  function nearestS(path,p){ if(!path) return 0; const L=path.getTotalLength(),N=1000; let bestS=0,bestD=1e9; for(let i=0;i<=N;i++){const s=i/N; const q=path.getPointAtLength(s*L); const dx=q.x-p.x,dy=q.y-p.y; const d=dx*dx+dy*dy; if(d<bestD){bestD=d;bestS=s;}} return bestS;}
  function reachedForward(a,b,target){ return (b>=a) ? (target>=a && target<=b) : (target>=a || target<=b); }

  function parseSVG(raw){
    if(!raw || !raw.trim()) return null;
    return new DOMParser().parseFromString(raw, "image/svg+xml");
  }
  function getViewBox(doc){
    const root = doc.querySelector('svg');
    return (root && root.getAttribute('viewBox')) ? root.getAttribute('viewBox') : VIEWBOX_FALLBACK;
  }
  function grabPathD(doc, id){ const el = doc.querySelector(`path#${id}`); return el ? el.getAttribute('d') : ''; }
  function grabFinishPoints(doc){
    const el = doc.querySelector('polyline#finish, line#finish');
    if(!el) return [];
    if (el.tagName.toLowerCase()==='polyline'){
      const pts=(el.getAttribute('points')||'').trim().split(/\s+/).map(s=>s.split(',').map(parseFloat));
      return pts.slice(0,2).map(([x,y])=>({x,y}));
    } else {
      return [{x:+el.getAttribute('x1')||0,y:+el.getAttribute('y1')||0},{x:+el.getAttribute('x2')||0,y:+el.getAttribute('y2')||0}];
    }
  }
  function grabPointFromData(doc,id){
    const el=doc.querySelector(`#${id}`); if(!el) return null;
    const dpt=(el.getAttribute('data-pt')||'').split(',').map(parseFloat);
    if (dpt.length===2 && dpt.every(Number.isFinite)) return {x:dpt[0],y:dpt[1]};
    return null;
  }
  function grabMarkersFromMetadata(doc){
    const md = doc.querySelector('metadata'); if(!md) return {};
    try{
      const obj = JSON.parse(md.textContent||"{}");
      const pick=k=> (obj[k]&&Array.isArray(obj[k].pts)&&obj[k].pts[0]) ? obj[k].pts[0] : null;
      return { pitIn:pick('pitIn'), pitOut:pick('pitOut'), pitStop:pick('pitStop') };
    }catch(e){ return {}; }
  }
  function grabStartGridFromMetadata(doc){
    const md = doc.querySelector('metadata'); if(!md) return null;
    try{
      const obj = JSON.parse(md.textContent||"{}");
      if (obj.start && Array.isArray(obj.start.pts))
        return obj.start.pts.map(p=>({x:p.x,y:p.y,num:p.num||null}));
    }catch(e){}
    return null;
  }
  function grabStartGridFromGroup(doc){
    const g = doc.querySelector('g#grid'); if(!g) return null;
    const nodes=[...g.querySelectorAll('circle')]; if(nodes.length===0) return null;
    return nodes.map(el=>{
      const [x,y]=(el.getAttribute('data-pt')||'0,0').split(',').map(parseFloat);
      const num=parseInt(el.getAttribute('data-num')||'0',10)||null;
      return {x,y,num};
    });
  }

  // -------- build & scene --------
  let parsed=null;
  function buildFromRaw(){
    if(!RAW){ report.textContent="SVG를 업로드하면 즉시 미리보기가 표시됩니다."; return null; }
    const doc=parseSVG(RAW); if(!doc){ report.textContent="SVG 파싱 실패"; return null; }
    stage.setAttribute('viewBox', getViewBox(doc));

    const dMain=grabPathD(doc,'main');
    const dPit =grabPathD(doc,'pit');

    gTrack.innerHTML='';
    const pMain=document.createElementNS(stage.namespaceURI,'path');
    const pPit =document.createElementNS(stage.namespaceURI,'path');
    pMain.setAttribute('d', dMain||'M 0 0');
    pPit .setAttribute('d', dPit ||'M 0 0');
    pMain.setAttribute('fill','none'); pPit.setAttribute('fill','none');
    pMain.setAttribute('stroke','#1f2937'); pMain.setAttribute('stroke-width','4.5');
    pPit .setAttribute('stroke','#94a3b8'); pPit .setAttribute('stroke-width','2.0');
    pMain.setAttribute('stroke-linecap','round'); pMain.setAttribute('stroke-linejoin','round');
    pPit .setAttribute('stroke-linecap','round'); pPit .setAttribute('stroke-linejoin','round');
    pMain.id='pMain'; pPit.id='pPit';
    gTrack.appendChild(pMain); gTrack.appendChild(pPit);

    const finPts=grabFinishPoints(doc);
    if(finPts.length===2){
      const ln=document.createElementNS(stage.namespaceURI,'line');
      ln.setAttribute('x1',finPts[0].x); ln.setAttribute('y1',finPts[0].y);
      ln.setAttribute('x2',finPts[1].x); ln.setAttribute('y2',finPts[1].y);  // ← y2 오타 수정
      ln.setAttribute('stroke','#ef4444'); ln.setAttribute('stroke-width','3');
      gTrack.appendChild(ln);
    }

    const mdMarks=grabMarkersFromMetadata(doc);
    const mk={
      pitIn:  grabPointFromData(doc,'pitIn')  || mdMarks.pitIn  || null,
      pitOut: grabPointFromData(doc,'pitOut') || mdMarks.pitOut || null,
      pitStop:grabPointFromData(doc,'pitStop')|| mdMarks.pitStop|| null
    };
    for (const [k,pt] of Object.entries(mk)){
      if(!pt) continue;
      const c=document.createElementNS(stage.namespaceURI,'circle');
      c.setAttribute('cx',pt.x); c.setAttribute('cy',pt.y); c.setAttribute('r','6');
      c.setAttribute('fill', k==='pitIn' ? '#22c55e' : (k==='pitOut' ? '#06b6d4' : '#f59e0b'));
      gTrack.appendChild(c);
      const label=text(pt.x+8,pt.y-8,k,12,'#334155'); gTrack.appendChild(label);
    }

    let grid=grabStartGridFromMetadata(doc) || grabStartGridFromGroup(doc) || [];
    grid=grid.slice().sort((a,b)=>(a.num||999)-(b.num||999));

    report.innerHTML = `
      main path: <b>${dMain ? 'OK' : 'MISSING'}</b><br>
      pit  path: <b>${dPit  ? 'OK' : 'MISSING'}</b><br>
      finish: <b>${finPts.length===2 ? 'OK' : 'MISSING'}</b><br>
      pitIn: <b>${mk.pitIn?'OK':'MISSING'}</b> · pitOut: <b>${mk.pitOut?'OK':'MISSING'}</b> · pitStop: <b>${mk.pitStop?'OK':'MISSING'}</b><br>
      start grid pts: <b>${grid.length}</b>
    `;
    return { pMain, pPit, finPts, mk, grid };
  }

  // ------- cars & animation -------
  let anim=null, tPrev=0;
  const cars=[];
  let clickBound=false;
  let selRing=null;

  function ensureSelRing(){
    if (selRing) return;
    selRing = document.createElementNS(stage.namespaceURI,'circle');
    selRing.setAttribute('r','10');
    selRing.setAttribute('fill','none');
    selRing.setAttribute('stroke','#0b5cff');
    selRing.setAttribute('stroke-width','3');
    selRing.setAttribute('stroke-dasharray','4 4');
    selRing.style.pointerEvents='none';
    selRing.style.display='none';
    gAct.appendChild(selRing);
  }

  function ensureCars(){
    gAct.innerHTML=''; cars.length=0; selRing=null; ensureSelRing();
    for(let i=0;i<20;i++){
      const c=document.createElementNS(stage.namespaceURI,'circle');
      c.setAttribute('r','6');
      c.setAttribute('fill',colors[i%colors.length]);
      c.setAttribute('stroke','white'); c.setAttribute('stroke-width','2');
      c.classList.add('car');
      c.dataset.idx=String(i);
      c.setAttribute('pointer-events','auto');

      const num = roster[i]?.num ?? (i+1);
      const label=text(0,0,String(num),10,'#0f172a');
      label.classList.add('carLabel');
      label.dataset.idx=String(i);
      label.setAttribute('pointer-events','auto');

      gAct.appendChild(c); gAct.appendChild(label);
      cars.push({
        id:i+1, num:num, name: roster[i]?.name || `Driver ${i+1}`, team: roster[i]?.team || `Team`,
        el:c, lab:label, mode:'main',
        sMain:0, sPit:0, vMul:0.95+Math.random()*0.10,
        trans:{on:false,t0:0,dur:params.transMs,a:{x:0,y:0},b:{x:0,y:0}},
        waitUntil:0, pitRequest:false
      });
    }
    bindCarClickOnce();
  }

  function bindCarClickOnce(){
    if (clickBound) return;
    gAct.addEventListener('click', onCarClick); // once 제거
    clickBound = true;
  }
  function onCarClick(ev){
    const t = ev.target;
    let idx = -1;
    if (t && t.dataset && t.dataset.idx) idx = parseInt(t.dataset.idx, 10);
    else if (t && t.closest) {
      const host = t.closest('[data-idx]');
      if (host) idx = parseInt(host.dataset.idx, 10);
    }
    if (!Number.isFinite(idx) || idx < 0) return;
    selectCar(idx, true);
  }

  function placeOnStart(parsed){
    const {pMain,grid,finPts}=parsed;
    if(grid && grid.length){
      for(let i=0;i<cars.length;i++){
        const gpt=grid[Math.min(i,grid.length-1)];
        const s=nearestS(pMain,{x:gpt.x,y:gpt.y});
        cars[i].sMain=s;
        const q=ptOn(pMain,s);
        cars[i].el.setAttribute('transform',`translate(${q.x},${q.y})`);
        cars[i].lab.setAttribute('x',q.x+8); cars[i].lab.setAttribute('y',q.y-8);
      }
    }else{
      let s0=0; if(finPts && finPts.length===2){ const mid={x:(finPts[0].x+finPts[1].x)/2,y:(finPts[0].y+finPts[1].y)/2}; s0=nearestS(pMain,mid); }
      const gap=0.01;
      for(let i=0;i<cars.length;i++){
        const s=(s0+i*gap)%1; cars[i].sMain=s; const q=ptOn(pMain,s);
        cars[i].el.setAttribute('transform',`translate(${q.x},${q.y})`);
        cars[i].lab.setAttribute('x',q.x+8); cars[i].lab.setAttribute('y',q.y-8);
      }
    }
  }

  function beginTrans(car,a,b){ car.trans.on=true; car.trans.t0=performance.now(); car.trans.a=a; car.trans.b=b; car.trans.dur=params.transMs; }
  function stepTrans(car,now){
    const w = Math.max(0, Math.min(1,(now-car.trans.t0)/car.trans.dur));
    const x = car.trans.a.x*(1-w)+car.trans.b.x*w;
    const y = car.trans.a.y*(1-w)+car.trans.b.y*w;
    car.el.setAttribute('transform',`translate(${x},${y})`);
    car.lab.setAttribute('x',x+8); car.lab.setAttribute('y',y-8);
    if(w>=1) car.trans.on=false;
  }

  function start(){
    if(!parsed){ parsed = buildFromRaw(); if(!parsed){ alert('SVG 파싱 실패'); return; } }
    ensureCars(); placeOnStart(parsed);
    for(const car of cars){ car.mode='main'; car.pitRequest=false; }
    tPrev=0; stateEl.textContent='state: main (20 cars)';
    if(anim) cancelAnimationFrame(anim);
    anim=requestAnimationFrame(loop);
    // 기본 선택(1번)
    selectCar(Math.max(0, Math.min(19, params.targetCar-1)), false);
  }
  function stop(){ if(anim) cancelAnimationFrame(anim); anim=null; stateEl.textContent='state: idle'; }

  function loop(now){
    if(!tPrev) tPrev=now;
    const dt=(now-tPrev)/1000; tPrev=now;

    const p={ main:document.getElementById('pMain'), pit:document.getElementById('pPit') };
    if(!p.main) return;

    const vMainBase = 1/Math.max(0.1, params.lapSec);
    const vPitBase  = vMainBase*Math.max(0.1, params.pitMul);

    const sMainIn  = parsed.mk.pitIn  ? nearestS(p.main, parsed.mk.pitIn ) : 0.0;
    const sMainOut = parsed.mk.pitOut ? nearestS(p.main, parsed.mk.pitOut) : 0.0;
    const sPitIn   = parsed.mk.pitIn  ? nearestS(p.pit , parsed.mk.pitIn ) : 0.0;
    const sPitOut  = parsed.mk.pitOut ? nearestS(p.pit , parsed.mk.pitOut) : 0.0;
    const sPitStop = parsed.mk.pitStop? nearestS(p.pit , parsed.mk.pitStop): sPitIn;

    for(const car of cars){
      const vMain=vMainBase*car.vMul, vPit=vPitBase*car.vMul;

      if(car.mode==='main'){
        const before=car.sMain;
        car.sMain=(car.sMain+vMain*dt)%1;
        const q=ptOn(p.main,car.sMain);
        car.el.setAttribute('transform',`translate(${q.x},${q.y})`);
        car.lab.setAttribute('x',q.x+8); car.lab.setAttribute('y',q.y-8);

        if (car.pitRequest && parsed.mk.pitIn && parsed.mk.pitOut){
          const hit = reachedForward(before, car.sMain, sMainIn);
          if (hit){
            car.sMain = sMainIn;
            const a = ptOn(p.main, sMainIn);
            const b = ptOn(p.pit , sPitIn );
            beginTrans(car, a, b);
            car.sPit=sPitIn;
            car.mode='toPit';
            car.pitRequest=false;
          }
        }

      } else if (car.mode==='toPit'){
        stepTrans(car, now);
        if(!car.trans.on) car.mode='pit';

      } else if (car.mode==='pit'){
        const before=car.sPit;
        car.sPit=(car.sPit+vPit*dt)%1;
        const q=ptOn(p.pit,car.sPit);
        car.el.setAttribute('transform',`translate(${q.x},${q.y})`);
        car.lab.setAttribute('x',q.x+8); car.lab.setAttribute('y',q.y-8);
        const reached = reachedForward(before, car.sPit, sPitStop);
        if(reached){
          car.mode='pitWait';
          car.waitUntil=performance.now()+Math.max(0,params.waitSec)*1000;
          car.sPit=sPitStop; const qq=ptOn(p.pit,sPitStop);
          car.el.setAttribute('transform',`translate(${qq.x},${qq.y})`);
          car.lab.setAttribute('x',qq.x+8); car.lab.setAttribute('y',qq.y-8);
        }

      } else if (car.mode==='pitWait'){
        const q=ptOn(p.pit,car.sPit);
        car.el.setAttribute('transform',`translate(${q.x},${q.y})`);
        car.lab.setAttribute('x',q.x+8); car.lab.setAttribute('y',q.y-8);
        if(now>=car.waitUntil) car.mode='pitToOut';

      } else if (car.mode==='pitToOut'){
        const before=car.sPit;
        car.sPit=(car.sPit+vPit*dt)%1;
        const q=ptOn(p.pit,car.sPit);
        car.el.setAttribute('transform',`translate(${q.x},${q.y})`);
        car.lab.setAttribute('x',q.x+8); car.lab.setAttribute('y',q.y-8);
        const reached = reachedForward(before, car.sPit, sPitOut);
        if(reached){
          car.sPit=sPitOut;
          const a=ptOn(p.pit ,sPitOut);
          const b=ptOn(p.main,sMainOut);
          beginTrans(car,a,b);
          car.sMain=sMainOut;
          car.mode='toMain';
        }

      } else if (car.mode==='toMain'){
        stepTrans(car, now);
        if(!car.trans.on) car.mode='main';
      }
    }

    // 선택 링 위치 업데이트
    if (currentSel>=0){
      const car = cars[currentSel];
      if (car){
        const path = (car.mode==='main' || car.mode==='toPit' || car.mode==='toMain') ? document.getElementById('pMain') : document.getElementById('pPit');
        let q;
        if (car.trans.on){
          const w = Math.max(0, Math.min(1,(now-car.trans.t0)/car.trans.dur));
          q = { x: car.trans.a.x*(1-w)+car.trans.b.x*w, y: car.trans.a.y*(1-w)+car.trans.b.y*w };
        }else{
          q = (car.mode==='main' || car.mode==='toMain') ? ptOn(document.getElementById('pMain'), car.sMain)
                                                         : ptOn(document.getElementById('pPit'),  car.sPit );
        }
        selRing.setAttribute('transform', `translate(${q.x},${q.y})`);
      }
    }

    anim=requestAnimationFrame(loop);
  }

  // ===== 선택/카드 =====
  const card = document.getElementById('card');
  const cHeader = document.getElementById('cHeader');
  const cSub = document.getElementById('cSub');
  const cMode = document.getElementById('cMode');
  let currentSel = -1;

  function showCardFor(idx){
    const car = cars[idx]; if(!car) return;
    cHeader.textContent = `#${car.num} ${car.name}`;
    cSub.textContent = `Team: ${car.team}`;
    cMode.textContent = `mode: ${car.mode}`;
    card.style.display='block';
  }
  function selectCar(idx, updateInput=true){
    currentSel = Math.max(0, Math.min(19, idx));
    params.targetCar = currentSel + 1;
    if (updateInput){
      const el = document.getElementById('targetCarInput');
      if (el) el.value = String(params.targetCar);
    }
    showCardFor(currentSel);
    // 하이라이트 링 표시
    selRing.style.display='block';
    const car = cars[currentSel];
    if (car){
      const tr = car.el.getAttribute('transform') || 'translate(0,0)';
      selRing.setAttribute('transform', tr);
      selRing.setAttribute('stroke', colors[(currentSel)%colors.length]);
    }
  }

  // Buttons
  document.getElementById('play').addEventListener('click', start);
  document.getElementById('stop').addEventListener('click', ()=> stop());
  document.getElementById('pitInNow').addEventListener('click', ()=>{
    if(!parsed){ alert('먼저 Play를 눌러주세요.'); return; }
    const idx=Math.max(1,Math.min(20,params.targetCar))-1;
    const car=cars[idx]; if(!car) return;
    if(!parsed.mk.pitIn || !parsed.mk.pitOut){ alert('pitIn/pitOut 마커가 없습니다.'); return; }
    if (car.mode==='main'){ car.pitRequest=true; stateEl.textContent=`state: Pit-In 요청 (car #${car.id})`; }
    selectCar(idx, true);
  });

  // ---------- 초기 미리보기 (업로드 직후 바로 표시) ----------
  if (RAW && RAW.trim().length>0) {
    parsed = buildFromRaw();              // 트랙, 마커, 그리드 렌더
    ensureCars(); placeOnStart(parsed);   // 차량 20대 위치만 배치(정지)
    stateEl.textContent='state: idle (ready)';
    // 기본 선택 1번
    selectCar(0, true);
  } else {
    report.textContent = "SVG를 업로드하세요.";
  }
})();
</script>
"""

html = html.replace("%%RAW_SVG%%", json.dumps(RAW_SVG))
html = html.replace("%%VIEWBOX%%", VIEWBOX_FALLBACK)

st.components.v1.html(html, height=950, scrolling=False)
