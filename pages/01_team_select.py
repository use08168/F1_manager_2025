# pages/01_team_select.py
# -*- coding: utf-8 -*-
import sys, re, base64, hashlib
from pathlib import Path

# ---- 루트/데이터/에셋 절대경로 ----
ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
DRIVER_DIR = ROOT / "driver_image"    # 드라이버 PNG들
LOGO_DIR   = ROOT / "team_logo"       # 팀 로고 PNG들
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st
import pandas as pd

st.set_page_config(page_title="팀 선택", layout="wide", page_icon="🏎️")

# ---- 테마 ----
try:
    from f1sim.ui.theme import apply_theme, brand_header, F1
    apply_theme()
except Exception:
    F1 = {"red":"#E10600","red_hover":"#FF2D1A","bg":"#0B0B0D","card":"#15151A",
          "text":"#F5F7FA","muted":"#A3A5A8","border":"#2A2A31"}
    def brand_header(title, subtitle=None):
        st.markdown(f"### {title}")
        if subtitle: st.caption(subtitle)

brand_header("Team Select", "카드를 눌러 팀을 고르세요")

# ---- 데이터 로드 & 가드 ----
missing = [p.name for p in [DATA/"teams.csv", DATA/"drivers.csv", DATA/"tracks.csv"] if not p.exists()]
if missing:
    st.error("누락된 파일: " + ", ".join(missing) + f"\n예상 위치: {DATA}")
    st.stop()

teams   = pd.read_csv(DATA / "teams.csv")
drivers = pd.read_csv(DATA / "drivers.csv")
tracks  = pd.read_csv(DATA / "tracks.csv").sort_values("round")

# ---- 유틸 ----

def _switch_after_pick(preferred: str = "research"):
    """
    팀 선택 후 이동할 우선순위.
    preferred에 "research"를 넣으면 R&D 우선.
    """
    candidates_by_key = {
        "research":  "pages/02_research.py",
        "pre_race":  "pages/04_pre_race.py",
        "crew":      "pages/03_crew_training.py",
        "home":      "app.py",
    }
    order = [preferred, "pre_race", "crew", "home"]

    from pathlib import Path
    base = Path(__file__).resolve().parents[1]
    for key in order:
        target = candidates_by_key[key]
        tgt_path = (base / target) if target != "app.py" else (base / "app.py")
        if tgt_path.exists():
            st.switch_page(target)
            return
    st.warning("이동할 페이지를 찾지 못했습니다. pages/ 폴더 파일명을 확인하세요.")



def _norm_hex(c: str | None) -> str | None:
    if not isinstance(c, str): return None
    c = c.strip()
    if not c: return None
    if not c.startswith("#"): c = "#" + c
    return c.upper() if re.fullmatch(r"#[0-9A-Fa-f]{6}", c) else None

def _slug(s: str) -> str:
    s = str(s).lower()
    s = re.sub(r"[^a-z0-9]+", "_", s).strip("_")
    return s

def _hash_idx(key: str, n: int) -> int:
    if n <= 0: return 0
    return int(hashlib.md5(key.encode("utf-8")).hexdigest(), 16) % n

@st.cache_data(show_spinner=False)
def _b64(path: str) -> str:
    p = Path(path)
    if not p.exists():
        return ""
    data = p.read_bytes()
    return "data:image/png;base64," + base64.b64encode(data).decode("ascii")

def _best_match_png(dirpath: Path, names: list[str]) -> Path | None:
    """정확 매칭 → 부분 매칭."""
    if not dirpath.exists(): return None
    cands = list(dirpath.glob("*.png"))
    if not cands: return None
    # 1) 정확 일치
    for nm in names:
        p = dirpath / f"{nm}.png"
        if p.exists(): return p
    # 2) 부분 일치
    for nm in names:
        t = nm.lower()
        for p in cands:
            if t in p.stem.lower(): return p
    return None

# ---- 컬럼 명 추론(드라이버) ----
drv_cols = {c.lower(): c for c in drivers.columns}
col_team = drv_cols.get("team_id", "team_id")
col_name = drv_cols.get("name") or drv_cols.get("driver_name")
col_num  = drv_cols.get("number") or drv_cols.get("car_no")
col_nat  = drv_cols.get("nationality") or drv_cols.get("country")
col_tname_from_drivers = drv_cols.get("team_name")  # ★ 새로 추가된 team_name

# ---- 팀 맵/색상 ----
if "team_color" not in teams.columns:
    teams["team_color"] = ""
