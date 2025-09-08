# pages/04_pre_race.py
# -*- coding: utf-8 -*-
from __future__ import annotations
import sys, json, time, random, base64, hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st
import pandas as pd

# ---- 테마/헤더 ----
try:
    from f1sim.ui.theme import apply_theme, brand_header, F1
    apply_theme()
except Exception:
    F1 = {"red":"#E10600","red_hover":"#FF2D1A","bg":"#0B0B0D","card":"#15151A",
          "text":"#FFFFFF","muted":"#D0D3D8","border":"#2A2A31"}
    def brand_header(t, s=None):
        st.markdown(f"### {t}")
        if s: st.caption(s)

st.set_page_config(page_title="Pre-Race Practice", page_icon="📋", layout="wide")

# ---- 전역 스타일 오버라이드: 텍스트/테두리 흰색 ----
st.markdown("""
<style>
/* 기본 텍스트를 흰색으로 강제 */
html, body, [data-testid="stAppViewContainer"], .stMarkdown, .stCaption, .stText,
label, p, h1, h2, h3, h4, h5, h6, .stMetric, .stMetric * { color: #fff !important; }

/* 기본 카드/컨테이너 테두리 밝게 */
div[data-testid="stVerticalBlock"] {
  border: 1px solid rgba(255,255,255,0.6) !important;
  border-radius: 12px;
  padding: 8px;
}

/* progress 텍스트 대비 */
[data-testid="stProgress"] div[role="progressbar"] + div { color: #fff !important; }

/* 슬라이더 라벨/값 */
[data-testid="stSlider"] label, [data-testid="stSlider"] span { color: #fff !important; }

/* 버튼 텍스트 색 고정 */
div[data-testid="stButton"] > button,
div[data-testid="stButton"] > button * { color: #000 !important; -webkit-text-fill-color:#000 !important; }
/* 프라이머리 버튼은 흰 글자 */
div[data-testid="stButton"] > button[kind="primary"],
div[data-testid="stButton"] > button[kind="primary"] * { color: #fff !important; -webkit-text-fill-color:#fff !important; }

/* 정보/성공 메시지 텍스트 */
.stAlert, .stAlert * { color: #fff !important; }
</style>
""", unsafe_allow_html=True)

# ---- 세이브/데이터 경로 ----
from f1sim.io.save import ensure_save_slot, get_paths
from f1sim.ui.sidebar import attach_reset_sidebar

DATA       = ROOT / "data"
DRIVER_DIR = ROOT / "driver_image"   # 있으면 사용
CAR_DIR    = ROOT / "car_image"      # 있으면 사용

team_id = st.session_state.get("team_id")
if not team_id:
    st.warning("팀을 먼저 선택하세요.")
    st.switch_page("pages/01_team_select.py")

save_dir = ensure_save_slot(st.session_state, DATA, str(team_id))
PATHS = get_paths(st.session_state, DATA)
attach_reset_sidebar()

# ---- 데이터 로드 ----
teams   = pd.read_csv(PATHS["teams"])
drivers = pd.read_csv(PATHS["drivers"])
tracks  = pd.read_csv(PATHS["tracks"]).sort_values("round")

team_id = str(st.session_state.get("team_id"))
round_no = int(st.session_state.get("round", int(tracks["round"].min())))

if "team_id" not in teams.columns:
    st.error("teams.csv에 team_id 컬럼이 없습니다.")
    st.stop()
teams["team_id"] = teams["team_id"].astype(str)
drivers["team_id"] = drivers["team_id"].astype(str)

if team_id not in set(teams["team_id"]):
    st.error(f"teams.csv에서 team_id={team_id} 를 찾지 못했습니다.")
    st.stop()

# ─────────────────────────────────────────────────────────────────────────────
# 유틸: 이미지 찾기/표시
# ─────────────────────────────────────────────────────────────────────────────
@st.cache_data(show_spinner=False)
def _b64(path: str) -> str:
    p = Path(path)
    if not p.exists(): return ""
    return "data:image/png;base64," + base64.b64encode(p.read_bytes()).decode("ascii")

def _slug(s: str) -> str:
    import re
    s = str(s).lower()
    s = re.sub(r"[^a-z0-9]+", "_", s).strip("_")
    return s

def _best_match_png(dirpath: Path, names: list[str]) -> Path | None:
    if not dirpath.exists(): return None
    cands = list(dirpath.glob("*.png"))
    if not cands: return None
    for nm in names:
        p = dirpath / f"{nm}.png"
        if p.exists(): return p
    for nm in names:
        t = nm.lower()
        for p in cands:
            if t in p.stem.lower(): return p
    return None

def _find_driver_img(name: str) -> Path | None:
    if not isinstance(name, str): return None
    if not DRIVER_DIR.exists(): return None
    s = _slug(name)
    parts = name.split()
    last = _slug(parts[-1]) if parts else s
    return _best_match_png(DRIVER_DIR, [name, s, last])

