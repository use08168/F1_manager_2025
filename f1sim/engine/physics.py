# -*- coding: utf-8 -*-
from __future__ import annotations
import numpy as np
from ..config import VREF_KMH, ALPHA_PACE, BETA_GRIP, GAMMA_WET, BASE_DEG, SEED

_rng = np.random.default_rng(SEED)

def ref_lap_time_sec(length_km: float) -> float:
    """트랙 길이로 기준 랩타임(초) 생성."""
    return float(length_km) / (VREF_KMH/3.6)

def perf_scalar(driver_row, team_row, *, quali_mode: bool, wet: bool, grip_idx: float) -> float:
    """드라이버/팀/그립을 0..1 스칼라로 요약(간단판)."""
    def norm(x): return float(x)/100.0
    t_perf = 0.5*norm(team_row["aero"]) + 0.5*norm(team_row["engine"])
    d_base = 0.6*norm(driver_row["pace"]) + 0.2*norm(driver_row["consistency"]) + 0.2*norm(driver_row["awareness"])
    d_adj  = (0.6*norm(driver_row["quali"]) + 0.4*d_base) if quali_mode \
             else ( (1-(0.5 if wet else 0.2))*d_base + (0.5 if wet else 0.2)*norm(driver_row["wet"]) )
    g_bonus = (float(grip_idx) - 0.5) * 0.2
    return max(0.0, min(1.0, 0.5*t_perf + 0.5*d_adj + g_bonus))

def lap_time_from_perf(ref_s: float, perf: float, *, grip_idx: float, wet: bool, noise: float) -> float:
    """성능→랩타임 변환."""
    base = float(ref_s) * (1.0 - ALPHA_PACE*perf + BETA_GRIP*(1.0 - float(grip_idx)))
    if wet: base *= (1.0 + GAMMA_WET)
    base *= float(_rng.normal(1.0, float(noise)))
    return max(0.0, base)

def stint_multiplier(comp: str, abrasion: float, tire_mgmt: float) -> float:
    """스틴트 평균 페이스 배율(마모/관리 반영)."""
    base_deg = BASE_DEG[comp] * (0.5 + 0.9*float(abrasion))
    mg = (100.0 - float(tire_mgmt))/100.0
    return 1.0 + base_deg*(1.0 + 0.6*mg)

def pit_loss_sec(pit_loss_track: float, *, sc_active: bool, pit_crew: float) -> float:
    """피트 손실(트랙 손실 × SC 할인 × 피트크루 보정)."""
    crew_bonus = (100.0 - float(pit_crew))/100.0
    loss = float(pit_loss_track) * (0.75 if sc_active else 1.0) * (1.0 + 0.06*crew_bonus)
    return float(loss)
