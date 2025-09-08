# app.py
# -*- coding: utf-8 -*-
import os, sys, re, base64, hashlib
from pathlib import Path
from dotenv import load_dotenv
import streamlit as st
import pandas as pd

# ── 환경설정(.env) ────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env") or load_dotenv()  # 루트 우선, 없으면 기본 경로 탐색

# ── 경로 상수 ─────────────────────────────────────────────────────────────────
DATA       = Path("data")              # 베이스 CSV 루트(불변)
PAGES      = ROOT / "pages"            # Streamlit 멀티페이지 디렉터리
DRIVER_DIR = ROOT / "driver_image"     # 드라이버 이미지(.png)
LOGO_DIR   = ROOT / "team_logo"        # 팀 로고(.png)

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# ── 내부 모듈 ─────────────────────────────────────────────────────────────────
from f1sim.io.save import ensure_save_slot, get_paths
from f1sim.core.sim import simulate_round

# (옵션) 테마/헤더
try:
    from f1sim.ui.theme import apply_theme, brand_header, F1
    apply_theme()
except Exception:
    F1 = {"red":"#E10600","red_hover":"#FF2D1A","bg":"#0B0B0D","card":"#15151A",
          "text":"#F5F7FA","muted":"#A3A5A8","border":"#2A2A31"}
    def brand_header(title, subtitle=None):
        st.markdown(f"### {title}")
        if subtitle: st.caption(subtitle)

# (옵션) 사이드바 리셋 버튼
try:
    from f1sim.ui.sidebar import attach_reset_sidebar
except Exception:
    def attach_reset_sidebar(): pass

# ── 페이지/레이아웃 ──────────────────────────────────────────────────────────
st.set_page_config(page_title="F1 Manager 2025", page_icon="🏁", layout="wide")
brand_header("F1 Manager 2025", "팀 운영 · 연구 · 훈련 허브")
attach_reset_sidebar()

# ── 데이터 가드(베이스 CSV 존재 체크) ─────────────────────────────────────────
need = [DATA/"teams.csv", DATA/"drivers.csv", DATA/"tracks.csv"]
missing = [p.name for p in need if not p.exists()]
if missing:
    st.error("누락된 파일: " + ", ".join(missing) + f"\n예상 위치: {DATA}")
    st.stop()

# ── 세션 기본값 ───────────────────────────────────────────────────────────────
st.session_state.setdefault("team_id", None)
# round 기본값은 '현재 사용중인 루트(세이브 슬롯 있으면 슬롯, 없으면 data)'의 tracks.csv로부터 설정
st.session_state.setdefault("round", None)

# ── 유틸 ─────────────────────────────────────────────────────────────────────
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
    if not p.exists(): return ""
    data = p.read_bytes()
    return "data:image/png;base64," + base64.b64encode(data).decode("ascii")

def _best_match_png(dirpath: Path, names: list[str]) -> Path | None:
    if not dirpath.exists(): return None
    cands = list(dirpath.glob("*.png"))
    if not cands: return None
    # 정확 매칭
    for nm in names:
        p = dirpath / f"{nm}.png"
        if p.exists(): return p
    # 부분 매칭
    for nm in names:
        t = nm.lower()
        for p in cands:
            if t in p.stem.lower(): return p
    return None

# ── 루트 선택(세이브 슬롯 경로 주입) ──────────────────────────────────────────
# 팀이 선택되면: 세이브 슬롯 생성/보장 → 이후 모든 CSV는 슬롯에서 읽기/쓰기
# 팀이 없으면: 베이스(DATA)에서 읽기(읽기 전용)
team_id = st.session_state.get("team_id")

if team_id:
    slot = ensure_save_slot(st.session_state, DATA, team_id=str(team_id))
    paths = get_paths(st.session_state, DATA)   # {'root', 'teams', 'drivers', 'tracks', ...}
    ROOT_IO = paths["root"]                     # Path
else:
    ROOT_IO = DATA
    paths = {"root": DATA,
             "teams": DATA / "teams.csv",
             "drivers": DATA / "drivers.csv",
             "tracks": DATA / "tracks.csv"}

# ── CSV 로드(현재 루트 기준) ─────────────────────────────────────────────────
teams   = pd.read_csv(paths["teams"])
drivers = pd.read_csv(paths["drivers"])
tracks  = pd.read_csv(paths["tracks"]).sort_values("round")

# round 기본값 세팅(최초 1회)
if st.session_state["round"] is None:
    st.session_state["round"] = int(tracks["round"].min())

