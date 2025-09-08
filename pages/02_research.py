# pages/02_research.py
# -*- coding: utf-8 -*-
import sys, json
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))

import streamlit as st
import pandas as pd

# ---- 테마/헤더 ----
try:
    from f1sim.ui.theme import apply_theme, brand_header, F1
    apply_theme()
except Exception:
    F1 = {"red":"#E10600","red_hover":"#FF2D1A","bg":"#0B0B0D","card":"#15151A",
          "text":"#F5F7FA","muted":"#A3A5A8","border":"#2A2A31"}
    def brand_header(t, s=None):
        st.markdown(f"### {t}")
        if s: st.caption(s)


# ---- 글로벌 스타일: 본문 흰색 + 버튼 커스텀 ----
st.set_page_config(page_title="R&D", page_icon="🧪", layout="wide")
st.markdown(f"""
<style>
/* 본문 텍스트 흰색 — 버튼/입력 내부 span, div 는 건드리지 않음 */
html, body,
.stMarkdown, .stChatMessage, .stCaption, .stText,
label, p, h1, h2, h3, h4, h5, h6 {{
  color: {F1["text"]} !important;
}}
</style>
""", unsafe_allow_html=True)



brand_header("차량 연구 (R&D)", "엔지니어 브리핑 → 선택지 카드 → 최종 제출/진행/적용")

# ---- 데이터 로드 ----
from f1sim.io.save import ensure_save_slot, get_paths
from f1sim.ui.sidebar import attach_reset_sidebar

DATA = ROOT / "data"
# 팀 선택 여부 확인 후, R&D 진입 시 세이브 슬롯 보장
team_id = st.session_state.get("team_id")
if not team_id:
    st.warning("팀을 먼저 선택하세요.")
    st.switch_page("pages/01_team_select.py")

save_dir = ensure_save_slot(st.session_state, DATA, team_id)
PATHS = get_paths(st.session_state, DATA)

# 사이드바: 진행 데이터 삭제 버튼
attach_reset_sidebar()

RD_PATH = PATHS["rd"]
teams   = pd.read_csv(PATHS["teams"])
tracks  = pd.read_csv(PATHS["tracks"]).sort_values("round")

# ---- 세션 가드 ----
team_id = st.session_state.get("team_id")
if not team_id:
    st.warning("팀을 먼저 선택하세요.")
    st.switch_page("pages/01_team_select.py")

# ---- 현재 팀 상태/라운드 ----
trow = teams.set_index("team_id").loc[team_id].to_dict()
round_no = int(st.session_state.get("round", int(tracks["round"].min())))
next3 = tracks[tracks["round"].between(round_no, min(round_no+2, int(tracks["round"].max())))][
    ["round","name","grip_index","abrasion_index"]
].to_dict("records")

# 누락 컬럼 기본값
defaults = {
    "aero": 70, "engine": 70, "reliability": 70, "dev_efficiency": 70,
    "pit_crew": 70, "strategy": 75, "team_morale": 70, "budget_musd": 120.0
}
for k, v in defaults.items():
    trow.setdefault(k, v)

# ---- 백로그 로드/컬럼 보정(paid/charged_musd 추가) ----
if RD_PATH.exists():
    backlog = pd.read_csv(RD_PATH)
else:
    backlog = pd.DataFrame(columns=[
        "project_id","team_id","planned_round","title","area","cost_musd",
        "eta_rounds","remaining_rounds","risk","efficiency","expected_gain_hint",
        "status","reason","paid","charged_musd"
    ])
# 오래된 파일 호환
for col, default in [("paid", 0), ("charged_musd", 0.0)]:
    if col not in backlog.columns:
        backlog[col] = default

# ---- 유틸 ----
def _pill(text, color):
    return f"""<span style="
        display:inline-block; padding:2px 8px; border-radius:999px; 
        font-size:.78rem; font-weight:700; color:white; background:{color};
    ">{text}</span>"""

