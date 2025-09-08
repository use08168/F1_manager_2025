# f1sim/ui/theme.py
# -*- coding: utf-8 -*-
from __future__ import annotations
import streamlit as st

# 한 톤 더 어둡게 + 텍스트 콘트라스트 상향
F1 = {
    "red":        "#E10600",
    "red_hover":  "#FF2D1A",
    "bg":         "#0B0D12",  # 전체 배경
    "card":       "#11151C",  # 카드/사이드바/입력 배경
    "text":       "#E6EAF2",  # 본문 글자
    "muted":      "#9AA1AA",  # 캡션/보조
    "border":     "#243043",  # 경계선
}

_GLOBAL_CSS = f"""
<style>
/* -------- 베이스 -------- */
html, body, [data-testid="stAppViewContainer"] {{
  background: {F1["bg"]} !important;
  color: {F1["text"]} !important;
}}
.block-container {{ padding-top: 0.8rem !important; }}

/* 헤더/데코 제거(상단 하얀 줄 방지) */
[data-testid="stHeader"],
[data-testid="stToolbar"],
[data-testid="stDecoration"] {{ display: none !important; }}

/* -------- 사이드바/카드 -------- */
[data-testid="stSidebar"] {{
  background: {F1["card"]} !important;
  border-right: 1px solid {F1["border"]};
}}
div[role="region"], .stContainer, .stChatMessage, .stMarkdown, .stAlert {{
  color: {F1["text"]} !important;
}}
/* 컨테이너 기본 테두리/배경(페이지별 컨테이너가 하얗게 나오는 것 방지) */
div[data-testid="stVerticalBlock"] {{
  background: transparent !important;
}}
/* 확장자(Expander) */
.streamlit-expanderHeader {{
  background: {F1["card"]};
  border: 1px solid {F1["border"]};
  border-radius: 8px;
}}
.stAlert {{
  background: {F1["card"]};
  border: 1px solid {F1["border"]};
  border-radius: 8px;
}}

/* -------- 버튼/위젯 -------- */
.stButton > button {{
  background: {F1["red"]} !important;
  color: #fff !important;
  border: 1px solid {F1["red"]};
  border-radius: 10px;
  font-weight: 700;
}}
.stButton > button:hover {{
  background: {F1["red_hover"]} !important;
  border-color: {F1["red_hover"]} !important;
}}
/* 입력 위젯 공통(텍스트/셀렉트/멀티셀렉트/슬라이더 핸들 등) */
input, textarea, select, [data-baseweb="select"] > div, .stTextInput > div > div,
.stTextArea > div > div, .stNumberInput > div > div, .stDateInput > div > div {{
  background: {F1["card"]} !important;
  color: {F1["text"]} !important;
  border: 1px solid {F1["border"]} !important;
}}
/* 슬라이더 라벨/값 */
[data-testid="stSlider"] label, [data-testid="stSlider"] span {{ color: {F1["text"]} !important; }}

/* -------- 탭 -------- */
.stTabs [data-baseweb="tab-list"] {{
  gap: 0.4rem;
  border-bottom: 1px solid {F1["border"]};
}}
.stTabs [data-baseweb="tab"] {{ color: {F1["muted"]}; }}
.stTabs [aria-selected="true"] {{
  color: {F1["text"]};
  border-bottom: 3px solid {F1["red"]};
}}

/* -------- DataFrame(그리드) -------- */
[data-testid="stDataFrame"] thead tr th {{
  background: {F1["card"]} !important;
  color: {F1["text"]} !important;
  border-bottom: 1px solid {F1["border"]};
}}
[data-testid="stDataFrame"] tbody tr td {{
  background: {F1["bg"]} !important;
  color: {F1["text"]} !important;
  border-bottom: 1px solid {F1["border"]};
}}
</style>
"""

def apply_theme():
    """페이지 최상단에서 한 번 호출."""
    st.markdown(_GLOBAL_CSS, unsafe_allow_html=True)

def brand_header(title: str, subtitle: str | None = None):
    """상단 브랜드 바: 얇은 레드 라인 + 타이틀."""
    st.markdown(
        f"""
<div style="border-bottom: 3px solid {F1['red']}; margin-bottom: 0.8rem;"></div>
<h1 style="margin: 0 0 0.2rem 0; color: {F1['text']};">{title}</h1>
{f'<div style="color:{F1["muted"]}; margin-bottom:1rem;">{subtitle}</div>' if subtitle else ''}
""",
        unsafe_allow_html=True,
    )
