# f1sim/ai/llm_client.py
# -*- coding: utf-8 -*-
import os, json, hashlib
from dotenv import load_dotenv
from openai import OpenAI
from jsonschema import validate, ValidationError

load_dotenv()
API_KEY = os.getenv("OPENAI_API_KEY")
if not API_KEY:
    raise RuntimeError("OPENAI_API_KEY 환경변수가 없습니다. .env에 설정해 주세요.")

client = OpenAI(api_key=API_KEY)

def digest_inputs(obj: dict) -> str:
    import hashlib, json
    return hashlib.sha256(json.dumps(obj, sort_keys=True).encode("utf-8")).hexdigest()

# ── ✨ 추가: LLM JSON 값 자동 보정 ────────────────────────────────────────────
def _clamp(x, lo, hi, default=None, cast=float):
    try:
        v = cast(x)
    except Exception:
        return default if default is not None else lo
    if v != v:  # NaN
        return default if default is not None else lo
    return min(hi, max(lo, v))

def _sanitize_for_schema(schema_name: str, data: dict) -> dict:
    """스키마 이름에 따라 숫자 범위를 안전하게 클램핑."""
    if schema_name == "crew_training_outcome":
        for o in data.get("outcomes", []):
            # dev_speed_multiplier: [0.8, 1.3], 기본 1.0
            if "dev_speed_multiplier" in o:
                o["dev_speed_multiplier"] = _clamp(o.get("dev_speed_multiplier", 1.0), 0.8, 1.3, default=1.0, cast=float)
            # pit gain factor: [0,1]
            if "realized_pit_gain_factor" in o:
                o["realized_pit_gain_factor"] = _clamp(o.get("realized_pit_gain_factor", 0.0), 0.0, 1.0, default=0.0, cast=float)
            # morale: [-2,2]
            if "morale_delta" in o:
                o["morale_delta"] = _clamp(o.get("morale_delta", 0.0), -2.0, 2.0, default=0.0, cast=float)
            # 선택 필드(드라이버/전략/신뢰성)
            if "realized_driver_skill_delta" in o:
                o["realized_driver_skill_delta"] = _clamp(o.get("realized_driver_skill_delta", 0.0), -5.0, 5.0, default=0.0, cast=float)
            if "realized_tire_mgmt_delta" in o:
                o["realized_tire_mgmt_delta"] = _clamp(o.get("realized_tire_mgmt_delta", 0.0), -5.0, 5.0, default=0.0, cast=float)
            if "strategy_delta" in o:
                o["strategy_delta"] = _clamp(o.get("strategy_delta", 0.0), -10.0, 10.0, default=0.0, cast=float)
            if "reliability_delta" in o:
                o["reliability_delta"] = _clamp(o.get("reliability_delta", 0.0), -10.0, 10.0, default=0.0, cast=float)

    elif schema_name == "crew_training_plan":
        for p in data.get("plans", []):
            if "pit_gain_hint" in p:
                p["pit_gain_hint"] = _clamp(p.get("pit_gain_hint", 0.3), 0.0, 1.0, default=0.3, cast=float)
            if "morale_hint" in p:
                p["morale_hint"] = _clamp(p.get("morale_hint", 0.0), -1.0, 1.0, default=0.0, cast=float)
            if "cost_musd" in p:
                p["cost_musd"] = _clamp(p.get("cost_musd", 0.0), 0.0, 999.0, default=0.0, cast=float)
            if "sessions" in p:
                p["sessions"] = int(_clamp(p.get("sessions", 1), 1, 4, default=1, cast=float))
            # HR 힌트도 0..1로 정리
            for k in ("driver_skill_hint","dev_speed_hint","strategy_hint","reliability_hint"):
                if k in p:
                    p[k] = _clamp(p.get(k, 0.0), 0.0, 1.0, default=0.0, cast=float)
    return data
# ─────────────────────────────────────────────────────────────────────────────

def ask_llm_json(schema: dict, system_prompt: str, user_prompt: str, temperature: float = 0.4) -> dict:
    """
    schema: {"name":"...", "schema":{...}}  (jsonschema dict)
    OpenAI 응답을 스키마로 검증해 dict로 반환.
    """
    resp = client.chat.completions.create(
        model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        temperature=temperature,
        response_format={"type": "json_schema", "json_schema": schema},
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    )
    raw = resp.choices[0].message.content
    data = json.loads(raw)

    # ✨ 검증 전 보정
    data = _sanitize_for_schema(schema.get("name",""), data)

    try:
        validate(instance=data, schema=schema["schema"])
    except ValidationError as e:
        # 마지막 방어: dev_speed_multiplier 누락/0 같은 흔한 실수를 기본값으로 채우고 한 번 더 시도
        data = _sanitize_for_schema(schema.get("name",""), data)
        try:
            validate(instance=data, schema=schema["schema"])
        except ValidationError:
            raise RuntimeError(f"LLM JSON invalid: {e.message}")

    return data
