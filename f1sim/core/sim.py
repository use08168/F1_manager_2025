# f1sim/core/sim.py
# -*- coding: utf-8 -*-
from __future__ import annotations
from pathlib import Path
from typing import Tuple, Dict, List
import json

import numpy as np
import pandas as pd

from ..engine.physics import (
    ref_lap_time_sec,
    perf_scalar,
    lap_time_from_perf,
    stint_multiplier,
    pit_loss_sec,
)
from ..engine.events import sample_safety_periods, is_in_any, rain_flag, dnf_flag
from ..engine.strategy import choose_strategy
from ..config import QUAL_NOISE, RACE_NOISE, SEED
from ..config import SC_FACTOR as _SCF, VSC_FACTOR as _VSCF

# 전역 RNG (엔진 내부 SEED와 동일)
_rng = np.random.default_rng(SEED)

# 필수 스키마(최소 요건)
REQUIRED_TRACKS = [
    "round", "name", "length_km", "laps",
    "grip_index", "abrasion_index", "pit_loss_sec",
    "rain_base_prob", "sc_base_prob", "vsc_base_prob",
]
REQUIRED_TEAMS = ["team_id", "name", "pit_crew"]
REQUIRED_DRIVERS = ["driver_id", "team_id", "name", "skill", "tire_mgmt"]  # 데이터 호환용 최소세트


# ─────────────────────────────────────────────────────────────────────────────
# 유틸
# ─────────────────────────────────────────────────────────────────────────────
def assert_csv_schema(df: pd.DataFrame, req: List[str], label: str) -> None:
    missing = [c for c in req if c not in df.columns]
    if missing:
        raise ValueError(f"{label} CSV missing columns: {missing}")


def _load_pre_bonus_map(root: Path, round_no: int) -> Dict[str, float]:
    """
    프리 레이스에서 산출한 드라이버별 보너스(0.0~0.05 권장)를 로드한다.
    파일 패턴: root/sim/pre_bonus_round_{RR}_{team_id}.csv
      - 컬럼: driver_id, bonus_decimal (필수), 그 외 무시
    """
    m: Dict[str, float] = {}
    simdir = Path(root) / "sim"
    if not simdir.exists():
        return m
    for p in simdir.glob(f"pre_bonus_round_{round_no:02d}_*.csv"):
        try:
            df = pd.read_csv(p)
            if "driver_id" in df.columns and "bonus_decimal" in df.columns:
                for _, r in df.iterrows():
                    did = str(r["driver_id"]).strip()
                    bonus = float(r["bonus_decimal"])
                    if did:
                        # 안전 범위 클램프 (최대 +5% 정도)
                        m[did] = max(0.0, min(0.05, bonus))
        except Exception:
            # 손상 파일은 무시
            pass
    return m


def _load_round(round_no: int, root: Path):
    """
    현재 세이브 루트(root) 기준으로 라운드/팀/드라이버/로스터를 불러온다.
    - root/teams.csv, root/drivers.csv, root/tracks.csv 사용
    - (선택) root/roster_round_{RR}.csv 있으면 우선 적용
    """
    root = Path(root)

    tracks = pd.read_csv(root / "tracks.csv")
    teams = pd.read_csv(root / "teams.csv")
    drivers = pd.read_csv(root / "drivers.csv")

    assert_csv_schema(tracks, REQUIRED_TRACKS, "tracks")
    assert_csv_schema(teams, REQUIRED_TEAMS, "teams")
    assert_csv_schema(drivers, REQUIRED_DRIVERS, "drivers")

    if round_no not in set(tracks["round"]):
        raise ValueError(f"invalid round={round_no}")

    track = tracks.loc[tracks["round"] == round_no].iloc[0]

    # (선택) 라운드별 로스터 사용
    roster_path = root / f"roster_round_{round_no:02d}.csv"
    if roster_path.exists():
        roster = pd.read_csv(roster_path)
        pairs = [
            (
                str(r["team_id"]),
                [str(r["driver_slot_1"]), str(r["driver_slot_2"])],
            )
            for _, r in roster.iterrows()
        ]
    else:
        # 기본: team_id로 그룹핑하여 각 팀 상위 2명
        g = drivers.groupby("team_id")["driver_id"].apply(list).to_dict()
        pairs: List[tuple[str, List[str]]] = []
        for t, ids in g.items():
            ids = [str(x) for x in ids]
            if len(ids) < 2:
                raise ValueError(f"{t}: 드라이버가 2명 미만")
            pairs.append((str(t), ids[:2]))

    # 인덱스 세팅
    teams_idx = teams.set_index("team_id")
    drivers_idx = drivers.set_index("driver_id")

    return track, teams_idx, drivers_idx, pairs


