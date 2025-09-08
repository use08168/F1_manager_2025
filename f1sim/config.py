# -*- coding: utf-8 -*-
# ---- 튜닝 노브 (간단판) ----
SEED = 2025

# 랩타임 구성
VREF_KMH    = 215.0   # 기준 평균속도(km/h)
ALPHA_PACE  = 0.22    # 성능 민감도
BETA_GRIP   = 0.06    # 그립 영향
GAMMA_WET   = 0.05    # 비가 올 때 배율
QUAL_NOISE  = 0.003
RACE_NOISE  = 0.002

# 타이어/전략
COMPOUNDS   = ["S", "M", "H"]
BASE_DEG    = {"S": 0.010, "M": 0.006, "H": 0.004}
ABR_SPLIT   = 0.65    # 마모도 기준: 낮으면 1스톱(2스틴트), 높으면 2스톱(3스틴트)

# 이벤트/신뢰성
BASE_DNF    = 0.004
AWARE_SAFE  = 0.25
AGGRISK     = 0.20
RELRISK     = 0.35

# SC/VSC
SC_FACTOR   = 0.60    # SC 동안 페이스 배율(느려짐 → 실질 랩타임↑)
VSC_FACTOR  = 0.75
SC_LAPS     = (3, 5)
VSC_LAPS    = (1, 3)
