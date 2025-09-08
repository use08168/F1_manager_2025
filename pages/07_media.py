# pages/07_media.py
# -*- coding: utf-8 -*-
from __future__ import annotations
import json, re, random, os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import streamlit as st
import pandas as pd

# ─────────────────────────────────────────────────────────────────────────────
# 경로 & 공용
def find_root(start: Path) -> Path:
    cur = start
    for _ in range(6):
        if (cur / "info").exists() and (cur / "circuit").exists():
            return cur
        cur = cur.parent
    return start

ROOT        = find_root(Path(__file__).resolve())
INFO_DIR    = ROOT / "info"
DATA_DIR    = ROOT / "data"
SAVE_ROOT   = DATA_DIR / "saves"

TEAMS_CSV_INFO   = INFO_DIR / "teams.csv"
TEAMS_CSV_DATA   = DATA_DIR / "teams.csv"
DRIVERS_CSV_INFO = INFO_DIR / "drivers.csv"
DRIVERS_CSV_DATA = DATA_DIR / "drivers.csv"
TRACKS_CSV       = (INFO_DIR/"tracks.csv") if (INFO_DIR/"tracks.csv").exists() else (DATA_DIR/"tracks.csv")

def _norm_col(df, candidates, default=None):
    for c in candidates:
        if c in df.columns:
            return c
    if default and default in df.columns:
        return default
    return None

def _hex(c: str) -> str:
    if not c: return ""
    c = str(c).strip()
    return c if c.startswith("#") else ("#" + c) if re.fullmatch(r"[0-9A-Fa-f]{6}", c) else c

def load_team_catalog():
    by_id, by_name, color_by_id, color_by_name = {}, {}, {}, {}
    for p in [TEAMS_CSV_DATA, TEAMS_CSV_INFO]:
        if not p.exists(): continue
        df = pd.read_csv(p)
        col_id  = _norm_col(df, ["team_id","id"])
        col_nm  = _norm_col(df, ["name","team","constructor","team_name"], "name")
        col_col = _norm_col(df, ["team_color","color","hex","primary_color"], "team_color")
        if not col_nm: continue
        for _, r in df.iterrows():
            tid = str(r[col_id]).strip() if col_id and pd.notna(r[col_id]) else None
            nm  = str(r[col_nm]).strip()  if pd.notna(r[col_nm]) else ""
            col = _hex(str(r[col_col]).strip()) if col_col and pd.notna(r[col_col]) else ""
            if tid: by_id[tid] = nm
            if nm:  by_name[nm] = tid or by_name.get(nm)
            if tid and col: color_by_id[tid] = col
            if nm  and col: color_by_name[nm] = col
    return by_id, by_name, color_by_id, color_by_name

def ensure_save_dir() -> Path:
    st.session_state.setdefault("save_dir", "")
    p = Path(st.session_state["save_dir"]) if st.session_state["save_dir"] else None
    if p and p.exists():
        return p
    # 없으면 마지막 변경된 세이브 폴더를 자동 탐색
    SAVE_ROOT.mkdir(parents=True, exist_ok=True)
    slots = [d for d in SAVE_ROOT.glob("run_*") if d.is_dir()]
    if slots:
        slots.sort(key=lambda d: d.stat().st_mtime, reverse=True)
        st.session_state["save_dir"] = str(slots[0])
        return slots[0]
    # 아무것도 없으면 새로 만든다
    ts = datetime.now().strftime("run_%Y%m%d_%H%M%S")
    p = SAVE_ROOT / ts
    p.mkdir(parents=True, exist_ok=True)
    st.session_state["save_dir"] = str(p)
    return p

# ─────────────────────────────────────────────────────────────────────────────
# 레이스 결과 로딩(여러 포맷을 관대하게 수용)
def _try_load_json(p: Path):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None