def _risk_pill(risk: str) -> str:
    risk = (risk or "").lower()
    if risk == "low":  return _pill("LOW RISK", "#2b9348")
    if risk == "mid":  return _pill("MEDIUM",   "#f9c74f")
    if risk == "high": return _pill("HIGH",     "#f94144")
    return _pill("UNKNOWN", "#6c757d")

def _area_kr(area: str) -> str:
    m = {
        "vehicle_design":"차량 디자인",
        "front_wing":"프런트 윙",
        "rear_wing":"리어 윙",
        "brakes":"브레이크",
        "engine":"엔진",
    }
    return m.get(area, area)

def _score(dec: dict, team_dev_eff: float) -> float:
    eff = float(dec.get("efficiency", 0))
    gain = float(dec.get("expected_gain_hint", 0))
    dev = float(team_dev_eff) / 100.0
    return max(0.0, min(1.0, eff * gain * dev))

def _eta_abs_round(eta_rounds: int) -> int:
    try:
        return int(round_no + int(eta_rounds))
    except Exception:
        return round_no + 1

def _predict_gains(dec: dict, team_state: dict) -> dict:
    """apply_effects와 동일 로직으로 예상 상승치 계산(표시용)"""
    dev = float(team_state.get("dev_efficiency", 70)) / 100.0
    cost = float(dec.get("cost_musd", 0.0))
    mul  = float(dec.get("expected_gain_hint", 0.5)) * float(dec.get("efficiency", 0.6))
    gain = mul * dev * cost * 0.2
    area = dec.get("area","")
    aero = reli = eng = 0.0
    if area == "vehicle_design":
        aero += gain*0.8; reli += gain*0.4
    elif area == "front_wing":
        aero += gain*1.0
    elif area == "rear_wing":
        aero += gain*0.9
    elif area == "brakes":
        reli += gain*0.9
    elif area == "engine":
        eng  += gain*1.0
    return {"aero":aero, "reliability":reli, "engine":eng}

# ---- 좌/우 영역 ----
L, R = st.columns([0.62, 0.38])

