# pages/03_crew_training.py
# -*- coding: utf-8 -*-
import sys, json, time, hashlib
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))

import streamlit as st
import pandas as pd
from datetime import datetime

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

st.set_page_config(page_title="Crew Training", page_icon="🛠️", layout="wide")

# ---- 경로/데이터 ----
from f1sim.io.save import ensure_save_slot, get_paths
from f1sim.ui.sidebar import attach_reset_sidebar

DATA = ROOT / "data"

team_id = st.session_state.get("team_id")
if not team_id:
    st.warning("팀을 먼저 선택하세요.")
    st.switch_page("pages/01_team_select.py")

save_dir = ensure_save_slot(st.session_state, DATA, str(team_id))
PATHS = get_paths(st.session_state, DATA)
attach_reset_sidebar()

# 현재 루트에서 로드
teams  = pd.read_csv(PATHS["teams"])
tracks = pd.read_csv(PATHS["tracks"]).sort_values("round")
LOG_PATH = PATHS["crew_log"]

team_id = str(st.session_state.get("team_id"))
round_no = int(st.session_state.get("round", int(tracks["round"].min())))

# ---- 팀 상태 ----
if "team_id" not in teams.columns:
    st.error("teams.csv에 team_id 컬럼이 없습니다.")
    st.stop()
teams["team_id"] = teams["team_id"].astype(str)
if team_id not in set(teams["team_id"]):
    st.error(f"teams.csv에서 team_id={team_id} 를 찾지 못했습니다.")
    st.stop()

trow = teams.set_index("team_id").loc[team_id].to_dict()
defaults = {
    "pit_crew": 70, "team_morale": 70, "budget_musd": 120.0,
    "dev_efficiency": 70, "aero": 70, "engine": 70, "reliability": 70, "strategy": 75,
    "dev_speed": 1.00
}
for k, v in defaults.items():
    trow.setdefault(k, v)

brand_header("크루 훈련", "훈련 제안 → 선택 → 최종 제출(확정) → 효과 적용 & 로그 기록")

# ▶ 최근 결과 요약(있다면 상단 표시)
last = st.session_state.get("crew_last_result")
if last:
    with st.container(border=True):
        st.markdown("#### ✅ 최근 훈련 결과")
        st.markdown(f"- 적용 시각: {last['ts']}")
        st.markdown(f"- 예산: ${last['budget_before']:.2f}M → **${last['budget_after']:.2f}M**")
        if last.get("pit_crew_delta") is not None:
            st.markdown(f"- 피트 크루: +{last['pit_crew_delta']:.2f}p (현재 {last['pit_crew_after']:.2f})")
        if last.get("hr_summary"):
            hr = last["hr_summary"]
            st.markdown(f"- 개발 속도(dev_speed): {hr['dev_speed_after']:.3f}")
            st.markdown(f"- 전략(strategy): {hr['strategy_after']:.1f} · 신뢰성(reliability): {hr['reliability_after']:.1f}")
        with st.expander("상세 로그"):
            st.json(last.get("logs", []))

# ---- 전역 색상/버튼 ----
st.markdown(f"""
<style>
html, body, .stMarkdown, .stChatMessage, .stCaption, .stText,
label, p, h1, h2, h3, h4, h5, h6 {{ color: {F1["text"]} !important; }}
#finalsubmit div[data-testid="stButton"]>button,
#crewbtn div[data-testid="stButton"]>button {{
  width:100%; min-height:46px; line-height:46px;
}}
#finalsubmit div[data-testid="stButton"]>button {{ background:{F1["red"]} !important; border-color:{F1["red"]} !important; color:#fff !important; }}
#crewbtn div[data-testid="stButton"]>button {{ background:#2a2a31 !important; border-color:#2a2a31 !important; color:#fff !important; }}

/* disabled 상태 색상 고정 */
div[data-testid="stButton"] > button:disabled,
div[data-testid="stButton"] > button[disabled] {{
  color:#fff !important; -webkit-text-fill-color:#fff !important;
  opacity:0.6;
}}
</style>
""", unsafe_allow_html=True)

# ---- 유틸 ----
def _pill(text, color):
    return f"""<span style="display:inline-block; padding:2px 8px; border-radius:999px;
    font-size:.78rem; font-weight:700; color:white; background:{color};">{text}</span>"""

def _risk_pill(risk: str) -> str:
    r = (risk or "").lower()
    return {
        "low": _pill("LOW", "#2b9348"),
        "mid": _pill("MID", "#f9c74f"),
        "high": _pill("HIGH", "#f94144"),
    }.get(r, _pill("?", "#6c757d"))

