import streamlit as st
import json, os, re, base64
import pandas as pd

st.set_page_config(layout="wide", page_title="SVG Race Preview — Auto-Calibrated + Speed Multiplier")
st.title("🏁 SVG Race Preview — Auto-Calibrated + Speed Multiplier + Pit Travel Fixed")

# ---------------- CSV 경로 ----------------
INFO_DIR     = "info"
DRIVERS_CSV  = os.path.join(INFO_DIR, "drivers.csv")
TEAMS_CSV    = os.path.join(INFO_DIR, "teams.csv")
TRACKS_CSV   = os.path.join(INFO_DIR, "tracks.csv")
CALIB_CSV    = os.path.join(INFO_DIR, "circuit_calibration.csv")

# 이미지 폴더(리스트!)
IMG_DIRS = ["driver_image"]

def _norm_col(df, candidates, default=None):
    for c in candidates:
        if c in df.columns: return c
    if default and default in df.columns: return default
    return None

# 이름 → TLA(세 글자) (CSV에 abbr 없을 때만 사용)
EX_TLA = {
    "LEWIS HAMILTON":"HAM","MAX VERSTAPPEN":"VER","CHARLES LECLERC":"LEC","LANDO NORRIS":"NOR",
    "CARLOS SAINZ":"SAI","OSCAR PIASTRI":"PIA","GEORGE RUSSELL":"RUS","FERNANDO ALONSO":"ALO",
    "SERGIO PEREZ":"PER","ESTEBAN OCON":"OCO","PIERRE GASLY":"GAS","VALTTERI BOTTAS":"BOT",
    "ZHOU GUANYU":"ZHO","YUKI TSUNODA":"TSU","NICO HULKENBERG":"HUL","KEVIN MAGNUSSEN":"MAG",
    "ALEXANDER ALBON":"ALB","LANCE STROLL":"STR","LOGAN SARGEANT":"SAR"
}
def make_tla(name: str) -> str:
    if not name: return "DRV"
    key = re.sub(r"\s+"," ",name).strip().upper()
    if key in EX_TLA: return EX_TLA[key]
    tokens = re.split(r"[\s\-]+", key)
    last = re.sub(r"[^A-Z]","", tokens[-1] if tokens else key)
    if len(last) >= 3: return last[:3]
    base = last
    for t in tokens[:-1]:
        t = re.sub(r"[^A-Z]","", t)
        if not t: continue
        base += t[0]
        if len(base) >= 3: break
    return (base + "XXX")[:3]

def _find_img_bytes(name: str):
    """언어 처리 최소화: 정확히 '<이름>.png' 또는 .jpg 만 시도"""
    if not name: return None
    candidates = [f"{name}.png", f"{name}.jpg"]
    for d in IMG_DIRS:
        if not os.path.isdir(d): continue
        for fn in candidates:
            p = os.path.join(d, fn)
            if os.path.exists(p):
                try:
                    with open(p, "rb") as f:
                        return f.read()
                except:
                    pass
    return None

def _img_to_data_uri(b: bytes, ext="png") -> str:
    b64 = base64.b64encode(b).decode("ascii")
    mime = "image/png" if ext.lower()=="png" else "image/jpeg"
    return f"data:{mime};base64,{b64}"

def _to_hex(c: str) -> str:
    if not c: return ""
    c = str(c).strip()
    if re.fullmatch(r"#?[0-9A-Fa-f]{6}", c):
        return c if c.startswith("#") else ("#" + c)
    return c

