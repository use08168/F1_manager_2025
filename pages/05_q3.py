# pages/05_q3.py
# -*- coding: utf-8 -*-
from __future__ import annotations

# ─────────────────────────────────────────────────────────────────────────────
# Q3 전용 독립 실행 페이지
# - Q2 상위 10명만 참가
# - 종료 시 Q1(16~20) + Q2(11~15) + Q3(1~10) 결합하여 본선 그리드 확정
# - 우리팀이 Q3에 0명이면: Q3를 빠른 오프스크린 시뮬로 계산 → 바로 본선으로 이동
# ─────────────────────────────────────────────────────────────────────────────
import re, json, base64, random, os
from pathlib import Path
from dataclasses import dataclass, field
from datetime import datetime
import streamlit as st
import pandas as pd

# ===================== 세션/경로 설정 =====================
SESSION       = "Q3"
DURATION_MIN  = 12
MAIN_PAGE     = "pages/06_main_race.py"

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
SAVE_ROOT   = DATA_DIR / "saves"
CIRCUIT_DIR = ROOT / "circuit"

DRIVER_IMG_DIRS = [ROOT/"driver_image", ROOT/"images/drivers"]
TIRE_IMG_DIRS   = [ROOT/"tire", ROOT/"tires", ROOT/"images/tires"]

DRIVERS_CSV_INFO = INFO_DIR / "drivers.csv"
DRIVERS_CSV_DATA = DATA_DIR / "drivers.csv"
TEAMS_CSV_INFO   = INFO_DIR / "teams.csv"
TEAMS_CSV_DATA   = DATA_DIR / "teams.csv"
TRACKS_CSV       = (INFO_DIR/"tracks.csv") if (INFO_DIR/"tracks.csv").exists() else (DATA_DIR/"tracks.csv")
CALIB_CSV        = INFO_DIR / "circuit_calibration.csv"

# ===================== 유틸/로드 =====================
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
    b64 = base64.b64encode(b).decode("ascii")
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
            b64 = base64.b64encode(png.read_bytes()).decode("ascii")
            return f"data:image/png;base64,{b64}"
    return ""

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
    out=[]
    for _,r in df.iterrows():
        out.append({"name": str(r[name]).strip(),
                    "round": int(r[rd]) if rd and pd.notna(r[rd]) else None,
                    "lap_sec": float(r[lap]) if lap and pd.notna(r[lap]) else None})
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

def load_calibration(csv: Path):
    if not csv.exists(): return []
    df = pd.read_csv(csv)
    cols = {c.lower(): c for c in df.columns}
    out=[]
    for _,r in df.iterrows():
        g=lambda k: r[cols[k]] if k in cols and pd.notna(r[cols[k]]) else None
        out.append({"file":g("file"),"circuit":g("circuit"),
                    "lap_sec_csv": float(g("lap_sec_csv")) if g("lap_sec_csv") else None,
                    "pit_travel_sec": float(g("pit_travel_sec")) if g("pit_travel_sec") else None})
    return out

def match_calib(calibs, circuit_name:str):
    def slug(s): return re.sub(r"[^a-z0-9]","", (s or "").strip().lower())
    sc = slug(circuit_name)
    for c in calibs:
        nm = (c.get("circuit") or Path(str(c.get("file") or "")).stem)
        if slug(nm) == sc: return c
    return {}

def find_svg_for_track(track_name: str) -> Path | None:
    if not track_name or not CIRCUIT_DIR.exists(): return None
    cands = list(CIRCUIT_DIR.glob("*.svg"))
    key = re.sub(r"[^a-z0-9]","", track_name.lower())
    for p in cands:
        if re.sub(r"[^a-z0-9]","", p.stem.lower()) == key: return p
    for p in cands:
        if key in re.sub(r"[^a-z0-9]","", p.stem.lower()): return p
    return cands[0] if cands else None

# ===================== 날씨(LLM + 폴백) =====================
WEATHER_SCHEMA = {
  "name":"quali_weather",
  "schema":{
    "type":"object","additionalProperties":False,
    "properties":{
      "version":{"type":"string"},
      "circuit":{"type":"string"},
      "session":{"type":"string"},
      "air_temp_c":{"type":"number"},
      "track_temp_c":{"type":"number"},
      "rain_prob":{"type":"number","minimum":0,"maximum":1},
      "rain_intensity":{"type":"number","minimum":0,"maximum":1},
      "wetness":{"type":"number","minimum":0,"maximum":1},
      "grip_base":{"type":"number","minimum":0.6,"maximum":1.05}
    },
    "required":["circuit","session","air_temp_c","track_temp_c","rain_prob","rain_intensity","wetness","grip_base"]
  }
}

def prompt_weather(circuit:str, session:str):
    sys_p = "You are an F1 race engineer meteorologist. Output ONLY JSON that follows the provided JSON schema."
    usr_p = (
      f"Circuit: {circuit}\nSession: {session}\n"
      "Return air_temp_c, track_temp_c, rain_prob (0-1), rain_intensity (0-1), wetness (0-1), grip_base (0.6-1.05)."
    )
    return sys_p, usr_p

def get_weather_for_circuit(circuit:str, session:str):
    try:
        from f1sim.ai.llm_client import ask_llm_json
        sys_p, usr_p = prompt_weather(circuit, session)
        js = ask_llm_json(WEATHER_SCHEMA, sys_p, usr_p, temperature=0.2)
        return js
    except Exception:
        rnd = random.Random(hash(circuit)%10_000)
        wet_round = rnd.random() < 0.25
        rain_prob = 0.05 + (0.55 if wet_round else 0.0)
        rain_int  = 0.2  if wet_round else 0.0
        wetness   = min(1.0, rain_prob * rain_int * 1.5)
        return {
            "version":"0.1","circuit":circuit,"session":session,
            "air_temp_c": 22 + rnd.uniform(-4,6),
            "track_temp_c": 30 + rnd.uniform(-6,10),
            "rain_prob": rain_prob, "rain_intensity": rain_int,
            "wetness": wetness, "grip_base": 0.97 + rnd.uniform(-0.03,0.04)
        }

