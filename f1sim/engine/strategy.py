# -*- coding: utf-8 -*-
from __future__ import annotations
from typing import List, Tuple
import numpy as np
from ..config import ABR_SPLIT, SEED

_rng = np.random.default_rng(SEED)

def choose_strategy(laps: int, abrasion: float) -> List[Tuple[str,int]]:
    """
    abrasion < ABR_SPLIT → 2스틴트(1스톱)
    abrasion ≥ ABR_SPLIT → 3스틴트(2스톱)
    컴파운드는 간단 무작위.
    """
    laps = int(laps)
    if float(abrasion) < ABR_SPLIT:
        segs = [laps//2, laps - laps//2]
        comps = ["M","H"]
    else:
        s1, s2 = int(laps*0.30), int(laps*0.35)
        segs = [s1, s2, laps - s1 - s2]
        comps = ["S","M","H"]
    stints = []
    for seg in segs:
        stints.append((_rng.choice(comps).item() if hasattr(_rng.choice(comps), "item") else _rng.choice(comps), int(seg)))
    return stints