def _predict_delta(plan: dict, state: dict) -> float:
    cur_pit = float(state.get("pit_crew", 70))
    diminishing = max(0.2, 1.0 - cur_pit/130.0)
    cost = float(plan.get("cost_musd", 0.0))
    ses  = int(plan.get("sessions", 1))
    hint = float(plan.get("pit_gain_hint", 0.5))
    base = hint * (0.35 + 0.25*(ses-1)) * (0.5 + 0.5*min(cost,5.0)/5.0)
    risk_mult = {"low":1.0, "mid":0.85, "high":0.7}.get((plan.get("fatigue_risk","mid") or "mid").lower(), 0.85)
    return base * 0.8 * risk_mult * diminishing * 10.0

def _stable_key(plan: dict) -> str:
    title = str(plan.get("title", ""))
    return hashlib.md5(title.encode("utf-8")).hexdigest()[:8]

# ---- 좌/우 ----
L, R = st.columns([0.62, 0.38])

with L:
    st.subheader("트레이닝 마스터 · 제안 받기")

    max_spend = float(pd.to_numeric([trow.get("budget_musd", 0.0)])[0])
    spend_default = min(5.0, max_spend) if max_spend > 0 else 0.0
    spend = st.slider("훈련 예산 상한(MUSD)", 0.0, max_spend, spend_default, 0.5,
                      help="상한이 높을수록 고강도 훈련안이 나올 수 있습니다.")
    tloc = dict(trow); tloc["team_id"] = team_id; tloc["budget_musd"] = float(spend)

    if st.button("LLM으로 훈련 제안 생성", type="primary", use_container_width=True):
        from f1sim.ai.llm_client import ask_llm_json, digest_inputs
        from f1sim.ai.schemas import CREW_TRAINING_PLAN_SCHEMA
        from f1sim.ai.prompts import system_common, prompt_crew_training

        inputs = {"team": tloc, "round": round_no, "max_budget_hint": float(spend)}
        js = ask_llm_json(
            CREW_TRAINING_PLAN_SCHEMA,
            system_prompt=system_common(),
            user_prompt=(
                # 인적자원 효과도 가능하면 제안하도록 요청
                prompt_crew_training(tloc, round_no, float(spend)) + "\n- Also propose optional human-resource effects (driver/dev/strategy/reliability).\n"
                f"- inputs_digest: {digest_inputs(inputs)}\n"
            )
        )
        st.session_state["crew_prop"] = js
        st.session_state["crew_picks"] = []
        st.success("훈련 제안을 수신했습니다.")

    prop = st.session_state.get("crew_prop")
    if prop:
        with st.expander("원본 제안 JSON 열기"):
            st.json(prop)

    if prop:
        plans = prop.get("plans", [])
        st.markdown("#### 👨‍🔧 브리핑")
        with st.chat_message("assistant"):
            st.markdown(
                f"현재 피트 크루 {int(trow['pit_crew'])}점, 팀 사기 {int(trow['team_morale'])}점 기준으로 "
                f"총 **{len(plans)}건**의 훈련안을 준비했습니다. 예산 상한 **${float(spend):.1f}M** 내에서 구성했어요."
            )
        st.markdown("---")
        st.markdown("#### 🔎 선택지")
        st.caption("체크한 항목은 우측 패널의 ‘최종 제출’에서 한 번에 확정됩니다. 안정성을 위해 '선택 확정'도 제공됩니다.")

        # 체크박스 → 선택 수집
        new_picks = []
        for i, p in enumerate(plans, 1):
            title = p.get("title","")
            cost  = float(p.get("cost_musd",0))
            ses   = int(p.get("sessions",1))
            risk  = p.get("fatigue_risk","mid")
            gain  = _predict_delta(p, trow)

            # 인적자원 힌트 뱃지
            hr_badges = []
            for k, txt, color in [
                ("driver_skill_hint","DRV","#3a86ff"),
                ("dev_speed_hint","DEV","#8338ec"),
                ("strategy_hint","STR","#ff006e"),
                ("reliability_hint","REL","#fb5607")
            ]:
                if p.get(k) is not None:
                    hr_badges.append(_pill(f"{txt}:{p[k]:.2f}", color))
            hr_html = " ".join(hr_badges)

            with st.container(border=True):
                c1, c2 = st.columns([0.70, 0.30])
                with c1:
                    st.markdown(f"**{i}. {title}** &nbsp; {_risk_pill(risk)} {hr_html}", unsafe_allow_html=True)
                    st.markdown(f"- 세션: {ses} · 비용: ${cost:.2f}M")
                    st.markdown(f"- 예상 상승: pit_crew +{gain:.1f}p")
                    st.caption(p.get("reason","사유 없음"))
                with c2:
                    key = f"pick_tr_{_stable_key(p)}"
                    checked = st.checkbox("선택", key=key)
                    if checked:
                        new_picks.append(p)

        # 선택 확정(스냅샷) 버튼
        col_fix1, col_fix2 = st.columns([1,1])
        with col_fix1:
            if st.button("선택 확정", key="btn_fix_picks", use_container_width=True):
                st.session_state["crew_picks"] = list(new_picks)
                st.session_state["crew_picks_fixed_at"] = time.time()
                st.success(f"{len(new_picks)}개 선택을 확정했습니다.")
        with col_fix2:
            st.caption("체크만으로도 제출 가능하지만, 확정하면 리런드롭에 더 안전합니다.")

        # 기본 동기화(확정 없으면 체크 상태 반영)
        if not st.session_state.get("crew_picks"):
            st.session_state["crew_picks"] = list(new_picks)