# ---------------- CSV 로드 (최소 처리) ----------------
def load_roster(drivers_csv, teams_csv):
    roster, team_color_map = [], {}

    # teams.csv: team → team_color (그대로 매칭, strip만)
    if os.path.exists(teams_csv):
        tdf = pd.read_csv(teams_csv)
        team_col  = _norm_col(tdf, ["team","constructor","team_name","name"], "team")
        color_col = _norm_col(tdf, ["team_color","color","hex","primary_color"], "team_color")
        if team_col and color_col:
            for _, r in tdf.iterrows():
                t = str(r[team_col]).strip() if pd.notna(r[team_col]) else ""
                col_raw = str(r[color_col]).strip() if pd.notna(r[color_col]) else ""
                if t:
                    team_color_map[t] = _to_hex(col_raw)

    # drivers.csv: name, abbr, team, (optional color), vmul
    if os.path.exists(drivers_csv):
        df = pd.read_csv(drivers_csv)
        num_col   = _norm_col(df, ["num","number","no","car_number"], "num")
        name_col  = _norm_col(df, ["name","driver","driver_name"], "name")
        team_col  = _norm_col(df, ["team","constructor","team_name"], "team")
        vmul_col  = _norm_col(df, ["vmul","speed_mul","speed_factor"], None)
        color_col = _norm_col(df, ["color","hex","primary_color"], None)
        abbr_col  = _norm_col(df, ["abbr","code","tla","short","short_name"], "abbr")

        for _, r in df.iterrows():
            num  = int(r[num_col]) if num_col and pd.notna(r[num_col]) else None
            name = str(r[name_col]).strip() if name_col and pd.notna(r[name_col]) else ""
            team = str(r[team_col]).strip() if team_col and pd.notna(r[team_col]) else ""
            raw_v = float(r[vmul_col]) if vmul_col and pd.notna(r[vmul_col]) else 1.0
            vMul = float(raw_v)
            if not (0.1 <= vMul <= 3.0):
                vMul = 1.0
            color = str(r[color_col]).strip() if color_col and pd.notna(r[color_col]) else ""
            if not color and team:
                color = team_color_map.get(team, "")  # 그대로 매칭
            color = _to_hex(color)
            abbr = (str(r[abbr_col]).strip().upper() if abbr_col and pd.notna(r[abbr_col]) else make_tla(name))

            img_bytes = _find_img_bytes(name)
            img_uri = _img_to_data_uri(img_bytes, "png") if img_bytes else ""

            roster.append({
                "num": num, "name": name, "team": team, "vMul": vMul,
                "color": color, "abbr": abbr, "img": img_uri
            })

    # 20대 보정
    if len(roster) < 20:
        base = len(roster)
        for i in range(base, 20):
            name = f"Driver {i+1}"
            abbr = make_tla(name)
            img_bytes = _find_img_bytes(name)
            img_uri = _img_to_data_uri(img_bytes,"png") if img_bytes else ""
            roster.append({
                "num": i+1, "name": name, "team": f"Team {chr(65 + (i%5))}",
                "vMul": 1.0, "color": "", "abbr": abbr, "img": img_uri
            })
    else:
        roster = roster[:20]

    # 결측 최소 채움
    for i, r in enumerate(roster):
        if not r["num"]:  r["num"]  = i+1
        if not r["name"]: r["name"] = f"Driver {i+1}"
        if not r["team"]: r["team"] = f"Team {chr(65 + (i%5))}"
        if not isinstance(r["vMul"], (int,float)) or r["vMul"]<=0: r["vMul"]=1.0
        if not r.get("abbr"): r["abbr"] = make_tla(r["name"])
    return roster

def load_tracks(tracks_csv):
    tracks=[]
    if os.path.exists(tracks_csv):
        df = pd.read_csv(tracks_csv)
        name_col = _norm_col(df, ["name","circuit","track","circuit_name","track_name"], "name")
        len_col  = _norm_col(df, ["length_km","length","km","track_km"], "length_km")
        lap_col  = _norm_col(df, ["typical_lap_sec","lap_sec","lap_time_sec","avg_lap_sec","lap_time"], "lap_sec")
        pit_col  = _norm_col(df, ["pit_speed_kmh","pit_limit_kmh","pit_kmh"], "pit_speed_kmh")
        if name_col:
            for _,r in df.iterrows():
                name = str(r[name_col]).strip() if pd.notna(r[name_col]) else ""
                if not name: continue
                length_km = float(r[len_col]) if len_col and pd.notna(r[len_col]) else None
                # lap은 숫자면 그대로, "m:ss"면 파싱
                lap_raw = r[lap_col] if lap_col and lap_col in r and pd.notna(r[lap_col]) else None
                lap_sec = None
                if isinstance(lap_raw, (int,float)): lap_sec = float(lap_raw)
                elif isinstance(lap_raw, str) and ":" in lap_raw:
                    mm, ss = lap_raw.split(":")
                    try: lap_sec = float(mm)*60 + float(ss)
                    except: lap_sec = None
                pit_kmh   = float(r[pit_col]) if pit_col and pd.notna(r[pit_col]) else None
                tracks.append({"name":name, "length_km":length_km, "lap_sec":lap_sec, "pit_kmh":pit_kmh})
    return tracks

def load_calibration(calib_csv):
    """info/circuit_calibration.csv 읽어서 dict 리스트 반환"""
    if not os.path.exists(calib_csv):
        return []
    df = pd.read_csv(calib_csv)
    cols = {c.lower(): c for c in df.columns}
    out=[]
    for _,r in df.iterrows():
        get=lambda k: r[cols[k]] if k in cols and pd.notna(r[cols[k]]) else None
        out.append({
            "file": get("file"),
            "circuit": get("circuit"),
            "lap_sec_csv": float(get("lap_sec_csv")) if get("lap_sec_csv") else None,
            "pit_travel_sec": float(get("pit_travel_sec")) if get("pit_travel_sec") else None,
            "px_per_sec": float(get("px_per_sec")) if get("px_per_sec") else None
        })
    return out