# ===================== AI 계획(안전 보정) =====================
def get_ai_plan(session, circuit, duration_sec, drivers, player_team, lap_base):
    def clamp(x, lo, hi):
        return max(lo, min(hi, x))

    others = [d for d in drivers if d.get("team") != player_team]
    if not others:
        return []

    try:
        from f1sim.ai.llm_client import ask_llm_json
        AI_PLAN_SCHEMA = {
            "name": "quali_ai_plan",
            "schema": {
                "type": "object", "additionalProperties": False,
                "properties": {
                    "version": {"type": "string"},
                    "session": {"type": "string", "enum": ["Q1", "Q2", "Q3"]},
                    "circuit": {"type": "string"},
                    "duration_sec": {"type": "number", "minimum": 300, "maximum": 1200},
                    "plans": {
                        "type": "array", "items": {
                            "type": "object", "additionalProperties": False,
                            "properties": {
                                "name": {"type": "string"},
                                "team": {"type": "string"},
                                "base_vmul": {"type": "number", "minimum": 0.96, "maximum": 1.12},
                                "runs": {"type": "array", "items": {
                                    "type": "object", "additionalProperties": False,
                                    "properties": {
                                        "start_sec": {"type": "number", "minimum": 0, "maximum": 1200},
                                        "laps": {"type": "integer", "minimum": 1, "maximum": 6},
                                        "timed_laps": {"type": "array", "items": {"type": "integer", "minimum": 1, "maximum": 6}},
                                    },
                                    "required": ["start_sec", "laps", "timed_laps"]
                                }}
                            },
                            "required": ["name", "team", "base_vmul", "runs"]
                        }
                    }
                },
                "required": ["version", "session", "circuit", "duration_sec", "plans"]
            }
        }
        lines = "\n".join([f"- {d.get('name')} ({d.get('team')})" for d in others])
        sys_p = "You are an F1 race engineer. Output ONLY JSON that follows the provided JSON schema."
        usr_p = (
            f"Session: {session}\nCircuit: {circuit}\nDuration(sec): {duration_sec}\n"
            f"Ref lap(sec): {float(lap_base):.3f}\nDrivers (exclude player's team):\n{lines}\n"
            "- Each driver makes 1–3 runs; after last hot lap do in-lap and box.\n"
            "- Vary pace: warm-up(0.95×) → push(1.05×) on timed laps. Consider driver rating and team strength."
        )
        js = ask_llm_json(AI_PLAN_SCHEMA, sys_p, usr_p, temperature=0.25) or {}
        raw_plans = js.get("plans") or []
        valid = {(d.get("name"), d.get("team")) for d in others}
        out=[]
        for p in raw_plans:
            if (p.get("name"), p.get("team")) not in valid: 
                continue
            try:
                base = float(p.get("base_vmul", 1.0)); base = clamp(base, 0.96, 1.12)
            except Exception:
                base = 1.0
            runs=[]
            for r in (p.get("runs") or []):
                try:
                    stt  = float(r.get("start_sec", 0.0)); stt = clamp(stt, 0, max(0, duration_sec-60))
                    laps = int(r.get("laps", 3));         laps = int(clamp(laps, 1, 6))
                    tl   = r.get("timed_laps") or [2]
                    tls  = sorted({int(x) for x in tl if 1 <= int(x) <= laps}) or ([2] if laps>=2 else [1])
                    runs.append({"start_sec": stt, "laps": laps, "timed_laps": tls})
                except Exception:
                    continue
            if not runs:
                runs = [{"start_sec": 30.0, "laps": 3, "timed_laps": [2]}]
            out.append({"name": p.get("name"), "team": p.get("team"), "base_vmul": float(base), "runs": runs})
        if out:
            return out
    except Exception:
        pass

    # 폴백
    rnd = random.Random(hash((session, circuit, duration_sec)) & 0xffffffff)
    out=[]
    for d in others:
        rating = d.get("rating")
        if rating is None:
            rating = 82.0 + rnd.uniform(-4,4)
        try:
            rating = float(rating)
        except Exception:
            rating = 82.0
        base_v = 0.99 + (max(60.0, min(100.0, rating))-60.0)*(0.10/40.0)
        base_v = float(max(0.96, min(1.12, base_v)))
        t0 = rnd.uniform(10, 80)
        t1 = t0 + rnd.uniform(180, 320)
        t1 = max(0.0, min(float(duration_sec-60), float(t1)))
        runs=[{"start_sec": float(t0), "laps":3, "timed_laps":[2]},
              {"start_sec": float(t1), "laps":3, "timed_laps":[2]}]
        out.append({"name": d.get("name"), "team": d.get("team"), "base_vmul": base_v, "runs": runs})
    return out

# ===================== 저장소/그리드 구성 =====================
def ensure_save_dir() -> Path:
    if "save_dir" in st.session_state and st.session_state["save_dir"]:
        p = Path(st.session_state["save_dir"])
        p.mkdir(parents=True, exist_ok=True)
        return p
    SAVE_ROOT.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("run_%Y%m%d_%H%M%S")
    p = SAVE_ROOT / ts
    p.mkdir(parents=True, exist_ok=True)
    st.session_state["save_dir"] = str(p)
    return p

def persist_quali_result(session_name: str, payload: dict):
    st.session_state.setdefault("quali", {})
    st.session_state["quali"][session_name] = payload
    save_dir = ensure_save_dir()
    out = save_dir / f"quali_{session_name}.json"
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(out)

def _sorted_by_best(res_list: list[dict]) -> list[dict]:
    return sorted(res_list, key=lambda x: (9999.0 if x.get("best") in (None, "") else float(x.get("best"))))

def _mk_entry(i:int, r:dict)->dict:
    return {"pos": i, "name": r["name"], "team": r["team"], "abbr": r.get("abbr",""), "best": r.get("best")}

def compute_and_store_main_grid():
    """Q1/Q2/Q3 결과를 결합해 본선 그리드를 만들어 세션/파일에 저장."""
    quali = st.session_state.get("quali") or {}
    q1 = quali.get("Q1") or {}
    q2 = quali.get("Q2") or {}
    q3 = quali.get("Q3") or {}
    if not (q1.get("results") and q2.get("results") and q3.get("results")):
        return None

    r1 = _sorted_by_best(q1["results"])
    r2 = _sorted_by_best(q2["results"])
    r3 = _sorted_by_best(q3["results"])

    # Q1: 하위 5 → 그리드 16..20
    tail_q1 = r1[15:20]
    # Q2: 하위 5 → 그리드 11..15
    tail_q2 = r2[10:15]
    # Q3: 상위 10 → 그리드 1..10
    top_q3  = r3[:10]

    grid = []
    # 1..10
    for i, r in enumerate(top_q3, start=1):
        grid.append(_mk_entry(i, r))
    # 11..15
    for i, r in enumerate(tail_q2, start=11):
        grid.append(_mk_entry(i, r))
    # 16..20
    for i, r in enumerate(tail_q1, start=16):
        grid.append(_mk_entry(i, r))

    # 세션 저장 + 파일 저장
    st.session_state.setdefault("quali_state", {})
    st.session_state["quali_state"]["grid_main"] = grid
    save_dir = ensure_save_dir()
    (save_dir / "grid_main.json").write_text(json.dumps(grid, ensure_ascii=False, indent=2), encoding="utf-8")
    return grid

# 빠른 오프스크린 Q3 계산(우리팀이 Q3에 없을 때)
def quick_simulate_q3(roster10: list[dict], lap_base: float, env: dict) -> dict:
    rnd = random.Random(hash(("Q3_quick", env.get("grip_base",1.0), lap_base)) & 0xffffffff)
    # 팀/드라이버 스킬 기반으로 약간 빠르게
    out=[]
    for d in roster10:
        rating = d.get("rating") or 85.0
        try: rating = float(rating)
        except: rating = 85.0
        # 낮을수록 빠른 타임
        base = lap_base
        # 그립/온도 등 약간 반영
        grip = float(env.get("grip_base", 0.97))
        wet  = float(env.get("wetness", 0.0))
        env_mul = (1.0 / max(0.9, min(1.05, grip))) * (1.02 if wet>0.3 else 1.0)
        skill_mul = 1.0 - (max(60.0, min(100.0, rating)) - 80.0) * 0.0025
        noise = 1.0 + rnd.uniform(-0.006, 0.010)
        best = base * env_mul * skill_mul * noise
        out.append({"name":d["name"], "team":d["team"], "abbr":d.get("abbr",""),
                    "best": round(float(best), 3), "laps":[round(float(best),3)], "compound":"soft"})
    out = _sorted_by_best(out)
    return {
        "session": "Q3",
        "duration_sec": int(DURATION_MIN*60),
        "laps_ref_sec": float(lap_base),
        "env": env,
        "results": out
    }

# ===================== 실행 =====================
@dataclass
class DriverPlan:
    name: str
    team: str
    abbr: str
    color: str
    img: str
    base_vmul: float
    is_player: bool
    runs: list[dict] = field(default_factory=list)

