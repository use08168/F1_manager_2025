# f1sim/ai/schemas.py
# -*- coding: utf-8 -*-

# --- R&D ---
RESEARCH_JSON_SCHEMA = {
  "name": "research_plan",
  "schema": {
    "type": "object",
    "additionalProperties": False,
    "properties": {
      "version": {"type":"string"},
      "module":  {"type":"string","enum":["research"]},
      "round":   {"type":"integer","minimum":1},
      "team_id": {"type":"string"},
      "inputs_digest": {"type":"string"},
      "decisions": {
        "type":"array",
        "items":{
          "type":"object",
          "required":["title","area","cost_musd","eta_rounds","risk","efficiency","expected_gain_hint","reason"],
          "additionalProperties": False,
          "properties":{
            "title":{"type":"string"},
            "area":{"type":"string","enum":["vehicle_design","front_wing","rear_wing","brakes","engine"]},
            "cost_musd":{"type":"number","minimum":0},
            "eta_rounds":{"type":"integer","minimum":1,"maximum":6},
            "risk":{"type":"string","enum":["low","mid","high"]},
            "efficiency":{"type":"number","minimum":0,"maximum":1},
            "expected_gain_hint":{"type":"number","minimum":0,"maximum":1},
            "reason":{"type":"string"}
          }
        }
      },
      "effects_hint": {
        "type":"object",
        "additionalProperties": False,
        "properties":{
          "priority_order":{"type":"array","items":{"type":"string"}},
          "focus_ratio":{"type":"object","patternProperties":{
            "^[a-z_]+$":{"type":"number","minimum":0,"maximum":1}
          }}
        }
      },
      "narrative":{"type":"string"}
    },
    "required":["version","module","round","team_id","inputs_digest","decisions","effects_hint","narrative"]
  }
}

# --- Crew Training: 계획 ---
CREW_TRAINING_PLAN_SCHEMA = {
  "name": "crew_training_plan",
  "schema": {
    "type":"object",
    "additionalProperties": False,
    "properties": {
      "version": {"type":"string"},
      "module":  {"type":"string","enum":["crew_training"]},
      "round":   {"type":"integer","minimum":1},
      "team_id": {"type":"string"},
      "inputs_digest": {"type":"string"},
      "plans": {
        "type":"array",
        "items":{
          "type":"object",
          "required":["title","focus","sessions","cost_musd","fatigue_risk","pit_gain_hint","reason"],
          "additionalProperties": False,
          "properties":{
            "title":{"type":"string"},
            "focus":{"type":"string","enum":["pitstop_choreo","wheel_gun","jack_team","endurance","crisis_sim","equipment_calib"]},
            "sessions":{"type":"integer","minimum":1,"maximum":4},
            "cost_musd":{"type":"number","minimum":0},
            "fatigue_risk":{"type":"string","enum":["low","mid","high"]},
            "pit_gain_hint":{"type":"number","minimum":0,"maximum":1},
            "morale_hint":{"type":"number","minimum":-1,"maximum":1},
            "reason":{"type":"string"}
          }
        }
      },
      "narrative":{"type":"string"}
    },
    "required":["version","module","round","team_id","inputs_digest","plans","narrative"]
  }
}