def match_calib(calibs, circuit_name:str=None, svg_filename:str=None):
    """회로명 우선, 없으면 파일명 스템으로 매칭(최소 처리: strip/lower만)"""
    def slug(s): return re.sub(r"[^a-z0-9]","", (s or "").strip().lower())
    if not calibs: return {}
    if circuit_name:
        sc = slug(circuit_name)
        for c in calibs:
            if slug(c.get("circuit")) == sc: return c
    if svg_filename:
        stem = os.path.splitext(os.path.basename(svg_filename))[0]
        ss = slug(stem)
        for c in calibs:
            if slug(c.get("file")) == ss or slug(c.get("circuit")) == ss:
                return c
    return {}

roster = load_roster(DRIVERS_CSV, TEAMS_CSV)
tracks = load_tracks(TRACKS_CSV)
calibs = load_calibration(CALIB_CSV)

# ---------------- SVG 업로드 & 서킷 자동 매칭 ----------------
u = st.file_uploader("SVG 업로드", type=["svg"])
RAW_SVG = u.getvalue().decode("utf-8", "ignore") if u else ""
VIEWBOX_FALLBACK = "0 0 1200 800"

def guess_circuit_name_from_filename(fname:str) -> str:
    if not fname: return ""
    nm = os.path.splitext(fname)[0]
    return re.sub(r"[_\-]+", " ", nm).strip()

guessed = guess_circuit_name_from_filename(u.name if u else "")
track_names = [t["name"] for t in tracks] if tracks else []
default_idx = 0
if guessed and track_names:
    g_low = guessed.lower()
    for i,tn in enumerate(track_names):
        if g_low in tn.lower() or tn.lower() in g_low:
            default_idx = i; break

colA, colB = st.columns([2,1])
with colA:
    circuit = st.selectbox("서킷 선택(파일명 자동 추정)", track_names if track_names else ["(CSV tracks 없음)"], index=default_idx if track_names else 0)
with colB:
    # base_kmh는 fallback 계산용(일반적으로 calib_csv가 있으면 안 씀)
    base_kmh = st.number_input("기준 속도 (km/h) — (보정 없을 때만 사용)", min_value=50.0, max_value=400.0, value=220.0, step=5.0)

sel_track = tracks[track_names.index(circuit)] if track_names else None

# --- 자동 보정 매칭 ----
calib_row = match_calib(calibs, circuit_name=circuit, svg_filename=(u.name if u else None))

# Lap(sec) & pit travel 기본값 (보정 없을 때 대비)
lap_def = sel_track["lap_sec"] if (sel_track and sel_track.get("lap_sec")) else 2.5
pit_travel_def = None   # 없으면 기존 방식(vPit) fallback 사용
if sel_track and not sel_track.get("lap_sec") and sel_track.get("length_km"):
    lap_def = 3600.0 * float(sel_track["length_km"]) / max(1e-6, float(base_kmh))

# 보정값 있으면 우선
if calib_row.get("lap_sec_csv"):    lap_def = float(calib_row["lap_sec_csv"])
if calib_row.get("pit_travel_sec"): pit_travel_def = float(calib_row["pit_travel_sec"])

