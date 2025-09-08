# prep_circuit_metrics.py
# 1단계: 모든 서킷 SVG를 스캔해 길이/시간 보정용 메트릭 CSV 생성
# 사용 전 설치:  pip install svgpathtools pandas

import os
import re
import json
import math
from pathlib import Path
from typing import Optional, Tuple, Dict, Any

import pandas as pd
try:
    from svgpathtools import parse_path, Path as SvgPath
except ImportError as e:
    raise SystemExit("svgpathtools 가 필요합니다. 먼저 설치하세요:  pip install svgpathtools") from e

import xml.etree.ElementTree as ET

# ---- 경로 구성 (test4.py 와 같은 경로 기준) ----
BASE_DIR    = Path(__file__).resolve().parent
CIRCUIT_DIR = BASE_DIR / "circuit"
INFO_DIR    = BASE_DIR / "info"
INFO_DIR.mkdir(exist_ok=True)

TRACKS_CSV  = INFO_DIR / "tracks.csv"
OUT_CSV     = INFO_DIR / "circuit_calibration.csv"

# tracks.csv 에 랩타임 없을 때 추정 속도
DEFAULT_BASE_KMH = 220.0

# ---------------- XML helpers ----------------
def _localname(tag: str) -> str:
    return tag.split('}', 1)[-1] if '}' in tag else tag

def _find_path_d(root: ET.Element, target_id: str) -> Optional[str]:
    for el in root.iter():
        if _localname(el.tag) == "path" and el.get("id") == target_id:
            d = el.get("d")
            if d and d.strip():
                return d
    return None

def _grab_point_by_id(root: ET.Element, pid: str) -> Optional[Tuple[float,float]]:
    """id=pid 엘리먼트에서 data-pt='x,y' 또는 (cx,cy) 혹은 (x,y)를 읽음"""
    for el in root.iter():
        if el.get("id") == pid:
            dpt = el.get("data-pt")
            if dpt and "," in dpt:
                try:
                    x, y = map(float, dpt.split(","))
                    return (x, y)
                except:
                    pass
            # circle(cx,cy) or generic(x,y)
            try:
                if _localname(el.tag) == "circle":
                    cx = float(el.get("cx","0") or "0")
                    cy = float(el.get("cy","0") or "0")
                    return (cx, cy)
                else:
                    x = float(el.get("x","nan"))
                    y = float(el.get("y","nan"))
                    if math.isfinite(x) and math.isfinite(y):
                        return (x, y)
            except:
                pass
    return None

def _grab_markers_from_metadata(root: ET.Element) -> Dict[str, Any]:
    """<metadata>{...JSON...}</metadata> 형태에서 pitIn/pitOut/pitStop 추출 시도"""
    for el in root.iter():
        if _localname(el.tag) == "metadata":
            txt = (el.text or "").strip()
            if not txt:
                continue
            try:
                obj = json.loads(txt)
            except:
                continue
            out = {}
            for key in ("pitIn","pitOut","pitStop","start"):
                if key in obj:
                    out[key] = obj[key]
            return out
    return {}

# --------------- 기하/길이 계산 helpers ---------------
def _path_len_px(d: Optional[str]) -> float:
    if not d:
        return 0.0
    try:
        p = parse_path(d)
        return float(p.length(error=1e-3))
    except Exception:
        return 0.0

def _nearest_s(path: SvgPath, x: float, y: float, samples: int = 4000) -> float:
    """점(x,y)에 가장 가까운 경로상의 아크길이 s(px) 근사"""
    L = float(path.length(error=1e-3))
    best_s, best_d2 = 0.0, 1e30
    for i in range(samples+1):
        s = (L * i) / samples
        try:
            t = path.ilength(s, error=1e-3)
            z = path.point(t)
        except Exception:
            # 최후: 파라미터 t 균등 샘플
            t = i / samples
            z = path.point(t)
        dx, dy = (z.real - x), (z.imag - y)
        d2 = dx*dx + dy*dy
        if d2 < best_d2:
            best_d2, best_s = d2, s
    return best_s

def _pit_segment_len_px(pit_d: Optional[str], pit_in_xy: Optional[Tuple[float,float]], pit_out_xy: Optional[Tuple[float,float]]) -> float:
    if not pit_d or not pit_in_xy or not pit_out_xy:
        return 0.0
    try:
        pit_path = parse_path(pit_d)
        L = float(pit_path.length(error=1e-3))
        s_in  = _nearest_s(pit_path, pit_in_xy[0],  pit_in_xy[1])
        s_out = _nearest_s(pit_path, pit_out_xy[0], pit_out_xy[1])
        if L <= 0:
            return 0.0
        # 경로 진행 방향 기준 in→out 아크길이
        seg = (s_out - s_in) if s_out >= s_in else (L - s_in + s_out)
        return float(seg)
    except Exception:
        return 0.0