with R:
    st.subheader("최종 제출 · 로그")
    picks = st.session_state.get("crew_picks", []) or []
    total_cost = sum(float(p.get("cost_musd",0)) for p in picks) if picks else 0.0

    # 🛡️ 방탄 복구: picks가 비면 체크박스 상태로 복구
    if not picks and st.session_state.get("crew_prop"):
        plans = st.session_state["crew_prop"].get("plans", [])
        rec = []
        for p in plans:
            key = f"pick_tr_{_stable_key(p)}"
            if st.session_state.get(key, False):
                rec.append(p)
        if rec:
            picks = rec
            st.session_state["crew_picks"] = rec
            total_cost = sum(float(p.get("cost_musd",0)) for p in picks)

    if picks:
        st.markdown("**선택된 항목**")
        for i, p in enumerate(picks, 1):
            st.write(f"- {i}) {p.get('title','?')} · 세션 {int(p.get('sessions',1))} · ${float(p.get('cost_musd',0.0)):.2f}M")
        # 가상의 소요 시간(게임 시간) 안내: 세션당 2시간 가정
        total_hours = sum(int(p.get("sessions",1)) for p in picks) * 2
        st.info(f"예상 비용: ${total_cost:.2f}M / 보유 예산: ${float(trow.get('budget_musd',0.0)):.2f}M · 예상 소요(게임 시간): 약 {total_hours}시간 (즉시 적용 모드)")

    c1, c2 = st.columns(2)
    with c1:
        st.markdown('<div id="finalsubmit">', unsafe_allow_html=True)
        submit = st.button("최종 제출", use_container_width=True, disabled=(not bool(st.session_state.get("crew_picks"))))
        st.markdown('</div>', unsafe_allow_html=True)
    with c2:
        st.markdown('<div id="crewbtn">', unsafe_allow_html=True)
        if st.button("프리 레이스로 이동", use_container_width=True):
            st.switch_page("pages/04_pre_race.py")
        st.markdown('</div>', unsafe_allow_html=True)

    if submit:
        st.session_state["confirm_ct_submit"] = True

    # 확인 단계
    if st.session_state.get("confirm_ct_submit"):
        st.warning("훈련을 진행하겠습니까? 훈련비는 확정 후 회수가 불가능합니다.")
        cc1, cc2 = st.columns(2)
        with cc1:
            st.markdown('<div id="finalsubmit">', unsafe_allow_html=True)
            if st.button("확인", use_container_width=True, key="ct_yes"):
                from f1sim.ai.llm_client import ask_llm_json, digest_inputs
                from f1sim.ai.schemas import CREW_TRAINING_OUTCOME_SCHEMA
                from f1sim.ai.prompts import system_common, prompt_crew_training_outcome
                from f1sim.ai.apply_effects import apply_crew_training_effect, apply_hr_side_effects

                with st.spinner("훈련 결과 생성 및 적용 중..."):
                    st.toast("LLM에게 훈련 결과를 요청 중...", icon="🧠")
                    inputs = {"team":{"team_id":team_id, **trow}, "round":round_no, "picks":picks}
                    outcome = ask_llm_json(
                        CREW_TRAINING_OUTCOME_SCHEMA,
                        system_prompt=system_common(),
                        user_prompt=(
                            prompt_crew_training_outcome(trow, round_no, picks) +
                            "\n- If available, also output human-resource fields (driver/dev/strategy/reliability)\n"
                            f"- inputs_digest: {digest_inputs(inputs)}\n"
                        ),
                        temperature=0.5
                    )

                    # 1) 예산 차감
                    teams_df = pd.read_csv(PATHS["teams"])
                    teams_df["team_id"] = teams_df["team_id"].astype(str)
                    teams_df = teams_df.set_index("team_id")
                    cur_budget = float(pd.to_numeric([teams_df.loc[team_id, "budget_musd"]])[0]) if "budget_musd" in teams_df.columns else 0.0
                    new_budget = round(max(0.0, cur_budget - float(total_cost)), 2)
                    teams_df.loc[team_id, "budget_musd"] = new_budget

                    # 2) 팀 능력(피트/사기) 적용
                    state = teams_df.loc[team_id].to_dict()
                    for k, v in defaults.items(): state.setdefault(k, v)
                    out_map = {o.get("ref_title", o.get("title","")): o for o in outcome.get("outcomes", [])}
                    logs = []
                    pit_delta_total = 0.0
                    for p in picks:
                        o = out_map.get(p.get("title",""), {})
                        before = float(state.get("pit_crew", 70))
                        state = apply_crew_training_effect(state, p, o)
                        after = float(state.get("pit_crew", 70))
                        pit_delta_total += (after-before)
                        logs.append({
                            "ts": datetime.now().isoformat(timespec="seconds"),
                            "round": round_no,
                            "team_id": team_id,
                            "title": p.get("title",""),
                            "sessions": int(p.get("sessions",1)),
                            "risk": p.get("fatigue_risk",""),
                            "cost_musd": float(p.get("cost_musd",0)),
                            "pit_gain_applied": round(after-before, 2),
                            "morale_delta": float(o.get("morale_delta",0.0)),
                            "incidents": "; ".join(o.get("incidents",[])) if isinstance(o.get("incidents",[]), list) else str(o.get("incidents","")),
                            "narrative": o.get("narrative","")
                        })

                    # 3) 팀 state 저장
                    for k, v in state.items():
                        teams_df.loc[team_id, k] = v
                    teams_df.reset_index().to_csv(PATHS["teams"], index=False, encoding="utf-8")

                    # 4) HR 사이드 효과(드라이버/개발/전략/신뢰성) 적용
                    hr_summary = apply_hr_side_effects(PATHS["root"], team_id, picks, outcome.get("outcomes", []))

                    # 5) 로그 저장
                    if LOG_PATH.exists():
                        try:
                            log_df = pd.read_csv(LOG_PATH)
                        except Exception:
                            log_df = pd.DataFrame(columns=list(logs[0].keys()))
                    else:
                        log_df = pd.DataFrame(columns=list(logs[0].keys()))
                    log_df = pd.concat([log_df, pd.DataFrame(logs)], ignore_index=True)
                    log_df.to_csv(LOG_PATH, index=False, encoding="utf-8")

                    # 6) 즉시 재로드로 수치 반영(예산/능력치)
                    teams_latest = pd.read_csv(PATHS["teams"])
                    teams_latest["team_id"] = teams_latest["team_id"].astype(str)
                    t_after = teams_latest.set_index("team_id").loc[team_id].to_dict()

                    # 7) 요약 패널 표시용 세션 저장
                    st.session_state["crew_last_result"] = {
                        "ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "budget_before": cur_budget,
                        "budget_after": new_budget,
                        "pit_crew_delta": pit_delta_total,
                        "pit_crew_after": float(t_after.get("pit_crew", 0)),
                        "hr_summary": hr_summary,
                        "logs": logs
                    }

                st.success("훈련이 적용되었습니다. 예산 차감 및 능력치가 반영되었습니다.")
                st.session_state["crew_picks"] = []
                st.session_state["confirm_ct_submit"] = False
                st.rerun()
            st.markdown('</div>', unsafe_allow_html=True)

        with cc2:
            st.markdown('<div id="crewbtn">', unsafe_allow_html=True)
            if st.button("취소", use_container_width=True, key="ct_no"):
                st.session_state["confirm_ct_submit"] = False
                st.info("제출이 취소되었습니다.")
                st.rerun()
            st.markdown('</div>', unsafe_allow_html=True)

# --- 버튼 텍스트 가독성 보정(맨 마지막에 강제) ---
st.markdown("""
<style>
div[data-testid="stButton"] > button,
div[data-testid="stButton"] > button * {
  color:#000 !important; -webkit-text-fill-color:#000 !important;
}
#finalsubmit div[data-testid="stButton"]>button,
#finalsubmit div[data-testid="stButton"]>button *,
#crewbtn div[data-testid="stButton"]>button,
#crewbtn div[data-testid="stButton"]>button *{
  color:#fff !important; -webkit-text-fill-color:#fff !important;
}
</style>
""", unsafe_allow_html=True)