# ── 표시용 팀 이름 매핑/컬러 ─────────────────────────────────────────────────
drv_cols = {c.lower(): c for c in drivers.columns}
col_team = drv_cols.get("team_id", "team_id")
col_name = drv_cols.get("name") or drv_cols.get("driver_name")
col_num  = drv_cols.get("number") or drv_cols.get("car_no")
col_nat  = drv_cols.get("nationality") or drv_cols.get("country")
col_tname_from_drivers = drv_cols.get("team_name")

team_map = dict(zip(teams["team_id"].astype(str), teams["name"].astype(str)))
team_colors = {
    str(r["team_id"]): (_norm_hex(r.get("team_color")) or "#0F0F13")
    for r in teams.to_dict(orient="records")
}

from collections import Counter
team_display_name = {}
if col_tname_from_drivers and col_tname_from_drivers in drivers.columns:
    for tid, g in drivers.groupby(drivers[col_team].astype(str)):
        vals = g[col_tname_from_drivers].dropna().astype(str).tolist()
        if vals:
            team_display_name[str(tid)] = Counter(vals).most_common(1)[0][0]
for tid, nm in team_map.items():
    team_display_name.setdefault(str(tid), nm)

def _find_team_logo(team_id: str) -> Path | None:
    disp = team_display_name.get(str(team_id), team_map.get(str(team_id), str(team_id)))
    exact = LOGO_DIR / f"{disp}.png"
    if exact.exists(): return exact
    p = _best_match_png(LOGO_DIR, [disp, _slug(disp), team_map.get(str(team_id), ""), _slug(team_map.get(str(team_id), ""))])
    if p: return p
    if LOGO_DIR.exists():
        cands = list(LOGO_DIR.glob("*.png"))
        if cands: return cands[_hash_idx(str(team_id), len(cands))]
    return None

def _find_driver_img_by_name(name: str) -> Path | None:
    if not isinstance(name, str): return None
    s = _slug(name)
    parts = name.split()
    last = _slug(parts[-1]) if parts else s
    return _best_match_png(DRIVER_DIR, [name, s, last])

def get_team_drivers(team_id: str) -> list[dict]:
    df = drivers[drivers[col_team].astype(str) == str(team_id)].copy()
    if col_num in df.columns: df = df.sort_values(col_num)
    elif col_name in df.columns: df = df.sort_values(col_name)
    rows = []
    for _, r in df.head(2).iterrows():
        name = str(r.get(col_name, "Unknown"))
        num  = str(r.get(col_num, "?"))
        nat  = str(r.get(col_nat, "")).upper()
        imgp = _find_driver_img_by_name(name)
        rows.append({"name": name, "number": num, "nat": nat, "img": imgp})
    while len(rows) < 2:
        rows.append({"name":"TBD","number":"?","nat":"","img":None})
    return rows[:2]

def card_team_summary(team_id: str) -> str:
    d1, d2 = get_team_drivers(team_id)
    logo_p = _find_team_logo(team_id)
    team_bg = team_colors.get(str(team_id), "#0F0F13")
    disp = team_display_name.get(str(team_id), team_map.get(str(team_id), str(team_id)))

    def duo(img1, img2, h=200):
        def tag(p):
            if p and Path(p).exists():
                return f'<img src="{_b64(str(p))}" style="width:100%; height:100%; object-fit:cover; display:block;"/>'
            return '<div style="width:100%; height:100%; background:#0f0f13;"></div>'
        return f'''
<div style="width:100%; height:{h}px; background:#0f0f13; overflow:hidden; display:flex; gap:2px;">
  <div style="flex:1; height:100%;">{tag(d1["img"])}</div>
  <div style="flex:1; height:100%;">{tag(d2["img"])}</div>
</div>'''

    def logo(box=80, img=44):
        box_css = f"width:{box}px; height:{box}px; background:{team_bg}; border:1px solid {F1['border']}; border-radius:12px; display:grid; place-items:center;"
        if logo_p and logo_p.exists():
            return f'<div style="{box_css}"><img src="{_b64(str(logo_p))}" style="width:{img}px; height:{img}px; object-fit:contain; display:block;"/></div>'
        return f'<div style="{box_css}; color:#777;">?</div>'

    def row(d):
        return f'<div style="display:flex; gap:8px; align-items:center;"><b>#{d["number"]}</b><span>{d["name"]}</span><span style="color:{F1["muted"]};">· {d["nat"]}</span></div>'

    return f"""
<div style="background:{F1['card']}; border:1px solid {F1['border']}; border-radius:16px; overflow:hidden; margin-bottom:12px;">
  <div style="height:4px; background:{team_bg};"></div>
  {duo(d1["img"], d2["img"], h=200)}
  <div style="padding:12px 14px;">
    <div style="display:flex; gap:12px;">
      {logo()}
      <div style="flex:1; display:flex; flex-direction:column; gap:6px;">
        <div style="font-weight:800; color:{F1['text']}; font-size:1.05rem;">{disp}</div>
        <div style="display:flex; flex-direction:column; gap:6px; font-size:.92rem;">
          {row(d1)}{row(d2)}
        </div>
      </div>
    </div>
  </div>
</div>
"""