def run_session_q3():
    st.set_page_config(layout="wide", page_title=f"{SESSION} — Qualifying")

    # 최신 API 사용
    qp = st.query_params
    if "quali_result_b64" in qp:
        # JS가 넘겨준 Q3 결과 수신 → 저장 → 그리드 완성 → 본선 이동
        try:
            b64 = qp.get("quali_result_b64", "")
            js = json.loads(base64.b64decode(b64.encode("ascii")).decode("utf-8"))
            persist_quali_result(SESSION, js)
        except Exception as e:
            st.warning(f"결과 저장 실패: {e}")
        finally:
            st.query_params.clear()

        grid = compute_and_store_main_grid()
        if grid:
            try:
                st.switch_page(MAIN_PAGE)
                return
            except Exception:
                st.success("본선 그리드를 구성했습니다. 사이드바에서 06_main_race.py로 이동하세요.")
        # 어떤 이유로 실패해도 아래 UI가 뜨도록 계속 진행

    # 다크 UI 약간
    st.markdown("""
    <style>
      :root, html, body { background:#0b0f1a !important; color:#e5e7eb !important; }
      [data-testid="stAppViewContainer"] { background:#0b0f1a !important; }
      .block-container{ padding-top:0.5rem !important; padding-bottom:0.5rem !important; }
      div[data-testid="stVerticalBlock"]{ border:1px solid rgba(255,255,255,.08); border-radius:12px;
                                          padding:4px !important; margin:4px 0 !important; }
    </style>
    """, unsafe_allow_html=True)

    # 팀/트랙/보정
    by_id, by_name, color_by_id, color_by_name = load_team_catalog()
    tracks = load_tracks(TRACKS_CSV)
    if not tracks:
        st.error(f"tracks.csv를 찾지 못했거나 비어 있습니다: {TRACKS_CSV}")
        st.stop()
    min_round = min([t["round"] for t in tracks if t["round"] is not None] or [1])
    st.session_state.setdefault("round", min_round)
    round_no = int(st.session_state["round"])
    trk = [t for t in tracks if t["round"] == round_no]
    trk = trk[0] if trk else tracks[0]
    circuit = trk["name"]

    svg_path = find_svg_for_track(circuit)
    if not svg_path or not svg_path.exists():
        st.error(f"서킷 SVG가 없습니다: circuit/{circuit}.svg")
        st.stop()
    RAW_SVG = svg_path.read_text(encoding="utf-8", errors="ignore")
    calibs = load_calibration(CALIB_CSV)
    calib  = match_calib(calibs, circuit)
    lap_base = float(calib.get("lap_sec_csv") or trk.get("lap_sec") or 90.0)
    pit_travel = float(calib.get("pit_travel_sec") or 16.0)

    # 날씨/노면
    weather = get_weather_for_circuit(circuit, SESSION)
    env = {
        "air_temp_c": float(weather.get("air_temp_c", 22.0)),
        "track_temp_c": float(weather.get("track_temp_c", 30.0)),
        "rain_prob": float(weather.get("rain_prob", 0.0)),
        "rain_intensity": float(weather.get("rain_intensity", 0.0)),
        "wetness": float(weather.get("wetness", 0.0)),
        "grip_base": float(weather.get("grip_base", 0.97)),
    }

    # 전체 로스터
    roster = load_roster(by_id, color_by_id, color_by_name)
    if not roster:
        st.error("drivers.csv 필요")
        st.stop()

    # 플레이어 팀 (사이드바)
    teams_in_roster = sorted({r["team"] for r in roster if r.get("team")})
    default_idx = 0
    sel_from_state = st.session_state.get("team_id")
    if sel_from_state:
        nm = by_id.get(str(sel_from_state))
        if nm and nm in teams_in_roster:
            default_idx = teams_in_roster.index(nm)
    player_team = st.sidebar.selectbox("플레이어 팀", teams_in_roster, index=min(default_idx, max(0, len(teams_in_roster)-1)))
    st.session_state["player_team_last"] = player_team

    # Q2 → Q3 참가자(10명) 구성
    st.session_state.setdefault("quali_state", {})
    qstate = st.session_state["quali_state"]
    adv_q3 = qstate.get("advancers_Q3")

    if not adv_q3:
        q2res = (st.session_state.get("quali") or {}).get("Q2")
        if q2res and isinstance(q2res.get("results"), list):
            res = q2res["results"]
            res_sorted = _sorted_by_best(res)
            adv_q3 = [(r["name"], r["team"]) for r in res_sorted[:10]]
            qstate["advancers_Q3"] = adv_q3
        else:
            # 폴백: 로스터 앞에서 10명
            adv_q3 = [(r["name"], r["team"]) for r in roster[:10]]
            qstate["advancers_Q3"] = adv_q3

    # 명단으로 로스터 필터
    allowed = set(adv_q3)
    roster_q3 = [r for r in roster if (r["name"], r["team"]) in allowed]

    # 우리팀 드라이버가 Q3에 0명이라면 → 오프스크린 Q3 계산 후 그리드 확정/본선 전환
    my_in_q3 = [r for r in roster_q3 if r["team"] == player_team]
    if len(my_in_q3) == 0:
        # 빠른 Q3 결과 생성/저장
        q3quick = quick_simulate_q3(roster_q3, lap_base, env)
        persist_quali_result("Q3", q3quick)
        grid = compute_and_store_main_grid()
        if grid:
            st.info("우리팀이 Q3에 진출하지 못해 Q3를 빠르게 계산했습니다. 본선으로 이동합니다.")
            try:
                st.switch_page(MAIN_PAGE)
                return
            except Exception:
                st.success("본선 그리드를 구성했습니다. 사이드바에서 06_main_race.py로 이동하세요.")
        # 여기서 실패하면 아래 인터랙티브 UI로 계속

    # 내 드라이버(최대 2명)
    my_drivers = sorted([d for d in roster_q3 if d["team"] == player_team], key=lambda x: (x.get("num") or 999))[:2]

    # AI 플랜
    duration_sec = int(DURATION_MIN * 60)
    ai_plans = get_ai_plan(SESSION, circuit, duration_sec, roster_q3, player_team, lap_base)
    map_ai = {(p["name"], p["team"]): p for p in ai_plans}

    # 타이어 이미지
    tire_imgs = {k: _tire_uri(k) for k in ["soft","medium","hard","intermediate","wet"]}

    # PLAN 구성
    @dataclass
    class _DP:
        name: str; team: str; abbr: str; color: str; img: str; base_vmul: float; is_player: bool; runs: list

    plans = []
    rnd = random.Random(42)
    for d in my_drivers:
        vm = 1.0 + (0.02 if (d.get("rating") and float(d["rating"])>=90) else 0.0)
        plans.append(_DP(d["name"], d["team"], d["abbr"], d["color"] or "", _img_uri(d["name"]), vm, True, runs=[]))
    for d in roster_q3:
        if d["team"] == player_team: 
            continue
        p = map_ai.get((d["name"], d["team"]))
        vm = float(p["base_vmul"]) if p else (1.0 + rnd.uniform(-0.02, 0.02))
        rr = list(p["runs"]) if p else [{"start_sec": rnd.uniform(10, 80), "laps":3, "timed_laps":[2]},
                                        {"start_sec": rnd.uniform(180, 300), "laps":3, "timed_laps":[2]}]
        plans.append(_DP(d["name"], d["team"], d["abbr"], d["color"] or "", _img_uri(d["name"]), vm, False, runs=rr))

    # 레이아웃
    L, R = st.columns([0.66, 0.34])

    # ============ 왼쪽(트랙 + 컨트롤 + 종료) ============
    with L:
        html = r"""
<style>
  :root, html, body { background:#0b0f1a; color:#e5e7eb; }
  #wrap { display:grid; grid-template-columns: 1fr 420px; gap:14px; margin-top:8px; }
  #left { position:relative; background:#0e1117; border:1px solid #1f2937; border-radius:14px; padding:0; }
  #right{ background:#0b0f1a; }
  #stage{ width:100%; height:900px; background:#0e1117; border-radius:10px; box-shadow:0 6px 24px rgba(0,0,0,.35); user-select:none; }
  #dock { margin-top:10px; background:#0b0f1a; border:1px solid #1e293b; border-radius:12px; padding:12px; }
  .muted { color:#94a3b8; font-size:12px; }
  .row { display:flex; justify-content:space-between; padding:2px 0; font-variant-numeric:tabular-nums; }
  .row .pos { width:24px; text-align:right; color:#a3e635; }
  .row .name { flex:1; margin:0 6px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; display:flex; align-items:center; gap:6px; }
  .row .gap { width:210px; text-align:right; color:#e2e8f0; }
  .btn { font-size:12px; padding:6px 10px; border-radius:8px; border:1px solid #334155; background:#0f172a; color:#e5e7eb; cursor:pointer; }
  .btn.primary { background:#0b5cff; border-color:#0b5cff; color:#fff; }
  select, .opt { background:#0b1220; color:#e5e7eb; border:1px solid #334155; border-radius:8px; padding:6px 8px; font-size:12px; }
  .leader { background:#0b1220; border:1px solid #1e293b; border-radius:12px; padding:12px; margin-top:10px; }
  .clock { font-weight:700; font-size:16px; letter-spacing:0.5px; }
  .selRing { pointer-events:none; display:none; }
  #rows { max-height:600px; overflow-y:auto; padding-right:6px; }
  .tireMini { width:18px; height:18px; border-radius:4px; border:1px solid #0b1220; }

  #hudTop {
    position:absolute; left:14px; top:14px; z-index:5;
    background:rgba(8,12,20,.78); border:1px solid rgba(30,41,59,.9);
    backdrop-filter: blur(4px);
    border-radius:12px; padding:10px; min-width:280px;
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

  #playerPane .title { font-weight:800; margin-bottom:6px; }
  #playerPane .grid { display:grid; grid-template-columns: 1fr 1fr; gap:10px; }
  #playerPane .card { display:flex; gap:12px; align-items:flex-start; border:1px solid #1e293b; border-radius:10px; padding:10px; background:#0b1220; }
  #playerPane .card img.avatar { width:72px; height:72px; object-fit:cover; border-radius:8px; border:1px solid #0b1220; }
  #playerPane .line { display:flex; gap:8px; align-items:center; margin-top:6px; flex-wrap:wrap; }
  .tireIcon { width:24px; height:24px; vertical-align:middle; border-radius:4px; border:1px solid #0b1220; }

  #sessionDone {
    position:absolute; inset:0; display:none; align-items:center; justify-content:center;
    background:rgba(0,0,0,.55); z-index:10; border-radius:12px;
  }
  #sessionDone .panel {
    background:#0b1220; border:1px solid #1e293b; border-radius:14px; padding:18px 16px; text-align:center; width:360px;
  }
</style>

<div id="wrap">
  <div id="left">
    <div id="hudTop">
      <div style="display:flex; justify-content:space-between; align-items:center; gap:8px;">
        <div class="clock">⏱ <span id="timeText">-:--.-</span></div>
        <div class="speed">
          <button class="btn" data-m="1">1×</button>
          <button class="btn" data-m="2">2×</button>
          <button class="btn" data-m="4">4×</button>
          <button class="btn" data-m="10">10×</button>
          <button class="btn" data-m="30">30×</button>
        </div>
      </div>
      <div class="muted" style="margin:4px 0 2px;">배속은 <b>시간과 물리</b>가 함께 가속됩니다.</div>
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
      <div class="kv"><div>베스트</div><div id="selBest">-</div></div>
      <div class="kv"><div>갭</div><div id="selGap">-</div></div>
      <div class="kv"><div>진행</div><div id="selProg">-</div></div>
      <div class="laps" id="selLaps"></div>
    </div>

    <svg id="stage" viewBox="0 0 1200 800">
      <defs><clipPath id="clip"><rect x="0" y="0" width="1200" height="800"/></clipPath></defs>
      <g id="track" clip-path="url(#clip)"></g>
      <g id="actors" clip-path="url(#clip)"></g>
      <circle id="selRing" class="selRing" r="10" stroke="#0b5cff" stroke-width="3" stroke-dasharray="4 4" fill="none"></circle>
      <foreignObject x="0" y="0" width="1" height="1"></foreignObject>
    </svg>

    <div id="dock">
      <div id="playerPane">
        <div class="title">플레이어 드라이버 컨트롤</div>
        <div class="grid" id="playerCards"></div>
      </div>
    </div>

    <div id="sessionDone">
      <div class="panel">
        <div style="font-weight:800; font-size:18px; margin-bottom:8px;">Session Complete</div>
        <div class="muted" style="margin-bottom:10px;">결과를 저장하고 본선 그리드를 확정합니다.</div>
        <div style="display:flex; gap:8px; justify-content:center;">
          <button id="btnExport" class="btn">결과 JSON 복사</button>
          <button id="btnNext" class="btn primary">본선으로</button>
        </div>
      </div>
    </div>
  </div>

  <div id="right">
    <div class="leader">
      <div style="font-weight:700;margin-bottom:6px;">Leaderboard (Q3: 10 drivers)
        <span id="lapInfo" class="muted"></span>
      </div>
      <div id="rows"></div>
    </div>

    <div class="leader" id="teamTel" style="margin-top:10px;">
      <div style="font-weight:700;margin-bottom:6px;">Team Telemetry</div>
      <div id="tmCards"></div>
    </div>
  </div>
</div>

<script>
(function(){
  const RAW = %%RAW_SVG%%;
  const PLAN = %%PLAN_JSON%%;
  const LAP_BASE = %%LAP_BASE%%;
  const DURATION = %%DURATION%%;
  const PIT_TRAVEL = %%PIT_TRAVEL%%;
  const ENV = %%ENV_JSON%%;
  const TIRE_IMGS = %%TIRE_IMGS%%;
  const SESSION_STR = %%SESSION_STR%%;

  const TRANS_SIM = 0.25;
  const PIT_WAIT_SEC = 4.0;
  const FUEL_PER_LAP = 1.6;
  const FUEL_FLOW_MAX = 100.0/3600.0;
  const TRACK_GRIP_FACTOR = Math.max(0.8, Math.min(1.04, ENV.grip_base)) * (1 - 0.10*ENV.wetness);

  const PACE = {
    "Attack":    {speed:1.020, wear:1.40},
    "Aggressive":{speed:1.010, wear:1.18},
    "Standard":  {speed:1.000, wear:1.00},
    "Light":     {speed:0.992, wear:0.86},
    "Conserve":  {speed:0.985, wear:0.74},
  };
  const FUELMIX = {
    "Push":     {speed:1.010, burn:1.30},
    "Balanced": {speed:1.000, burn:1.00},
    "Conserve": {speed:0.995, burn:0.80},
  };
  const TIRE = {
    soft:         {gripDry:1.030, gripWet:0.78, wearDry:0.080, wearWet:0.16},
    medium:       {gripDry:1.000, gripWet:0.80, wearDry:0.060, wearWet:0.14},
    hard:         {gripDry:0.980, gripWet:0.82, wearDry:0.045, wearWet:0.12},
    intermediate: {gripDry:0.945, gripWet:1.020,wearDry:0.120, wearWet:0.070},
    wet:          {gripDry:0.905, gripWet:1.000,wearDry:0.180, wearWet:0.080},
  };

  let SPEED = 2, simT = -5.0, running = true;
  const stage=document.getElementById('stage'), gTrack=document.getElementById('track'), gAct=document.getElementById('actors');
  const rows=document.getElementById('rows'), lapInfo=document.getElementById('lapInfo');
  const timeText=document.getElementById('timeText'), selRing=document.getElementById('selRing');
  const sessionDone = document.getElementById('sessionDone');

  const selPanel=document.getElementById('selPanel'), selImg=document.getElementById('selImg');
  const selTitle=document.getElementById('selTitle'), selTeamSmall=document.getElementById('selTeamSmall');
  const selMode=document.getElementById('selMode'), selTy=document.getElementById('selTy');
  const selBest=document.getElementById('selBest'), selGap=document.getElementById('selGap');
  const selProg=document.getElementById('selProg'), selLaps=document.getElementById('selLaps');

  document.querySelectorAll('.speed .btn').forEach(b=>{
    b.addEventListener('click', ()=>{ const m=parseFloat(b.getAttribute('data-m')||'1'); if(Number.isFinite(m)) SPEED=m; });
  });

  document.getElementById('btnExport').addEventListener('click', ()=>{
    const js = JSON.stringify(exportResult(), null, 2);
    navigator.clipboard.writeText(js).then(()=>{ alert('결과 JSON을 복사했습니다.'); });
  });
  document.getElementById('btnNext').addEventListener('click', ()=>{
    const js = JSON.stringify(exportResult());
    try { localStorage.setItem('quali_'+SESSION_STR, js); } catch(e){}
    const b64 = btoa(unescape(encodeURIComponent(js)));
    const url = new URL(window.location.href);
    url.searchParams.set('quali_result_b64', b64);
    url.searchParams.set('goto', 'MAIN');
    window.location.href = url.toString();
  });

  // ── SVG 유틸
  function parseSVG(raw){ return (!raw||!raw.trim())?null:new DOMParser().parseFromString(raw, "image/svg+xml"); }
  function getViewBox(doc){ const root=doc.querySelector('svg'); return (root && root.getAttribute('viewBox'))?root.getAttribute('viewBox'):"0 0 1200 800"; }
  function grabPathD(doc,id){ const el=doc.querySelector(`path#${id}`); if(el) return el.getAttribute('d')||''; const any=doc.querySelector('path'); return any?(any.getAttribute('d')||''):''; }
  function text(x,y,str,size=10,fill='#e5e7eb'){const t=document.createElementNS(stage.namespaceURI,'text');t.setAttribute('x',x);t.setAttribute('y',y);t.setAttribute('font-size',String(size));t.setAttribute('fill',fill);t.textContent=str;return t;}
  function nearestS(path,p){ if(!path||!p) return 0; const L=path.getTotalLength(),N=1000; let bestS=0,bestD=1e9; for(let i=0;i<=N;i++){const s=i/N; const q=path.getPointAtLength(s*L); const dx=q.x-p.x,dy=q.y-p.y; const d=dx*dx+dy*dy; if(d<bestD){bestD=d;bestS=s;} } return bestS; }
  function ptOn(path,s){ const L=Math.max(1,path.getTotalLength()); const c=Math.max(0,Math.min(1,s)); const q=path.getPointAtLength(c*L); return {x:q.x,y:q.y}; }
  function reachedForward(a,b,target){ return (b>=a) ? (target>=a && target<=b) : (target>=a || target<=b); }
  function fmtTime(t){ if (t<0) return `-${Math.abs(t).toFixed(1)}s`; const mm=Math.floor(t/60); const ss=(t%60).toFixed(1).padStart(4,'0'); return `${mm}:${ss}`; }
  function placeAt(el, lab, x, y){ el.setAttribute('transform', `translate(${x},${y})`); lab.setAttribute('x', x+8); lab.setAttribute('y', y-8); }

  // 트랙/마커
  let sFinish=0, sMainOut=0, sPitStop=0, sPitOut=0, sPitInMain=0.90, sPitInPit=0.02;
  function build(){
    const doc = parseSVG(RAW); if(!doc) return;
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

  // 엔티티
  const defaultCols=['#ff6b00','#00a3ff','#ffd400','#5ad469','#c86bff','#ff4d6d','#3bc9db','#fab005','#9b59b6','#2ecc71',
                     '#e67e22','#3498db','#f1c40f','#1abc9c','#e84393','#16a085','#c0392b','#8e44ad','#2980b9','#2ecc71'];
  const cars=[]; const pendingReleases=[]; const pendingBoxes=[];
  let selectedIdx=null, sessionBest=null;
  const prevRank = new Map();
  let lastOrder = [];

  function mkCar(info, idx){
    const c=document.createElementNS(stage.namespaceURI,'circle'); c.setAttribute('r','6');
    const col=(info.color && /^#?[0-9A-Fa-f]{6}$/.test(info.color))?(info.color.startsWith('#')?info.color:'#'+info.color):defaultCols[idx%defaultCols.length];
    c.setAttribute('fill', col); c.setAttribute('stroke','#fff'); c.setAttribute('stroke-width','2'); c.classList.add('car'); c.dataset.idx=String(idx);
    const label=text(0,0,(info.abbr||`D${idx+1}`),9,'#e5e7eb'); label.classList.add('carLabel'); label.dataset.idx=String(idx);
    gAct.appendChild(c); gAct.appendChild(label);

    const defaultTy = (ENV.wetness>=0.65? "wet" : (ENV.wetness>=0.30? "intermediate" : "soft"));
    return {
      ...info, color:col, el:c, lab:label,
      mode:'pit', s:0, sPit:0, lap:0, dist:0,
      runIdx:-1, lapsLeft:0, lastCross:null, best:null,
      lapTimes:[], inLap:false, pitTargetS:null, waitUntil:null, wantBox:false,
      compound: defaultTy, nextCompound: defaultTy, tireLife:1.0,
      pace:"Standard", fuelMix:"Balanced", fuel:0.0
    };
  }

  function syncSelRing(){
    if (selectedIdx === null){ selRing.style.display='none'; return; }
    const car = cars[selectedIdx];
    if (!car){ selRing.style.display='none'; return; }
    const tr = car.el.getAttribute('transform') || 'translate(0,0)';
    selRing.setAttribute('transform', tr);
    selRing.setAttribute('stroke', car.el.getAttribute('fill') || '#0b5cff');
    selRing.style.display='block';
  }
  function renderSelPanel(bestRef){
    if (selectedIdx===null){ selPanel.style.display='none'; return; }
    const c = cars[selectedIdx]; if (!c){ selPanel.style.display='none'; return; }
    selPanel.style.display='block';
    selImg.src       = c.img || '';
    selTitle.textContent = `#${c.abbr} ${c.name}`;
    selTeamSmall.textContent  = c.team;
    selMode.textContent  = c.mode + (c.inLap? ' (in-lap)' : '');
    selTy.textContent    = `${c.compound} (${Math.round(c.tireLife*100)}%)`;
    selBest.textContent  = (c.best===null? '—' : `${c.best.toFixed(3)}s`);
    selGap.textContent   = (bestRef===null || c.best===null) ? '—' : `+${(c.best-bestRef).toFixed(3)}s`;
    selProg.textContent  = `run ${Math.max(0,c.runIdx+1)} · ${c.lap} L · left ${Math.max(0,c.lapsLeft)} · fuel ${Math.max(0,c.fuel).toFixed(1)}kg`;
    if (c.lapTimes.length){
      const list = c.lapTimes.map((x,i)=>`L${i+1}: ${x.toFixed(3)}s`).join('<br/>');
      selLaps.innerHTML = list;
    } else { selLaps.innerHTML = '<span class="muted">아직 기록 없음</span>'; }
  }
  function showSelection(idx){
    idx = Math.max(0, Math.min(cars.length-1, idx));
    const car = cars[idx]; if (!car) return;
    selectedIdx = idx; renderSelPanel(sessionBest); syncSelRing();
  }
  gAct.addEventListener('click', (ev)=>{
    const t = ev.target.closest('[data-idx]'); if(!t) return;
    const idx = parseInt(t.getAttribute('data-idx')||'-1',10);
    if (Number.isFinite(idx) && idx>=0) showSelection(idx);
  });

  function findCar(name, team){
    const norm = s => (s||'').toString().trim().toLowerCase();
    const nName = norm(name), nTeam=norm(team);
    let car = cars.find(c=>norm(c.name)===nName && norm(c.team)===nTeam);
    if (car) return car;
    car = cars.find(c=>norm(c.abbr)===nName || norm(c.abbr)===norm((name||'').split(' ')[0]));
    if (car) return car;
    return cars.find(c=>norm(c.name).includes(nName)) || null;
  }

  function canChangeTireNow(car){ return !!car && car.mode === 'pitStopWait'; }

  window.releaseNow = function(name, team, laps=3, timed=[2]){
    const car = findCar(name, team);
    if (!car){ pendingReleases.push({name,team,laps,timed}); return; }
    if (car.mode!=='pit') return;
    car.runIdx = (car.runIdx<0 ? 0 : car.runIdx+1);
    car.lapsLeft = Math.max(1, parseInt(laps||3));
    car.timed = new Set(Array.isArray(timed)? timed.map(x=>parseInt(x,10)): [2]);
    car.inLap = false; car.wantBox = false;
    car.lastCross=null; car.lap=0;
    car.mode='pitGo'; car.pitTargetS = sPitOut;
    const lapsFuel = 1 + car.lapsLeft + 1;
    car.fuel = lapsFuel * FUEL_PER_LAP * 1.05;
    car.compound = car.nextCompound || car.compound;
  }
  window.boxNow = function(name, team){
    const car = findCar(name, team);
    if (!car){ pendingBoxes.push({name,team}); return; }
    if (car.mode==='main'){ car.inLap = true; car.lapsLeft = 0; car.wantBox = false; }
    else { car.wantBox = true; car.lapsLeft = 0; }
  }

  // 플레이어 카드
  const playerCtrlRefs = {};
  function keyOf(p){ return `${p.name}|${p.team}`; }
  function playerCards(){
    const mount = document.getElementById('playerCards'); if (!mount) return;
    mount.replaceChildren();
    const players = PLAN.filter(p=>p.isPlayer).slice(0,2);
    players.forEach((p)=>{
      const card=document.createElement('div'); card.className='card';
      const img=document.createElement('img'); img.src=p.img||''; img.className='avatar';
      const rbox=document.createElement('div');
      const h=document.createElement('div'); h.style.fontWeight='700'; h.textContent=`#${p.abbr} ${p.name}`;
      const s=document.createElement('div'); s.className='muted'; s.textContent=`${p.team} · v× ${p.base_vmul.toFixed(2)}`;

      const line1=document.createElement('div'); line1.className='line';
      const selTy = document.createElement('select');
      ["soft","medium","hard","intermediate","wet"].forEach(k=>{ const o=document.createElement('option'); o.value=k; o.textContent=k[0].toUpperCase()+k.slice(1); selTy.appendChild(o); });
      selTy.value = (ENV.wetness>=0.65? "wet" : (ENV.wetness>=0.30? "intermediate" : "soft"));
      const tyIcon = document.createElement('img'); tyIcon.className='tireIcon'; tyIcon.src = TIRE_IMGS[selTy.value] || '';
      const paceSel=document.createElement('select'); ["Attack","Aggressive","Standard","Light","Conserve"].forEach(x=>{const o=document.createElement('option'); o.value=x;o.textContent=x; paceSel.appendChild(o);}); paceSel.value="Standard";
      const fuelSel=document.createElement('select'); ["Push","Balanced","Conserve"].forEach(x=>{const o=document.createElement('option'); o.value=x;o.textContent=x; fuelSel.appendChild(o);}); fuelSel.value="Balanced";

      line1.appendChild(document.createTextNode('타이어')); line1.appendChild(selTy); line1.appendChild(tyIcon);
      line1.appendChild(document.createTextNode('페이스')); line1.appendChild(paceSel);
      line1.appendChild(document.createTextNode('연료')); line1.appendChild(fuelSel);

      const line2=document.createElement('div'); line2.className='line';
      const bSelect=document.createElement('button'); bSelect.className='btn'; bSelect.textContent='선택'; bSelect.dataset.action='select'; bSelect.dataset.name=p.name; bSelect.dataset.team=p.team;
      const bGo=document.createElement('button'); bGo.className='btn primary'; bGo.textContent='출발(3랩)'; bGo.dataset.action='release'; bGo.dataset.name=p.name; bGo.dataset.team=p.team;
      const bBox=document.createElement('button'); bBox.className='btn'; bBox.textContent='피트인'; bBox.dataset.action='box'; bBox.dataset.name=p.name; bBox.dataset.team=p.team;
      line2.appendChild(bSelect); line2.appendChild(bGo); line2.appendChild(bBox);

      rbox.appendChild(h); rbox.appendChild(s); rbox.appendChild(line1); rbox.appendChild(line2);
      card.appendChild(img); card.appendChild(rbox); mount.appendChild(card);

      const applyToCar=(forceIcon=false)=>{ 
        const car=findCar(p.name,p.team); if(!car) return; 
        car.pace=paceSel.value; car.fuelMix=fuelSel.value; 
        if (canChangeTireNow(car)){ car.nextCompound = selTy.value; }
        else { selTy.value = car.nextCompound || car.compound; }
        if (forceIcon) tyIcon.src = TIRE_IMGS[selTy.value] || '';
      };
      selTy.addEventListener('change', ()=>applyToCar(true));
      paceSel.addEventListener('change', ()=>applyToCar());
      fuelSel.addEventListener('change', ()=>applyToCar());
      [bSelect,bGo,bBox].forEach(btn=>{
        btn.addEventListener('click', ()=>{ applyToCar(true); const action=btn.dataset.action,name=btn.dataset.name,team=btn.dataset.team;
          if(action==='release'){ window.releaseNow(name,team,3,[2]); } 
          else if(action==='select'){ const car=findCar(name,team); if(!car) return; const idx=cars.indexOf(car); if(idx>=0) showSelection(idx); } 
          else if(action==='box'){ window.boxNow(name,team); }
        });
      });

      playerCtrlRefs[keyOf(p)] = {selTy, paceSel, fuelSel, tyIcon};
    });
  }
  function refreshPlayerCardStates(){
    PLAN.filter(p=>p.isPlayer).slice(0,2).forEach(p=>{
      const refs=playerCtrlRefs[`${p.name}|${p.team}`]; if(!refs) return;
      const car=findCar(p.name,p.team); if(!car) return;
      const allowed = canChangeTireNow(car);
      refs.selTy.disabled = !allowed;
      refs.paceSel.disabled = false;
      refs.fuelSel.disabled = false;
      refs.tyIcon.src = TIRE_IMGS[car.compound] || refs.tyIcon.src;
    });
  }

  // 텔레메트리
  function buildTeamTelemetry(){
    const mount=document.getElementById('tmCards'); if(!mount) return;
    mount.replaceChildren();
    PLAN.filter(p=>p.isPlayer).slice(0,2).forEach((p,ix)=>{
      const div=document.createElement('div'); div.className='tmCard'; div.id=`tm${ix}`;
      div.innerHTML = `
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;">
          <div><b>#${p.abbr}</b> ${p.name}</div>
          <img class="tireMini" id="tm${ix}Ty" src="">
        </div>
        <div class="muted" id="tm${ix}Stat">-</div>
        <div style="margin-top:6px;">Tire Life <span id="tm${ix}TirePct">100%</span></div>
        <div class="bar"><div id="tm${ix}TireBar"></div></div>
        <div style="margin-top:8px;">Fuel <span id="tm${ix}FuelKg">0.0kg</span></div>
        <div class="bar alt"><div id="tm${ix}FuelBar"></div></div>
      `;
      mount.appendChild(div);
    });
  }
  function updateTeamTelemetry(){
    PLAN.filter(p=>p.isPlayer).slice(0,2).forEach((p,ix)=>{
      const car=findCar(p.name,p.team); if(!car) return;
      const tyEl=document.getElementById(`tm${ix}Ty`); if(tyEl) tyEl.src=TIRE_IMGS[car.compound]||'';
      const stat=document.getElementById(`tm${ix}Stat`); if(stat) stat.textContent = `${car.pace} · ${car.fuelMix} · Lap ${car.lap}`;
      const lifePct=Math.round(car.tireLife*100);
      const tirePctEl=document.getElementById(`tm${ix}TirePct`); if(tirePctEl) tirePctEl.textContent=`${lifePct}%`;
      const tireBar=document.getElementById(`tm${ix}TireBar`); if(tireBar) tireBar.style.width=`${lifePct}%`;
      const fuelKg=Math.max(0,car.fuel).toFixed(1);
      const fuelEl=document.getElementById(`tm${ix}FuelKg`); if(fuelEl) fuelEl.textContent=`${fuelKg}kg`;
      const fuelBar=document.getElementById(`tm${ix}FuelBar`); if(fuelBar) fuelBar.style.width = `${Math.min(100,(car.fuel/(6*FUEL_PER_LAP))*100)}%`;
    });
  }

  // 결과 수집
  function exportResult(){
    const order = lastOrder.slice();
    return {
      session: SESSION_STR,
      duration_sec: DURATION,
      laps_ref_sec: LAP_BASE,
      env: ENV,
      results: order.map((c,i)=>({
        pos: i+1, name: c.name, team: c.team, abbr: c.abbr,
        best: (c.best===null? null : +c.best.toFixed(3)),
        laps: c.lapTimes.map(x=>+x.toFixed(3)),
        compound: c.compound
      }))
    };
  }

  // 빌드/루프
  let anim=null, tPrev=0;
  function start(){
    const built = build(); if(!built) return;
    const pMain=gTrack.querySelector('path:nth-of-type(1)'); const pPit=gTrack.querySelector('path:nth-of-type(2)');
    gAct.innerHTML=''; cars.length=0;

    for(let i=0;i<PLAN.length;i++){
      const car=mkCar(PLAN[i], i);
      car.sPit = (typeof sPitStop==='number'? sPitStop : 0.05);
      const q=ptOn(pPit, car.sPit);
      placeAt(car.el, car.lab, q.x, q.y);
      cars.push(car);
      prevRank.set(`${car.name}|${car.team}`, i);
    }

    playerCards();
    buildTeamTelemetry();

    PLAN.forEach((p,idx)=>{
      if (!p.isPlayer){
        const car = cars[idx];
        car._reserv = (Array.isArray(p.runs)? p.runs.map(r=>({t:r.start_sec, laps:r.laps, timed:new Set(r.timed_laps||[2])})) : []);
      }
    });
    setInterval(()=>{
      if (simT<0 || simT>DURATION) return;
      PLAN.forEach((p,idx)=>{
        if (p.isPlayer) return;
        const car = cars[idx];
        if (!car || car.mode!=='pit' || !car._reserv || car._reserv.length===0) return;
        const hit = car._reserv.find(z=>z && simT>=z.t && !z._used);
        if (hit){ hit._used = true; car.timed = hit.timed; window.releaseNow(p.name, p.team, hit.laps, Array.from(hit.timed)); }
      });
    }, 120);

    simT = -5.0; tPrev=0; if(anim) cancelAnimationFrame(anim); anim=requestAnimationFrame(loop);
  }

  function loop(now){
    if(!tPrev) tPrev=now;
    const dt=(now-tPrev)/1000; tPrev=now;
    const dtSim = dt * SPEED;

    if (running){
      simT += dtSim;
      timeText.textContent = (simT<0) ? `Starts in ${fmtTime(-simT)}` : `${fmtTime(simT)} / ${fmtTime(DURATION)}`;
      if (simT >= DURATION){ 
        running = false; 
        sessionDone.style.display='flex'; 
        try{ localStorage.setItem('quali_'+SESSION_STR, JSON.stringify(exportResult())); }catch(e){}
      }
    }

    const pMain=gTrack.querySelector('path:nth-of-type(1)'); const pPit=gTrack.querySelector('path:nth-of-type(2)');
    if(!pMain || !pPit){ anim=requestAnimationFrame(loop); return; }

    const baseMain  = 1 / Math.max(0.1, LAP_BASE);
    const vMainBase = baseMain * TRACK_GRIP_FACTOR;
    const vPit      = 1 / Math.max(0.5, PIT_TRAVEL);

    for(const car of cars){
      if (simT < 0){ const q=ptOn(pPit, car.sPit); placeAt(car.el, car.lab, q.x, q.y); continue; }

      if (car.mode==='pit'){
        const q=ptOn(pPit, car.sPit); placeAt(car.el, car.lab, q.x, q.y);
      } else if (car.mode==='pitGo'){
        const before=car.sPit;
        car.sPit=(car.sPit + vPit*dtSim)%1;
        const q=ptOn(pPit, car.sPit); placeAt(car.el, car.lab, q.x, q.y);
        const targetS = car.pitTargetS ?? sPitOut;
        if (reachedForward(before, car.sPit, targetS)){
          if (Math.abs(targetS - sPitOut) < 1e-3){
            const a=ptOn(pPit, sPitOut), b=ptOn(pMain, sMainOut);
            car.mode='toMain'; car.fx={t0Sim: simT, durSim: TRANS_SIM, ax:a.x, ay:a.y, bx:b.x, by:b.y};
          }else{
            car.mode='pitStopWait';
            car.compound = car.nextCompound || car.compound;
            car.waitUntil = simT + PIT_WAIT_SEC;
          }
        }
      } else if (car.mode==='pitStopWait'){
        const q=ptOn(pPit, car.sPit); placeAt(car.el, car.lab, q.x, q.y);
        if (simT >= (car.waitUntil||0)){ car.mode='pit'; car.tireLife = 1.0; }
      } else if (car.mode==='toMain'){
        const w=Math.max(0,Math.min(1,(simT - car.fx.t0Sim)/car.fx.durSim));
        const x=car.fx.ax*(1-w)+car.fx.bx*w, y=car.fx.ay*(1-w)+car.fx.by*w; placeAt(car.el, car.lab, x, y);
        if(w>=1){ car.mode='main'; car.s=sMainOut; car.lap=0; car.lastCross=null; if (car.wantBox){ car.inLap=true; car.wantBox=false; } else { car.inLap=false; } }
      } else if (car.mode==='toPit'){
        const w=Math.max(0,Math.min(1,(simT - car.fx.t0Sim)/car.fx.durSim));
        const x=car.fx.ax*(1-w)+car.fx.bx*w, y=car.fx.ay*(1-w)+car.fx.by*w; placeAt(car.el, car.lab, x, y);
        if(w>=1){ car.mode='pitGo'; car.sPit=sPitInPit; car.pitTargetS = sPitStop; }
      } else if (car.mode==='main'){
        const tDat = TIRE[car.compound] || TIRE.soft;
        const tireGrip = (ENV.wetness>0.3? tDat.gripWet : tDat.gripDry);
        const paceFx  = PACE[car.pace] || PACE.Standard;
        const mixFx   = FUELMIX[car.fuelMix] || FUELMIX.Balanced;
        const tireDegFx = (1 - 0.06*(1 - car.tireLife));
        const fuelMassFx= (1 - 0.006*car.fuel);
        const vmul = Math.max(0.90, Math.min(1.25, car.base_vmul * paceFx.speed * mixFx.speed * tireGrip * tireDegFx * fuelMassFx));
        const before=car.s;
        car.s = (car.s + vMainBase*vmul*dtSim) % 1;

        // 연료/마모
        const desiredRate = (FUEL_PER_LAP / LAP_BASE) * (FUELMIX[car.fuelMix]?.burn || 1.0);
        const actualRate  = Math.min(FUEL_FLOW_MAX, desiredRate);
        car.fuel = Math.max(0, car.fuel - actualRate * dtSim);

        const ds = (car.s - before + 1) % 1;
        const wearLap = (ENV.wetness>0.3? tDat.wearWet : tDat.wearDry) * paceFx.wear;
        car.tireLife = Math.max(0, car.tireLife - wearLap * ds);

        const sLine = (sFinish || 0.01);
        if (reachedForward(before, car.s, sLine)){
          car.lap += 1;
          if (car.lastCross === null){ car.lastCross = simT; }
          else {
            const lapTime = simT - car.lastCross; car.lastCross = simT;
            const isTimed = car.timed ? car.timed.has(car.lap) : true;
            if (isTimed){
              car.lapTimes.push(lapTime);
              if (car.best===null || lapTime < car.best) car.best = lapTime;
            }
            if (car.lapsLeft>0){ car.lapsLeft -= 1; if (car.lapsLeft<=0){ car.inLap = true; } }
            if (car.fuel <= 0.2) car.inLap = true;
          }
        }
        if (car.inLap && reachedForward(before, car.s, sPitInMain)){
          const a=ptOn(pMain, sPitInMain), b=ptOn(pPit, sPitInPit);
          car.mode='toPit'; car.fx={t0Sim: simT, durSim: TRANS_SIM, ax:a.x, ay:a.y, bx:b.x, by:b.y};
        }
        car.dist = (car.runIdx>=0?car.runIdx:0)*10 + car.lap + car.s;
        const q=ptOn(pMain, car.s); placeAt(car.el, car.lab, q.x, q.y);
      }
    }

    // 리더보드: 개인 베스트 기준 + 안정 정렬
    const sorted = cars.slice().sort((a,b)=>{
      const A = (a.best===null? Infinity : a.best);
      const B = (b.best===null? Infinity : b.best);
      if (A !== B) return A-B;
      const ra = prevRank.get(`${a.name}|${a.team}`) ?? 9999;
      const rb = prevRank.get(`${b.name}|${b.team}`) ?? 9999;
      return ra - rb;
    });
    sorted.forEach((c,i)=>prevRank.set(`${c.name}|${c.team}`, i));
    lastOrder = sorted;
    sessionBest = sorted[0] ? (sorted[0].best===null? null : sorted[0].best) : null;

    const ui = sorted.map((c,i)=>{
      const best = (c.best===null) ? "—" : `${c.best.toFixed(3)}s`;
      const gap  = (sessionBest===null || c.best===null) ? "—" : `+${(c.best-sessionBest).toFixed(3)}s`;
      const pos = String(i+1).padStart(2,' ');
      const ty  = TIRE_IMGS[c.compound] || '';
      return `<div class="row"><div class="pos">${pos}</div><div class="name"><img class="tireMini" src="${ty}"/>${c.abbr}</div><div class="gap">${best} / ${gap} · ${c.lap}L</div></div>`;
    }).join("");
    rows.innerHTML = ui;
    lapInfo.textContent = ` · t=${Math.max(0,simT).toFixed(1)}s`;

    renderSelPanel(sessionBest);
    syncSelRing();
    updateTeamTelemetry();
    refreshPlayerCardStates();

    requestAnimationFrame(loop);
  }

  // 시작!
  start();
})();
</script>
        """
        plan_payload = [
            {"name":p.name, "team":p.team, "abbr":p.abbr, "color":p.color or "",
             "img":p.img or "", "isPlayer":p.is_player, "base_vmul":float(p.base_vmul),
             "runs":p.runs}
            for p in plans
        ]
        html = (html
            .replace("%%RAW_SVG%%", json.dumps(RAW_SVG))
            .replace("%%PLAN_JSON%%", json.dumps(plan_payload, ensure_ascii=False))
            .replace("%%LAP_BASE%%", f"{float(lap_base):.6f}")
            .replace("%%DURATION%%", f"{int(duration_sec)}")
            .replace("%%SESSION_STR%%", json.dumps(SESSION))
            .replace("%%PIT_TRAVEL%%", f"{pit_travel:.3f}")
            .replace("%%ENV_JSON%%", json.dumps(env))
            .replace("%%TIRE_IMGS%%", json.dumps(tire_imgs))
        )
        st.components.v1.html(html, height=1400, scrolling=False)

    # ============ 오른쪽(날씨/노면 간단 패널) ============
    with R:
        if env["wetness"] >= 0.65:
            rec_comp = "wet"; rec_msg  = "노면 매우 젖음 → 풀 웻"
        elif env["wetness"] >= 0.30:
            rec_comp = "intermediate"; rec_msg  = "젖은 노면 → 인터미디엇"
        else:
            rec_comp = "soft" if env["track_temp_c"] <= 28 else "medium"
            rec_msg  = "건조 노면 → 소프트/미디엄"
        rec_img = tire_imgs.get(rec_comp, "")

        weather_html = f"""
<style>
  .wx {{background:#0b1220; border:1px solid #1e293b; border-radius:14px; padding:14px; color:#fff;}}
  .wx h3 {{ margin:0 0 8px 0; color:#fff; }}
  .wx .grid {{ display:grid; grid-template-columns: 1fr 1fr; gap:12px; }}
  .wx .metric {{ background:#0e1626; border:1px solid #203049; border-radius:12px; padding:12px; color:#fff; }}
  .bar {{ width:100%; height:14px; background:#0f172a; border:1px solid #334155; border-radius:999px; overflow:hidden; }}
  .bar>div {{ height:100%; background:#0b5cff; width:0%; }}
  .note {{ color:#ffffff; font-size:12px; margin-top:8px; opacity:0.9; }}
  .chip {{ display:inline-flex; align-items:center; gap:8px; background:#091224; border:1px solid #203049; padding:8px 10px; border-radius:12px; color:#fff; }}
  .tireBig {{ width:34px; height:34px; border-radius:6px; border:1px solid #0b1220; }}
</style>
<div class="wx">
  <h3>{SESSION} · Weather & Surface</h3>
  <div class="grid">
    <div class="metric">
      <b>Air Temp</b><div style="font-size:22px; font-weight:800;">{env['air_temp_c']:.0f}°C</div>
      <div class="note">대기 온도</div>
    </div>
    <div class="metric">
      <b>Track Temp</b><div style="font-size:22px; font-weight:800;">{env['track_temp_c']:.0f}°C</div>
      <div class="note">트랙 표면 온도</div>
    </div>
    <div class="metric">
      <b>Rain Probability</b>
      <div class="bar"><div style="width:{env['rain_prob']*100:.0f}%"></div></div>
      <div class="note">{env['rain_prob']*100:.0f}%</div>
    </div>
    <div class="metric">
      <b>Wetness</b>
      <div class="bar"><div style="width:{env['wetness']*100:.0f}%; background:#22c55e;"></div></div>
      <div class="note">{env['wetness']*100:.0f}%</div>
    </div>
    <div class="metric" style="grid-column: 1/3;">
      <b>Grip Base</b>
      <div class="bar"><div style="width:{min(100,max(0,int(env['grip_base']*100)))}%; background:#a78bfa;"></div></div>
      <div class="note">{env['grip_base']:.2f}</div>
    </div>
  </div>
  <div style="margin-top:12px;" class="chip">
    <img class="tireBig" src="{rec_img}"/> 
    <div><b>추천 타이어</b><div class="note">{rec_msg}</div></div>
  </div>
</div>
"""
        st.components.v1.html(weather_html, height=520, scrolling=False)

# 페이지 직접 실행
if __name__ == "__main__":
    run_session_q3()