# =========================
# L: 제안 생성 & 브리핑/선택지
# =========================
with L:
    st.subheader("엔지니어에게 제안 받기")

    max_spend = float(trow["budget_musd"])
    spend = st.slider("예산 상한(MUSD)", 0.0, max_spend, min(20.0, max_spend), 1.0,
                      help="상한을 높이면 더 큰 연구안을 제안하지만, ETA가 늘어날 수 있습니다.")

    tloc = dict(trow)
    tloc["team_id"] = team_id
    tloc["budget_musd"] = spend

    if st.button("LLM으로 연구 제안 생성", type="primary", use_container_width=True):
        from f1sim.ai.llm_client import ask_llm_json, digest_inputs
        from f1sim.ai.schemas import RESEARCH_JSON_SCHEMA
        from f1sim.ai.prompts import system_common, prompt_research

        budget_hint = (
            f"\n- 예산 상한(max_budget_hint): {spend:.1f} MUSD. 총 비용은 상한을 넘지 않게 구성."
            f"\n- 상한이 높을수록 복잡도 증가로 ETA가 1~2R 늘어날 수 있음을 반영."
        )
        inputs = {"team": tloc, "tracks": next3, "round": round_no, "max_budget_hint": spend}
        js = ask_llm_json(
            RESEARCH_JSON_SCHEMA,
            system_prompt=system_common(),
            user_prompt=(
                prompt_research(tloc, next3, round_no) + budget_hint +
                f"\n- inputs_digest: {digest_inputs(inputs)}\n"
            )
        )
        st.session_state["rd_proposal"] = js
        st.session_state["rd_picks_ui"] = []  # 이전 선택 초기화
        st.success("연구 제안을 수신했습니다.")

    prop = st.session_state.get("rd_proposal")

    # 원본 JSON은 expander로 숨김
    if prop:
        with st.expander("원본 제안 JSON 열기"):
            st.json(prop)

    # 엔지니어 브리핑 + 선택지 카드
    if prop:
        decs = prop.get("decisions", [])
        st.markdown("#### 👨‍🔧 엔지니어 브리핑")
        with st.chat_message("assistant"):
            st.markdown(
                f"매니저님, 이번 라운드 기준으로 총 **{len(decs)}건**의 연구안을 준비했습니다. "
                f"개발 효율 **{int(trow['dev_efficiency'])}%**, 예산 상한 **${spend:.1f}M**을 반영했어요. "
                "상한이 높아질수록 ETA가 다소 길어질 수 있습니다."
            )

        st.markdown("---")
        st.markdown("#### 🔎 선택지")
        st.caption("체크한 항목은 우측 패널의 ‘최종 제출’에서 한 번에 확정됩니다.")

        picks = st.session_state.get("rd_picks_ui", [])
        # 선택지 카드
        for i, d in enumerate(decs, 1):
            area = d.get("area", "")
            title = d.get("title", "제목 없음")
            cost  = float(d.get("cost_musd", 0))
            eta   = int(d.get("eta_rounds", 1))
            riskp = _risk_pill(d.get("risk"))
            score = _score(d, trow["dev_efficiency"])
            eta_abs = _eta_abs_round(eta)
            gains = _predict_gains(d, trow)

            with st.container(border=True):
                c1, c2 = st.columns([0.70, 0.30])
                with c1:
                    st.markdown(
                        f"**{i}. [{_area_kr(area)}] {title}**  &nbsp; {riskp}",
                        unsafe_allow_html=True
                    )
                    st.markdown(
                        f"- 예상 완료: R{eta_abs} (ETA {eta}R) · 비용: ${cost:.1f}M"
                    )
                    gain_txt = []
                    if gains["aero"]>0: gain_txt.append(f"aero +{gains['aero']:.1f}")
                    if gains["reliability"]>0: gain_txt.append(f"reliability +{gains['reliability']:.1f}")
                    if gains["engine"]>0: gain_txt.append(f"engine +{gains['engine']:.1f}")
                    if gain_txt:
                        st.markdown("예상 상승: " + " · ".join(gain_txt))
                    st.progress(int(score*100), text=f"추천도 {int(score*100)} / 100")
                    st.caption(d.get("reason", "사유 설명 없음"))
                with c2:
                    key = f"pick_{i}"
                    checked_now = st.checkbox("선택", key=key,
                                              value=any(p.get("title")==d.get("title") and p.get("area")==d.get("area") for p in picks))
                    # 선택/해제 반영
                    if checked_now and not any(p.get("title")==d.get("title") and p.get("area")==d.get("area") for p in picks):
                        tmp = dict(d); tmp["_eta_abs"] = eta_abs; tmp["_score"] = score
                        picks.append(tmp)
                    if not checked_now:
                        picks = [p for p in picks if not (p.get("title")==d.get("title") and p.get("area")==d.get("area"))]
        st.session_state["rd_picks_ui"] = picks