# --------------- tracks.csv 로드 ---------------
def _pick_col(df, candidates):
    for c in candidates:
        if c in df.columns:
            return c
    return None

def parse_lap_time_to_sec(v) -> Optional[float]:
    """숫자면 그대로, 'm:ss(.sss)' / '1m28.3s' / '88.3' 같은 문자열을 초로 변환"""
    if pd.isna(v):
        return None
    if isinstance(v, (int, float)):
        return float(v) if v > 0 else None
    s = str(v).strip().lower()
    if not s:
        return None
    # "m:ss(.sss)"
    m = re.match(r"^(\d+):(\d+(?:\.\d+)?)$", s)
    if m:
        mm = float(m.group(1)); ss = float(m.group(2))
        return mm*60 + ss
    # "1m28.3s" / "1 m 28.3 s"
    m = re.match(r"^(\d+)\s*m\s*(\d+(?:\.\d+)?)\s*s$", s)
    if m:
        mm = float(m.group(1)); ss = float(m.group(2))
        return mm*60 + ss
    # 순수 실수 문자열 "88.3"
    try:
        x = float(s)
        return x if x > 0 else None
    except:
        return None

def load_tracks(tracks_csv: Path) -> pd.DataFrame:
    if not tracks_csv.exists():
        return pd.DataFrame()

    df = pd.read_csv(tracks_csv)

    # 이름 컬럼 통합 → name
    name_col = _pick_col(df, ["name","circuit","track","circuit_name","track_name"])
    if not name_col:
        return pd.DataFrame()  # 이름이 없으면 매칭 불가
    if name_col != "name":
        df = df.rename(columns={name_col: "name"})
    df["name"] = df["name"].astype(str).str.strip()

    # 길이 컬럼 통합 → length_km
    len_col = _pick_col(df, ["length_km","km","track_km","circuit_km","distance_km"])
    if len_col and len_col != "length_km":
        df = df.rename(columns={len_col: "length_km"})
    if "length_km" in df.columns:
        df["length_km"] = pd.to_numeric(df["length_km"], errors="coerce")

    # 랩타임 컬럼 통합 → lap_sec
    lap_col = _pick_col(df, [
        "lap_sec","typical_lap_sec","lap_time_sec","avg_lap_sec","average_lap_sec",
        "lap_time","typical_lap","pole_sec","qualy_sec"
    ])
    if lap_col and lap_col != "lap_sec":
        df = df.rename(columns={lap_col: "lap_sec"})
    if "lap_sec" in df.columns:
        df["lap_sec"] = df["lap_sec"].apply(parse_lap_time_to_sec)

    # 피트 속도 → pit_speed_kmh
    pit_col = _pick_col(df, ["pit_speed_kmh","pit_limit_kmh","pit_kmh"])
    if pit_col and pit_col != "pit_speed_kmh":
        df = df.rename(columns={pit_col: "pit_speed_kmh"})
    if "pit_speed_kmh" in df.columns:
        df["pit_speed_kmh"] = pd.to_numeric(df["pit_speed_kmh"], errors="coerce")

    # 필요한 것만 반환
    cols = ["name","length_km","lap_sec","pit_speed_kmh"]
    for c in cols:
        if c not in df.columns:
            df[c] = pd.NA
    return df[cols]

# --------------- 매칭 & 처리 ---------------
def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(s).lower())

def match_track(tracks_df: pd.DataFrame, file_stem: str) -> Optional[Dict[str, Any]]:
    """파일명과 tracks.name 매칭(최소 처리: 1)slug 완전일치 2)부분 포함)"""
    if tracks_df.empty:
        return None
    fs = _slug(file_stem)
    # 1) 완전일치
    m = tracks_df[tracks_df["name"].apply(_slug) == fs]
    if not m.empty:
        return m.iloc[0].to_dict()
    # 2) 부분 포함(양방향)
    slugs = tracks_df["name"].apply(_slug)
    m = tracks_df[(slugs.str.contains(fs, na=False))]
    if not m.empty:
        return m.iloc[0].to_dict()
    return None

