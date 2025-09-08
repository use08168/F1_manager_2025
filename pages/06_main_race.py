# pages/06_main_race.py
# -*- coding: utf-8 -*-
from __future__ import annotations
import re, json, random
from pathlib import Path
from dataclasses import dataclass
import streamlit as st
import pandas as pd

# ─────────────────────────────────────────────────────────────────────────────
# 경로/리소스
def find_root(start: Path) -> Path:
    cur = start
    for _ in range(6):
        if (cur/"info").exists() and (cur/"circuit").exists():
            return cur
        cur = cur.parent
    return start

ROOT        = find_root(Path(__file__).resolve())
INFO_DIR    = ROOT / "info"
DATA_DIR    = ROOT / "data"
CIRCUIT_DIR = ROOT / "circuit"

DRIVER_IMG_DIRS = [ROOT/"driver_image", ROOT/"images/drivers"]
TIRE_IMG_DIRS   = [ROOT/"tire", ROOT/"tires", ROOT/"images/tires"]

DRIVERS_CSV_INFO = INFO_DIR / "drivers.csv"
DRIVERS_CSV_DATA = DATA_DIR / "drivers.csv"
TEAMS_CSV_INFO   = INFO_DIR / "teams.csv"
TEAMS_CSV_DATA   = DATA_DIR / "teams.csv"
TRACKS_CSV       = (INFO_DIR/"tracks.csv") if (INFO_DIR/"tracks.csv").exists() else (DATA_DIR/"tracks.csv")

# ─────────────────────────────────────────────────────────────────────────────
# 공통 유틸
def _norm_col(df, candidates, default=None):
    for c in candidates:
        if c in df.columns: return c
    if default and default in df.columns: return default
    return None

def _hex(c: str) -> str:
    if not c: return ""
    c = str(c).strip()
    return c if c.startswith("#") else ("#" + c) if re.fullmatch(r"[0-9A-Fa-f]{6}", c) else c

def _abbr_from_name(name: str) -> str:
    if not name: return "DRV"
    key = re.sub(r"\s+"," ",name).strip().upper()
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
    if not name: return None
    for d in DRIVER_IMG_DIRS:
        png = d/f"{name}.png"; jpg = d/f"{name}.jpg"
        if png.exists(): return png.read_bytes()
        if jpg.exists(): return jpg.read_bytes()
    return None

def _img_uri(name: str):
    b = _find_img_bytes(name)
    if not b: return ""
    import base64 as _b64
    b64 = _b64.b64encode(b).decode("ascii")
    return f"data:image/png;base64,{b64}"

def _tire_uri(compound: str):
    key = (compound or "").strip().lower()
    fname = {"soft":"soft","s":"soft",
             "medium":"medium","m":"medium",
             "hard":"hard","h":"hard",
             "intermediate":"intermediate","i":"intermediate","inters":"intermediate",
             "wet":"wet","w":"wet"}.get(key, key or "soft")
    for d in TIRE_IMG_DIRS:
        png = d/f"{fname}.png"
        if png.exists():
            import base64 as _b64
            b64 = _b64.b64encode(png.read_bytes()).decode("ascii")
            return f"data:image/png;base64,{b64}"
    return ""

# ─────────────────────────────────────────────────────────────────────────────
# 데이터 적재
def load_team_catalog():
    by_id, by_name, color_by_id, color_by_name = {}, {}, {}, {}
    for p in [TEAMS_CSV_DATA, TEAMS_CSV_INFO]:
        if not p.exists(): continue
        df = pd.read_csv(p)
        col_id  = _norm_col(df, ["team_id","id"])
        col_nm  = _norm_col(df, ["name","team","constructor","team_name"], "name")
        col_col = _norm_col(df, ["team_color","color","hex","primary_color"], "team_color")
        if not col_nm: continue
        for _,r in df.iterrows():
            tid = str(r[col_id]).strip() if col_id and pd.notna(r[col_id]) else None
            nm  = str(r[col_nm]).strip()  if pd.notna(r[col_nm]) else ""
            col = _hex(str(r[col_col]).strip()) if col_col and pd.notna(r[col_col]) else ""
            if tid: by_id[tid] = nm
            if nm:  by_name[nm] = tid or by_name.get(nm)
            if tid and col: color_by_id[tid] = col
            if nm  and col: color_by_name[nm] = col
    return by_id, by_name, color_by_id, color_by_name

def load_tracks(csv: Path):
    if not csv.exists(): return []
    df = pd.read_csv(csv)
    cols = {c.lower(): c for c in df.columns}
    name = cols.get("name") or cols.get("track") or cols.get("circuit") or list(df.columns)[0]
    rd   = cols.get("round") or cols.get("order")
    lap  = cols.get("typical_lap_sec") or cols.get("lap_sec") or cols.get("lap_time_sec") or cols.get("avg_lap_sec")
    laps_tot = cols.get("laps") or cols.get("race_laps") or cols.get("total_laps")
    out=[]
    for _,r in df.iterrows():
        out.append({"name": str(r[name]).strip(),
                    "round": int(r[rd]) if rd and pd.notna(r[rd]) else None,
                    "lap_sec": float(r[lap]) if lap and pd.notna(r[lap]) else None,
                    "total_laps": int(r[laps_tot]) if laps_tot and pd.notna(r[laps_tot]) else None})
    out.sort(key=lambda x: (999 if x["round"] is None else x["round"], x["name"]))
    return out