# ── 본문: 팀 선택 유도 / 요약 카드 / 빠른 이동 ────────────────────────────────
if not team_id:
    st.info("먼저 팀을 선택해 주세요.")
    if st.button("팀 선택으로 이동", type="primary"):
        st.switch_page("pages/01_team_select.py")
    # 현재 라운드 정보 표시(베이스 tracks 기준)
    r0 = int(tracks["round"].min())
    trk0 = tracks[tracks["round"]==r0].iloc[0].to_dict()
    st.markdown(
        f"<div style='color:{F1['muted']}; font-size:.92rem;'>현재 라운드: <b>{r0}</b> · 서킷: <b>{trk0['name']}</b></div>",
        unsafe_allow_html=True
    )
    st.stop()

# 팀 요약 카드
st.markdown(card_team_summary(team_id), unsafe_allow_html=True)

# 현재 I/O 루트 안내(슬롯 경로 시각화)
st.caption(f"저장 루트: `{ROOT_IO}`")

# 빠른 이동(존재하는 페이지만 노출)
def page_exists(fname: str) -> bool:
    return (PAGES / fname).exists()

st.write("")
cols = st.columns(4)
with cols[0]:
    if page_exists("00_intro.py") and st.button("👋 인트로", use_container_width=True):
        st.switch_page("pages/00_intro.py")
with cols[1]:
    if page_exists("01_team_select.py") and st.button("🏎️ 팀 선택", use_container_width=True):
        st.switch_page("pages/01_team_select.py")
with cols[2]:
    if page_exists("02_research.py") and st.button("🧪 차량 연구 (R&D)", use_container_width=True, type="primary"):
        st.switch_page("pages/02_research.py")
with cols[3]:
    if page_exists("03_crew_training.py") and st.button("🛠️ 크루 훈련", use_container_width=True, type="primary"):
        st.switch_page("pages/03_crew_training.py")

st.write("")
cols2 = st.columns(4)
with cols2[0]:
    if page_exists("04_pre_race.py") and st.button("📋 프리 레이스", use_container_width=True):
        st.switch_page("pages/04_pre_race.py")
with cols2[1]:
    if page_exists("05_qualifying.py") and st.button("⏱️ 퀄리파잉", use_container_width=True):
        st.switch_page("pages/05_qualifying.py")
with cols2[2]:
    if page_exists("06_main_race.py") and st.button("🏁 메인 레이스", use_container_width=True):
        st.switch_page("pages/06_main_race.py")
with cols2[3]:
    if page_exists("07_media.py") and st.button("🎤 미디어", use_container_width=True):
        st.switch_page("pages/07_media.py")

# 현재 라운드/서킷 간단 표시(세이브 슬롯 tracks 기준)
round_no = int(st.session_state.get("round", int(tracks["round"].min())))
trk = tracks[tracks["round"]==round_no].iloc[0].to_dict()
st.markdown(
    f"<div style='color:{F1['muted']}; font-size:.92rem;'>현재 라운드: <b>{round_no}</b> · 서킷: <b>{trk['name']}</b></div>",
    unsafe_allow_html=True
)

# ── (선택) 스모크 테스트: 시뮬 1라운드 실행 버튼 ───────────────────────────────
with st.expander("개발자 도구 · 스모크 테스트", expanded=False):
    st.caption("세이브 슬롯 루트에서 퀄리/레이스를 1회 실행합니다.")
    if st.button("라운드 시뮬레이션 실행", help="현재 round 값을 사용해 quali/race CSV를 세이브 슬롯에 기록"):
        try:
            qdf, rdf = simulate_round(round_no, root=ROOT_IO)
            st.success("시뮬 완료. 아래 미리보기와 세이브 슬롯 sim/ 폴더를 확인하세요.")
            st.dataframe(qdf.head(10), use_container_width=True)
            st.dataframe(rdf.head(10), use_container_width=True)
        except Exception as e:
            st.error(f"시뮬 실패: {e}")
