# f1sim/io/save.py
# -*- coding: utf-8 -*-
from __future__ import annotations
from pathlib import Path
import shutil, time
import pandas as pd

BASE_FILES = ["teams.csv", "drivers.csv", "tracks.csv"]

def _now_slot(team_id: str | None = None) -> str:
    ts = time.strftime("%Y%m%d_%H%M%S")
    return f"run_{ts}" + (f"_{team_id}" if team_id else "")

def create_save_slot(DATA: Path, team_id: str | None = None) -> Path:
    """data/saves/run_타임스탬프_(팀ID)/ 에 base CSV 복제."""
    saves = DATA / "saves"
    saves.mkdir(parents=True, exist_ok=True)
    slot = saves / _now_slot(team_id)
    slot.mkdir(parents=True, exist_ok=False)

    # 기본 CSV 복제(없으면 빈 파일로 생성)
    for name in BASE_FILES:
        src = DATA / name
        dst = slot / name
        if src.exists():
            shutil.copy2(src, dst)
        else:
            pd.DataFrame().to_csv(dst, index=False, encoding="utf-8")

    # 연구/훈련 부가 파일은 비어있는 스켈레톤으로 준비
    (slot / "rd_projects.csv").write_text(
        "project_id,team_id,planned_round,title,area,cost_musd,eta_rounds,remaining_rounds,risk,efficiency,expected_gain_hint,status,reason,paid,charged_musd\n",
        encoding="utf-8"
    )
    (slot / "crew_training_log.csv").write_text(
        "ts,round,team_id,title,sessions,risk,cost_musd,pit_gain_applied,morale_delta,incidents,narrative\n",
        encoding="utf-8"
    )
    return slot

def ensure_save_slot(state, DATA: Path, team_id: str | None = None) -> Path:
    """세션에 save_dir이 없으면 새 슬롯을 만들고 경로를 저장."""
    sd = state.get("save_dir")
    if sd and Path(sd).exists():
        return Path(sd)
    slot = create_save_slot(DATA, team_id)
    state["save_dir"] = str(slot)
    return slot

def get_paths(state, DATA: Path) -> dict[str, Path]:
    """세이브 경로 우선으로 각 CSV 경로 반환. 없으면 data/의 기본 경로."""
    root = Path(state.get("save_dir")) if state.get("save_dir") else DATA
    if not root.exists():
        root = DATA
    return {
        "root": root,
        "teams": root / "teams.csv",
        "drivers": root / "drivers.csv",
        "tracks": root / "tracks.csv",
        "rd": root / "rd_projects.csv",
        "crew_log": root / "crew_training_log.csv",
    }

def delete_current_save(state) -> None:
    """현재 세이브 폴더 삭제 + 세션 상태 초기화(안전)."""
    sd = state.get("save_dir")
    if sd and Path(sd).exists():
        shutil.rmtree(sd, ignore_errors=True)
    # 게임 진행 관련 키 초기화
    for k in [
        "save_dir", "team_id", "round",
        "rd_proposal", "rd_picks_ui", "confirm_final_submit",
        "crew_prop", "crew_picks", "confirm_ct_submit",
        "quali", "race"
    ]:
        state.pop(k, None)