# ---------------- HTML/JS ----------------
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
  .btns { display:flex; gap:8px; margin:8px 0 12px; flex-wrap:wrap; }
  .btn  { font-size:13px; padding:6px 10px; border-radius:8px; border:1px solid #cbd5e1; background:white; cursor:pointer; }
  .btn.primary { background:#0b5cff; color:#fff; border-color:#0b5cff; }
  .grid2 { display:grid; grid-template-columns: 1fr 1fr; gap:8px; margin:6px 0 12px; }
  .panel label { font-size:12px; color:#0f172a; display:block; }
  .panel input { width:100%; box-sizing:border-box; padding:6px 8px; border-radius:8px; border:1px solid #cbd5e1; background:#fff; font-size:13px; }
  .car, .carLabel { cursor: pointer; pointer-events: auto; }
  .speed .btn { padding:6px 10px; }
  .btn.active { background:#0b5cff; color:#fff; border-color:#0b5cff; }
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
      <span class="chip">Markers: pitIn / pitOut / pitStop</span>
    </div>

    <div class="grid2">
      <label>Pit wait (sec)
        <input id="waitSecInput" type="number" min="0" step="0.1" value="3.0">
      </label>
      <label>Transition (ms)
        <input id="transMsInput" type="number" min="50" step="50" value="900">
      </label>
      <label>선택 차량 속도 ×
        <input id="carMulInput" type="number" min="0.1" step="0.05" value="1.00">
      </label>
      <label>Pit-In 대상 차량 (1~20)
        <input id="targetCarInput" type="number" min="1" max="20" step="1" value="1">
      </label>
    </div>

    <div style="margin:4px 0 6px; font-weight:600;">배속</div>
    <div class="btns speed" id="speedBtns">
      <button class="btn" data-m="0.5">0.5×</button>
      <button class="btn active" data-m="1">1×</button>
      <button class="btn" data-m="2">2×</button>
      <button class="btn" data-m="4">4×</button>
      <button class="btn" data-m="10">10×</button>
    </div>

    <div class="btns">
      <button id="play" class="btn primary">▶ Play(재시작)</button>
      <button id="stop" class="btn">⏯ Stop(일시정지/재개)</button>
      <button id="pitInNow" class="btn">Pit-In (선택 차량)</button>
    </div>
    <div class="muted" id="state">state: idle</div>

    <h3>선수 카드</h3>
    <div id="card" style="display:none; padding:10px; border:1px solid #cbd5e1; border-radius:10px; background:#fff;">
      <div style="display:flex; gap:10px; align-items:center;">
        <img id="cImg" src="" alt="driver" style="width:96px; height:96px; object-fit:cover; border-radius:12px; border:1px solid #e5e7eb;">
        <div>
          <div id="cHeader" style="font-weight:700; font-size:14px; margin-bottom:4px;">-</div>
          <div class="muted" id="cSub">-</div>
          <div id="cMode" class="muted" style="margin-top:4px;">mode: -</div>
        </div>
      </div>
    </div>

    <h3>보정 정보</h3>
    <div id="report" class="muted"></div>
  </div>
</div>

<script>
(function(){
  const RAW = %%RAW_SVG%%;
  const VIEWBOX_FALLBACK = "%%VIEWBOX%%";
  const ROSTER = %%ROSTER_JSON%%;
  const TRACK_INFO = %%TRACK_INFO%%;
  const CIRCUIT_NAME = "%%CIRCUIT_NAME%%";
  const BASE_KMH = %%BASE_KMH%%;
  const CALIB = %%CALIB_JSON%%; // {lap_sec_csv, pit_travel_sec, px_per_sec, ...}

  const stage = document.getElementById('stage');
  const gTrack= document.getElementById('track');
  const gAct  = document.getElementById('actors');
  const report= document.getElementById('report');
  const stateEl=document.getElementById('state');

  const roster = (Array.isArray(ROSTER) && ROSTER.length) ? ROSTER : [];

  // 실시간 파라미터 (배속 중심)
  const params = {
    lapSecBase: %%LAP_BASE%%,            // 보정된 랩타임(초)
    pitTravelBase: %%PIT_TRAVEL_BASE%%,  // 보정된 pit in→out 시간(초), 없으면 null
    waitSec: 3.0,
    transMs: 900,
    speedMul: 1.0,
    targetCar: 1
  };

  const waitIn  = document.getElementById('waitSecInput');
  const transIn = document.getElementById('transMsInput');
  const carMulIn= document.getElementById('carMulInput');
  const carIn   = document.getElementById('targetCarInput');

  function bindLive(inputEl, key, mapFn){
    inputEl.addEventListener('input', ()=>{
      const v = mapFn ? mapFn(inputEl.value) : parseFloat(inputEl.value);
      if (Number.isFinite(v)) {
        params[key] = v;
        if (key==='targetCar') selectCar(v-1, false);
      }
    });
  }
  bindLive(waitIn, 'waitSec', v=>Math.max(0, parseFloat(v)));
  bindLive(transIn,'transMs', v=>Math.max(50, parseInt(v||"0",10)));
  bindLive(carIn,  'targetCar', v=>Math.min(20, Math.max(1, parseInt(v||"1",10))));
  carMulIn.addEventListener('input', ()=>{
    const v = Math.max(0.1, parseFloat(carMulIn.value||"1"));
    if (Number.isFinite(v) && currentSel>=0 && cars[currentSel]) { cars[currentSel].vMul = v; showCardFor(currentSel); }
  });

  // 배속 버튼
  const speedBtns = document.getElementById('speedBtns');
  speedBtns.addEventListener('click', (ev)=>{
    const b = ev.target.closest('button[data-m]');
    if(!b) return;
    const m = parseFloat(b.getAttribute('data-m')||"1");
    if (!Number.isFinite(m)) return;
    params.speedMul = m;
    [...speedBtns.querySelectorAll('button')].forEach(x=>x.classList.remove('active'));
    b.classList.add('active');
  });

  // ---------------- SVG helpers ----------------
  const colors=['#ff6b00','#00a3ff','#ffd400','#5ad469','#c86bff','#ff4d6d','#3bc9db','#fab005','#9b59b6','#2ecc71',
                '#e67e22','#3498db','#f1c40f','#1abc9c','#e84393','#16a085','#c0392b','#8e44ad','#2980b9','#2ecc71'];
  function text(x,y,str,size=10,fill='#0f172a'){const t=document.createElementNS(stage.namespaceURI,'text');t.setAttribute('x',x);t.setAttribute('y',y);t.setAttribute('font-size',String(size));t.setAttribute('fill',fill);t.textContent=str;return t;}
  function ptOn(path,s){const L=Math.max(1,path.getTotalLength()); const c=Math.max(0,Math.min(1,s)); const q=path.getPointAtLength(c*L); return {x:q.x,y:q.y};}
  function nearestS(path,p){ if(!path) return 0; const L=path.getTotalLength(),N=1000; let bestS=0,bestD=1e9; for(let i=0;i<=N;i++){const s=i/N; const q=path.getPointAtLength(s*L); const dx=q.x-p.x,dy=q.y-p.y; const d=dx*dx+dy*dy; if(d<bestD){bestD=d;bestS=s;}} return bestS;}
  function reachedForward(a,b,target){ return (b>=a) ? (target>=a && target<=b) : (target>=a || target<=b); }
  function parseSVG(raw){ return (!raw||!raw.trim())?null:new DOMParser().parseFromString(raw, "image/svg+xml"); }
  function getViewBox(doc){ const root = doc.querySelector('svg'); return (root && root.getAttribute('viewBox')) ? root.getAttribute('viewBox') : VIEWBOX_FALLBACK; }
  function grabPathD(doc, id){ const el = doc.querySelector(`path#${id}`); return el ? el.getAttribute('d') : ''; }
  function grabFinishPoints(doc){
    const el = doc.querySelector('polyline#finish, line#finish'); if(!el) return [];
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
    if (dpt.length===2 && dpt.every(Number.isFinite)) return {x:dpt[0],y:dpt[1]}; return null;
  }
  function grabMarkersFromMetadata(doc){
    const md = doc.querySelector('metadata'); if(!md) return {};
    try{ const obj = JSON.parse(md.textContent||"{}");
      const pick=k=> (obj[k]&&Array.isArray(obj[k].pts)&&obj[k].pts[0]) ? obj[k].pts[0] : null;
      return { pitIn:pick('pitIn'), pitOut:pick('pitOut'), pitStop:pick('pitStop') };
    }catch(e){ return {}; }
  }
  function grabStartGridFromMetadata(doc){
    const md = doc.querySelector('metadata'); if(!md) return null;
    try{ const obj = JSON.parse(md.textContent||"{}");
      if (obj.start && Array.isArray(obj.start.pts)) return obj.start.pts.map(p=>({x:p.x,y:p.y,num:p.num||null}));
    }catch(e){} return null;
  }
  function grabStartGridFromGroup(doc){
    const g = doc.querySelector('g#grid'); if(!g) return null;
    const nodes=[...g.querySelectorAll('circle')]; if(nodes.length===0) return null;
    return nodes.map(el=>{
      const [x,y]=(el.getAttribute('data-pt')||'0,0').split(',').map(parseFloat);
      const num=parseInt(el.getAttribute('data-num')||'0',10)||null; return {x,y,num};
    });
  }
  function sAdd(a, delta){ let s=a+delta; while(s<0) s+=1; while(s>=1) s-=1; return s; }
  function segFrac(a,b){ return (b>=a) ? (b-a) : (1-a+b); }

  // -------- build & scene --------
  let parsed=null, mainLenPx=0;
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
      ln.setAttribute('x2',finPts[1].x); ln.setAttribute('y2',finPts[1].y);
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

    try{ mainLenPx = document.getElementById('pMain').getTotalLength(); }catch(e){ mainLenPx = 0; }

    // 리포트
    report.innerHTML = `
      main path: <b>${dMain ? 'OK' : 'MISSING'}</b> · 길이(px): <b>${mainLenPx.toFixed(1)}</b><br>
      pit  path: <b>${dPit  ? 'OK' : 'MISSING'}</b><br>
      circuit: <b>${CIRCUIT_NAME||'-'}</b><br>
      lap(base): <b>${params.lapSecBase.toFixed(3)}s</b> · pit travel(base): <b>${params.pitTravelBase?params.pitTravelBase.toFixed(3)+'s':'-'}</b>
    `;
    return { pMain, pPit, finPts, mk, grid };
  }

  // ------- cars & animation -------
  let anim=null, tPrev=0, paused=false;
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
      const info = roster[i] || {};
      const c=document.createElementNS(stage.namespaceURI,'circle');
      c.setAttribute('r','6');
      const col = (info.color && /^#?[0-9A-Fa-f]{6}$/.test(info.color)) ? (info.color[0]==="#"?info.color:("#"+info.color)) : null;
      c.setAttribute('fill', col || colors[i%colors.length]);
      c.setAttribute('stroke','white'); c.setAttribute('stroke-width','2');
      c.classList.add('car'); c.dataset.idx=String(i); c.setAttribute('pointer-events','auto');

      const abbr = (info.abbr && String(info.abbr).trim()) ? String(info.abbr).toUpperCase() : `D${i+1}`;
      const label=text(0,0,abbr,9,'#0f172a');
      label.classList.add('carLabel'); label.dataset.idx=String(i); label.setAttribute('pointer-events','auto');

      gAct.appendChild(c); gAct.appendChild(label);
      cars.push({
        id:i+1, num: (Number.isFinite(info.num)?info.num:(i+1)),
        name: info.name || `Driver ${i+1}`,
        team: info.team || `Team`,
        abbr: abbr,
        img: info.img || "",
        el:c, lab:label, mode:'main',
        sMain:0, sPit:0, vMul: (Number.isFinite(info.vMul) && info.vMul >= 0.1 && info.vMul <= 3.0) ? info.vMul : 1.0,
        trans:{on:false,t0:0,dur:params.transMs,a:{x:0,y:0},b:{x:0,y:0}},
        waitUntil:0, pitRequest:false,
        pitMove:null  // {seg1, seg2, sIn, sStop, sOut, phase, prog}
      });
    }
    bindCarClickOnce();
  }

  function bindCarClickOnce(){ if (clickBound) return; gAct.addEventListener('click', onCarClick); clickBound = true; }
  function onCarClick(ev){
    const t = ev.target; let idx = -1;
    if (t && t.dataset && t.dataset.idx) idx = parseInt(t.dataset.idx, 10);
    else if (t && t.closest) { const host = t.closest('[data-idx]'); if (host) idx = parseInt(host.dataset.idx, 10); }
    if (!Number.isFinite(idx) || idx < 0) return; selectCar(idx, true);
  }

  function placeOnStart(parsed){
    const {pMain,grid,finPts}=parsed;
    if(grid && grid.length){
      for(let i=0;i<cars.length;i++){
        const gpt=grid[Math.min(i,grid.length-1)];
        const s=nearestS(pMain,{x:gpt.x,y:gpt.y});
        cars[i].sMain=s; const q=ptOn(pMain,s);
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

  // --- 재시작(초기화) ---
  function start(){
    if(!parsed){ parsed = buildFromRaw(); if(!parsed){ alert('SVG 파싱 실패'); return; } }
    ensureCars(); placeOnStart(parsed);
    for(const car of cars){ car.mode='main'; car.pitRequest=false; car.pitMove=null; }
    tPrev=0; paused=false; stateEl.textContent=`state: main (20 cars) — circuit: ${CIRCUIT_NAME||'-'}`;
    if(anim) cancelAnimationFrame(anim);
    anim=requestAnimationFrame(loop);
    selectCar(Math.max(0, Math.min(19, params.targetCar-1)), false);
  }

  // --- 토글 일시정지/재개 ---
  function togglePause(){
    if (anim){ cancelAnimationFrame(anim); anim=null; paused=true; stateEl.textContent='state: paused';
    } else { if(!parsed){ parsed = buildFromRaw(); if(!parsed){ alert('SVG 파싱 실패'); return; } }
      tPrev=0; paused=false; stateEl.textContent='state: resumed'; anim=requestAnimationFrame(loop);
    }
  }

  function loop(now){
    if(!tPrev) tPrev=now;
    const dt=(now-tPrev)/1000; tPrev=now;

    const p={ main:document.getElementById('pMain'), pit:document.getElementById('pPit') };
    if(!p.main) return;

    // 보정된 랩타임/피트 시간에 배속 적용
    const lapSecAdj = Math.max(0.1, params.lapSecBase / Math.max(0.1, params.speedMul));
    const waitAdj   = Math.max(0, params.waitSec / Math.max(0.1, params.speedMul));
    const vMain = 1 / lapSecAdj; // s per sec

    // pit 관련 s 위치(매 프레임 계산)
    const sMainIn  = parsed.mk.pitIn  ? nearestS(p.main, parsed.mk.pitIn ) : 0.0;
    const sMainOut = parsed.mk.pitOut ? nearestS(p.main, parsed.mk.pitOut) : 0.0;
    const sPitIn   = parsed.mk.pitIn  ? nearestS(p.pit , parsed.mk.pitIn ) : 0.0;
    const sPitOut  = parsed.mk.pitOut ? nearestS(p.pit , parsed.mk.pitOut) : 0.0;
    const sPitStop = parsed.mk.pitStop? nearestS(p.pit , parsed.mk.pitStop): sPitIn;

    // pit 세그먼트 분해(길이 비율)
    const segTot  = segFrac(sPitIn, sPitOut);
    const seg1    = segFrac(sPitIn, sPitStop);
    const seg2    = segTot - seg1 + 0; // 둘의 합이 segTot
    const tPitBase= params.pitTravelBase; // 없으면 null

    for(const car of cars){
      if(car.mode==='main'){
        const before=car.sMain;
        car.sMain=(car.sMain + vMain*car.vMul*dt) % 1;
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
        if(!car.trans.on){
          car.mode='pit';
          // pit 이동 계획 설정
          if (tPitBase && segTot>0){
            car.pitMove = { seg1, seg2, segTot, sIn:sPitIn, sStop:sPitStop, sOut:sPitOut, phase:'toStop', prog:0 };
          }else{
            car.pitMove = null; // fallback: 예전 방식 사용
          }
        }

      } else if (car.mode==='pit'){
        if (car.pitMove){ // 고정 시간 방식
          const t1 = (seg1/Math.max(segTot,1e-6)) * (tPitBase/Math.max(params.speedMul,0.1));
          const dur = Math.max(t1, 1e-6);
          car.pitMove.prog = Math.min(1, car.pitMove.prog + dt/dur);
          const sCur = sAdd(car.pitMove.sIn, car.pitMove.prog * car.pitMove.seg1);
          car.sPit = sCur;
          const q=ptOn(p.pit,car.sPit);
          car.el.setAttribute('transform',`translate(${q.x},${q.y})`);
          car.lab.setAttribute('x',q.x+8); car.lab.setAttribute('y',q.y-8);
          if (car.pitMove.prog>=1){
            car.mode='pitWait';
            car.waitUntil=performance.now()+waitAdj*1000;
            car.pitMove.phase='wait';
          }
        } else { // fallback: 길이/속도 곱 방식(보정 없음)
          const vPit = vMain*0.6*car.vMul; // 임시 계수(과거 pitMul=0.6)
          const before=car.sPit;
          car.sPit=(car.sPit+vPit*dt)%1;
          const q=ptOn(p.pit,car.sPit);
          car.el.setAttribute('transform',`translate(${q.x},${q.y})`);
          car.lab.setAttribute('x',q.x+8); car.lab.setAttribute('y',q.y-8);
          const reached = reachedForward(before, car.sPit, sPitStop);
          if(reached){
            car.mode='pitWait';
            car.waitUntil=performance.now()+waitAdj*1000;
            car.sPit=sPitStop; const qq=ptOn(p.pit,sPitStop);
            car.el.setAttribute('transform',`translate(${qq.x},${qq.y})`);
            car.lab.setAttribute('x',qq.x+8); car.lab.setAttribute('y',qq.y-8);
          }
        }

      } else if (car.mode==='pitWait'){
        const q=ptOn(p.pit,car.sPit);
        car.el.setAttribute('transform',`translate(${q.x},${q.y})`);
        car.lab.setAttribute('x',q.x+8); car.lab.setAttribute('y',q.y-8);
        if(now>=car.waitUntil){
          car.mode='pitToOut';
          if (car.pitMove){ car.pitMove.phase='toOut'; car.pitMove.prog=0; }
        }

      } else if (car.mode==='pitToOut'){
        if (car.pitMove){ // 고정 시간 방식
          const t2 = (seg2/Math.max(segTot,1e-6)) * (tPitBase/Math.max(params.speedMul,0.1));
          const dur = Math.max(t2, 1e-6);
          car.pitMove.prog = Math.min(1, car.pitMove.prog + dt/dur);
          const sCur = sAdd(car.pitMove.sStop, car.pitMove.prog * car.pitMove.seg2);
          car.sPit = sCur;
          const q=ptOn(p.pit,car.sPit);
          car.el.setAttribute('transform',`translate(${q.x},${q.y})`);
          car.lab.setAttribute('x',q.x+8); car.lab.setAttribute('y',q.y-8);

          if (car.pitMove.prog>=1){
            car.sPit=sPitOut;
            const a=ptOn(p.pit ,sPitOut);
            const b=ptOn(p.main,sMainOut);
            beginTrans(car,a,b);
            car.sMain=sMainOut;
            car.mode='toMain';
          }
        } else { // fallback
          const vPit = vMain*0.6*car.vMul;
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
        }

      } else if (car.mode==='toMain'){
        stepTrans(car, now);
        if(!car.trans.on) car.mode='main';
      }
    }

    // 선택 링 위치
    if (currentSel>=0){
      const car = cars[currentSel];
      if (car){
        let q;
        if (car.trans.on){
          const w = Math.max(0, Math.min(1,(now-car.trans.t0)/car.trans.dur));
          q = { x: car.trans.a.x*(1-w)+car.trans.b.x*w, y: car.trans.a.y*(1-w)+car.trans.b.y*w };
        }else{
          q = (car.mode==='main' || car.mode==='toMain')
            ? ptOn(document.getElementById('pMain'), car.sMain)
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
  const cImg  = document.getElementById('cImg');
  let currentSel = -1;

  function showCardFor(idx){
    const car = cars[idx]; if(!car) return;
    cHeader.textContent = `#${car.num} ${car.name} (${car.abbr})`;
    cSub.textContent = `Team: ${car.team} · v× ${car.vMul.toFixed(2)}`;
    cMode.textContent = `mode: ${car.mode}`;
    if (car.img && car.img.startsWith("data:")) cImg.src = car.img; else cImg.src = "";
    card.style.display='block';
    if (carMulIn) carMulIn.value = car.vMul.toFixed(2);
  }
  function selectCar(idx, updateInput=true){
    currentSel = Math.max(0, Math.min(19, idx));
    params.targetCar = currentSel + 1;
    if (updateInput){
      const el = document.getElementById('targetCarInput');
      if (el) el.value = String(params.targetCar);
    }
    showCardFor(currentSel);
    selRing.style.display='block';
    const car = cars[currentSel];
    if (car){
      const tr = car.el.getAttribute('transform') || 'translate(0,0)';
      selRing.setAttribute('transform', tr);
      const fill = car.el.getAttribute('fill') || colors[currentSel%colors.length];
      selRing.setAttribute('stroke', fill);
    }
  }

  // Buttons
  document.getElementById('play').addEventListener('click', start);
  document.getElementById('stop').addEventListener('click', togglePause);
  document.getElementById('pitInNow').addEventListener('click', ()=>{
    if(!parsed){ alert('먼저 Play를 눌러주세요.'); return; }
    const idx=Math.max(1,Math.min(20,params.targetCar))-1;
    const car=cars[idx]; if(!car) return;
    if(!parsed.mk.pitIn || !parsed.mk.pitOut){ alert('pitIn/pitOut 마커가 없습니다.'); return; }
    if (car.mode==='main'){ car.pitRequest=true; stateEl.textContent=`state: Pit-In 요청 (car #${car.id})`; }
    selectCar(idx, true);
  });

  // 초기 미리보기
  if (RAW && RAW.trim().length>0) {
    parsed = buildFromRaw();
    ensureCars(); placeOnStart(parsed);
    stateEl.textContent='state: idle (ready)';
    selectCar(0, true);
  } else {
    report.textContent = "SVG를 업로드하세요.";
  }
})();
</script>
"""

# ---- 치환 주입 ----
html = html.replace("%%RAW_SVG%%", json.dumps(RAW_SVG))
html = html.replace("%%VIEWBOX%%", VIEWBOX_FALLBACK)
html = html.replace("%%ROSTER_JSON%%", json.dumps(roster, ensure_ascii=False))
html = html.replace("%%TRACK_INFO%%", json.dumps(sel_track or {}, ensure_ascii=False))
html = html.replace("%%CIRCUIT_NAME%%", (circuit if track_names else ""))
html = html.replace("%%BASE_KMH%%", f"{float(base_kmh):.3f}")
html = html.replace("%%CALIB_JSON%%", json.dumps(calib_row or {}, ensure_ascii=False))
html = html.replace("%%LAP_BASE%%", f"{float(lap_def):.6f}")
html = html.replace("%%PIT_TRAVEL_BASE%%", "null" if pit_travel_def is None else f"{float(pit_travel_def):.6f}")

st.components.v1.html(html, height=950, scrolling=False)
