# f1sim/ui/sidebar.py
# -*- coding: utf-8 -*-
from pathlib import Path
import streamlit as st
from f1sim.io.save import delete_current_save

def attach_reset_sidebar():
    with st.sidebar:
        st.markdown("### 세이브 관리")
        sd = st.session_state.get("save_dir")
        if sd and Path(sd).exists():
            st.caption(f"현재 세이브: `{Path(sd).name}`")
        else:
            st.caption("현재 세이브 없음")

        if st.button("현재 진행 데이터 삭제", use_container_width=True):
            delete_current_save(st.session_state)
            st.success("진행 데이터를 삭제했습니다. 처음부터 다시 시작할 수 있어요.")
            st.rerun()
