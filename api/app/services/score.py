import json

from ..policies import get_risk_config, DEFAULT_RISK_CONFIG

REACH_BUCKETS = [
  (0, 0), (1, 5), (10, 10), (100, 15), (1000, 25), (10000, 35), (100000, 45)
]

WEIGHTS = {
  "data_class": {"internal": 0, "confidential": 25},
  "output_scope": {"internal_only": 0, "api_external": 25, "public": 40},
  "autonomy": {"readonly": 0, "auto_action": 20},
  "external_tools": {"none": 0, "has_tools": 10},
}

def _reach_points(n: int) -> int:
    pts = 0
    for thr, w in REACH_BUCKETS:
        if n >= thr: pts = w
        else: break
    return pts

def band(score: int) -> str:
    if score >= 60: return "red"
    if score >= 30: return "amber"
    return "green"

def score_agent(signals: dict, config: dict | None = None) -> tuple[int, str, list[str]]:
    config = config or DEFAULT_RISK_CONFIG
    weights = config.get("weights", DEFAULT_RISK_CONFIG["weights"])
    thresholds = config.get("band_thresholds", DEFAULT_RISK_CONFIG["band_thresholds"])
    s = 0
    reasons: list[str] = []

    dc = signals.get("data_class", "internal")
    s += weights["data_class"].get(dc, 0)
    if dc == "confidential": reasons.append("confidential data")

    scope = signals.get("output_scope", ["internal_only"])
    flat_scope = "public" if "public" in scope else ("api_external" if "api_external" in scope else "internal_only")
    s += weights["output_scope"].get(flat_scope, 0)
    if flat_scope != "internal_only": reasons.append(f"egress={flat_scope}")

    aut = signals.get("autonomy", "readonly")
    s += weights["autonomy"].get(aut, 0)
    if aut == "auto_action": reasons.append("autonomous")

    tools = signals.get("external_tools", [])
    if tools and len(tools) > 0:
        s += weights["external_tools"]["has_tools"]
        reasons.append("external_tools")

    rc = int(signals.get("reach_count", 0) or 0)
    rp = _reach_points(rc)
    s += rp
    if rp > 0: reasons.append(f"reach={rc}")

    def band(score: int) -> str:
        if score >= thresholds.get("red", 60): return "red"
        if score >= thresholds.get("amber", 30): return "amber"
        return "green"

    return s, band(s), reasons