# ─────────────────────────────────────────────────────────────────────────────
# 퀄리파잉
# ─────────────────────────────────────────────────────────────────────────────
def run_qualifying(round_no: int, root: Path) -> pd.DataFrame:
    """
    - root/sim/quali_round_{RR}.csv 저장
    - 프리 레이스 보너스가 있으면 perf × (1 + bonus) 반영
    """
    root = Path(root)
    (root / "sim").mkdir(parents=True, exist_ok=True)

    track, teams, drivers, pairs = _load_round(round_no, root)
    wet = False  # 퀄리는 기본 건조로 가정
    ref = ref_lap_time_sec(float(track["length_km"]))

    bonus_map = _load_pre_bonus_map(root, round_no)

    rows = []
    for team_id, dids in pairs:
        for did in dids:
            drow = drivers.loc[str(did)]
            trow = teams.loc[str(team_id)]
            perf = perf_scalar(
                drow, trow,
                quali_mode=True, wet=wet, grip_idx=float(track["grip_index"])
            )
            # 프리 보너스(있으면 약간 가산)
            b = float(bonus_map.get(str(did), 0.0))
            perf = max(0.0, min(1.2, perf * (1.0 + b)))

            lap = lap_time_from_perf(
                ref, perf,
                grip_idx=float(track["grip_index"]), wet=wet, noise=QUAL_NOISE
            )
            rows.append({
                "round": int(round_no),
                "team_id": str(team_id),
                "driver_id": str(did),
                "quali_time_s": float(lap),
            })

    q = pd.DataFrame(rows).sort_values("quali_time_s").reset_index(drop=True)
    q["grid_pos"] = range(1, len(q) + 1)

    q_path = root / "sim" / f"quali_round_{round_no:02d}.csv"
    q.to_csv(q_path, index=False, encoding="utf-8")
    return q