team_map = dict(zip(teams["team_id"].astype(str), teams["name"].astype(str)))
team_ids = list(team_map.keys())
team_colors = {
    str(r["team_id"]): (_norm_hex(r.get("team_color")) or "#0F0F13")
    for r in teams.to_dict(orient="records")
}

# ---- 드라이버쪽 team_name을 팀 표시명으로 우선 사용 (로고 파일명과 일치하도록) ----
from collections import Counter
team_display_name = {}
if col_tname_from_drivers and col_tname_from_drivers in drivers.columns:
    for tid, g in drivers.groupby(drivers[col_team].astype(str)):
        vals = g[col_tname_from_drivers].dropna().astype(str).tolist()
        if vals:
            team_display_name[str(tid)] = Counter(vals).most_common(1)[0][0]
for tid in team_ids:
    team_display_name.setdefault(str(tid), team_map[tid])

# ---- 세션 ----
st.session_state.setdefault("team_id", None)
# round 상태는 다음 페이지에서 쓸 수 있으니 기본값만 세팅 (UI는 제거)
rr_default = int(tracks["round"].min()) if len(tracks) else 1
st.session_state.setdefault("round", rr_default)
st.session_state.setdefault("quali", None)
st.session_state.setdefault("race", None)

# =========================================================
# 이미지/정보 매칭
# =========================================================
def _find_driver_image_by_name(name: str) -> Path | None:
    """이름 전체 → 슬러그 → 성(last name) 순서로 탐색."""
    if not isinstance(name, str): return None
    s = _slug(name)
    parts = name.split()
    last = _slug(parts[-1]) if parts else s
    return _best_match_png(DRIVER_DIR, [name, s, last])

def get_team_drivers(team_id: str) -> list[dict]:
    """팀의 드라이버 2명(번호/이름/국가/이미지). 2명 미만이면 폴백."""
    df = drivers[drivers[col_team].astype(str) == str(team_id)].copy()
    if col_num in df.columns: df = df.sort_values(col_num)
    elif col_name in df.columns: df = df.sort_values(col_name)
    rows = []
    for _, r in df.head(2).iterrows():
        name = str(r.get(col_name, "Unknown"))
        num  = str(r.get(col_num, "?"))
        nat  = str(r.get(col_nat, "")).upper()
        imgp = _find_driver_image_by_name(name)
        rows.append({"name": name, "number": num, "nat": nat, "img": imgp})
    while len(rows) < 2:
        rows.append({"name":"TBD", "number":"?", "nat":"", "img": None})
    return rows[:2]

def _find_team_logo(team_id: str) -> Path | None:
    """drivers.team_name 우선 → 정확 파일명(팀 이름.png) → 슬러그/부분일치 → 폴백."""
    disp = team_display_name.get(str(team_id), team_map[str(team_id)])
    exact = LOGO_DIR / f"{disp}.png"
    if exact.exists(): return exact
    p = _best_match_png(LOGO_DIR, [disp, _slug(disp), team_map[str(team_id)], _slug(team_map[str(team_id)])])
    if p: return p
    if LOGO_DIR.exists():
        cands = list(LOGO_DIR.glob("*.png"))
        if cands: return cands[_hash_idx(str(team_id), len(cands))]
    return None

# =========================================================
# HTML 생성기
# =========================================================
def _html_duo_hero(img1: Path | None, img2: Path | None, height_px: int = 200) -> str:
    def tag(p: Path | None) -> str:
        if p and p.exists():
            uri = _b64(str(p))
            return f'<img src="{uri}" style="width:100%; height:100%; object-fit:cover; display:block;"/>'
        return '<div style="width:100%; height:100%; background:#0f0f13;"></div>'
    return f"""
<div style="width:100%; height:{height_px}px; background:#0f0f13; overflow:hidden; display:flex; gap:2px;">
  <div style="flex:1; height:100%;">{tag(img1)}</div>
  <div style="flex:1; height:100%;">{tag(img2)}</div>
</div>
"""

def _html_logo_fixed(path: Path | None, box_px: int, img_px: int, bg: str) -> str:
    box = f"width:{box_px}px; height:{box_px}px; background:{bg}; border:1px solid {F1['border']}; border-radius:12px; display:grid; place-items:center;"
    if path and path.exists():
        uri = _b64(str(path))
        return f'<div style="{box}"><img src="{uri}" style="width:{img_px}px; height:{img_px}px; object-fit:contain; display:block;"/></div>'
    return f'<div style="{box}; color:#777;">?</div>'