def _find_car_img(team_name: str) -> Path | None:
    if not isinstance(team_name, str): return None
    if not CAR_DIR.exists(): return None
    return _best_match_png(CAR_DIR, [team_name, _slug(team_name)])

def _stable_key(*parts) -> str:
    return hashlib.md5(("::".join(map(str, parts))).encode("utf-8")).hexdigest()[:10]

# ─────────────────────────────────────────────────────────────────────────────
# 팀/드라이버 뷰 데이터
# ─────────────────────────────────────────────────────────────────────────────
team_row = teams.set_index("team_id").loc[team_id].to_dict()
team_name = str(team_row.get("name", team_id))

d2 = drivers[drivers["team_id"] == team_id].copy()
drv_num = None
for cand in ["number", "car_no", "no", "driver_no"]:
    if cand in d2.columns:
        drv_num = cand; break
if drv_num:
    d2 = d2.sort_values(drv_num)
elif "name" in d2.columns:
    d2 = d2.sort_values("name")
d2 = d2.head(2).copy()
if d2.empty:
    st.error("드라이버가 최소 1명 이상 있어야 합니다.")
    st.stop()

driver_infos = []
for _, r in d2.iterrows():
    info = {
        "driver_id": str(r.get("driver_id", "")) if "driver_id" in d2.columns else str(r.name),
        "name": str(r.get("name", "Unknown")),
        "number": str(r.get(drv_num, "?")) if drv_num else "?",
        "img": _find_driver_img(str(r.get("name", "")))
    }
    driver_infos.append(info)

car_img = _find_car_img(team_name)

# 차량 스펙(표시 전용 — 있으면 사용)
spec_cols = [c for c in ["aero","engine","brakes","reliability","strategy"] if c in teams.columns]
team_specs = {c: float(team_row.get(c, 0)) for c in spec_cols}

# ─────────────────────────────────────────────────────────────────────────────
# 프리 레이스 상태/타깃/스코어 저장 파일
# ─────────────────────────────────────────────────────────────────────────────
SIM_DIR = PATHS["root"] / "sim"
SIM_DIR.mkdir(parents=True, exist_ok=True)
TARGETS_PATH = SIM_DIR / f"pre_targets_round_{round_no:02d}_{team_id}.json"
RESULTS_PATH = SIM_DIR / f"pre_results_round_{round_no:02d}_{team_id}.csv"
BONUS_PATH   = SIM_DIR / f"pre_bonus_round_{round_no:02d}_{team_id}.csv"

# ─────────────────────────────────────────────────────────────────────────────
# 타깃 생성(한번만). 드라이버별로 downforce, braking, power ∈ [0,100]
# ─────────────────────────────────────────────────────────────────────────────
def _new_targets(drivers_list):
    seed_base = int(hashlib.md5(f"{team_id}-{round_no}".encode()).hexdigest(), 16) % (2**32)
    rnd = random.Random(seed_base)
    tg = {}
    for d in drivers_list:
        tg[d["driver_id"]] = {
            "downforce": rnd.randint(0, 100),
            "braking":   rnd.randint(0, 100),
            "power":     rnd.randint(0, 100)
        }
    return tg

if "pre_targets" not in st.session_state:
    if TARGETS_PATH.exists():
        try:
            st.session_state["pre_targets"] = json.loads(TARGETS_PATH.read_text(encoding="utf-8"))
        except Exception:
            st.session_state["pre_targets"] = _new_targets(driver_infos)
    else:
        st.session_state["pre_targets"] = _new_targets(driver_infos)
        TARGETS_PATH.write_text(json.dumps(st.session_state["pre_targets"], ensure_ascii=False), encoding="utf-8")

st.session_state.setdefault("pre_attempt", 1)   # 1..3
st.session_state.setdefault("pre_history", [])  # list of dict rows

# ─────────────────────────────────────────────────────────────────────────────
# 점수/보너스/힌트
# ─────────────────────────────────────────────────────────────────────────────
def score_driver(inputs: dict, target: dict) -> dict:
    sd = {}
    for k in ["downforce","braking","power"]:
        sd[f"score_{k}"] = max(0.0, 100.0 - abs(float(inputs.get(k,0))-float(target.get(k,0))))
    sd["score_total"] = (sd["score_downforce"] + sd["score_braking"] + sd["score_power"]) / 3.0
    return sd

def bonus_from_best(best_score: float) -> float:
    return min(0.01, max(0.0, best_score/100.0 * 0.01))