# ─────────────────────────────────────────────────────────────────────────────
# 레이스
# ─────────────────────────────────────────────────────────────────────────────
def run_race(round_no: int, root: Path, qdf: pd.DataFrame | None = None) -> pd.DataFrame:
    """
    - 퀄리 결과(qdf)가 없으면 root/sim/quali_round_{RR}.csv → 없으면 run_qualifying 호출
    - 결과를 root/sim/race_round_{RR}.csv 로 저장
    """
    root = Path(root)
    (root / "sim").mkdir(parents=True, exist_ok=True)

    track, teams, drivers, pairs = _load_round(round_no, root)

    # 퀄리 결과 확보
    if qdf is None:
        q_path = root / "sim" / f"quali_round_{round_no:02d}.csv"
        qdf = pd.read_csv(q_path) if q_path.exists() else run_qualifying(round_no, root)

    # 레이스 파라미터
    laps = int(track["laps"])
    ref = ref_lap_time_sec(float(track["length_km"]))
    wet = bool(rain_flag(float(track["rain_base_prob"])))
    events = sample_safety_periods(
        laps, float(track["sc_base_prob"]), float(track["vsc_base_prob"])
    )
    events_py = {
        "SC": [(int(s), int(e)) for (s, e) in events.get("SC", [])],
        "VSC": [(int(s), int(e)) for (s, e) in events.get("VSC", [])],
    }

    # 프리 보너스
    bonus_map = _load_pre_bonus_map(root, round_no)

    out_rows = []

    # 그리드 순서대로 시뮬
    for _, row in qdf.sort_values("grid_pos").iterrows():
        did, team_id = str(row["driver_id"]), str(row["team_id"])
        drow, trow = drivers.loc[did], teams.loc[team_id]
        grid_pos = int(row["grid_pos"])

        dnf = bool(dnf_flag(drow, trow))
        stints = choose_strategy(laps, float(track["abrasion_index"]))
        total_time, total_pits, cur_lap = 0.0, 0, 1
        fastest_lap = float("inf")

        for (comp, seg_laps) in stints:
            mult = stint_multiplier(
                comp, float(track["abrasion_index"]), float(drow["tire_mgmt"])
            )

            for _ in range(int(seg_laps)):
                lap_no = cur_lap

                perf = perf_scalar(
                    drow, trow,
                    quali_mode=False, wet=wet, grip_idx=float(track["grip_index"])
                )
                # 프리 보너스 가산
                b = float(bonus_map.get(did, 0.0))
                perf = max(0.0, min(1.2, perf * (1.0 + b)))

                lap_t = lap_time_from_perf(
                    ref, perf,
                    grip_idx=float(track["grip_index"]), wet=wet, noise=RACE_NOISE
                )
                lap_t *= float(mult)

                # SC/VSC 영향 (랩타임 증가)
                if is_in_any(lap_no, events_py["SC"]):
                    lap_t *= (1.0 / float(_SCF))
                elif is_in_any(lap_no, events_py["VSC"]):
                    lap_t *= (1.0 / float(_VSCF))

                total_time += float(lap_t)
                fastest_lap = min(fastest_lap, float(lap_t))
                cur_lap += 1

                # DNF 확률 분산(전체 레이스 중 1회라도 발생)
                if dnf and _rng.random() < 1.0 / max(1, laps):
                    # 레이스 중단
                    cur_lap = laps + 1
                    break

            # 스틴트 종료 → 피트
            if cur_lap > laps:
                break
            total_pits += 1
            sc_active = is_in_any(cur_lap, events_py["SC"])
            total_time += pit_loss_sec(
                float(track["pit_loss_sec"]),
                sc_active=sc_active,
                pit_crew=float(trow["pit_crew"]),
            )

        finished = (cur_lap > laps) and (not dnf)
        status = "Finished" if finished else "DNF"
        out_rows.append(
            {
                "round": int(round_no),
                "team_id": team_id,
                "driver_id": did,
                "grid_pos": int(grid_pos),
                "total_time_s": float(total_time) if status == "Finished" else None,
                "fastest_lap_s": None if fastest_lap == float("inf") else float(fastest_lap),
                "pit_stops": int(total_pits),
                "status": status,
                "wet": bool(wet),
                "events_json": json.dumps(events_py),
            }
        )

    df = pd.DataFrame(out_rows)

    # 순위/포인트 계산
    fin = df[df["status"] == "Finished"].sort_values("total_time_s").copy()
    dnf_df = df[df["status"] != "Finished"].copy()

    fin["pos"] = np.arange(1, len(fin) + 1, dtype=int)
    if len(dnf_df):
        dnf_df["pos"] = np.arange(len(fin) + 1, len(fin) + len(dnf_df) + 1, dtype=int)

    out_df = (
        pd.concat([fin, dnf_df], ignore_index=True)
        .sort_values("pos")
        .reset_index(drop=True)
    )

    # 포인트 (Top10: 25,18,15,12,10,8,6,4,2,1)
    pts = [25, 18, 15, 12, 10, 8, 6, 4, 2, 1]
    out_df["points"] = 0
    for i in range(min(10, len(fin))):
        out_df.loc[out_df.index[i], "points"] = pts[i]

    r_path = root / "sim" / f"race_round_{round_no:02d}.csv"
    out_df.to_csv(r_path, index=False, encoding="utf-8")
    return out_df


# ─────────────────────────────────────────────────────────────────────────────
# 라운드 일괄 실행
# ─────────────────────────────────────────────────────────────────────────────
def simulate_round(round_no: int, root: Path) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    퀄리 → 레이스를 연속 수행하고 CSV 저장.
    """
    q = run_qualifying(round_no, root)
    r = run_race(round_no, root, qdf=q)
    return q, r