def _html_driver_rows(d1: dict, d2: dict) -> str:
    def row(d):
        num = f'#{d.get("number","?")}'
        name = d.get("name","")
        nat = d.get("nat","")
        return f'<div style="display:flex; gap:8px; align-items:center;"><b>{num}</b><span>{name}</span><span style="color:{F1["muted"]};">· {nat}</span></div>'
    return f'<div style="display:flex; flex-direction:column; gap:6px; font-size:.92rem;">{row(d1)}{row(d2)}</div>'

# ---- 카드 공통 CSS (팀색 hover/selected 지원: --team-color 변수 사용) ----
st.markdown(f"""
<style>
.team-card {{
  background:{F1["card"]}; border:1px solid {F1["border"]}; border-radius:16px;
  overflow:hidden; transition:all .15s ease; position:relative; min-height:430px; display:flex; flex-direction:column; margin-bottom: 10px;
}}
.team-card:hover {{
  border-color: var(--team-color, {F1["red"]});
  box-shadow: 0 0 0 2px var(--team-color, {F1["red"]});
  transform: translateY(-2px);
}}
.team-card.selected {{
  border-color: var(--team-color, {F1["red"]});
  box-shadow: 0 0 0 3px var(--team-color, {F1["red"]});
}}
.card-body {{ padding:12px 14px; display:flex; flex-direction:column; gap:12px; flex:1; }}
.card-title {{ font-weight:800; color:{F1["text"]}; font-size:1.05rem; }}
.pick-btn > button {{ background:{F1["red"]} !important; color:white !important; border:1px solid {F1["red"]} !important; border-radius:10px !important; width:100% !important; font-weight:800 !important; }}
.pick-btn > button:hover {{ background:{F1["red_hover"]} !important; border-color:{F1["red_hover"]} !important; }}
.ribbon {{ position:absolute; top:10px; left:-6px; background:{F1["red"]}; color:white; padding:4px 10px; font-size:.78rem; font-weight:800; transform:rotate(-6deg); border-radius:6px; box-shadow:0 2px 8px rgba(0,0,0,.35); }}
</style>
""", unsafe_allow_html=True)

# =========================================================
# 카드 렌더링 (모든 HTML을 한 번에 출력)
# =========================================================
def render_team_card(team_id: str, team_name: str):
    d1, d2 = get_team_drivers(team_id)
    logo_p = _find_team_logo(team_id)
    selected = (st.session_state.get("team_id") == str(team_id))
    team_bg = team_colors.get(str(team_id), "#0F0F13")
    display_name = team_display_name.get(str(team_id), team_name)

    # 카드 전체 HTML
    card_html = f"""
<div class="team-card{' selected' if selected else ''}" style="--team-color: {team_bg};">
  <div style="height:4px; background:{team_bg};"></div>
  {_html_duo_hero(d1["img"], d2["img"], height_px=200)}
  <div class="card-body">
    <div style="display:flex; gap:12px;">
      {_html_logo_fixed(logo_p, box_px=80, img_px=44, bg=team_bg)}
      <div style="flex:1; display:flex; flex-direction:column; gap:6px;">
        <div class="card-title">{display_name}</div>
        {_html_driver_rows(d1, d2)}
      </div>
    </div>
  </div>
  {"<div class='ribbon'>SELECTED</div>" if selected else ""}
</div>
"""
    st.markdown(card_html, unsafe_allow_html=True)

    # 선택 버튼
    picked = st.button("이 팀으로 선택", key=f"pick_{team_id}", use_container_width=True, type="primary")
    if picked:
        st.session_state["team_id"] = str(team_id)
        st.session_state["quali"] = None
        st.session_state["race"]  = None
        st.success(f"{team_name} 선택 완료!")
        _switch_after_pick("research") 

# =========================================================
# 5열 × 2행 고정 렌더링 (총 10팀)
# =========================================================
cards_per_row = 5
rows = [team_ids[i:i+cards_per_row] for i in range(0, min(10, len(team_ids)), cards_per_row)]
for row in rows:
    cols = st.columns(cards_per_row, gap="small")
    for col, tid in zip(cols, row):
        with col:
            render_team_card(str(tid), str(team_map[tid]))

# (선택) 디버그
with st.expander("이미지/로고 매칭 디버그"):
    dbg = []
    for tid in team_ids[:10]:
        d1, d2 = get_team_drivers(tid)
        dbg.append({
            "team_id": tid,
            "team_display_name": team_display_name.get(str(tid)),
            "logo_exact": str((LOGO_DIR / f"{team_display_name.get(str(tid), '')}.png").resolve()),
            "driver1_img": str(d1["img"]) if d1["img"] else "(none)",
            "driver2_img": str(d2["img"]) if d2["img"] else "(none)",
        })
    st.dataframe(pd.DataFrame(dbg), use_container_width=True, height=260)