# --- Crew Training: 계획 ---
CREW_TRAINING_PLAN_SCHEMA = {
  "name": "crew_training_plan",
  "schema": {
    "type":"object",
    "additionalProperties": False,
    "properties": {
      "version": {"type":"string"},
      "module":  {"type":"string","enum":["crew_training"]},
      "round":   {"type":"integer","minimum":1},
      "team_id": {"type":"string"},
      "inputs_digest": {"type":"string"},
      "plans": {
        "type":"array",
        "items":{
          "type":"object",
          "required":["title","focus","sessions","cost_musd","fatigue_risk","pit_gain_hint","reason"],
          "additionalProperties": False,
          "properties":{
            "title":{"type":"string"},
            "focus":{"type":"string","enum":[
              "pitstop_choreo","wheel_gun","jack_team","endurance","crisis_sim","equipment_calib",
              # ↓ 인적자원 확장(선택)
              "driver_racecraft","driver_quali","sim_rig","dev_pipeline","strategy_ops","reliability_ops","data_engineering"
            ]},
            "sessions":{"type":"integer","minimum":1,"maximum":4},
            "cost_musd":{"type":"number","minimum":0},
            "fatigue_risk":{"type":"string","enum":["low","mid","high"]},
            "pit_gain_hint":{"type":"number","minimum":0,"maximum":1},
            "morale_hint":{"type":"number","minimum":-1,"maximum":1},

            # ↓ 선택적 인적자원 힌트(0..1 스케일)
            "driver_skill_hint":{"type":"number","minimum":0,"maximum":1},
            "dev_speed_hint":{"type":"number","minimum":0,"maximum":1},
            "strategy_hint":{"type":"number","minimum":0,"maximum":1},
            "reliability_hint":{"type":"number","minimum":0,"maximum":1},
            # 대상 드라이버 지정(선택)
            "target_driver_ids":{"type":"array","items":{"type":"string"}},

            "reason":{"type":"string"}
          }
        }
      },
      "narrative":{"type":"string"}
    },
    "required":["version","module","round","team_id","inputs_digest","plans","narrative"]
  }
}

# --- Crew Training: 결과 ---
CREW_TRAINING_OUTCOME_SCHEMA = {
  "name":"crew_training_outcome",
  "schema":{
    "type":"object",
    "additionalProperties": False,
    "properties":{
      "version":{"type":"string"},
      "module":{"type":"string","enum":["crew_training_outcome"]},
      "round":{"type":"integer","minimum":1},
      "team_id":{"type":"string"},
      "inputs_digest":{"type":"string"},
      "outcomes":{
        "type":"array",
        "items":{
          "type":"object",
          "required":["ref_title","realized_pit_gain_factor","morale_delta","incidents","narrative"],
          "additionalProperties": False,
          "properties":{
            "ref_title":{"type":"string"},
            "realized_pit_gain_factor":{"type":"number","minimum":0,"maximum":1},
            "morale_delta":{"type":"number","minimum":-2,"maximum":2},
            "incidents":{"type":"array","items":{"type":"string"}},
            "narrative":{"type":"string"},

            # ↓ 선택적 인적자원 실효값
            "realized_driver_skill_delta":{"type":"number"},   # points scale로 해석(예: +1.5p)
            "realized_tire_mgmt_delta":{"type":"number"},      # 드라이버 타이어 관리(+/-)
            "dev_speed_multiplier":{"type":"number","minimum":0.0,"maximum":2.0},
            "strategy_delta":{"type":"number"},                # 팀 전략 포인트(+/-)
            "reliability_delta":{"type":"number"},             # 팀 신뢰성 포인트(+/-)
            "target_driver_ids":{"type":"array","items":{"type":"string"}}
          }
        }
      }
    },
    "required":["version","module","round","team_id","inputs_digest","outcomes"]
  }
}
AI_RACE_CONTROL_PLAN_SCHEMA = {
  "name":"ai_race_control_plan",
  "schema":{
    "type":"object","additionalProperties": False,
    "properties":{
      "plans":{"type":"array","items":{
        "type":"object","additionalProperties": False,
        "properties":{
          "team":{"type":"string"},
          "pace":{"type":"array","items":{
            "type":"object","additionalProperties": False,
            "properties":{
              "from":{"type":"integer","minimum":1},
              "to":{"type":"integer","minimum":1},
              "vmul":{"type":"number","minimum":0.98,"maximum":1.03}
            },"required":["from","to","vmul"]
          }},
          "pit_laps":{"type":"array","items":{"type":"integer","minimum":2}}
        },"required":["team","pace","pit_laps"]
      }}
    },"required":["plans"]
  }
}