def process_svg(svg_path: Path, track_info: Optional[Dict[str,Any]]) -> Dict[str, Any]:
    data = {
        "file": svg_path.name,
        "circuit": svg_path.stem,
        "main_len_px": None,
        "pit_len_px": None,
        "lap_sec_csv": None,
        "lap_sec_src": None,   # csv / estimated(220km/h)
        "length_km": None,
        "px_per_sec": None,
        "sec_per_px": None,
        "pit_travel_sec": None,
        "notes": ""
    }

    try:
        tree = ET.parse(str(svg_path))
    except Exception as e:
        data["notes"] = f"SVG parse error: {e}"
        return data
    root = tree.getroot()

    d_main = _find_path_d(root, "main")
    d_pit  = _find_path_d(root, "pit")

    main_len = _path_len_px(d_main)
    data["main_len_px"] = round(main_len, 3) if main_len else None

    # pit 마커 찾기: id 우선, 없으면 metadata JSON
    pit_in_xy  = _grab_point_by_id(root, "pitIn")
    pit_out_xy = _grab_point_by_id(root, "pitOut")
    if (pit_in_xy is None or pit_out_xy is None):
        md = _grab_markers_from_metadata(root)
        def _pick_xy(o, k):
            try:
                pts = o.get(k, {}).get("pts", [])
                if pts and isinstance(pts[0], dict):
                    return (float(pts[0]["x"]), float(pts[0]["y"]))
            except Exception:
                pass
            return None
        if pit_in_xy is None and md:
            pit_in_xy = _pick_xy(md, "pitIn")
        if pit_out_xy is None and md:
            pit_out_xy = _pick_xy(md, "pitOut")

    pit_len = _pit_segment_len_px(d_pit, pit_in_xy, pit_out_xy)
    data["pit_len_px"] = round(pit_len, 3) if pit_len else None

    # tracks.csv 매칭 데이터
    if track_info:
        if "lap_sec" in track_info and pd.notna(track_info["lap_sec"]):
            data["lap_sec_csv"] = float(track_info["lap_sec"])
            data["lap_sec_src"] = "csv"
        if "length_km" in track_info and pd.notna(track_info["length_km"]):
            data["length_km"] = float(track_info["length_km"])

    # lap_sec_csv 없으면 length_km로 추정하여라도 채워넣기
    if (data["lap_sec_csv"] is None or data["lap_sec_csv"] <= 0) and data["length_km"]:
        est = 3600.0 * data["length_km"] / max(1e-6, DEFAULT_BASE_KMH)
        data["lap_sec_csv"] = est
        data["lap_sec_src"] = f"estimated({DEFAULT_BASE_KMH}km/h)"

    # px_per_sec 계산
    if data["main_len_px"] and data["lap_sec_csv"] and data["lap_sec_csv"] > 0:
        px_per_sec = data["main_len_px"] / data["lap_sec_csv"]
        data["px_per_sec"] = round(px_per_sec, 6)
        data["sec_per_px"] = round(1.0/px_per_sec, 9)
        if data["pit_len_px"]:
            data["pit_travel_sec"] = round(data["pit_len_px"] / px_per_sec, 4)

    # 주석
    if not d_main:
        data["notes"] = (data["notes"] + "; " if data["notes"] else "") + "main path missing"
    if d_pit and (pit_in_xy is None or pit_out_xy is None):
        data["notes"] = (data["notes"] + "; " if data["notes"] else "") + "pit markers missing"
    if d_pit and data["pit_len_px"] is None:
        data["notes"] = (data["notes"] + "; " if data["notes"] else "") + "pit length not computed"

    return data

# --------------- 메인 ---------------
def main():
    if not CIRCUIT_DIR.exists():
        raise SystemExit(f"circuit 폴더가 없습니다: {CIRCUIT_DIR}")

    tracks_df = load_tracks(TRACKS_CSV)

    rows = []
    for svg in sorted(CIRCUIT_DIR.glob("*.svg")):
        track_info = match_track(tracks_df, svg.stem) if not tracks_df.empty else None
        row = process_svg(svg, track_info)
        # 매칭된 정식 이름이 있으면 덮어쓰기
        if track_info and "name" in track_info and isinstance(track_info["name"], str):
            row["circuit"] = track_info["name"].strip()
        rows.append(row)

    # CSV 저장
    cols = [
        "file","circuit","main_len_px","pit_len_px",
        "lap_sec_csv","lap_sec_src","length_km",
        "px_per_sec","sec_per_px","pit_travel_sec","notes"
    ]
    df = pd.DataFrame(rows, columns=cols)
    df.to_csv(OUT_CSV, index=False, encoding="utf-8-sig")

    # 요약 출력
    print(f"[완료] {len(rows)}개 서킷 분석 → {OUT_CSV}")
    warn = df[df["notes"].notna() & (df["notes"]!="")]
    if not warn.empty:
        print("\n다음 항목은 확인 필요:")
        for _, r in warn.iterrows():
            print(f" - {r['file']}: {r['notes']}")

if __name__ == "__main__":
    main()
