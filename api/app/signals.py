from typing import Dict, Tuple, List, Any
import json

from sqlalchemy.orm import Session
from sqlalchemy import text

from .models import Agent, AgentSignal, RiskScore, ClassificationMap
from .policies import get_risk_config, DEFAULT_RISK_CONFIG


def load_classification_rules(db: Session) -> Dict[Tuple[str, str], ClassificationMap]:
    """
    Build a lookup:
      key = (selector_type, selector_value)
      value = ClassificationMap row
    """
    rules: Dict[Tuple[str, str], ClassificationMap] = {}
    for row in db.query(ClassificationMap).all():
        rules[(row.selector_type, row.selector_value)] = row
    return rules


def load_project_audience(db: Session) -> Dict[str, int]:
    """
    Read project_audience via raw SQL, return:
      { project_id: reach_count }
    """
    rows = db.execute(text("SELECT project_id, reach_count FROM project_audience")).fetchall()
    return {r.project_id: r.reach_count for r in rows}


def bucket_reach(reach_count: int) -> str:
    """
    Turn numeric audience into a simple category.
    Adjust thresholds later if you want.
    """
    if reach_count >= 5000:
        return "org_wide"
    if reach_count >= 200:
        return "department"
    if reach_count >= 20:
        return "team"
    return "individual"


def ensure_json_list(value: str) -> str:
    """
    Make sure output_scope / external_tools is stored as a JSON string list.
    We keep it as TEXT in DB, but semantically it is a list.
    """
    if not value:
        return "[]"
    try:
        parsed = json.loads(value)
        if isinstance(parsed, list):
            return value
    except Exception:
        pass
    return json.dumps([value])


def compute_risk_band(
    data_class: str,
    output_scope: List[str],
    reach_bucket: str,
    autonomy: str,
    external_tools: List[str],
    config: Dict[str, Any] | None = None,
) -> (str, int, List[str]):
    config = config or DEFAULT_RISK_CONFIG
    weights = config.get("weights", DEFAULT_RISK_CONFIG["weights"])
    thresholds = config.get("band_thresholds", DEFAULT_RISK_CONFIG["band_thresholds"])
    score = 0
    reasons: List[str] = []

    score += weights["data_class"].get(data_class, 0)
    if data_class == "confidential":
        reasons.append("confidential data")

    scope_weight = 0
    if "api_external" in output_scope:
        scope_weight = weights["output_scope"].get("api_external", 0)
        reasons.append("external API egress enabled")
    elif "internal_only" in output_scope:
        scope_weight = weights["output_scope"].get("internal_only", 0)
        reasons.append("internal-only outputs")
    score += scope_weight

    score += weights["autonomy"].get(autonomy, 0)
    if autonomy == "auto_action":
        reasons.append("autonomous actions enabled")
    else:
        reasons.append("read-only / human-in-loop")

    score += weights["reach"].get(reach_bucket, 0)
    if reach_bucket == "org_wide":
        reasons.append("organisation-wide reach")
    elif reach_bucket == "department":
        reasons.append("department-level reach")
    elif reach_bucket == "team":
        reasons.append("team-level reach")

    if external_tools:
        score += weights["external_tools"].get("has_tools", 0)
        reasons.append("integrates external tools: " + ", ".join(external_tools[:3]))

    score = min(score, 100)

    if score >= thresholds.get("red", 80):
        band = "red"
    elif score >= thresholds.get("amber", 40):
        band = "amber"
    else:
        band = "green"

    return band, score, reasons


def recompute_all_signals(db: Session) -> dict:
    """
    Core job:
      - Read all agents
      - Join with classification_map + project_audience
      - Derive 5 signals
      - Write agent_signals + risk_scores
    For demo simplicity, we wipe existing signals/scores and rebuild.
    """
    rules = load_classification_rules(db)
    risk_config = get_risk_config(db)
    audience = load_project_audience(db)

    # Wipe old state for a clean recompute
    db.query(AgentSignal).delete()
    db.query(RiskScore).delete()
    db.flush()

    agents = db.query(Agent).all()
    count = 0

    for agent in agents:
        project_id = agent.project_id or ""
        rule = rules.get(("agent", agent.agent_id)) or rules.get(("project", project_id))

        # Defaults
        data_class = "internal"
        output_scope_list: List[str] = ["internal_only"]
        dlp_template = ""
        external_tools: List[str] = []
        if agent.tags:
            try:
                parsed_tags = json.loads(agent.tags)
                if isinstance(parsed_tags, list):
                    external_tools = parsed_tags
            except Exception:
                external_tools = []

        if rule:
            data_class = rule.data_class
            try:
                output_scope_list = json.loads(rule.default_output_scope)
                if not isinstance(output_scope_list, list):
                    output_scope_list = ["internal_only"]
            except Exception:
                output_scope_list = ["internal_only"]
            if rule.required_dlp_template:
                dlp_template = rule.required_dlp_template

        # Reach from project_audience
        reach_count = audience.get(project_id, 1)
        reach_bucket = bucket_reach(reach_count)

        autonomy = agent.autonomy or "readonly"

        sig = AgentSignal(
            agent_id=agent.agent_id,
            data_class=data_class,
            output_scope=json.dumps(output_scope_list),
            reach=reach_bucket,
            autonomy=autonomy,
            external_tools=json.dumps(external_tools),
        )
        db.add(sig)

        band, score, reasons = compute_risk_band(
            data_class=data_class,
            output_scope=output_scope_list,
            reach_bucket=reach_bucket,
            autonomy=autonomy,
            external_tools=external_tools,
            config=risk_config,
        )

        risk = RiskScore(
            agent_id=agent.agent_id,
            band=band,
            score=score,
            reasons=json.dumps(reasons),
        )
        db.add(risk)

        # Mirror classification back to agents for easy querying
        agent.data_class = data_class
        agent.output_scope = json.dumps(output_scope_list)
        agent.autonomy = autonomy
        agent.dlp_template = dlp_template

        count += 1

    db.commit()

    bands = dict(
        db.execute(
            text("SELECT band, COUNT(*) FROM risk_scores GROUP BY band")
        ).fetchall()
    )

    return {"agents_processed": count, "bands": bands}
