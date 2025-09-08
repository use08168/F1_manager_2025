import base64
import streamlit as st

st.set_page_config(layout="wide", page_title="Track Editor + Pit Preview")

st.title("🏁 Track Editor + Pit Preview (Main / Pit / Finish / Pit-In / Pit-Out / Pit-Stop / Start Grid)")

# 1) Optional background image (for tracing)
bg_uploader = st.file_uploader(
    "배경 이미지 업로드 (선택, PNG/JPG/SVG/PDF)",
    type=["png", "jpg", "jpeg", "svg", "pdf"]
)

bg_data_url = ""
if bg_uploader:
    mime = (bg_uploader.type or "").lower()
    name = (bg_uploader.name or "").lower()

    # --- PDF 처리: PyMuPDF로 선택 페이지를 PNG로 변환 ---
    if mime == "application/pdf" or name.endswith(".pdf"):
        try:
            import fitz  # PyMuPDF
            doc = fitz.open(stream=bg_uploader.getvalue(), filetype="pdf")
            total = doc.page_count
            # 페이지 및 렌더 배율 선택(원하면 고정값으로 바꿔도 됨)
            pg = st.number_input("PDF 페이지 선택", min_value=1, max_value=total, value=1, step=1)
            zoom = st.slider("PDF 렌더 배율", 1.0, 4.0, 2.0, 0.1)
            page = doc.load_page(pg-1)
            pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
            png_bytes = pix.tobytes("png")

            b64 = base64.b64encode(png_bytes).decode("utf-8")
            bg_data_url = f"data:image/png;base64,{b64}"
        except Exception as e:
            st.warning("PDF를 이미지로 변환하려면 PyMuPDF가 필요합니다: pip install pymupdf")
            st.exception(e)

    # --- 이미지/SVG 그대로 데이터 URL로 ---
    else:
        raw = bg_uploader.getvalue()
        # SVG MIME 보정
        if mime in ("image/svg+xml", "image/svg", "text/svg") or name.endswith(".svg"):
            mime = "image/svg+xml"
        elif not mime.startswith("image/"):
            # 알 수 없는 경우 PNG로 가정
            mime = "image/png"
        b64 = base64.b64encode(raw).decode("utf-8")
        bg_data_url = f"data:{mime};base64,{b64}"

