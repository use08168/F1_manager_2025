# f1sim/ai/prompts.py
# -*- coding: utf-8 -*-

def system_common() -> str:
    return (
        "당신은 F1 팀 운영 시뮬레이터의 설계 도우미입니다.\n"
        "규칙:\n"
        "- 반드시 '유효한 JSON'만 출력합니다. 설명/마크다운/코드블록 금지.\n"
        "- 제공된 JSON 스키마를 엄격히 준수합니다.\n"
        "- 수치는 '가중치/힌트'로만 제시하고 최종 수치 계산은 엔진이 합니다.\n"
        "- 리스크와 트레이드오프를 반드시 포함합니다.\n"
    )

def prompt_research(team_state: dict, next_tracks: list, round_no: int) -> str:
    tid   = team_state.get("team_id", "UNKNOWN")
    aero  = team_state.get("aero", 70)
    eng   = team_state.get("engine", 70)
    reli  = team_state.get("reliability", 70)
    dev   = team_state.get("dev_efficiency", 70)
    pit   = team_state.get("pit_crew", 70)
    strat = team_state.get("strategy", 75)
    bud   = team_state.get("budget_musd", 120.0)

    return f"""
입력:
- round: {round_no}
- team_id: {tid}
- 현재 스탯: aero={aero}, engine={eng}, reliability={reli}, dev_efficiency={dev},
  pit_crew={pit}, strategy={strat}, budget_musd={bud}
- 다음 트랙 3개: {next_tracks}

요구:
- module='research' JSON을 schema에 맞게 출력.
- decisions는 2~4개. area는 ['vehicle_design','front_wing','rear_wing','brakes','engine'] 중에서만.
- 각 결정에 반드시 eta_rounds 포함(1~6).
- efficiency와 expected_gain_hint는 0~1 사이 가중치로 제시.
- 총 비용이 입력된 예산 상한을 넘지 않도록 구성.
- 예산 상한이 높아질수록 복잡도가 증가해 ETA가 1~2R 늘어날 수 있음을 반영.
- narrative에 간단한 전략 조언 포함.
"""

# --- Crew training ---

def prompt_crew_training(team_state: dict, round_no: int, max_budget_hint: float) -> str:
    tid   = team_state.get("team_id","UNKNOWN")
    pit   = team_state.get("pit_crew",70)
    morale= team_state.get("team_morale",70)
    bud   = team_state.get("budget_musd",120.0)

    return f"""
입력:
- round: {round_no}
- team_id: {tid}
- 현재 스탯: pit_crew={pit}, team_morale={morale}, budget_musd={bud}
- 훈련 예산 상한(max_budget_hint)={max_budget_hint}

요구:
- module='crew_training' JSON을 schema에 맞게 출력.
- 3~5개의 훈련안을 제시.
- 각 훈련안은 focus ∈ ['pitstop_choreo','wheel_gun','jack_team','endurance','crisis_sim','equipment_calib'] 중 하나.
- sessions는 1~4, fatigue_risk는 ['low','mid','high'] 중 하나.
- pit_gain_hint는 0~1, morale_hint는 -1~1 범위의 가중치 힌트.
- 총 비용은 예산 상한을 넘지 않도록 하고, 상한이 높을수록 더 강도 높은/많은 세션 제시.
- 각 안에 간단한 이유(reason) 포함.
- narrative에 오늘의 훈련 방향/주의점 간단 요약.
"""

def prompt_crew_training_outcome(team_state: dict, round_no: int, picks: list[dict]) -> str:
    """
    선택된 훈련안(picks)을 바탕으로 실제 결과(가중치/사건/내러티브)를 출력하도록 요청.
    """
    tid   = team_state.get("team_id","UNKNOWN")
    pit   = team_state.get("pit_crew",70)
    morale= team_state.get("team_morale",70)

    return f"""
입력:
- round: {round_no}
- team_id: {tid}
- 현재 스탯: pit_crew={pit}, team_morale={morale}
- 선택된 훈련안 목록(제목/세션/리스크/코스트 등): {picks}

요구:
- module='crew_training_outcome' JSON을 schema에 맞게 출력.
- outcomes는 각 훈련안 별로 1개씩.
- realized_pit_gain_factor는 0~1 범위(낮은 피로/낮은 리스크일수록 높을 가능성).
- morale_delta는 -2..+2 범위(고강도/피로 누적은 음수 가능).
- incidents는 훈련 중 발생한 이슈 요약(없으면 빈 배열).
- narrative에 세션별 간략한 하이라이트/교훈을 2~4문장으로 작성.
"""

# f1sim/ai/prompts.py 에 추가
def system_ai_race_control():
    return (
        "You are generating a compact race-control schedule for an SVG race animation. "
        "Return ONLY JSON that matches the schema. No extra commentary."
    )

def prompt_ai_race_control(roster, circuit_name: str, lap_base_sec: float, player_team: str):
    drv_lines = "\n".join([f"- {r['name']} ({r['team']})" for r in roster])
    return (
        f"Circuit: {circuit_name}\n"
        f"Reference lap time (sec): {lap_base_sec:.3f}\n"
        f"Drivers (in roster order):\n{drv_lines}\n\n"
        f"The player team '{player_team}' must be left unplanned (empty pace & pit_laps). "
        "For each other team, propose 2–3 pace segments with vmul in [0.98, 1.03] and 0–2 pit stops. "
        "Keep schedules smooth and reasonable.\n"
        "Output JSON with top-level key 'plans', aligned by team name."
    )