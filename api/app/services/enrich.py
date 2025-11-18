import json
from sqlalchemy import text
from sqlalchemy.orm import Session
from ..models import Agent, AgentSignal, RiskScore, ProjectAudience
from .score import score_agent
from ..policies import get_risk_config

def _jd(x): return json.dumps(x, separators=(",", ":"), ensure_ascii=False)

def _project_reach(db: Session, project_id: str | None) -> int:
    if not project_id:
        return 0
    row = db.query(ProjectAudience).filter_by(project_id=project_id).first()
    return int(row.reach_count) if row else 0

def sync_signals_and_score(db: Session, agent: Agent):
    """Maintain AgentSignal from Agent, then append a fresh RiskScore. Commit happens at caller."""
    sig = db.query(AgentSignal).filter_by(agent_id=agent.agent_id).first()
    scope = json.loads(agent.output_scope or '["internal_only"]')
    tools = json.loads(agent.tags or "[]")
    if not sig:
        sig = AgentSignal(agent_id=agent.agent_id)
        db.add(sig)

    sig.data_class     = agent.data_class or "internal"
    sig.output_scope   = _jd(scope or ["internal_only"])
    sig.reach_count    = _project_reach(db, agent.project_id)
    sig.autonomy       = agent.autonomy or "readonly"
    sig.external_tools = _jd(tools or [])
    db.flush()

    risk_config = get_risk_config(db)

    score, b, reasons = score_agent({
        "data_class": sig.data_class,
        "output_scope": scope or ["internal_only"],
        "reach_count": sig.reach_count,
        "autonomy": sig.autonomy,
        "external_tools": tools or []
    }, config=risk_config)
    db.add(RiskScore(agent_id=agent.agent_id, band=b, score=score, reasons=_jd(reasons)))

def upsert_agent_from_event(db: Session, ev: dict, enrich: dict):
    """Create/update Agent based on canonical event + classification enrich, then update signals + score."""
    a = db.query(Agent).filter_by(agent_id=ev["agent_id"]).first()
    if not a:
        a = Agent(agent_id=ev["agent_id"], platform=ev["platform"])
        db.add(a)
    a.project_id   = ev.get("project_id")
    a.location     = ev.get("location")
    a.owner_email  = ev.get("owner_email")
    a.data_class   = enrich["data_class"]
    a.output_scope = _jd(enrich["output_scope"])
    a.autonomy     = a.autonomy or "readonly"
    a.dlp_template = enrich["dlp_template"]
    a.tags         = a.tags or _jd([])

    sync_signals_and_score(db, a)
