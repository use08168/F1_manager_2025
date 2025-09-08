# f1sim/event_state.py
# -*- coding: utf-8 -*-
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List
import math
import copy

DRY = ("soft", "medium", "hard")
WET = ("intermediate", "wet")
ALL_COMPOUNDS = DRY + WET

TIRE_SETS_DEFAULT = {
    "hard": 2, "medium": 3, "soft": 8, "intermediate": 4, "wet": 3
}  # 총 20세트

@dataclass
class TireSet:
    compound: str
    life: float = 1.0  # 1.0=새거, 0.0=수명 끝
    used: bool = False

@dataclass
class DriverInv:
    sets: Dict[str, List[TireSet]] = field(default_factory=dict)

    def ensure_default(self):
        if self.sets:
            return
        for c, n in TIRE_SETS_DEFAULT.items():
            self.sets[c] = [TireSet(compound=c, life=1.0, used=False) for _ in range(n)]

    def mount_and_update(self, compound: str, life_left: float):
        if compound not in self.sets or not self.sets[compound]:
            return
        tgt = None
        for s in self.sets[compound]:
            if not s.used:
                tgt = s
                break
        if tgt is None:
            tgt = max(self.sets[compound], key=lambda x: x.life)
        tgt.used = True
        tgt.life = max(0.0, min(1.0, float(life_left)))

    def available_counts(self) -> Dict[str, int]:
        return {c: sum(1 for s in self.sets.get(c, []) if not s.used) for c in ALL_COMPOUNDS}

@dataclass
class EventState:
    circuit: str
    roster: List[dict]
    tire_by_driver: Dict[str, DriverInv] = field(default_factory=dict)
    q1_results: List[dict] = field(default_factory=list)
    q2_results: List[dict] = field(default_factory=list)
    q3_results: List[dict] = field(default_factory=list)
    grid: List[dict] = field(default_factory=list)

    def dkey(self, driver_name: str, team: str) -> str:
        return f"{team}::{driver_name}"

    def ensure_inventories(self):
        for d in self.roster:
            k = self.dkey(d["name"], d["team"])
            if k not in self.tire_by_driver:
                self.tire_by_driver[k] = DriverInv()
                self.tire_by_driver[k].ensure_default()

    def survivors_for_q2(self) -> List[str]:
        if not self.q1_results: return []
        order = [r for r in self.q1_results if math.isfinite(r.get("best", math.inf))]
        order.sort(key=lambda x: x["best"])
        return [self.dkey(r["name"], r["team"]) for r in order[:15]]

    def survivors_for_q3(self) -> List[str]:
        if not self.q2_results: return []
        order = [r for r in self.q2_results if math.isfinite(r.get("best", math.inf))]
        order.sort(key=lambda x: x["best"])
        return [self.dkey(r["name"], r["team"]) for r in order[:10]]

    def compute_grid(self):
        g = [None]*20
        if self.q3_results:
            q3o = [r for r in self.q3_results if math.isfinite(r.get("best", math.inf))]
            q3o.sort(key=lambda x: x["best"])
            for i, r in enumerate(q3o[:10]):
                g[i] = r
        if self.q2_results:
            q2o = [r for r in self.q2_results if math.isfinite(r.get("best", math.inf))]
            q2o.sort(key=lambda x: x["best"])
            tail = q2o[10:15]
            for i, r in enumerate(tail):
                g[10+i] = r
        if self.q1_results:
            q1o = [r for r in self.q1_results if math.isfinite(r.get("best", math.inf))]
            q1o.sort(key=lambda x: x["best"])
            tail = q1o[15:20]
            for i, r in enumerate(tail):
                g[15+i] = r
        pool = []
        for arr in (self.q3_results, self.q2_results, self.q1_results):
            if not arr: continue
            for r in arr:
                if r not in g:
                    pool.append(r)
        j = 19
        for r in pool:
            while j >= 0 and g[j] is not None:
                j -= 1
            if j >= 0:
                g[j] = r
                j -= 1
        self.grid = []
        for i, r in enumerate(g):
            if not r: continue
            item = copy.deepcopy(r)
            item["grid_pos"] = i+1
            self.grid.append(item)

    def _register_results(self, session: str, results: List[dict]):
        safe = []
        for r in results:
            best = float(r.get("best")) if r.get("best") is not None else math.inf
            safe.append({
                "name": r["name"], "team": r["team"], "abbr": r.get("abbr",""),
                "color": r.get("color",""), "best": best,
                "compound": r.get("compound","soft"),
                "tireLife": float(r.get("tireLife", 1.0)),
            })
        safe.sort(key=lambda x: x["best"])
        if session == "Q1": self.q1_results = safe
        elif session == "Q2": self.q2_results = safe
        elif session == "Q3": self.q3_results = safe

    def _apply_tire_updates(self, results: List[dict]):
        self.ensure_inventories()
        for r in results:
            k = self.dkey(r["name"], r["team"])
            inv = self.tire_by_driver.get(k)
            if not inv: continue
            comp = (r.get("compound") or "soft").lower()
            life_left = float(r.get("tireLife", 1.0))
            inv.mount_and_update(comp, life_left)

    def register_session(self, session: str, results: List[dict]):
        self._register_results(session, results)
        self._apply_tire_updates(results)
        if session == "Q3":
            self.compute_grid()

def ensure_event_state(st_session_state, circuit: str, roster: List[dict]) -> EventState:
    key = "event_state"
    if key not in st_session_state or st_session_state[key].circuit != circuit:
        st_session_state[key] = EventState(circuit=circuit, roster=roster)
        st_session_state[key].ensure_inventories()
    return st_session_state[key]

def survivors_for_session(state: EventState, session: str) -> List[str]:
    if session == "Q1":
        return [state.dkey(d["name"], d["team"]) for d in state.roster]
    if session == "Q2":
        return state.survivors_for_q2()
    if session == "Q3":
        return state.survivors_for_q3()
    return []

def filter_roster_by_keys(roster: List[dict], keys: List[str], keyfunc) -> List[dict]:
    s = set(keys)
    return [d for d in roster if keyfunc(d) in s]