# 2) Embed a full HTML editor with SVG + JS
html = r"""
<style>
  .toolbar { display:flex; gap:12px; align-items:center; padding:10px 12px; background:#f8fafc; border:1px solid #e2e8f0; border-radius:12px; }
  .toolbar .group { display:flex; gap:8px; align-items:center; }
  .toolbar label { font-size:13px; color:#334155; }
  .toolbar select, .toolbar button, .toolbar input[type="number"] { font-size:13px; padding:6px 8px; border-radius:8px; border:1px solid #cbd5e1; background:white; }
  .toolbar button { cursor:pointer; }
  .toolbar button.primary { background:#0b5cff; color:white; border-color:#0b5cff; }
  .toolbar button.warn { background:#ef4444; color:white; border-color:#ef4444; }

  #wrap { display:grid; grid-template-columns: 1fr 360px; gap:16px; margin-top:12px; }
  #left { background:white; border:1px solid #e5e7eb; border-radius:14px; padding:12px; }
  #right { background:#f8fafc; border:1px solid #e5e7eb; border-radius:14px; padding:12px; }

  #stage { width:100%; height:820px; background:white; border-radius:10px; box-shadow:0 6px 24px rgba(0,0,0,0.08); user-select:none; touch-action:none; }
  #panel { font-size:13px; color:#334155; }
  #panel h3 { margin:10px 0 8px; font-size:14px; color:#0f172a; }
  #hint { font-size:12px; color:#64748b; margin-top:6px; }

  .legend { display:flex; flex-wrap:wrap; gap:8px; margin:8px 0; }
  .legend .chip { font-size:11px; padding:2px 6px; border-radius:999px; border:1px solid #cbd5e1; background:white; }
  .muted { color:#64748b; font-size:12px; }
</style>

<div class="toolbar">
  <div class="group">
    <label>Layer</label>
    <select id="layer">
      <option value="main">main (두꺼운 코스)</option>
      <option value="pit">pit (얇은 피트레인)</option>
      <option value="finish">finish (결승선: 2점)</option>
      <option value="pitIn">pit-in (메인↦피트 접속점: 1점)</option>
      <option value="pitOut">pit-out (피트↦메인 접속점: 1점)</option>
      <option value="pitStop">pit-stop (멈출 위치: 1점)</option>
      <option value="start">start (스타트 그리드: 최대 20점)</option>
    </select>
  </div>

  <div class="group">
    <label>Tool</label>
    <select id="tool">
      <option value="add">점 추가</option>
      <option value="drag">드래그 이동</option>
      <option value="del">점 삭제</option>
    </select>
  </div>

  <div class="group">
    <button id="undo">UNDO</button>
    <button id="clear">현재 레이어 비우기</button>
    <button id="export">SVG 내보내기</button>
    <label for="importSvg">SVG 불러오기</label>
    <input id="importSvg" type="file" accept=".svg" />
  </div>

  <div id="hint" class="muted">· MAIN · 캔버스를 클릭해 점 추가</div>
</div>

<div id="wrap">
  <div id="left">
    <svg id="stage" viewBox="0 0 1200 800">
      <defs></defs>
      <g id="bg"></g>
      <g id="paths"></g>
      <g id="draw"></g>
      <g id="actors"></g>
    </svg>
  </div>

  <div id="right">
    <div id="panel">
      <h3>미리보기</h3>
      <div class="legend">
        <span class="chip">메인: 굵은 진회색</span>
        <span class="chip">피트: 얇은 회색</span>
        <span class="chip">결승선/피트 in·out/스톱: 표시점</span>
        <span class="chip">스타트 그리드: start 레이어 점(1→20)</span>
      </div>

      <div style="display:grid; grid-template-columns: 1fr 1fr; gap:8px; margin-bottom:8px;">
        <label>Lap(sec)<br><input id="lapSec" type="number" min="0.5" step="0.1" value="2.0"></label>
        <label>Pit wait(sec)<br><input id="waitSec" type="number" min="0" step="0.1" value="3.0"></label>
        <label>Transition(ms)<br><input id="transMs" type="number" min="50" step="50" value="900"></label>
        <label>Pit speed x<br><input id="pitMul" type="number" min="0.1" step="0.1" value="0.6"></label>
      </div>

      <div style="display:flex; gap:8px; margin:6px 0 12px;">
        <button id="play" class="primary">▶ Play</button>
        <button id="stop">⏹ Stop</button>
        <button id="pitInNow">Pit In</button>
        <div id="state" class="muted" style="margin-left:8px;">state: idle</div>
      </div>

      <h3>팁</h3>
      <ul class="muted">
        <li>레이어를 선택하고, 도구에서 <b>점 추가 / 드래그 / 삭제</b>를 고르세요.</li>
        <li><b>finish</b>는 점 2개(선), <b>pitIn/pitOut/pitStop</b>은 점 1개만 유지합니다.</li>
        <li><b>start</b>는 최대 20점까지 — 점 순서가 그리드 순번(1→20)이 됩니다.</li>
        <li>UNDO로 바로 직전 상태를 되돌릴 수 있습니다.</li>
        <li>Play 후 <b>Pit In</b>을 누르면 현재 위치에서 pitIn 지점을 실제로 지나칠 때만 피트로 전환됩니다.</li>
      </ul>
    </div>
  </div>
</div>

<script>
(function(){
  const stage = document.getElementById('stage');
  const gBg   = document.getElementById('bg');
  const gPaths= document.getElementById('paths');
  const gDraw = document.getElementById('draw');
  const gAct  = document.getElementById('actors');

  // === background image (optional) ===
  const BG_URL = "%%BG%%";
  if (BG_URL && BG_URL.length > 0) {
    const img = document.createElementNS(stage.namespaceURI, 'image');
    img.setAttribute('href', BG_URL);
    img.setAttribute('x', '0'); img.setAttribute('y', '0');
    img.setAttribute('width', '1200'); img.setAttribute('height', '800');
    img.setAttribute('opacity', '0.85');
    gBg.appendChild(img);
  }

  // ====== Editor State ======
  const layers = {
    main:    { pts: [] },
    pit:     { pts: [] },
    finish:  { pts: [] },   // 2 points line
    pitIn:   { pts: [] },   // 1 point
    pitOut:  { pts: [] },   // 1 point
    pitStop: { pts: [] },   // 1 point
    start:   { pts: [] }    // up to 20 points
  };
  let active = 'main';
  let tool   = 'add';

  const hist = [];
  function snapshot(){
    const copy = JSON.parse(JSON.stringify(layers));
    hist.push(copy);
    if (hist.length > 100) hist.shift();
  }
  function restore(obj){
    Object.keys(layers).forEach(k=>layers[k]=JSON.parse(JSON.stringify(obj[k]||{pts:[]})));
    normalizeLayers();
    render();
    hint();
  }
  function normalizeLayers(){
    for (const k of Object.keys(layers)){
      if (!Array.isArray(layers[k].pts)) layers[k].pts = [];
    }
  }

  // UI controls
  const selLayer = document.getElementById('layer');
  const selTool  = document.getElementById('tool');
  selLayer.addEventListener('change', e=>{ active = e.target.value; hint(); render();});
  selTool.addEventListener('change',  e=>{ tool   = e.target.value; hint();});

  function hint(){
    const layerName = (typeof active === 'string' ? active : 'main').toUpperCase();
    const t = (tool === 'add') ? '캔버스를 클릭해 점 추가' :
              (tool === 'drag') ? '점 드래그로 이동 / 점 더블클릭 삭제' :
              '점을 클릭하면 삭제';
    const el = document.getElementById('hint');
    if (el) el.textContent = `· ${layerName} · ${t}`;
  }

  // helpers
  function svgPoint(evt){
    const pt = stage.createSVGPoint();
    pt.x = evt.clientX; pt.y = evt.clientY;
    return pt.matrixTransform(stage.getScreenCTM().inverse());
  }
  function clamp(n,a,b){ return Math.max(a, Math.min(b, n)); }

  // click/drag logic
  let drag={ on:false, layer:null, idx:-1 };

  stage.addEventListener('mousedown', (e)=>{
    const p = svgPoint(e);
    const L = layers[active];
    if (tool==='add'){
      // constraints by layer
      if (active==='finish' && L.pts.length>=2) { L.pts = []; }
      if ((active==='pitIn' || active==='pitOut' || active==='pitStop') && L.pts.length>=1){ L.pts=[]; }
      if (active==='start' && L.pts.length>=20){ /* cap 20 */ return; }
      L.pts.push({x:p.x, y:p.y});
      snapshot(); render();
    } else if (tool==='drag'){
      const idx = pickPoint(L.pts, p, 12);
      if (idx>=0){
        drag={ on:true, layer:active, idx };
      }
    } else if (tool==='del'){
      const idx = pickPoint(L.pts, p, 12);
      if (idx>=0){ L.pts.splice(idx,1); snapshot(); render(); }
    }
  });
  stage.addEventListener('mousemove', (e)=>{
    if (!drag.on) return;
    const p = svgPoint(e);
    const L = layers[drag.layer];
    if (!L || !Array.isArray(L.pts) || !L.pts[drag.idx]) return;
    L.pts[drag.idx].x = p.x; L.pts[drag.idx].y = p.y;
    render();
  });
  window.addEventListener('mouseup', ()=>{
    if (drag.on){ drag.on=false; snapshot(); render(); }
  });

  function pickPoint(pts, p, r){
    if (!Array.isArray(pts)) return -1;
    let best=-1, bd=r*r;
    for (let i=0;i<pts.length;i++){
      const q=pts[i]; if(!q) continue;
      const dx=q.x-p.x, dy=q.y-p.y, d=dx*dx+dy*dy;
      if (d<=bd){ bd=d; best=i; }
    }
    return best;
  }

  // Build path from poly points
  function polyToPath(pts){
    const arr = Array.isArray(pts) ? pts : [];
    if (arr.length===0) return '';
    let d=`M ${arr[0].x} ${arr[0].y}`;
    for (let i=1;i<arr.length;i++){
      const pt=arr[i]; if(!pt) continue;
      d += ` L ${pt.x} ${pt.y}`;
    }
    return d;
  }

  // nearest s on path (0..1) to point p (sampling)
  function nearestS(pathEl, p){
    if (!pathEl) return 0;
    const L = pathEl.getTotalLength();
    const N = 1000;
    let bestS=0, bestD=1e9;
    for (let i=0;i<=N;i++){
      const s = i/N;
      const q = pathEl.getPointAtLength(s*L);
      const dx=q.x-p.x, dy=q.y-p.y, d=dx*dx+dy*dy;
      if (d<bestD){ bestD=d; bestS=s; }
    }
    return bestS;
  }

  // Render all layers (paths + control points + markers)
  function render(){
    normalizeLayers();

    // clear groups
    gPaths.innerHTML='';
    gDraw.innerHTML='';
    // Paths: main/pit
    const pMain = document.createElementNS(stage.namespaceURI, 'path');
    const pPit  = document.createElementNS(stage.namespaceURI, 'path');
    const dMain = polyToPath(layers.main.pts);
    const dPit  = polyToPath(layers.pit.pts);
    pMain.setAttribute('d', dMain || 'M 0 0');
    pPit .setAttribute('d', dPit  || 'M 0 0');
    pMain.setAttribute('fill','none');
    pPit .setAttribute('fill','none');
    pMain.setAttribute('stroke','#1f2937'); // dark
    pPit .setAttribute('stroke','#94a3b8'); // gray
    pMain.setAttribute('stroke-width','4.5');
    pPit .setAttribute('stroke-width','2.0');
    pMain.setAttribute('stroke-linecap','round');
    pPit .setAttribute('stroke-linecap','round');
    pMain.setAttribute('stroke-linejoin','round');
    pPit .setAttribute('stroke-linejoin','round');
    pMain.id='pMain'; pPit.id='pPit';
    gPaths.appendChild(pMain);
    gPaths.appendChild(pPit);

    // finish line (2 points)
    if (layers.finish.pts.length===2){
      const a=layers.finish.pts[0], b=layers.finish.pts[1];
      const ln = document.createElementNS(stage.namespaceURI,'line');
      ln.setAttribute('x1',a.x); ln.setAttribute('y1',a.y);
      ln.setAttribute('x2',b.x); ln.setAttribute('y2',b.y);
      ln.setAttribute('stroke','#ef4444'); ln.setAttribute('stroke-width','3');
      gPaths.appendChild(ln);
    }

    // markers: pitIn, pitOut, pitStop (single points)
    drawMarker('pitIn',  '#22c55e'); // green
    drawMarker('pitOut', '#06b6d4'); // cyan
    drawMarker('pitStop','#f59e0b'); // amber

    // control points
    drawPoints('main');
    drawPoints('pit');
    drawPoints('finish');
    drawPoints('pitIn');
    drawPoints('pitOut');
    drawPoints('pitStop');
    drawPoints('start'); // 그리드 점(1→20)
  }

  function drawMarker(key,color){
    const L = layers[key];
    const pts = Array.isArray(L.pts)? L.pts : [];
    if (pts.length<1 || !pts[0]) return;
    const {x,y}=pts[0];
    const c = document.createElementNS(stage.namespaceURI,'circle');
    c.setAttribute('cx',x); c.setAttribute('cy',y);
    c.setAttribute('r','6'); c.setAttribute('fill',color);
    gPaths.appendChild(c);

    const label = document.createElementNS(stage.namespaceURI,'text');
    label.setAttribute('x', x+8); label.setAttribute('y', y-8);
    label.setAttribute('font-size','13'); label.setAttribute('fill','#0f172a');
    label.textContent = key;
    gPaths.appendChild(label);
  }

  function drawPoints(key){
    const L = layers[key];
    const pts = Array.isArray(L.pts) ? L.pts : [];
    for (let i=0;i<pts.length;i++){
      const pt = pts[i];
      if (!pt || typeof pt.x!=='number' || typeof pt.y!=='number') continue;
      const {x,y} = pt;

      const c = document.createElementNS(stage.namespaceURI,'circle');
      c.setAttribute('cx',x); c.setAttribute('cy',y);
      c.setAttribute('r', key==='pitStop' ? '6' : '5');
      c.setAttribute('fill', key===active ? '#0b5cff' : '#94a3b8');
      c.setAttribute('opacity','0.95');
      c.dataset.layer=key; c.dataset.idx=String(i);
      gDraw.appendChild(c);

      const label = document.createElementNS(stage.namespaceURI,'text');
      label.setAttribute('x', x+8); label.setAttribute('y', y-8);
      label.setAttribute('font-size','12'); label.setAttribute('fill','#334155');
      label.textContent = i+1;
      gDraw.appendChild(label);
    }
  }

  // Buttons
  document.getElementById('undo').addEventListener('click', ()=>{
    if (hist.length<=1) return;
    hist.pop();
    restore(hist[hist.length-1]);
  });

  document.getElementById('clear').addEventListener('click', ()=>{
    layers[active].pts = [];
    snapshot(); render();
  });

  // Export SVG
  document.getElementById('export').addEventListener('click', ()=>{
    const dMain = polyToPath(layers.main.pts);
    const dPit  = polyToPath(layers.pit.pts);

    function ptStr1(p){ return `${p.x},${p.y}`; }
    function ptStrSingle(key){
      const L=layers[key], p=(Array.isArray(L.pts)&&L.pts[0])?L.pts[0]:null;
      return p?ptStr1(p):'';
    }
    const fin = (layers.finish.pts.length===2) ? 
      `${layers.finish.pts[0].x},${layers.finish.pts[0].y} ${layers.finish.pts[1].x},${layers.finish.pts[1].y}` : '';

    // start grid circles
    const startCircles = (layers.start.pts||[]).slice(0,20).map(p=>`      <circle class="startPt" data-pt="${ptStr1(p)}" r="0"/>`).join("\n");

    const svg =
`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1200 800">
  <g id="track">
    <path id="main" d="${dMain}" fill="none" stroke="#1f2937" stroke-width="4.5" stroke-linecap="round" stroke-linejoin="round"/>
    <path id="pit"  d="${dPit}"  fill="none" stroke="#94a3b8" stroke-width="2"   stroke-linecap="round" stroke-linejoin="round"/>
    <polyline id="finish" points="${fin}" fill="none" stroke="#ef4444" stroke-width="3"/>
    <circle id="pitIn"  data-pt="${ptStrSingle('pitIn')}"  r="0"/>
    <circle id="pitOut" data-pt="${ptStrSingle('pitOut')}" r="0"/>
    <circle id="pitStop" data-pt="${ptStrSingle('pitStop')}" r="0"/>
    <g id="start">
${startCircles}
    </g>
  </g>
  <metadata>
    ${JSON.stringify(layers)}
  </metadata>
</svg>`;

    const blob = new Blob([svg], {type:"image/svg+xml"});
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = "track.svg";
    a.click();
    URL.revokeObjectURL(a.href);
  });

  // Import SVG
  document.getElementById('importSvg').addEventListener('change', async (ev)=>{
    const file = ev.target.files[0];
    if (!file) return;
    const txt = await file.text();

    // 1) 먼저 metadata JSON 시도 (가장 정확)
    const metaMatch = txt.match(/<metadata>\s*([\s\S]*?)\s*<\/metadata>/i);
    if (metaMatch){
      try{
        const parsed = JSON.parse(metaMatch[1]);
        if (parsed && parsed.main && parsed.pit){
          Object.keys(layers).forEach(k=>{
            layers[k].pts = Array.isArray(parsed[k]?.pts) ? parsed[k].pts : [];
          });
          snapshot(); render();
          return;
        }
      }catch(e){ /* fallthrough to manual parse */ }
    }

    // 2) 수동 파싱 (main/pit paths + single markers + start group)
    function grab(re){
      const m = txt.match(re);
      return m?m[1]:'';
    }
    const dMain = grab(/<path[^>]*id="main"[^>]*d="([^"]+)"/i);
    const dPit  = grab(/<path[^>]*id="pit"[^>]*d="([^"]+)"/i);

    function pathToPts(dStr){
      // simple "M x y L x y ..." parser
      const pts=[];
      const re = /[ML]\s*([-\d.]+)[ ,]([-\d.]+)/ig;
      let m;
      while ((m=re.exec(dStr))!==null){
        pts.push({x:parseFloat(m[1]), y:parseFloat(m[2])});
      }
      return pts;
    }

    layers.main.pts = pathToPts(dMain);
    layers.pit .pts = pathToPts(dPit);

    function readPt(id){
      const m = txt.match(new RegExp(`<circle[^>]*id="${id}"[^>]*data-pt="([^"]*)"`, 'i'));
      if (m && m[1]){
        const [sx,sy]=m[1].split(',').map(parseFloat);
        if (!Number.isNaN(sx) && !Number.isNaN(sy)) return [{x:sx,y:sy}];
      }
      return [];
    }
    layers.pitIn.pts  = readPt('pitIn');
    layers.pitOut.pts = readPt('pitOut');
    layers.pitStop.pts= readPt('pitStop');

    // finish
    const mFin = txt.match(/<polyline[^>]*id="finish"[^>]*points="([^"]*)"/i);
    if (mFin && mFin[1]){
      const arr = mFin[1].trim().split(/\s+/).map(s=>s.split(',').map(parseFloat));
      layers.finish.pts = arr.slice(0,2).map(([x,y])=>({x,y}));
    }

    // start group circles
    const startBlock = txt.match(/<g[^>]*id="start"[^>]*>([\s\S]*?)<\/g>/i);
    const startPts = [];
    if (startBlock){
      const re = /<circle[^>]*data-pt="([^"]+)"[^>]*>/ig;
      let m;
      while ((m=re.exec(startBlock[1]))!==null){
        const [sx,sy] = m[1].split(',').map(parseFloat);
        if (!Number.isNaN(sx)&&!Number.isNaN(sy)) startPts.push({x:sx,y:sy});
      }
    }
    layers.start.pts = startPts.slice(0,20);

    snapshot(); render();
  });

  // ====== Preview (cars + bot) ======
  const stateEl  = document.getElementById('state');
  const lapSecEl = document.getElementById('lapSec');
  const waitEl   = document.getElementById('waitSec');
  const transEl  = document.getElementById('transMs');
  const pitMulEl = document.getElementById('pitMul');

  // 20 cars (bot=1)
  const cars = []; // {id, el, lb, sMain, vMain}
  function clearField(){
    for(const c of cars){ if(c.el) c.el.remove(); if(c.lb) c.lb.remove(); }
    cars.length = 0;
  }
  function mkCar(id, fill){
    const c = document.createElementNS(stage.namespaceURI,'circle');
    c.setAttribute('r','5'); c.setAttribute('fill',fill);
    c.setAttribute('stroke','white'); c.setAttribute('stroke-width','1.5');
    gAct.appendChild(c);
    const t = document.createElementNS(stage.namespaceURI,'text');
    t.setAttribute('font-size','10'); t.setAttribute('fill','#111');
    t.setAttribute('paint-order','stroke'); t.setAttribute('stroke','#fff'); t.setAttribute('stroke-width','3');
    gAct.appendChild(t);
    return {el:c, lb:t, id};
  }

  function getPaths(){
    return {
      main: document.getElementById('pMain'),
      pit : document.getElementById('pPit')
    };
  }
  function ptOn(path, s){
    const L = Math.max(1, path.getTotalLength());
    const q = path.getPointAtLength(clamp(s,0,1)*L);
    return {x:q.x, y:q.y};
  }

  function spawnCars(n){
    clearField();
    const p = getPaths();
    const N = Math.max(1, n|0);
    const baseV = 1/Math.max(0.1, parseFloat(lapSecEl.value||"2.0"));

    const useGrid = (layers.start.pts && layers.start.pts.length>0);
    for(let i=0;i<N;i++){
      const pal = ['#2563eb','#0ea5e9','#10b981','#84cc16','#a855f7','#f97316','#f43f5e','#14b8a6','#22c55e','#eab308'];
      const col = i===0 ? '#ff6b00' : pal[i%pal.length];
      const car = mkCar(i+1, col);

      let s0;
      if (useGrid){
        const idx = i % layers.start.pts.length;
        const gp = layers.start.pts[idx];
        s0 = nearestS(p.main, gp); // 그리드 점을 메인 레인에 투영
      }else{
        s0 = (i / N) % 1; // 균등 배치
      }

      car.sMain = s0;
      car.vMain = baseV * (0.95 + Math.random()*0.1);
      cars.push(car);
    }

    // bot은 cars[0]
    bot.id = 1;
    bot.el = cars[0].el;
    bot.labelEl = cars[0].lb;
    bot.sMain = cars[0].sMain;
  }

  function placeCars(){
    const p = getPaths();
    for(const c of cars){
      const q = ptOn(p.main, c.sMain);
      c.el.setAttribute('transform', `translate(${q.x},${q.y})`);
      c.lb.setAttribute('x', q.x+6); c.lb.setAttribute('y', q.y-6);
      c.lb.textContent = c.id;
    }
  }

  // bot state
  const bot = {
    mode:'idle', // 'main','toPit','pit','pitWait','pitToOut','toMain'
    id:1,
    sMain:0, sPit:0,
    speed:1,
    el:null,
    labelEl:null,
    trans:{ on:false, t0:0, dur:800, a:{x:0,y:0}, b:{x:0,y:0} },
    waitUntil:0
  };
  let pitQueued=false; // PitIn 예약 플래그
  let anim=null, tPrev=0;

  function beginTransition(a, b){ // {x,y} -> {x,y}
    bot.trans.on=true;
    bot.trans.t0=performance.now();
    bot.trans.a=a; bot.trans.b=b;
    bot.trans.dur = Math.max(100, parseInt(transEl.value||"900",10));
  }
  function stepTransition(now){
    const w = clamp((now - bot.trans.t0)/bot.trans.dur, 0, 1);
    const x = bot.trans.a.x*(1-w) + bot.trans.b.x*w;
    const y = bot.trans.a.y*(1-w) + bot.trans.b.y*w;
    bot.el.setAttribute('transform', `translate(${x},${y})`);
    if (bot.labelEl){ bot.labelEl.setAttribute('x', x+6); bot.labelEl.setAttribute('y', y-6); bot.labelEl.textContent = bot.id||1; }
    if (w>=1) bot.trans.on=false;
  }

  function reachedForward(a, b, target){
    // did we pass 'target' when moving forward from a to b on a circle [0,1)?
    if (b>=a) return (target>=a && target<=b);
    else return (target>=a || target<=b); // wrap-around
  }

  function start(){
    render(); // ensure latest path elements exist
    const p = getPaths();
    if (!p.main || layers.main.pts.length<2){
      alert('메인 레인을 먼저 그려주세요.');
      return;
    }
    // 20 cars 생성 (start 레이어가 있으면 그리드 기준으로 스폰)
    spawnCars(20);
    placeCars();

    bot.mode='main';
    bot.sPit=0;
    bot.speed = 1 / Math.max(0.1, parseFloat(lapSecEl.value||"2.0"));
    bot.trans.dur = Math.max(100, parseInt(transEl.value||"900",10));
    pitQueued = false;

    tPrev=0;
    stateEl.textContent = 'state: main';
    if (anim) cancelAnimationFrame(anim);
    anim = requestAnimationFrame(loop);
  }

  function stop(){
    if (anim) cancelAnimationFrame(anim);
    anim=null;
    bot.mode='idle';
    stateEl.textContent = 'state: idle';
  }

  function loop(now){
    if (!tPrev) tPrev=now;
    const dt = (now - tPrev)/1000; tPrev=now;

    const p = getPaths();
    const vMain = bot.speed;
    const vPit  = vMain * Math.max(0.1, parseFloat(pitMulEl.value||"0.6"));

    // === NPC 메인 주행 ===
    for (let i=1;i<cars.length;i++){ // 0번은 bot
      const c = cars[i];
      c.sMain = (c.sMain + c.vMain*dt) % 1;
      const qq = ptOn(p.main, c.sMain);
      c.el.setAttribute('transform', `translate(${qq.x},${qq.y})`);
      c.lb.setAttribute('x', qq.x+6); c.lb.setAttribute('y', qq.y-6);
      c.lb.textContent = c.id;
    }

    // compute s for special points (projections)
    const sMainOut = (layers.pitOut.pts[0]) ? nearestS(p.main, layers.pitOut.pts[0]) : 0.0;
    const sPitIn   = (layers.pitIn.pts[0])  ? nearestS(p.pit,  layers.pitIn.pts[0])  : 0.0;
    const sPitOut  = (layers.pitOut.pts[0]) ? nearestS(p.pit,  layers.pitOut.pts[0]) : 0.0;
    const sPitStop = (layers.pitStop.pts[0])? nearestS(p.pit,  layers.pitStop.pts[0]): sPitIn;

    // --- Update by mode ---
    if (bot.mode==='main'){
      const before = bot.sMain;
      bot.sMain = (bot.sMain + vMain*dt) % 1;
      const q = ptOn(p.main, bot.sMain);
      bot.el.setAttribute('transform', `translate(${q.x},${q.y})`);
      if (bot.labelEl){ bot.labelEl.setAttribute('x', q.x+6); bot.labelEl.setAttribute('y', q.y-6); bot.labelEl.textContent = bot.id||1; }
      stateEl.textContent = 'state: main';

      if (pitQueued){
        const sMainIn = (layers.pitIn.pts[0]) ? nearestS(p.main, layers.pitIn.pts[0]) : null;
        if (sMainIn!=null){
          if (reachedForward(before, bot.sMain, sMainIn)){
            // pitIn 투영 지점까지 실제로 도달한 순간만 브릿지
            bot.sMain = sMainIn;
            const A = ptOn(p.main, sMainIn);
            const B = ptOn(p.pit,  sPitIn);
            beginTransition(A, B);
            bot.sPit = sPitIn;
            bot.mode='toPit';
            stateEl.textContent='state: toPit ▶';
            pitQueued=false;
          }
        }
      }

    } else if (bot.mode==='toPit'){
      stepTransition(now);
      if (!bot.trans.on){
        bot.mode='pit';
        stateEl.textContent='state: pit';
      }

    } else if (bot.mode==='pit'){
      const before = bot.sPit;
      bot.sPit = (bot.sPit + vPit*dt) % 1;
      const q = ptOn(p.pit, bot.sPit);
      bot.el.setAttribute('transform', `translate(${q.x},${q.y})`);
      if (bot.labelEl){ bot.labelEl.setAttribute('x', q.x+6); bot.labelEl.setAttribute('y', q.y-6); bot.labelEl.textContent = bot.id||1; }
      stateEl.textContent='state: pit';

      const reached = reachedForward(before, bot.sPit, sPitStop);
      if (reached){
        bot.mode='pitWait';
        bot.waitUntil = performance.now() + Math.max(0, parseFloat(waitEl.value||"3.0"))*1000;
        bot.sPit = sPitStop;
        const qq = ptOn(p.pit, sPitStop);
        bot.el.setAttribute('transform', `translate(${qq.x},${qq.y})`);
        if (bot.labelEl){ bot.labelEl.setAttribute('x', qq.x+6); bot.labelEl.setAttribute('y', qq.y-6); }
        stateEl.textContent='state: pit WAIT';
      }

    } else if (bot.mode==='pitWait'){
      const q = ptOn(p.pit, bot.sPit);
      bot.el.setAttribute('transform', `translate(${q.x},${q.y})`);
      if (bot.labelEl){ bot.labelEl.setAttribute('x', q.x+6); bot.labelEl.setAttribute('y', q.y-6); }
      stateEl.textContent='state: pit WAIT';

      if (now >= bot.waitUntil){
        bot.mode='pitToOut';
        stateEl.textContent='state: pit → out';
      }

    } else if (bot.mode==='pitToOut'){
      const before = bot.sPit;
      bot.sPit = (bot.sPit + vPit*dt) % 1;
      const q = ptOn(p.pit, bot.sPit);
      bot.el.setAttribute('transform', `translate(${q.x},${q.y})`);
      if (bot.labelEl){ bot.labelEl.setAttribute('x', q.x+6); bot.labelEl.setAttribute('y', q.y-6); }
      stateEl.textContent='state: pit → out';

      const reached = reachedForward(before, bot.sPit, sPitOut);
      if (reached){
        bot.sPit = sPitOut;
        const a = ptOn(p.pit,  sPitOut);
        const b = ptOn(p.main, sMainOut);
        beginTransition(a, b);
        bot.sMain = sMainOut;
        bot.mode='toMain';
        stateEl.textContent='state: toMain ▶';
      }

    } else if (bot.mode==='toMain'){
      stepTransition(now);
      if (!bot.trans.on){
        bot.mode='main';
        stateEl.textContent='state: main';
      }
    }

    anim = requestAnimationFrame(loop);
  }

  // control buttons
  document.getElementById('play').addEventListener('click', start);
  document.getElementById('stop').addEventListener('click', stop);

  document.getElementById('pitInNow').addEventListener('click', ()=>{
    pitQueued = true;           // 메인 레인에서 pitIn(S)을 '지나치면' 전환
    stateEl.textContent = 'state: wait for pitIn';
  });

  // init
  snapshot();
  hint();
  render();

})();
</script>
"""

html = html.replace("%%BG%%", bg_data_url)

st.components.v1.html(html, height=950, scrolling=False)