# =========================
# R: 최종 제출 · 백로그/진행/삭제
# =========================
with R:
    st.subheader("최종 제출 · 백로그 · 진행")

    ui_picks = st.session_state.get("rd_picks_ui", [])
    total_cost = sum(float(d.get("cost_musd",0)) for d in ui_picks) if ui_picks else 0.0

    if ui_picks:
        st.markdown("**선택된 항목**")
        for i, d in enumerate(ui_picks, 1):
            st.write(f"- {i}) [{_area_kr(d['area'])}] {d['title']} · ETA {d['eta_rounds']}R · ${float(d['cost_musd']):.1f}M")
        # 평문 표기(기호 제거)
        st.info(f"예상 비용: ${total_cost:.1f}M / 보유 예산: ${float(trow['budget_musd']):.1f}M")

    # ===== 최종 제출/크루 이동 =====
    cfs1, cfs2 = st.columns(2)
    with cfs1:
        st.markdown('<div id="finalsubmit">', unsafe_allow_html=True)
        disable_final = (not ui_picks) or (total_cost > float(trow["budget_musd"]))
        if st.button("최종 제출", use_container_width=True, disabled=disable_final):
            if disable_final:
                st.warning("선택 항목이 없거나 예산이 부족합니다.")
            else:
                st.session_state["confirm_final_submit"] = True
        st.markdown('</div>', unsafe_allow_html=True)
    with cfs2:
        st.markdown('<div id="crewbtn">', unsafe_allow_html=True)
        if st.button("크루 훈련으로 이동", use_container_width=True):
            st.switch_page("pages/03_crew_training.py")
        st.markdown('</div>', unsafe_allow_html=True)

    # 최종 제출 확인 단계
    if st.session_state.get("confirm_final_submit"):
        st.warning("연구를 진행하겠습니까? 연구가 시작되면 연구비는 회수가 불가능 합니다.")
        cc1, cc2 = st.columns(2)
        with cc1:
            if st.button("확인",use_container_width=True):
                # 1) 예산 차감
                teams_df = teams.set_index("team_id")
                cur = float(teams_df.loc[team_id, "budget_musd"])
                if total_cost > cur:
                    st.error("예산이 부족합니다.")
                    st.session_state["confirm_final_submit"] = False
                else:
                    new = round(cur - total_cost, 2)
                    teams_df.loc[team_id, "budget_musd"] = new
                    teams_df.reset_index().to_csv(PATHS["teams"], index=False, encoding="utf-8")
                    # 2) 백로그 기록 (paid=1, charged_musd 세팅)
                    rows = []
                    for d in ui_picks:
                        pid = f"{team_id}-{round_no}-{d['area']}-{abs(hash(d['title']))%10000}"
                        rows.append({
                            "project_id": pid,
                            "team_id": team_id,
                            "planned_round": round_no,
                            "title": d["title"],
                            "area": d["area"],
                            "cost_musd": float(d["cost_musd"]),
                            "eta_rounds": int(d["eta_rounds"]),
                            "remaining_rounds": int(d["eta_rounds"]),
                            "risk": d["risk"],
                            "efficiency": float(d["efficiency"]),
                            "expected_gain_hint": float(d["expected_gain_hint"]),
                            "status": "in_progress",
                            "reason": d.get("reason",""),
                            "paid": 1,
                            "charged_musd": float(d["cost_musd"]),
                        })
                    new_backlog = pd.concat([backlog, pd.DataFrame(rows)], ignore_index=True)
                    new_backlog.to_csv(RD_PATH, index=False, encoding="utf-8")
                    # 상태 정리
                    st.session_state["rd_picks_ui"] = []
                    st.session_state["confirm_final_submit"] = False
                    st.success("연구가 시작되었습니다. 예산이 차감되었습니다.")
                    st.rerun()
                    
        with cc2:
            if st.button("취소",use_container_width=True):
                st.session_state["confirm_final_submit"] = False
                st.info("최종 제출이 취소되었습니다.")
                

    st.markdown("---")

    # ===== 백로그 표시 & 진행/적용(정렬/크기 일치) =====
    mine = backlog[backlog["team_id"]==team_id].copy()
    if len(mine):
        st.caption("진행 중/완료 대기 프로젝트")
        mine = mine.sort_values(["status","remaining_rounds","planned_round"])
        st.dataframe(mine, use_container_width=True, height=300)

        b1, b2 = st.columns(2)
        with b1:
            st.markdown('<div id="progressbtn">', unsafe_allow_html=True)
            if st.button("연구 진행", use_container_width=True):
                def dec(r):
                    if r["team_id"]!=team_id or r["status"]!="in_progress": return r
                    r["remaining_rounds"] = max(0, int(r["remaining_rounds"])-1)
                    if r["remaining_rounds"] == 0:
                        r["status"] = "ready_to_apply"
                    return r
                updated = backlog.apply(dec, axis=1)
                updated.to_csv(RD_PATH, index=False, encoding="utf-8")
                st.success("연구 시작")
                st.rerun()
            st.markdown('</div>', unsafe_allow_html=True)
        with b2:
            st.markdown('<div id="applybtn">', unsafe_allow_html=True)
            if st.button("완료 적용", type="primary", use_container_width=True):
                from f1sim.ai.apply_effects import apply_research_effect
                mask = (backlog["team_id"]==team_id) & (backlog["status"]=="ready_to_apply")
                ready = backlog[mask].to_dict("records")
                if not ready:
                    st.info("적용할 완료 프로젝트가 없습니다.")
                else:
                    teams_df = teams.set_index("team_id")
                    state = teams_df.loc[team_id].to_dict()
                    for k, v in defaults.items(): state.setdefault(k, v)
                    for prj in ready:
                        state = apply_research_effect(state, prj)  # 비용은 최종 제출 시 차감됨
                    for k, v in state.items():
                        teams_df.loc[team_id, k] = v
                    teams_df.reset_index().to_csv(DATA/"teams.csv", index=False, encoding="utf-8")
                    backlog.loc[mask, "status"] = "completed"
                    backlog.to_csv(RD_PATH, index=False, encoding="utf-8")
                    st.success(f"{len(ready)}개 프로젝트 적용 완료")
                    st.rerun()
            st.markdown('</div>', unsafe_allow_html=True)
    else:
        st.info("백로그가 비어 있습니다. 왼쪽에서 제안을 생성하고 ‘최종 제출’로 확정하세요.")

    st.markdown("---")
    # ===== 삭제(검은 글씨, 즉시 반영; 예산 환불 없음) =====
    rm_id = st.text_input("프로젝트 ID 삭제", placeholder="project_id 붙여넣기")
    st.markdown('<div id="delarea">', unsafe_allow_html=True)
    if st.button("삭제", use_container_width=True):
        if rm_id:
            new_backlog = backlog[backlog["project_id"] != rm_id]
            new_backlog.to_csv(RD_PATH, index=False, encoding="utf-8")
            st.success("삭제되었습니다. (예산은 환불되지 않습니다)")
            st.rerun()
        else:
            st.warning("삭제할 project_id를 입력해 주세요.")
    st.markdown('</div>', unsafe_allow_html=True)