def load_roster(by_id, color_by_id, color_by_name):
    roster=[]; src=None
    if DRIVERS_CSV_INFO.exists():
        src = DRIVERS_CSV_INFO
    elif DRIVERS_CSV_DATA.exists():
        src = DRIVERS_CSV_DATA
    if not src or not src.exists(): return roster

    df = pd.read_csv(src)
    num  = _norm_col(df, ["num","number","no","car_number"], "num")
    name = _norm_col(df, ["name","driver","driver_name"], "name")
    team = _norm_col(df, ["team","constructor","team_name"], None)
    team_id = _norm_col(df, ["team_id","constructor_id","tid"], None)
    abbr = _norm_col(df, ["abbr","code","tla","short","short_name"], None)
    rate = _norm_col(df, ["skill","overall","rating","pace"], None)

    for _,r in df.iterrows():
        nm = str(r[name]).strip() if name and pd.notna(r[name]) else ""
        if not nm: continue
        tm, tid = "", None
        if team and pd.notna(r[team]):
            tm = str(r[team]).strip()
        elif team_id and pd.notna(r[team_id]):
            tid = str(r[team_id]).strip()
            tm = by_id.get(tid, f"Team {tid}")
        else:
            tm = "Team"
        ab = (str(r[abbr]).strip().upper() if abbr and pd.notna(r[abbr]) else _abbr_from_name(nm))
        rating = float(r[rate]) if rate and pd.notna(r[rate]) else None
        color = color_by_name.get(tm) or (color_by_id.get(tid) if tid else "")
        roster.append({
            "num": int(r[num]) if num and pd.notna(r[num]) else None,
            "name": nm, "team": tm, "abbr": ab, "rating": rating, "color": color
        })

    if len(roster) < 20:
        base=len(roster)
        for i in range(base,20):
            roster.append({"num": i+1, "name": f"Driver {i+1}", "team": f"Team {chr(65+(i%5))}",
                           "abbr": f"D{i+1}", "rating": None, "color": ""})
    for i,r in enumerate(roster[:20]):
        r["num"]  = r["num"] or (i+1)
        r["abbr"] = r["abbr"] or _abbr_from_name(r["name"])
    return roster[:20]

# ─────────────────────────────────────────────────────────────────────────────
# 그리드(스타팅 포지션)
def build_grid(roster: list[dict]) -> list[dict]:
    # st.session_state["quali_state"]["final_grid"] 우선 사용
    qstate = st.session_state.get("quali_state") or {}
    final_grid = qstate.get("final_grid")
    if isinstance(final_grid, list) and final_grid:
        # 항목: {"name","team","abbr","color"?}
        return final_grid
    # 호환: st.session_state["quali"]["Q3"]["results"] → Q2 → Q1
    qraw = st.session_state.get("quali") or {}
    for key in ("Q3","Q2","Q1"):
        if key in qraw and qraw[key].get("results"):
            return qraw[key]["results"]
    # 폴백: 번호순
    return sorted(
        [{"name":r["name"],"team":r["team"],"abbr":r["abbr"],"color":r.get("color","")} for r in roster],
        key=lambda x: (next((d.get("num",999) for d in roster if d["name"]==x["name"] and d["team"]==x["team"]), 999), x["name"])
    )

# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class DriverSlot:
    name: str
    team: str
    abbr: str
    color: str
    rating: float|None
    img: str