def hint_word(delta: float) -> str:
    # delta = target - input
    if abs(delta) <= 2:
        return "거의 정확! 🎯"
    sign = "▲" if delta > 0 else "▼"
    mag = abs(delta)
    if mag > 15: level = "많이"
    elif mag > 7: level = "조금"
    else: level = "살짝"
    return f"{level} {'높여요' if delta>0 else '낮춰요'} {sign}"

# ─────────────────────────────────────────────────────────────────────────────
# 헤더/진행 안내
# ─────────────────────────────────────────────────────────────────────────────
trk = tracks[tracks["round"]==round_no].iloc[0].to_dict()
brand_header("프리 레이스 (Practice)", f"Round {round_no} · {trk.get('name','Unknown Circuit')}")
st.caption("설명: 드라이버별 비밀 설정(다운포스·브레이킹·출력)을 맞춰 점수를 올리세요. 총 3회 시도하며, 최고 점수에 비례해 차량에 **최대 +1%** 보너스가 적용됩니다. (보너스는 팀 기본 성능을 바꾸지 않고 퀄리파잉/레이스에만 일시 반영)")

att = int(st.session_state["pre_attempt"])
prog = min(att-1, 3) / 3.0
st.progress(prog, text=f"진행 {att-1}/3 완료")

# ─────────────────────────────────────────────────────────────────────────────
# 선수/차량 카드 + 입력 컨트롤 (+ 직전 시도 힌트)
# ─────────────────────────────────────────────────────────────────────────────
st.divider()
st.subheader("세팅 입력")

cols = st.columns(2)
for ix, info in enumerate(driver_infos):
    col = cols[ix % 2]
    with col:
        with st.container(border=True):
            c1, c2 = st.columns([0.32, 0.68])
            with c1:
                if info["img"] and Path(info["img"]).exists():
                    st.image(info["img"], use_container_width=True)
                else:
                    st.markdown(
                        f"<div style='width:100%;aspect-ratio:1/1;background:#0f0f13;border:1px solid {F1['border']};border-radius:12px;display:grid;place-items:center;color:{F1['muted']};'>No Image</div>",
                        unsafe_allow_html=True
                    )
            with c2:
                st.markdown(f"**#{info['number']} {info['name']}**  · 팀: **{team_name}**")
                if car_img and Path(car_img).exists():
                    st.image(car_img, use_container_width=True)
                if team_specs:
                    st.caption("차량 스펙(표시용)")
                    cols2 = st.columns(len(team_specs))
                    for j,(k,v) in enumerate(team_specs.items()):
                        with cols2[j]:
                            st.metric(k, f"{v:.0f}")

            # 직전 시도 힌트(있으면 노출)
            tg = st.session_state["pre_targets"]
            hist = st.session_state["pre_history"]
            if att > 1:
                prev_rows = [r for r in hist if r["attempt"] == att-1 and r["driver_id"] == info["driver_id"]]
                if prev_rows:
                    r = prev_rows[0]  # 해당 드라이버의 직전 시도
                    td = tg[info["driver_id"]]  # {'downforce': int, 'braking': int, 'power': int}

                    # 안전한 실수 변환 후 방향 차이(타깃 - 입력)
                    h_df = float(td.get("downforce", 0)) - float(r.get("input_downforce", 0))
                    h_br = float(td.get("braking",   0)) - float(r.get("input_braking",   0))
                    h_pw = float(td.get("power",     0)) - float(r.get("input_power",     0))

                    st.info(
                        f"힌트 — 다운포스: {hint_word(h_df)} · 브레이킹: {hint_word(h_br)} · 출력: {hint_word(h_pw)}",
                        icon="💡"
                    )


            # 컨트롤(0..100)
            st.markdown("---")
            st.caption("값을 조절해 타깃에 가깝게 맞춰 보세요. (0~100)")
            key_pref = f"pr_input_{info['driver_id']}"
            st.session_state.setdefault(key_pref, {"downforce":50,"braking":50,"power":50})
            s = st.session_state[key_pref]
            s["downforce"] = st.slider(f"다운포스 · {info['name']}", 0, 100, int(s.get("downforce",50)), key=f"sld_df_{info['driver_id']}")
            s["braking"]   = st.slider(f"브레이킹 · {info['name']}", 0, 100, int(s.get("braking",50)),   key=f"sld_br_{info['driver_id']}")
            s["power"]     = st.slider(f"출력 · {info['name']}",     0, 100, int(s.get("power",50)),     key=f"sld_pw_{info['driver_id']}")
            st.session_state[key_pref] = s

st.divider()

