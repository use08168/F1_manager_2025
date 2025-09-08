# -*- coding: utf-8 -*-
from __future__ import annotations
from typing import Dict, List, Tuple
import numpy as np
from ..config import SEED, SC_LAPS, VSC_LAPS, BASE_DNF, AWARE_SAFE, AGGRISK, RELRISK

_rng = np.random.default_rng(SEED)

def sample_safety_periods(total_laps: int, p_sc: float, p_vsc: float) -> Dict[str, List[Tuple[int,int]]]:
    """간단 SC/VSC 생성: 각 최대 2회."""
    ev = {"SC": [], "VSC": []}
    for kind, p, rng_laps in (("SC", p_sc, SC_LAPS), ("VSC", p_vsc, VSC_LAPS)):
        for _ in range(2):
            if float(_rng.random()) < float(p):
                length = int(_rng.integers(rng_laps[0], rng_laps[1]+1))
                start  = int(_rng.integers(5, max(6, int(total_laps)-5)))
                end    = int(min(int(total_laps), start + length))
                ev[kind].append((start, end))
    return ev

def is_in_any(lap: int, ranges: List[Tuple[int,int]]) -> bool:
    return any(int(s) <= int(lap) <= int(e) for (s, e) in ranges)

def rain_flag(p_rain: float) -> bool:
    return bool(_rng.random() < float(p_rain))

def dnf_flag(driver_row, team_row) -> bool:
    """완주 실패 여부(한 레이스 전체에서 한 번이라도)."""
    def norm(x): return float(x)/100.0
    p = BASE_DNF \
        + RELRISK * (1.0 - norm(team_row["reliability"])) \
        + AGGRISK * norm(driver_row["aggression"]) \
        - AWARE_SAFE * norm(driver_row["awareness"])
    p = max(0.001, min(0.30, float(p)))
    return bool(_rng.random() < p)