st.markdown(f"""
<style>
/* 버튼 텍스트를 기본 '검은색'으로 리셋 (disabled 포함) */
div[data-testid="stButton"] > button,
div[data-testid="stButton"] > button *,
div[data-testid="stButton"] > button:disabled,
div[data-testid="stButton"] > button:disabled * {{
  color: #000 !important;
  -webkit-text-fill-color: #000 !important;  /* 크로미움/사파리 */
  opacity: 1 !important; filter: none !important;
}}

/* 컬러 버튼(우리가 지정한 컨테이너 id)만 다시 '흰 글자'로 오버라이드 */
#applybtn div[data-testid="stButton"] > button,
#applybtn div[data-testid="stButton"] > button *,
#finalsubmit div[data-testid="stButton"] > button,
#finalsubmit div[data-testid="stButton"] > button *,
#crewbtn div[data-testid="stButton"] > button,
#crewbtn div[data-testid="stButton"] > button * {{
  color: #fff !important;
  -webkit-text-fill-color: #fff !important;
}}

/* 밝은 배경 버튼 배경/테두리 */
#delarea  div[data-testid="stButton"] > button {{
  background:#E0E0E0 !important; border-color:#E0E0E0 !important;
}}
#progressbtn div[data-testid="stButton"] > button {{
  background:#FFD166 !important; border-color:#FFD166 !important;
}}

/* 버튼 크기/정렬 통일 */
#progressbtn div[data-testid="stButton"] > button,
#applybtn    div[data-testid="stButton"] > button,
#finalsubmit div[data-testid="stButton"] > button,
#crewbtn     div[data-testid="stButton"] > button,
#delarea     div[data-testid="stButton"] > button {{
  width:100%; min-height:46px; line-height:46px;
  white-space:nowrap; overflow:hidden; text-overflow:ellipsis;
}}
</style>
""", unsafe_allow_html=True)