# ─────────────────────────────────────────────────────────────────────────────
# 실행 버튼 (리셋/팀선택 버튼 제거)
# ─────────────────────────────────────────────────────────────────────────────
run_disabled = (att > 3)
if st.button("이번 프리 레이스 실행", type="primary", use_container_width=True, disabled=run_disabled):
    tg = st.session_state["pre_targets"]
    rows = []
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    for info in driver_infos:
        did = info["driver_id"]
        inp = st.session_state[f"pr_input_{did}"]
        sc = score_driver(inp, tg[did])
        row = {
            "ts": ts,
            "round": round_no,
            "team_id": team_id,
            "attempt": att,
            "driver_id": did,
            "target_downforce": tg[did]["downforce"],
            "target_braking":   tg[did]["braking"],
            "target_power":     tg[did]["power"],
            "input_downforce":  int(inp["downforce"]),
            "input_braking":    int(inp["braking"]),
            "input_power":      int(inp["power"]),
            "score_downforce":  float(sc["score_downforce"]),
            "score_braking":    float(sc["score_braking"]),
            "score_power":      float(sc["score_power"]),
            "score_total":      float(sc["score_total"]),
        }
        rows.append(row)

    st.session_state["pre_history"].extend(rows)
    pd.DataFrame(st.session_state["pre_history"]).to_csv(RESULTS_PATH, index=False, encoding="utf-8")

    st.session_state["pre_attempt"] = att + 1
    st.success(f"{att}회차 프리 레이스 결과를 기록했습니다. 힌트를 참고해 다음 시도에서 더 가깝게 맞춰보세요!")
    st.rerun()

# ─────────────────────────────────────────────────────────────────────────────
# 선수별 누적 결과(카드형)
# ─────────────────────────────────────────────────────────────────────────────
if Path(RESULTS_PATH).exists():
    prev = pd.read_csv(RESULTS_PATH)
    if not prev.empty:
        st.markdown("#### 누적 결과 (선수별)")
        ccols = st.columns(2)
        for ix, info in enumerate(driver_infos):
            col = ccols[ix % 2]
            with col, st.container(border=True):
                st.markdown(f"**#{info['number']} {info['name']}**")
                me = prev[prev["driver_id"] == info["driver_id"]].sort_values("attempt")
                if me.empty:
                    st.caption("아직 결과가 없습니다.")
                else:
                    # 최고점/최근점
                    best = float(me["score_total"].max())
                    last = float(me["score_total"].iloc[-1])
                    st.metric("최고점(100)", f"{best:.1f}", delta=f"{(last-best):.1f}" if last!=best else None)
                    # 시도별 간단 로그
                    for _, r in me.iterrows():
                        st.markdown(
                            f"- **{int(r['attempt'])}회차**: 총점 {r['score_total']:.1f}  "
                            f"(DF {r['score_downforce']:.0f} · BR {r['score_braking']:.0f} · PW {r['score_power']:.0f})"
                        )

# ─────────────────────────────────────────────────────────────────────────────
# 완료(3회) 시: 보너스 계산/저장 + 다음 단계 버튼
# ─────────────────────────────────────────────────────────────────────────────
done = (att > 3)
if done:
    st.divider()
    st.subheader("🎯 최종 결과 및 보너스")

    if not Path(RESULTS_PATH).exists():
        st.error("결과 파일이 없습니다. 프리 레이스를 먼저 실행하세요.")
        st.stop()

    df = pd.read_csv(RESULTS_PATH)
    if df.empty:
        st.error("결과 데이터가 비어 있습니다.")
        st.stop()

    best = df.groupby("driver_id")["score_total"].max().reset_index()
    best["bonus_decimal"] = (best["score_total"].clip(0,100) / 100.0 * 0.01).round(6)

    id_to_name = {d["driver_id"]: d["name"] for d in driver_infos}
    best["driver_name"] = best["driver_id"].map(id_to_name)
    best["round"] = round_no
    best["team_id"] = team_id
    best = best[["round","team_id","driver_id","driver_name","score_total","bonus_decimal"]]
    best.to_csv(BONUS_PATH, index=False, encoding="utf-8")

    st.session_state["pre_final_bonus"] = {r["driver_id"]: float(r["bonus_decimal"]) for _, r in best.iterrows()}

    # 선수별 카드로 보너스 표시
    bb_cols = st.columns(2)
    for ix, row in enumerate(best.itertuples(index=False)):
        with bb_cols[ix % 2], st.container(border=True):
            st.markdown(f"**{row.driver_name}**")
            st.metric("최고점(100)", f"{row.score_total:.1f}")
            st.metric("보너스(최대 1%)", f"+{row.bonus_decimal*100:.2f}%")

    st.caption("보너스는 팀 기본 차량 성능을 바꾸지 않고 **이번 라운드 퀄리파잉/레이스**에만 일시 반영됩니다.")
    st.info("다음 단계에서 각 드라이버의 성능 스칼라에 × (1 + bonus_decimal)을 곱해 반영하세요.")

    st.divider()
    if st.button("⏱️ 퀄리파잉으로 진행", type="primary", use_container_width=True):
        st.switch_page("pages/05_q1.py")
