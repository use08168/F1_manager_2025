# f1sim/ai/apply_effects.py
# -*- coding: utf-8 -*-
from __future__ import annotations
from pathlib import Path
from typing import List, Dict, Tuple
import pandas as pd
import math

# 팀 측정치 스케일(권장값)
PIT_GAIN_POINT_FACTOR = 10.0   # 0..1 → 0..10p 가산
MORALE_POINT_FACTOR   = 5.0    # Δmorale 실효 반영 배율(팀 사기)
CLIP_MIN, CLIP_MAX     = 0.0, 100.0

def _clip(x, lo=CLIP_MIN, hi=CLIP_MAX):
    return float(min(hi, max(lo, float(x))))

def _risk_mult(risk: str) -> float:
    return {"low":1.0, "mid":0.85, "high":0.7}.get((risk or "mid").lower(), 0.85)

def apply_crew_training_effect(state: dict, plan: dict, outcome: dict) -> dict:
    """
    기존 페이지 코드 호환: state(dict) in/out.
    - pit_crew: 계획·결과를 이용해 포인트 가산
    - team_morale: morale_delta 가산
    (드라이버/개발/전략/신뢰성은 파일 측면 변경이 필요하므로 별도 apply_hr_side_effects에서 처리)
    """
    state = dict(state)  # copy
    # 기본값 보정
    state.setdefault("pit_crew", 70.0)
    state.setdefault("team_morale", 70.0)

    sessions = int(plan.get("sessions", 1))
    risk = plan.get("fatigue_risk", "mid")

    pit_factor = float(outcome.get("realized_pit_gain_factor", 0.0))
    morale_d   = float(outcome.get("morale_delta", 0.0))

    # 점감효과(숙련도 높을수록 이득 작아짐)
    diminishing = max(0.2, 1.0 - float(state["pit_crew"])/130.0)
    base = pit_factor * (0.35 + 0.25*(sessions-1)) * _risk_mult(risk)
    delta_pit = base * PIT_GAIN_POINT_FACTOR * diminishing

    state["pit_crew"] = _clip(float(state["pit_crew"]) + delta_pit)
    state["team_morale"] = _clip(float(state["team_morale"]) + morale_d * MORALE_POINT_FACTOR, -50.0, 150.0)
    return state

def apply_hr_side_effects(root: Path, team_id: str,
                          plans: List[dict], outcomes: List[dict]) -> dict:
    """
    파일(세이브 슬롯 CSV)에 인적자원 효과를 반영:
      - drivers.csv: skill, tire_mgmt (team_id 소속 전체 혹은 target_driver_ids만)
      - teams.csv: dev_speed(배수), strategy, reliability
    반환: 요약 dict
    """
    team_id = str(team_id)

    # outcomes를 title 키로 매칭(계획과 연결)
    out_by_title = {o.get("ref_title", o.get("title","")): o for o in outcomes}

    # 로드
    t_p = root / "teams.csv"
    d_p = root / "drivers.csv"
    teams = pd.read_csv(t_p)
    drivers = pd.read_csv(d_p)

    # 기본 컬럼 보정
    for col, default in [("dev_speed", 1.00), ("strategy", 75.0), ("reliability", 70.0)]:
        if col not in teams.columns: teams[col] = default
    for col, default in [("skill", 75.0), ("tire_mgmt", 70.0)]:
        if col not in drivers.columns: drivers[col] = default

    teams["team_id"] = teams["team_id"].astype(str)
    drivers["team_id"] = drivers["team_id"].astype(str)

    if team_id not in set(teams["team_id"]):
        raise ValueError(f"team_id={team_id} not found in teams.csv")

    # 수정 누적
    t_mask = teams["team_id"] == team_id
    dev_speed_before = float(teams.loc[t_mask, "dev_speed"].iloc[0])
    strategy_before  = float(teams.loc[t_mask, "strategy"].iloc[0])
    reli_before      = float(teams.loc[t_mask, "reliability"].iloc[0])

    driver_rows = drivers[drivers["team_id"] == team_id].copy()
    d_ids = list(driver_rows.index)
    skill_before = driver_rows["skill"].astype(float).tolist()
    tire_before  = driver_rows["tire_mgmt"].astype(float).tolist()

    # 적용
    for p in plans:
        title = p.get("title","")
        o = out_by_title.get(title, {})

        # 대상 드라이버
        targets = o.get("target_driver_ids") or p.get("target_driver_ids") or list(driver_rows["driver_id"].astype(str))
        # 스케일: 드라이버 포인트는 ±로, dev_speed는 곱셈, 전략/신뢰성은 ±
        d_skill = float(o.get("realized_driver_skill_delta", 0.0))
        d_tmgmt = float(o.get("realized_tire_mgmt_delta", 0.0))
        dev_mul = float(o.get("dev_speed_multiplier", 1.0))
        strat_d = float(o.get("strategy_delta", 0.0))
        reli_d  = float(o.get("reliability_delta", 0.0))

        # 팀 반영
        teams.loc[t_mask, "dev_speed"] = max(0.8, min(1.3, dev_speed_before * dev_mul))
        teams.loc[t_mask, "strategy"]  = _clip(strategy_before + strat_d)
        teams.loc[t_mask, "reliability"] = _clip(reli_before + reli_d)
        # 드라이버 반영(해당 대상만)
        if "driver_id" in drivers.columns:
            drivers["driver_id"] = drivers["driver_id"].astype(str)
            dmask = (drivers["team_id"] == team_id) & (drivers["driver_id"].isin([str(x) for x in targets]))
        else:
            # driver_id 없으면 팀 소속 전체에 반영
            dmask = (drivers["team_id"] == team_id)

        drivers.loc[dmask, "skill"]      = drivers.loc[dmask, "skill"].astype(float).clip(CLIP_MIN, CLIP_MAX) + d_skill
        drivers.loc[dmask, "tire_mgmt"]  = drivers.loc[dmask, "tire_mgmt"].astype(float).clip(CLIP_MIN, CLIP_MAX) + d_tmgmt

    # 클립
    teams["strategy"]   = teams["strategy"].astype(float).clip(CLIP_MIN, CLIP_MAX)
    teams["reliability"]= teams["reliability"].astype(float).clip(CLIP_MIN, CLIP_MAX)
    drivers["skill"]    = drivers["skill"].astype(float).clip(CLIP_MIN, CLIP_MAX)
    drivers["tire_mgmt"]= drivers["tire_mgmt"].astype(float).clip(CLIP_MIN, CLIP_MAX)

    # 저장
    teams.to_csv(t_p, index=False, encoding="utf-8")
    drivers.to_csv(d_p, index=False, encoding="utf-8")

    # 요약
    return {
        "dev_speed_after": float(teams.loc[t_mask, "dev_speed"].iloc[0]),
        "strategy_after":  float(teams.loc[t_mask, "strategy"].iloc[0]),
        "reliability_after": float(teams.loc[t_mask, "reliability"].iloc[0]),
    }