# ─────────────────────────────────────────────────────────────────────────────
def run_main_race():
    st.set_page_config(layout="wide", page_title="Main Race — SVG")

    st.markdown("""
    <style>
      :root, html, body { background:#0b0f1a !important; color:#e5e7eb !important; }
      [data-testid="stAppViewContainer"] { background:#0b0f1a !important; }
      .block-container{ padding-top:0.5rem !important; padding-bottom:0.5rem !important; }
      div[data-testid="stVerticalBlock"]{ border:1px solid rgba(255,255,255,.08); border-radius:12px;
                                          padding:4px !important; margin:4px 0 !important; }
    </style>
    """, unsafe_allow_html=True)

    # 데이터 로딩
    by_id, by_name, color_by_id, color_by_name = load_team_catalog()
    tracks = load_tracks(TRACKS_CSV)
    if not tracks:
        st.error(f"tracks.csv가 없습니다: {TRACKS_CSV}")
        st.stop()

    min_round = min([t["round"] for t in tracks if t["round"] is not None] or [1])
    st.session_state.setdefault("round", min_round)
    round_no = int(st.session_state["round"])
    trk = [t for t in tracks if t["round"] == round_no]
    trk = trk[0] if trk else tracks[0]
    circuit = trk["name"]
    lap_base = float(trk.get("lap_sec") or 90.0)
    total_laps = int(trk.get("total_laps") or 50)

    # SVG
    def find_svg_for_track(track_name: str) -> Path | None:
        if not track_name or not CIRCUIT_DIR.exists(): return None
        cands = list(CIRCUIT_DIR.glob("*.svg"))
        key = re.sub(r"[^a-z0-9]","", track_name.lower())
        for p in cands:
            if re.sub(r"[^a-z0-9]","", p.stem.lower()) == key: return p
        for p in cands:
            if key in re.sub(r"[^a-z0-9]","", p.stem.lower()): return p
        return cands[0] if cands else None

    svg_path = find_svg_for_track(circuit)
    if not svg_path or not svg_path.exists():
        st.error(f"서킷 SVG가 없습니다: circuit/{circuit}.svg")
        st.stop()
    RAW_SVG = svg_path.read_text(encoding="utf-8", errors="ignore")

    # 로스터/플레이어 팀
    roster = load_roster(by_id, color_by_id, color_by_name)
    if not roster:
        st.error("drivers.csv 필요(info/ 또는 data/)")
        st.stop()

    teams_in_roster = sorted({r["team"] for r in roster if r.get("team")})
    default_idx = 0
    sel_from_state = st.session_state.get("team_id")
    if sel_from_state:
        nm = by_id.get(str(sel_from_state))
        if nm and nm in teams_in_roster:
            default_idx = teams_in_roster.index(nm)
    player_team = st.sidebar.selectbox("플레이어 팀", teams_in_roster, index=min(default_idx, max(0, len(teams_in_roster)-1)))
    st.session_state["player_team_last"] = player_team

    # 그리드 구성
    base_order = build_grid(roster)
    grid: list[DriverSlot] = []
    for r in base_order[:20]:
        drv = next((d for d in roster if d["name"]==r["name"] and d["team"]==r["team"]), None)
        color = r.get("color") or (drv.get("color","") if drv else "")
        abbr  = r.get("abbr")  or (drv["abbr"] if drv else _abbr_from_name(r["name"]))
        rating= (float(drv.get("rating")) if (drv and drv.get("rating") is not None) else None)
        grid.append(DriverSlot(r["name"], r["team"], abbr, color, rating, _img_uri(r["name"])))

    # 타이어 이미지
    tire_imgs = {k: _tire_uri(k) for k in ["soft","medium","hard","intermediate","wet"]}

    # PLAN(그룹 페이스 계층)
    rnd = random.Random(88)
    def base_v_from_rating(rt: float|None):
        r = rt if rt is not None else 80.0 + rnd.uniform(-6,6)
        return round(0.96 + (max(60.0, min(100.0, r))-60.0)*(0.16/40.0), 3)

    plan_payload = []
    N = len(grid)
    for idx,slot in enumerate(grid):
        vm = base_v_from_rating(slot.rating)
        # 그룹 스틴트
        if idx < max(4, N//5):      # 선두군
            cut = int(total_laps*0.35)
            stint = [{"to_lap": cut, "compound":"soft", "pace":"Aggressive"},
                     {"to_lap": total_laps, "compound":"medium", "pace":"Standard"}]
        elif idx < max(12, N*3//5): # 중위군
            cut = int(total_laps*0.40)
            stint = [{"to_lap": cut, "compound":"medium", "pace":"Standard"},
                     {"to_lap": total_laps, "compound":"soft", "pace":"Aggressive"}]
        else:                        # 후미군
            cut = int(total_laps*0.55)
            stint = [{"to_lap": cut, "compound":"medium", "pace":"Light"},
                     {"to_lap": total_laps, "compound":"hard", "pace":"Standard"}]
        plan_payload.append({
            "name": slot.name, "team": slot.team, "abbr": slot.abbr,
            "color": slot.color or "", "img": slot.img or "",
            "isPlayer": (slot.team == player_team),
            "base_vmul": vm,
            "stint_plan": stint
        })

    # ─────────────────────────────────────────────────────────────────────────
    # HTML 템플릿 (f-string 아님!)
    HTML_TMPL = r"""
<style>
  :root, html, body { background:#0b0f1a; color:#e5e7eb; }
  #wrap { display:grid; grid-template-columns: 1fr 400px; gap:14px; margin-top:8px; }
  #left { position:relative; background:#0e1117; border:1px solid #1f2937; border-radius:14px; padding:0; }
  #right{ background:#0b0f1a; }

  #stage{ width:100%; height:920px; background:#0e1117; border-radius:10px; box-shadow:0 6px 24px rgba(0,0,0,.35); user-select:none; }

  .muted { color:#94a3b8; font-size:12px; }
  .btn { font-size:12px; padding:6px 10px; border-radius:8px; border:1px solid #334155; background:#0f172a; color:#e5e7eb; cursor:pointer; }
  .btn.primary { background:#0b5cff; border-color:#0b5cff; color:#fff; }

  #hudTop {
    position:absolute; left:14px; top:14px; z-index:5;
    background:rgba(8,12,20,.78); border:1px solid rgba(30,41,59,.9);
    backdrop-filter: blur(4px);
    border-radius:12px; padding:10px; min-width:300px;
  }

  #selPanel {
    position:absolute; right:14px; top:14px; z-index:5;
    background:rgba(8,12,20,.84); border:1px solid rgba(30,41,59,.9);
    backdrop-filter: blur(4px);
    border-radius:12px; padding:12px; min-width:260px; max-width:380px; display:none;
  }
  #selPanel .row1 { display:flex; gap:10px; align-items:center; margin-bottom:8px; }
  #selImg { width:64px; height:64px; object-fit:cover; border-radius:8px; border:1px solid #0b1220; }
  #selTitle { font-weight:800; }
  #selPanel .kv { display:flex; justify-content:space-between; font-variant-numeric:tabular-nums; }
  #selPanel .laps { margin-top:8px; font-size:12px; line-height:1.25; max-height:160px; overflow:auto; }

  #lights {
    position:absolute; left:50%; transform:translateX(-50%);
    top:70px; display:flex; gap:12px; z-index:6; background:rgba(0,0,0,.3);
    padding:8px 10px; border-radius:12px; border:1px solid #1e293b;
  }
  .light { width:26px; height:26px; border-radius:50%; background:#111827; border:2px solid #ef4444; box-shadow:0 0 0 rgba(0,0,0,0); }
  .light.on { background:#ef4444; box-shadow:0 0 18px #ef4444; }

  #dock { margin-top:10px; background:#0b0f1a; border:1px solid #1e293b; border-radius:12px; padding:12px; }
  #playerPane .title { font-weight:800; margin-bottom:6px; }
  #playerPane .grid { display:grid; grid-template-columns: 1fr 1fr; gap:10px; }
  #playerPane .card { display:flex; gap:12px; align-items:flex-start; border:1px solid #1e293b; border-radius:10px; padding:10px; background:#0b1220; }
  #playerPane .card img.avatar { width:64px; height:64px; object-fit:cover; border-radius:8px; border:1px solid #0b1220; }
  #playerPane .line { display:flex; gap:8px; align-items:center; margin-top:6px; flex-wrap:wrap; }
  .tireIcon { width:22px; height:22px; vertical-align:middle; border-radius:4px; border:1px solid #0b1220; }

  .leader { background:#0b1220; border:1px solid #1e293b; border-radius:12px; padding:12px; margin-top:10px; }
  #rows { max-height:640px; overflow-y:auto; padding-right:6px; }
  .row { display:flex; justify-content:space-between; padding:3px 8px; border-radius:8px; margin:2px 0; align-items:center; }
  .row .pos { width:28px; text-align:right; color:#a3e635; font-variant-numeric:tabular-nums; }
  .row .name { flex:1; margin:0 6px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; display:flex; align-items:center; gap:6px; }
  .row .gap { width:210px; text-align:right; color:#e2e8f0; font-variant-numeric:tabular-nums; }

  .selRing { pointer-events:none; display:none; }
</style>

<div id="wrap">
  <div id="left">
    <div id="lights">
      <div class="light" id="L1"></div>
      <div class="light" id="L2"></div>
      <div class="light" id="L3"></div>
      <div class="light" id="L4"></div>
      <div class="light" id="L5"></div>
    </div>

    <div id="hudTop">
      <div style="display:flex; justify-content:space-between; align-items:center; gap:8px;">
        <div class="clock">⏱ <span id="timeText">Grid</span> · Lap <span id="lapText">0/%%TOTAL_LAPS%%</span></div>
        <div class="speed">
          <button class="btn" data-m="1">1×</button>
          <button class="btn" data-m="2">2×</button>
          <button class="btn" data-m="4">4×</button>
          <button class="btn" data-m="10">10×</button>
          <button class="btn" data-m="30">30×</button>
        </div>
      </div>
      <div class="muted" style="margin:4px 0 2px;">그리드 스타트 → 5 레드라이트 → 라이트 아웃!</div>
    </div>

    <div id="selPanel">
      <div class="row1">
        <img id="selImg" src="" alt="">
        <div>
          <div id="selTitle">-</div>
          <div class="muted" id="selTeamSmall">-</div>
        </div>
      </div>
      <div class="kv"><div>상태</div><div id="selMode">-</div></div>
      <div class="kv"><div>타이어</div><div id="selTy">-</div></div>
      <div class="kv"><div>랩/진행</div><div id="selProg">-</div></div>
      <div class="laps" id="selLaps"></div>
    </div>

    <svg id="stage" viewBox="0 0 1200 800">
      <defs><clipPath id="clip"><rect x="0" y="0" width="1200" height="800"/></clipPath></defs>
      <g id="track" clip-path="url(#clip)"></g>
      <g id="actors" clip-path="url(#clip)"></g>
      <circle id="selRing" class="selRing" r="9" stroke="#0b5cff" stroke-width="3" stroke-dasharray="4 4" fill="none"></circle>
      <foreignObject x="0" y="0" width="1" height="1"></foreignObject>
    </svg>

    <div id="dock">
      <div id="playerPane">
        <div class="title">플레이어 드라이버 컨트롤</div>
        <div class="grid" id="playerCards"></div>
      </div>
    </div>
  </div>

  <div id="right">
    <div class="leader">
      <div style="font-weight:700;margin-bottom:6px;">Leaderboard <span id="lbNote" class="muted">· Race Order</span></div>
      <div id="rows"></div>
    </div>
  </div>
</div>

<script>
(function(){
  // 서버에서 주입
  const RAW = %%RAW_SVG%%;
  const PLAN = %%PLAN_JSON%%;
  const LAP_BASE = %%LAP_BASE%%;
  const TOTAL_LAPS = %%TOTAL_LAPS%%;
  const TIRE_IMGS = %%TIRE_IMGS%%;
  const PLAYER_TEAM = %%PLAYER_TEAM%%;

  // 파라미터
  const TRANS_SIM = 0.25;
  const PIT_WAIT_SEC = 2.7;
  const PIT_TRAVEL = 18.0;
  const FUEL_PER_LAP = 1.6;
  const FUEL_FLOW_MAX = 100.0/3600.0;

  const PACE = {
    "Attack":    {speed:1.020, wear:1.40},
    "Aggressive":{speed:1.010, wear:1.18},
    "Standard":  {speed:1.000, wear:1.00},
    "Light":     {speed:0.992, wear:0.86},
    "Conserve":  {speed:0.985, wear:0.74},
  };
  const TIRE = {
    soft:         {gripDry:1.030, wearDry:0.060},
    medium:       {gripDry:1.000, wearDry:0.045},
    hard:         {gripDry:0.980, wearDry:0.035},
    intermediate: {gripDry:0.960, wearDry:0.080},
    wet:          {gripDry:0.930, wearDry:0.120},
  };

  // 런타임
  let SPEED = 1, simT = 0.0, running = false, raceFinished = false;

  const stage=document.getElementById('stage'), gTrack=document.getElementById('track'), gAct=document.getElementById('actors');
  const rows=document.getElementById('rows');
  const timeText=document.getElementById('timeText'), lapText=document.getElementById('lapText');
  const selRing=document.getElementById('selRing');

  const selPanel=document.getElementById('selPanel'), selImg=document.getElementById('selImg');
  const selTitle=document.getElementById('selTitle'), selTeamSmall=document.getElementById('selTeamSmall');
  const selMode=document.getElementById('selMode'), selTy=document.getElementById('selTy');
  const selProg=document.getElementById('selProg'), selLaps=document.getElementById('selLaps');

  document.querySelectorAll('.speed .btn').forEach(b=>{
    b.addEventListener('click', ()=>{ const m=parseFloat(b.getAttribute('data-m')||'1'); if(Number.isFinite(m)) SPEED=m; });
  });

  // SVG 유틸
  function parseSVG(raw){ return (!raw||!raw.trim())?null:new DOMParser().parseFromString(raw, "image/svg+xml"); }
  function getViewBox(doc){ const root=doc.querySelector('svg'); return (root && root.getAttribute('viewBox'))?root.getAttribute('viewBox'):"0 0 1200 800"; }
  function grabPathD(doc,id){ const el=doc.querySelector(`path#${id}`); if(el) return el.getAttribute('d')||''; const any=doc.querySelector('path'); return any?(any.getAttribute('d')||''):''; }
  function nearestS(path,p){ if(!path||!p) return 0; const L=path.getTotalLength(),N=1000; let bestS=0,bestD=1e9; for(let i=0;i<=N;i++){const s=i/N; const q=path.getPointAtLength(s*L); const dx=q.x-p.x,dy=q.y-p.y; const d=dx*dx+dy*dy; if(d<bestD){bestD=d;bestS=s;} } return bestS; }
  function reachedForward(a,b,target){ return (b>=a) ? (target>=a && target<=b) : (target>=a || target<=b); }
  function fmtTime(t){ const mm=Math.floor(t/60); const ss=(t%60).toFixed(1).padStart(4,'0'); return `${mm}:${ss}`; }

  // 법선 포함 좌표/차선
  function ptOnPlus(path,s){
    const L=Math.max(1,path.getTotalLength());
    const c=Math.max(0,Math.min(1,s));
    const P = path.getPointAtLength(c*L);
    const dL=3;
    const P2=path.getPointAtLength(Math.min(L, c*L+dL));
    const tx=P2.x-P.x, ty=P2.y-P.y;
    const mag=Math.hypot(tx,ty)||1;
    const nx=-ty/mag, ny=tx/mag;
    return {x:P.x,y:P.y,nx,ny};
  }
  function placeAtLane(el,lab,p,lane){
    const offset=6*(lane||0);
    const x=p.x+offset*p.nx, y=p.y+offset*p.ny;
    el.setAttribute('transform',`translate(${x},${y})`);
    lab.setAttribute('x',x+8); lab.setAttribute('y',y-8);
  }

  // 트랙
  let sFinish=0, sMainOut=0, sPitStop=0, sPitOut=0, sPitInMain=0.90, sPitInPit=0.02;
  function build(){
    const doc=parseSVG(RAW); if(!doc) return null;
    stage.setAttribute('viewBox', getViewBox(doc));
    const dMainRaw=grabPathD(doc,'main');
    const dPitRaw =grabPathD(doc,'pit');
    gTrack.innerHTML='';
    const pMain=document.createElementNS(stage.namespaceURI,'path');
    const pPit =document.createElementNS(stage.namespaceURI,'path');
    const dMain = dMainRaw || 'M 150,400 C 150,180 1050,180 1050,400 C 1050,620 150,620 150,400 Z';
    const dPit  = dPitRaw  || 'M 220,400 C 220,240 980,240 980,400 C 980,560 220,560 220,400 Z';
    pMain.setAttribute('d', dMain); pPit.setAttribute('d', dPit);
    pMain.setAttribute('fill','none'); pPit.setAttribute('fill','none');
    pMain.setAttribute('stroke','#3b4252'); pMain.setAttribute('stroke-width','4.5');
    pPit .setAttribute('stroke','#7c8596'); pPit .setAttribute('stroke-width','2.0');
    pMain.setAttribute('stroke-linecap','round'); pMain.setAttribute('stroke-linejoin','round');
    pPit .setAttribute('stroke-linecap','round'); pPit .setAttribute('stroke-linejoin','round');
    gTrack.appendChild(pMain); gTrack.appendChild(pPit);

    const fin = doc.querySelector('polyline#finish, line#finish');
    if(fin){
      let x1,y1,x2,y2;
      if (fin.tagName.toLowerCase()==='polyline'){
        const pts=(fin.getAttribute('points')||'').trim().split(/\s+/).map(s=>s.split(',').map(parseFloat));
        if (pts.length>=2){ x1=pts[0][0]; y1=pts[0][1]; x2=pts[1][0]; y2=pts[1][1]; }
      } else { x1=+fin.getAttribute('x1'); y1=+fin.getAttribute('y1'); x2=+fin.getAttribute('x2'); y2=+fin.getAttribute('y2'); }
      const ln=document.createElementNS(stage.namespaceURI,'line');
      ln.setAttribute('x1',x1); ln.setAttribute('y1',y1); ln.setAttribute('x2',x2); ln.setAttribute('y2',y2);
      ln.setAttribute('stroke','#ef4444'); ln.setAttribute('stroke-width','3'); gTrack.appendChild(ln);
      const mid={x:(x1+x2)/2,y:(y1+y2)/2}; sFinish = nearestS(pMain, mid);
    } else { sFinish=0.01; }

    function ptFromMeta(id){ const el=doc.querySelector(`#${id}`); if(!el) return null; const a=(el.getAttribute('data-pt')||'').split(',').map(parseFloat); if(a.length===2 && a.every(Number.isFinite)) return {x:a[0],y:a[1]}; return null; }
    const md = doc.querySelector('metadata'); let meta={}; try{ meta = md ? JSON.parse(md.textContent||"{}") : {}; }catch(e){ meta={}; }
    const mk = {
      pitIn : ptFromMeta('pitIn')  || (meta.pitIn  && meta.pitIn.pts  && meta.pitIn.pts[0])  || null,
      pitOut: ptFromMeta('pitOut') || (meta.pitOut && meta.pitOut.pts && meta.pitOut.pts[0]) || null,
      pitStop:ptFromMeta('pitStop')|| (meta.pitStop&& meta.pitStop.pts&& meta.pitStop.pts[0])|| null
    };
    sPitOut    = mk.pitOut  ? nearestS(pPit, mk.pitOut)  : 0.85;
    sMainOut   = mk.pitOut  ? nearestS(pMain, mk.pitOut) : 0.02;
    sPitStop   = mk.pitStop ? nearestS(pPit, mk.pitStop) : 0.05;
    sPitInMain = mk.pitIn   ? nearestS(pMain, mk.pitIn)  : 0.90;
    sPitInPit  = mk.pitIn   ? nearestS(pPit,  mk.pitIn)  : 0.02;

    return { pMain, pPit };
  }

  // 차량/그리드
  const defaultCols=['#ff6b00','#00a3ff','#ffd400','#5ad469','#c86bff','#ff4d6d','#3bc9db','#fab005','#9b59b6','#2ecc71',
                     '#e67e22','#3498db','#f1c40f','#1abc9c','#e84393','#16a085','#c0392b','#8e44ad','#2980b9','#2ecc71'];
  const cars=[]; let selectedIdx=null;

  function mkCar(info, idx){
    const c=document.createElementNS(stage.namespaceURI,'circle'); c.setAttribute('r','5');  // dot 더 촘촘하게 보이는 사이즈
    const col=(info.color && /^#?[0-9A-Fa-f]{6}$/.test(info.color))?(info.color.startsWith('#')?info.color:'#'+info.color):defaultCols[idx%defaultCols.length];
    c.setAttribute('fill', col); c.setAttribute('stroke','#fff'); c.setAttribute('stroke-width','1.8'); c.classList.add('car'); c.dataset.idx=String(idx);
    const lab=document.createElementNS(stage.namespaceURI,'text'); lab.textContent=(info.abbr||`D${idx+1}`); lab.setAttribute('font-size','9'); lab.setAttribute('fill','#e5e7eb'); lab.classList.add('carLabel'); lab.dataset.idx=String(idx);
    gAct.appendChild(c); gAct.appendChild(lab);
    const comp0 = "soft";
    return {
      ...info, color:col, el:c, lab,
      mode:'grid', s:0, sPit:0, lap:0, dist:0,
      lastCross:null, lastLapTime:null, lapTimes:[],
      compound: comp0, tireLife:1.0, pace:"Standard",
      fuel: 25.0, fuelMix: "Balanced",
      lane: 0,
      otk: { state:'none', until:0, dir:0, rival:null },
      _vmulInst: 1.0,
      base_vmul: parseFloat(info.base_vmul||1.0),
      plan: (info.stint_plan||[]),
      pitTargetS:null, waitUntil:null, wantBox:false
    };
  }

  function syncSelRing(){
    if (selectedIdx === null) { selRing.style.display='none'; return; }
    const car = cars[selectedIdx];
    if (!car) { selRing.style.display='none'; return; }
    selRing.style.display='block';
    const tr = car.el.getAttribute('transform') || 'translate(0,0)';
    selRing.setAttribute('transform', tr);
    selRing.setAttribute('stroke', car.el.getAttribute('fill') || '#0b5cff');
  }

  function renderSelPanel(){
    if (selectedIdx===null) { selPanel.style.display='none'; return; }
    const c = cars[selectedIdx]; if (!c) { selPanel.style.display='none'; return; }
    selPanel.style.display='block';
    selImg.src = c.img || '';
    selTitle.textContent = `#${c.abbr} ${c.name}`;
    selTeamSmall.textContent  = c.team;
    selMode.textContent  = c.mode + (c.wantBox? ' (box req)' : '');
    selTy.textContent    = c.compound.toUpperCase();
    selProg.textContent  = `Lap ${c.lap} · s=${c.s.toFixed(3)}`;
    if (c.lapTimes.length){ selLaps.innerHTML = c.lapTimes.map((x,i)=>`L${i+1}: ${x.toFixed(3)}s`).join('<br/>'); }
    else { selLaps.innerHTML = '<span class="muted">아직 기록 없음</span>'; }
  }

  function showSelection(idx){
    idx = Math.max(0, Math.min(cars.length-1, idx));
    const car = cars[idx]; if (!car) return;
    selectedIdx = idx; renderSelPanel(); syncSelRing();
  }
  gAct.addEventListener('click', (ev)=>{
    const t = ev.target.closest('[data-idx]'); if(!t) return;
    const idx = parseInt(t.getAttribute('data-idx')||'-1',10);
    if (Number.isFinite(idx) && idx>=0) showSelection(idx);
  });

  // 플레이어 카드
  function playerCards(){
    const mount=document.getElementById('playerCards'); if(!mount) return;
    mount.replaceChildren();
    const players = PLAN.filter(p=>p.isPlayer).slice(0,2);
    players.forEach((p)=>{
      const card=document.createElement('div'); card.className='card';
      const img=document.createElement('img'); img.src=p.img||''; img.className='avatar';
      const rbox=document.createElement('div');
      const h=document.createElement('div'); h.style.fontWeight='700'; h.textContent=`#${p.abbr} ${p.name}`;
      const s=document.createElement('div'); s.className='muted'; s.textContent=`${p.team} · v× ${p.base_vmul.toFixed(2)}`;
      const line1=document.createElement('div'); line1.className='line';
      const selTy=document.createElement('select'); ["soft","medium","hard","intermediate","wet"].forEach(k=>{const o=document.createElement('option');o.value=k;o.textContent=k[0].toUpperCase()+k.slice(1);selTy.appendChild(o);}); selTy.value="soft"; const tyIcon=document.createElement('img'); tyIcon.className='tireIcon'; tyIcon.src=TIRE_IMGS[selTy.value]||'';
      const paceSel=document.createElement('select'); ["Attack","Aggressive","Standard","Light","Conserve"].forEach(x=>{const o=document.createElement('option');o.value=x;o.textContent=x;paceSel.appendChild(o);}); paceSel.value="Standard";
      const bGo=document.createElement('button'); bGo.className='btn'; bGo.textContent='Pit Request';
      line1.appendChild(document.createTextNode('타이어')); line1.appendChild(selTy); line1.appendChild(tyIcon);
      line1.appendChild(document.createTextNode('페이스')); line1.appendChild(paceSel);
      line1.appendChild(bGo);
      rbox.appendChild(h); rbox.appendChild(s); rbox.appendChild(line1);
      card.appendChild(img); card.appendChild(rbox); mount.appendChild(card);

      const apply=()=>{ const car=cars.find(c=>c.name===p.name && c.team===p.team); if(!car) return; car.pace=paceSel.value; tyIcon.src=TIRE_IMGS[selTy.value]||''; if(car.mode==='pitStopWait') car.compound=selTy.value; else car.wantBox=true; };
      selTy.addEventListener('change', apply); paceSel.addEventListener('change', apply); bGo.addEventListener('click', ()=>{ const car=cars.find(c=>c.name===p.name && c.team===p.team); if(!car) return; car.wantBox=true; });
    });
  }

  // 스타트 라이트
  function startLights(){
    const Ls=[document.getElementById('L1'),document.getElementById('L2'),document.getElementById('L3'),document.getElementById('L4'),document.getElementById('L5')];
    let idx=0; running=false; simT=0.0;
    const timer = setInterval(()=>{
      if (idx<5){ Ls[idx].classList.add('on'); idx++; }
      else {
        clearInterval(timer);
        setTimeout(()=>{
          Ls.forEach(x=>x.classList.remove('on'));
          running = true; // Race start
        }, 500 + Math.random()*300);
      }
    }, 600);
  }

  // 빌드
  let pMain=null, pPit=null;
  function buildAll(){
    const built=build(); if(!built) return false;
    pMain=gTrack.querySelector('path:nth-of-type(1)');
    pPit =gTrack.querySelector('path:nth-of-type(2)');
    gAct.innerHTML=''; cars.length=0;

    // 그리드 정렬(피니시 라인 근처 뒤쪽으로 줄세우기)
    for(let i=0;i<PLAN.length;i++){
      const car=mkCar(PLAN[i], i);
      const s0 = (sFinish - 0.010*(i)) % 1; car.s = (s0<0? s0+1 : s0);
      const p = ptOnPlus(pMain, car.s);
      placeAtLane(car.el, car.lab, p, 0);
      cars.push(car);
    }

    playerCards();
    startLights();
    return true;
  }

  // 루프
  let anim=null, tPrev=0;
  function loop(now){
    if(!tPrev) tPrev=now;
    const dt=(now-tPrev)/1000; tPrev=now;
    const dtSim = dt * SPEED;

    if (running){ simT += dtSim; timeText.textContent = fmtTime(simT); } else { timeText.textContent = "Grid"; }
    if (!pMain || !pPit){ anim=requestAnimationFrame(loop); return; }

    const vMainBase = 1 / Math.max(0.1, LAP_BASE);
    const vPit = 1 / Math.max(0.5, PIT_TRAVEL);

    // 업데이트
    for(const car of cars){
      if (car.mode==='grid'){
        const p = ptOnPlus(pMain, car.s);
        placeAtLane(car.el, car.lab, p, 0);
        if (running){ car.mode='main'; car.lastCross=null; }
        continue;
      }
      if (car.mode==='pit'){
        const p=ptOnPlus(pPit, car.sPit); placeAtLane(car.el, car.lab, p, 0);
        continue;
      }
      if (car.mode==='pitGo'){
        const before=car.sPit;
        car.sPit=(car.sPit + vPit*dtSim)%1;
        const p=ptOnPlus(pPit, car.sPit); placeAtLane(car.el, car.lab, p, 0);
        const targetS = car.pitTargetS ?? 0.85;
        if (reachedForward(before, car.sPit, targetS)){
          if (Math.abs(targetS - 0.85) < 1e-3){
            const a=ptOnPlus(pPit, 0.85), b=ptOnPlus(pMain, 0.02);
            car.mode='toMain'; car.fx={t0Sim: simT, durSim: TRANS_SIM, ax:a.x, ay:a.y, bx:b.x, by:b.y};
          } else {
            car.mode='pitStopWait'; car.waitUntil = simT + PIT_WAIT_SEC;
          }
        }
        continue;
      }
      if (car.mode==='pitStopWait'){
        const p=ptOnPlus(pPit, car.sPit); placeAtLane(car.el, car.lab, p, 0);
        if (simT >= (car.waitUntil||0)){ car.mode='pit'; car.tireLife = 1.0; }
        continue;
      }
      if (car.mode==='toMain'){
        const w=Math.max(0,Math.min(1,(simT - car.fx.t0Sim)/car.fx.durSim));
        const x=car.fx.ax*(1-w)+car.fx.bx*w, y=car.fx.ay*(1-w)+car.fx.by*w;
        car.el.setAttribute('transform',`translate(${x},${y})`); car.lab.setAttribute('x',x+8); car.lab.setAttribute('y',y-8);
        if(w>=1){ car.mode='main'; car.s=0.02; }
        continue;
      }
      if (car.mode==='toPit'){
        const w=Math.max(0,Math.min(1,(simT - car.fx.t0Sim)/car.fx.durSim));
        const x=car.fx.ax*(1-w)+car.fx.bx*w, y=car.fx.ay*(1-w)+car.fx.by*w;
        car.el.setAttribute('transform',`translate(${x},${y})`); car.lab.setAttribute('x',x+8); car.lab.setAttribute('y',y-8);
        if(w>=1){ car.mode='pitGo'; car.sPit=0.02; car.pitTargetS = 0.05; }
        continue;
      }

      // === main 주행 ===
      const paceFx = PACE[car.pace] || PACE.Standard;
      const tDat = TIRE[car.compound] || TIRE.soft;

      const groupBias = (car.base_vmul || 1.0);
      const perLapNoise = 1.0 + ( (Math.sin((car.lap + car.s)*11.0 + car.base_vmul*7.7) ) * 0.004 );
      const vmul = Math.max(0.90, Math.min(1.25, groupBias * paceFx.speed * tDat.gripDry * perLapNoise * (1 - 0.004*car.fuel)));
      car._vmulInst = vmul;

      const before=car.s;
      car.s = (car.s + vMainBase*vmul*dtSim) % 1;

      const desiredRate = (FUEL_PER_LAP / LAP_BASE);
      const actualRate  = Math.min(FUEL_FLOW_MAX, desiredRate);
      car.fuel = Math.max(0, car.fuel - actualRate * dtSim);

      const ds = (car.s - before + 1) % 1;
      const wearLap = tDat.wearDry * (PACE[car.pace]?.wear || 1.0);
      car.tireLife = Math.max(0, car.tireLife - wearLap * ds);

      const sLine = (sFinish || 0.01);
      if (reachedForward(before, car.s, sLine)){
        car.lap += 1;
        if (car.lastCross === null){ car.lastCross = simT; }
        else { const lapTime = simT - car.lastCross; car.lastCross = simT; car.lastLapTime = lapTime; car.lapTimes.push(lapTime); }
        if (car.lap >= TOTAL_LAPS) { raceFinished = true; running = false; }
      }

      const plan = car.plan || [];
      const stint = plan.find(st => (car.lap < (st.to_lap||TOTAL_LAPS+1)));
      if (stint) {
        car.pace = stint.pace || car.pace;
        if (car.lap+0.0001 >= (stint.to_lap||9999) || car.tireLife<0.12) { car.wantBox = true; }
        if (car.mode==='pitStopWait') { car.compound = stint.compound || car.compound; }
      }
      if (car.wantBox && reachedForward(before, car.s, 0.90)) {
        const a=ptOnPlus(pMain, 0.90), b=ptOnPlus(pPit, 0.02);
        car.mode='toPit'; car.fx={t0Sim: simT, durSim: TRANS_SIM, ax:a.x, ay:a.y, bx:b.x, by:b.y};
        car.wantBox=false;
      }

      const p=ptOnPlus(pMain, car.s); placeAtLane(car.el, car.lab, p, car.lane);
    }

    // === 오버테이크 FSM ===
    const onMain = cars.filter(c => c.mode==='main').slice().sort((a,b)=> (b.lap+b.s) - (a.lap+a.s));
    for (let i=0; i<onMain.length-1; i++){
      const front=onMain[i], back=onMain[i+1];
      if (front.otk.state!=='none' || back.otk.state!=='none') continue;
      if (front.lap !== back.lap) continue;
      let gap = (front.s - back.s); if (gap < 0) gap += 1.0;
      if (gap > 0 && gap < 0.018 && (back._vmulInst||1.0) > (front._vmulInst||1.0) + 0.015){
        const dir = (Math.random()<0.5 ? -1 : +1);
        back.otk = { state:'prep', until: simT + 0.8, dir, rival: `${front.name}|${front.team}` };
        back.lane = dir;
      }
    }
    for (const car of onMain){
      if (car.otk.state==='none') continue;
      const rival = cars.find(c => `${c.name}|${c.team}`===car.otk.rival);
      const ahead = rival && ( (car.lap + car.s) > (rival.lap + rival.s) );
      if (car.otk.state==='prep'){
        if (simT >= car.otk.until){ car.otk.state='side'; car.otk.until = simT + 1.6; }
      } else if (car.otk.state==='side'){
        car.s = (car.s + 0.0022*SPEED) % 1;
        if (ahead || simT >= car.otk.until){ car.otk.state='merge'; car.otk.until = simT + 0.7; }
      } else if (car.otk.state==='merge'){
        if (simT >= car.otk.until){ car.lane = 0; car.otk={state:'none', until:0, dir:0, rival:null}; }
        else { const w = 1 - Math.max(0, Math.min(1, (car.otk.until - simT)/0.7)); car.lane = car.otk.dir * (1 - w); }
      }
    }
    for (const car of cars){
      if (car.mode==='main'){ const p=ptOnPlus(pMain, car.s); placeAtLane(car.el, car.lab, p, car.lane); }
      else if (car.mode==='pit' || car.mode==='pitGo' || car.mode==='pitStopWait'){ const p=ptOnPlus(pPit, car.sPit); placeAtLane(car.el, car.lab, p, 0); }
    }

    // 리더보드(랩/거리)
    const ordered = cars.slice().sort((a,b)=> (b.lap - a.lap) || (b.s - a.s));
    rows.innerHTML = ordered.map((c,i)=>{
      const pill = c.color ? c.color : '#334155';
      const last = (c.lastLapTime==null ? '—' : `${c.lastLapTime.toFixed(3)}s`);
      return `<div class="row" style="background:rgba(51,65,85,.25); border-left:4px solid ${pill}">
        <div class="pos">${String(i+1).padStart(2,' ')}</div>
        <div class="name"><b>${c.abbr}</b> <span class="muted">(${c.lap}/${TOTAL_LAPS})</span></div>
        <div class="gap">L:${last}</div>
      </div>`;
    }).join("");

    const lead = ordered[0]; lapText.textContent = `${lead?lead.lap:0}/${TOTAL_LAPS}`;

    renderSelPanel(); syncSelRing();

    if (raceFinished){ /* TODO: 결과 저장 및 다음 페이지 전환 훅 */ }

    requestAnimationFrame(loop);
  }

  // 시작
  function init(){
    if (!buildAll()) return;
    let anim=null; if(anim) cancelAnimationFrame(anim);
    requestAnimationFrame(loop);
  }
  init();
})();
</script>
"""

    # 치환
    html = (HTML_TMPL
            .replace("%%RAW_SVG%%", json.dumps(RAW_SVG))
            .replace("%%PLAN_JSON%%", json.dumps(plan_payload, ensure_ascii=False))
            .replace("%%LAP_BASE%%", f"{lap_base:.6f}")
            .replace("%%TOTAL_LAPS%%", str(total_laps))
            .replace("%%TIRE_IMGS%%", json.dumps({k:(v or "") for k,v in tire_imgs.items()}))
            .replace("%%PLAYER_TEAM%%", json.dumps(player_team))
            )

    st.components.v1.html(html, height=1320, scrolling=False)

# 실행
if __name__ == "__main__":
    run_main_race()