def load_main_race_result() -> dict | None:
    # 1) 세션 메모리에 race가 있으면 우선 사용
    race = st.session_state.get("race")
    if isinstance(race, dict) and race.get("results"):
        return race

    # 2) 세이브 폴더에서 *race*.json 최신 파일 찾기
    save_dir = ensure_save_dir()
    cands = sorted(save_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    for p in cands:
        if "race" in p.name.lower():
            js = _try_load_json(p)
            if isinstance(js, dict) and js.get("results"):
                return js

    # 3) quali/세션 결과만 있고 race가 없을 수도… 그 경우 None
    return None

# ─────────────────────────────────────────────────────────────────────────────
# LLM 스키마 & 호출(폴백 내장)
MEDIA_REPLY_SCHEMA = {
  "name": "media_reply",
  "schema": {
    "type": "object", "additionalProperties": False,
    "properties": {
      "reply_text":   {"type": "string"},
      "tone":         {"type": "string", "enum": ["diplomatic","fiery","humorous","technical","humble","confident"]},
      "score":        {"type": "number", "minimum": 0, "maximum": 100},
      "funding_musd": {"type": "number", "minimum": 0, "maximum": 50},
      "rationale":    {"type": "string"},
      "investor_take":{"type": "string"}
    },
    "required": ["reply_text","tone","score","funding_musd","rationale","investor_take"]
  }
}

def call_media_llm(context: dict, user_msg: str) -> dict:
    """
    ask_llm_json 사용. 실패 시 폴백.
    """
    sys_p = (
        "You are an F1 team principal at a press conference. "
        "Respond in Korean, concise but quotable. "
        "Also act as an investor-score judge: evaluate if this answer would attract new investment."
        "Output ONLY JSON following the provided schema."
    )
    # 문맥 요약
    team_name = context.get("team_name","Team")
    pos_str = ", ".join([f"{x['pos']}. {x['name']}({x.get('team','')})" for x in context.get("top3", [])])
    perf = f"우리팀 결과: {context.get('team_result','미등록')} / 우승 후보: {context.get('winner','미등록')}"
    usr_p = (
        f"[컨텍스트]\n"
        f"라운드: {context.get('round','?')} · 서킷: {context.get('circuit','?')}\n"
        f"최종 순위 상위 3명: {pos_str or '정보 없음'}\n"
        f"{perf}\n"
        f"관중/스폰서 관심사: {context.get('narrative_hint','공격적인 전략, 팀 철학, 장기 비전')}\n\n"
        f"[질문]\n{user_msg}\n\n"
        f"요구사항:\n- 기자 질문에 대한 자연스러운 한국어 답변(reply_text)\n"
        f"- 답변 톤(tone)과 설득력 점수(score, 0-100)\n"
        f"- 신규 투자금 추정치 funding_musd (0~5M 선호, 특별히 탁월하면 최대 10M)\n"
        f"- 판단 근거(rationale)와 투자자 관점 한줄 정리(investor_take)"
    )

    # 시도 1: 정식 클라이언트
    try:
        from f1sim.ai.llm_client import ask_llm_json
        out = ask_llm_json(MEDIA_REPLY_SCHEMA, sys_p, usr_p, temperature=0.6)
        # 방어적 캐스팅
        out["score"] = float(out.get("score", 60))
        out["funding_musd"] = float(out.get("funding_musd", 1.0))
        out["reply_text"] = str(out.get("reply_text",""))
        out["tone"] = str(out.get("tone","diplomatic"))
        out["rationale"] = str(out.get("rationale",""))
        out["investor_take"] = str(out.get("investor_take",""))
        return out
    except Exception:
        # 폴백(간단 휴리스틱)
        base = 55
        bonus = 0
        txt = user_msg.lower()
        # 우승/포디움/완주/전략 키워드 가산
        kw = {
            "win": 8, "p1": 8, "우승": 10, "podium": 6, "포디움": 6,
            "전략": 5, "strategy": 5, "개선": 3, "improve": 3, "엔진": 2, "aero": 2,
            "스폰서": 3, "투자": 4, "기록": 2, "랩": 1
        }
        for k, v in kw.items():
            if k in txt: bonus += v
        score = max(30, min(95, base + bonus + random.randint(-6, 6)))
        funding = round(max(0.5, min(10.0, score/15 + (3.0 if "우승" in txt or "win" in txt else 0.0))), 2)
        reply = "팀의 철학과 데이터를 기반으로 향후 업그레이드와 전략적 선택을 명확히 설명하겠습니다. 오늘 배운 것들을 다음 라운드에 반영해 더 좋은 결과를 약속드립니다."
        return {
            "reply_text": reply,
            "tone": "confident" if score >= 70 else "humble",
            "score": float(score),
            "funding_musd": float(funding),
            "rationale": "답변의 명확성, 데이터 활용, 장기 비전 언급이 투자자에게 긍정적이었음.",
            "investor_take": "리스크 관리와 성장 계획이 구체적이라 일정 수준의 투자 가치가 있음."
        }

# ─────────────────────────────────────────────────────────────────────────────
# 미디어/재무 저장
def load_media_finance() -> dict:
    save_dir = ensure_save_dir()
    fp = Path(save_dir) / "media_finance.json"
    if fp.exists():
        try:
            js = json.loads(fp.read_text(encoding="utf-8"))
            if isinstance(js, dict):
                return js
        except Exception:
            pass
    return {"total_funding_musd": 0.0, "log": []}

def persist_media_finance(entry: dict):
    save_dir = ensure_save_dir()
    fp = Path(save_dir) / "media_finance.json"
    js = load_media_finance()
    js["log"].append(entry)
    js["total_funding_musd"] = round(float(js.get("total_funding_musd", 0.0)) + float(entry.get("funding_musd", 0.0)), 2)
    fp.write_text(json.dumps(js, ensure_ascii=False, indent=2), encoding="utf-8")
    return js

# ─────────────────────────────────────────────────────────────────────────────
# 컨텍스트 조립(레이스 결과 요약)
def build_context_from_race(race_js: dict, by_id: dict, by_name: dict) -> dict:
    circuit = race_js.get("circuit") or race_js.get("track") or ""
    rnd = race_js.get("round") or st.session_state.get("round")
    results = race_js.get("results") or []
    results_sorted = sorted(results, key=lambda r: r.get("pos", 9999))
    top3 = results_sorted[:3]
    winner = top3[0]["name"] if top3 else None

    # 플레이어 팀 이름
    team_id = st.session_state.get("team_id")
    player_team = None
    if team_id is not None:
        player_team = by_id.get(str(team_id))
    # 우리팀 결과 텍스트
    team_res = None
    if player_team:
        my = [r for r in results_sorted if str(r.get("team","")).strip() == str(player_team).strip()]
        # 드라이버 2명 포맷 감안(둘의 최고 순위를 대표로)
        if my:
            best = min([r.get("pos",9999) for r in my])
            team_res = f"{player_team} 최고 순위 P{best}"
    return {
        "circuit": circuit, "round": rnd,
        "top3": top3, "winner": winner, "team_name": player_team,
        "team_result": team_res or "기록 없음",
        "narrative_hint": "공격적인 전략, 리스크 관리, 장기 비전"
    }

# ─────────────────────────────────────────────────────────────────────────────
# UI
def _attach_dark_css():
    st.markdown("""
    <style>
      :root, html, body { background:#0b0f1a !important; color:#e5e7eb !important; }
      [data-testid="stAppViewContainer"] { background:#0b0f1a !important; }
      .block-container{ padding-top:0.6rem !important; padding-bottom:0.6rem !important; }
      div[data-testid="stVerticalBlock"]{ border:1px solid rgba(255,255,255,.08); border-radius:12px; padding:8px 10px; margin:6px 0; }
      .pill { background:#0b1220; border:1px solid #1e293b; border-radius:12px; padding:10px 12px; }
      .chatbox { background:#0e1626; border:1px solid #203049; border-radius:12px; padding:10px 12px; margin:6px 0; }
      .me { border-color:#334155; background:#0b1220; }
      .ai { border-color:#a11d33; background:#170c12; }
      .muted { color:#94a3b8; font-size:12px; }
      .score { font-weight:800; }
      .fund { font-weight:800; color:#22c55e; }
      .btn { font-size:14px; padding:8px 12px; border-radius:8px; border:1px solid #334155; background:#0f172a; color:#e5e7eb; cursor:pointer; }
      .btn.primary { background:#a11d33; border-color:#a11d33; color:#fff; }
      .headerbar { display:flex; justify-content:space-between; align-items:center; }
      .headerbar .right { display:flex; gap:12px; align-items:center; }
      .tag { display:inline-block; padding:2px 8px; border:1px solid #334155; background:#0b1220; border-radius:999px; font-size:12px; }
      .top3{ display:grid; grid-template-columns: 1fr 1fr 1fr; gap:8px; }
      .card { background:#0b1220; border:1px solid #1e293b; border-radius:12px; padding:10px; }
    </style>
    """, unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
def main():
    st.set_page_config(layout="wide", page_title="07 · Media / Press Conference")

    _attach_dark_css()

    by_id, by_name, color_by_id, color_by_name = load_team_catalog()
    save_dir = ensure_save_dir()

    # 헤더
    L, R = st.columns([0.62, 0.38])
    with L:
        st.markdown(f"### 🗞️ 07 · Media / Press Conference")
        st.caption("메인 레이스 결과를 바탕으로 기자 질의응답을 진행합니다. 답변의 설득력에 따라 신규 투자금을 확보합니다.")

    with R:
        with st.container():
            fin = load_media_finance()
            st.markdown(
                f"""
                <div class="headerbar pill">
                  <div><b>Save:</b> {Path(save_dir).name}</div>
                  <div class="right">
                    <div class="tag">누적 투자금</div>
                    <div class="fund" style="font-size:18px;">${fin.get('total_funding_musd',0.0):.2f}M</div>
                  </div>
                </div>
                """, unsafe_allow_html=True
            )

    race_js = load_main_race_result()
    if not race_js:
        st.warning("메인 레이스 결과를 찾지 못했습니다. 먼저 Main Race를 완료해 주세요.")
        st.stop()

    # 컨텍스트 카드
    ctx = build_context_from_race(race_js, by_id, by_name)
    top3 = ctx.get("top3", [])
    top3 = [{"pos": r.get("pos"), "name": r.get("name"), "team": r.get("team")} for r in top3]

    with st.container():
        st.markdown("#### 레이스 요약")
        c1, c2, c3 = st.columns(3)
        if len(top3) >= 1:
            with c1:
                st.markdown(f"""<div class="card"><div class="muted">P1</div><div style="font-weight:800;">{top3[0]['name']}</div><div class="muted">{top3[0].get('team','')}</div></div>""", unsafe_allow_html=True)
        if len(top3) >= 2:
            with c2:
                st.markdown(f"""<div class="card"><div class="muted">P2</div><div style="font-weight:800;">{top3[1]['name']}</div><div class="muted">{top3[1].get('team','')}</div></div>""", unsafe_allow_html=True)
        if len(top3) >= 3:
            with c3:
                st.markdown(f"""<div class="card"><div class="muted">P3</div><div style="font-weight:800;">{top3[2]['name']}</div><div class="muted">{top3[2].get('team','')}</div></div>""", unsafe_allow_html=True)

        st.markdown(
            f"""
            <div class="pill" style="margin-top:8px;">
              <div><b>서킷</b> {ctx.get('circuit','?')} <span class="tag">라운드 {ctx.get('round','?')}</span></div>
              <div class="muted" style="margin-top:4px;"><b>우리팀</b> {ctx.get('team_name') or '—'} · {ctx.get('team_result')}</div>
            </div>
            """, unsafe_allow_html=True
        )

    # 대화 상태
    st.session_state.setdefault("media_chat", [])
    # 입력창
    with st.container():
        st.markdown("#### 기자 회견")
        col_in1, col_in2 = st.columns([0.8, 0.2])
        with col_in1:
            user_msg = st.text_input("기자 질문을 입력하세요", key="media_user_msg", placeholder="이번 레이스 전략이 보수적이었다는 비판이 있습니다. 어떻게 답하시겠습니까?")
        with col_in2:
            ask = st.button("질문 보내기", type="primary", use_container_width=True)

        if ask and user_msg.strip():
            out = call_media_llm(ctx, user_msg.strip())
            entry = {
                "ts": datetime.now().isoformat(timespec="seconds"),
                "user": user_msg.strip(),
                "ai": out.get("reply_text",""),
                "tone": out.get("tone","diplomatic"),
                "score": float(out.get("score", 60)),
                "funding_musd": float(out.get("funding_musd", 0.0)),
                "rationale": out.get("rationale",""),
                "investor_take": out.get("investor_take","")
            }
            st.session_state["media_chat"].append(entry)
            fin = persist_media_finance(entry)
            st.toast(f"투자금 +${entry['funding_musd']:.2f}M (누적 ${fin.get('total_funding_musd',0.0):.2f}M)", icon="💰")

    # 대화 로그
    with st.container():
        st.markdown("#### 대화 로그")
        if not st.session_state["media_chat"]:
            st.info("아직 대화가 없습니다. 위 입력창에 질문을 입력해 보세요.")
        else:
            for q in st.session_state["media_chat"][::-1]:
                st.markdown(f"""<div class="chatbox me"><b>기자</b><br/>{q['user']}</div>""", unsafe_allow_html=True)
                st.markdown(
                    f"""<div class="chatbox ai">
                           <div style="display:flex; justify-content:space-between; align-items:center;">
                             <div><b>감독</b> <span class="tag">{q['tone']}</span></div>
                             <div><span class="score">Score {q['score']:.0f}</span> · <span class="fund">+${q['funding_musd']:.2f}M</span></div>
                           </div>
                           <div style="margin-top:6px;">{q['ai']}</div>
                           <div class="muted" style="margin-top:8px;">근거: {q['rationale']} · 투자자 한줄평: {q['investor_take']}</div>
                         </div>""",
                    unsafe_allow_html=True
                )

    # 우측: 재무 요약 & 내보내기
    with st.sidebar:
        st.markdown("### 📈 재무 요약")
        fin = load_media_finance()
        st.metric("누적 투자금 (M USD)", f"{fin.get('total_funding_musd',0.0):.2f}")
        if st.button("대화/재무 로그 내보내기(JSON)"):
            save_dir = ensure_save_dir()
            fp = Path(save_dir) / "media_finance.json"
            st.download_button("media_finance.json 다운로드", data=fp.read_text(encoding="utf-8"), file_name="media_finance.json", mime="application/json")

        if st.button("대화 초기화"):
            st.session_state["media_chat"] = []
            st.toast("대화를 초기화했습니다.", icon="🧹")

        st.markdown("---")
        st.caption("※ LLM 호출 실패 시에도 폴백 로직으로 점수/투자금을 산정합니다.\n데이터는 현재 세이브 슬롯에 media_finance.json으로 기록됩니다.")

# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    main()
