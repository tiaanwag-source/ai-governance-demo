from __future__ import annotations

import json
import random
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Tuple

from fastapi import APIRouter, Depends
from sqlalchemy import text, func, asc
from sqlalchemy.orm import Session

from .db import get_db
from .models import (
    EventCanonical,
    Agent,
    AgentSignal,
    RiskScore,
    Approval,
    ClassificationMap,
    WatchdogRun,
)
from .signals import recompute_all_signals
from .policies import ensure_action_policy, action_policy_decision


PROJECTS = ["acme-ml-dev", "acme-ml-trusted", "acme-ml-sandbox"]
LOCATIONS = ["us-central1", "europe-west4", "asia-east1"]
OWNERS = [
    "alex.ryan@acme.example",
    "tina.shah@acme.example",
    "mike.lee@acme.example",
    "sara.kim@acme.example",
    "dan.cho@acme.example",
    "jason.ng@acme.example",
]
COPILOT_APPS = ["Word", "Excel", "Outlook", "PowerPoint", "Teams"]
COPILOT_OPS = [
    "CopilotSessionStarted",
    "CopilotPromptSubmitted",
    "CopilotMessageGenerated",
    "CopilotSessionEnded",
]
VERTEX_METHODS = [
    "aiplatform.agent.create",
    "aiplatform.agent.update",
    "aiplatform.agent.predict",
    "aiplatform.pipeline.run",
    "aiplatform.pipeline.failed",
]

demo_router = APIRouter(prefix="/demo", tags=["demo"])
FIXTURE_DIR = Path(__file__).resolve().parents[2] / "data"


def _load_fixture(name: str) -> List[Dict[str, object]]:
    path = FIXTURE_DIR / name
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _reset_tables(db: Session) -> None:
    for model in [AgentSignal, RiskScore, Approval, EventCanonical, Agent, ClassificationMap, WatchdogRun]:
        db.query(model).delete()
    db.flush()
    try:
        db.execute(text("DELETE FROM project_audience"))
    except Exception:
        pass
    db.commit()


def _upsert_agent_from_event(db: Session, ev: Dict[str, object]) -> None:
    agent = (
        db.query(Agent)
        .filter(Agent.agent_id == ev["agent_id"])
        .one_or_none()
    )
    if agent is None:
        agent = Agent(
            agent_id=ev["agent_id"], platform=ev["platform"]
        )
        db.add(agent)
    agent.project_id = ev.get("project_id")
    agent.location = ev.get("location")
    agent.owner_email = ev.get("owner_email")
    agent.data_class = "internal"
    agent.output_scope = '["internal_only"]'
    agent.autonomy = "readonly"
    agent.dlp_template = "dlp_tpl_finance_v2"
    agent.tags = "[]"


def _insert_event(db: Session, ev: Dict[str, object]) -> None:
    ec = EventCanonical(
        event_id=ev["event_id"],
        event_type=ev["event_type"],
        event_time=ev["event_time"],
        agent_id=ev["agent_id"],
        platform=ev["platform"],
        project_id=ev.get("project_id"),
        location=ev.get("location"),
        owner_email=ev.get("owner_email"),
        payload_json=ev["payload_json"],
    )
    db.add(ec)
    ensure_action_policy(db, ev["event_type"])
    _upsert_agent_from_event(db, ev)


def _make_vertex_event(idx: int) -> Dict[str, object]:
    project = random.choice(PROJECTS)
    location = random.choice(LOCATIONS)
    owner = random.choice(OWNERS)
    event_time = datetime.now(timezone.utc) - timedelta(seconds=idx * 5)
    agent_id = f"projects/{project}/locations/{location}/agents/{uuid.uuid4().hex[:10]}"
    payload = {
        "timestamp": event_time.isoformat(),
        "resource": {"labels": {"project_id": project, "location": location, "agent_id": agent_id}},
        "protoPayload": {
            "methodName": random.choice(VERTEX_METHODS),
            "authenticationInfo": {"principalEmail": owner},
            "metadata": {
                "jobId": f"vertex-job-{random.randint(10000,99999)}",
                "generationTokens": random.randint(50, 2000),
                "latencyMs": random.randint(50, 2000),
            },
        },
    }
    return {
        "event_id": uuid.uuid4().hex[:16],
        "event_type": payload["protoPayload"]["methodName"],
        "event_time": event_time,
        "agent_id": agent_id,
        "platform": "vertex",
        "project_id": project,
        "location": location,
        "owner_email": owner,
        "payload_json": json.dumps(payload),
    }


def _make_copilot_event(idx: int) -> Dict[str, object]:
    event_time = datetime.now(timezone.utc) - timedelta(seconds=idx * 3)
    owner = random.choice(OWNERS)
    app = random.choice(COPILOT_APPS)
    op = random.choice(COPILOT_OPS)
    session_id = uuid.uuid4().hex
    agent_id = f"m365-{app.lower()}-{session_id[:10]}"
    payload = {
        "CreationTime": event_time.isoformat(),
        "Operation": op,
        "SessionId": session_id,
        "UserId": owner,
        "App": app,
        "OrganizationId": "acme.example",
    }
    return {
        "event_id": uuid.uuid4().hex[:16],
        "event_type": op,
        "event_time": event_time,
        "agent_id": agent_id,
        "platform": "m365_copilot",
        "project_id": "m365",
        "location": "global",
        "owner_email": owner,
        "payload_json": json.dumps(payload),
    }


def _seed_classification_rules(db: Session) -> None:
    fixtures = _load_fixture("classification_fixtures.json")
    if not fixtures:
        fixtures = [
            {
                "selector_type": "project",
                "selector_value": "acme-ml-trusted",
                "data_class": "internal",
                "default_output_scope": ["internal_only"],
                "required_dlp_template": "dlp_tpl_finance_v2",
            },
            {
                "selector_type": "project",
                "selector_value": "acme-ml-sandbox",
                "data_class": "internal",
                "default_output_scope": ["internal_only"],
                "required_dlp_template": None,
            },
        ]
    for entry in fixtures:
        selector_type = entry["selector_type"]
        selector_value = entry["selector_value"]
        data_class = entry["data_class"]
        scope = json.dumps(entry.get("default_output_scope", ["internal_only"]))
        dlp = entry.get("required_dlp_template")
        row = (
            db.query(ClassificationMap)
            .filter(
                ClassificationMap.selector_type == selector_type,
                ClassificationMap.selector_value == selector_value,
            )
            .one_or_none()
        )
        if row is None:
            db.add(
                ClassificationMap(
                    selector_type=selector_type,
                    selector_value=selector_value,
                    data_class=data_class,
                    default_output_scope=scope,
                    required_dlp_template=dlp,
                )
            )
        else:
            row.data_class = data_class
            row.default_output_scope = scope
            row.required_dlp_template = dlp


def _seed_project_audience(db: Session) -> None:
    fixtures = _load_fixture("project_audience_fixtures.json")
    if not fixtures:
        fixtures = [
            {"project_id": "acme-ml-dev", "reach_count": 25000},
            {"project_id": "acme-ml-trusted", "reach_count": 4000},
            {"project_id": "acme-ml-sandbox", "reach_count": 120},
            {"project_id": "m365", "reach_count": 50000},
        ]
    db.execute(
        text(
            """
        CREATE TABLE IF NOT EXISTS project_audience (
            project_id TEXT PRIMARY KEY,
            reach_count INTEGER NOT NULL
        )
    """
        )
    )
    for entry in fixtures:
        project_id = entry["project_id"]
        reach = entry["reach_count"]
        db.execute(
            text(
                """
            INSERT INTO project_audience (project_id, reach_count)
            VALUES (:project_id, :reach)
            ON CONFLICT (project_id) DO UPDATE SET reach_count = EXCLUDED.reach_count
        """
            ),
            {"project_id": project_id, "reach": reach},
        )


def _flag_high_risk_agents(db: Session, limit: int = 10) -> List[str]:
    agents = (
        db.query(Agent)
        .filter(Agent.project_id == "acme-ml-dev")
        .order_by(asc(Agent.agent_id))
        .limit(limit)
        .all()
    )
    risky_ids: List[str] = []
    for agent in agents:
        agent.data_class = "confidential"
        agent.output_scope = '["api_external"]'
        agent.dlp_template = None
        agent.autonomy = "auto_action"
        agent.tags = json.dumps(["slack", "jira", "snowflake"])
        risky_ids.append(agent.agent_id)
        rule = (
            db.query(ClassificationMap)
            .filter(
                ClassificationMap.selector_type == "agent",
                ClassificationMap.selector_value == agent.agent_id,
            )
            .one_or_none()
        )
        payload = {
            "selector_type": "agent",
            "selector_value": agent.agent_id,
            "data_class": "confidential",
            "default_output_scope": '["api_external"]',
            "required_dlp_template": None,
        }
        if rule is None:
            db.add(ClassificationMap(**payload))
        else:
            rule.data_class = payload["data_class"]
            rule.default_output_scope = payload["default_output_scope"]
            rule.required_dlp_template = payload["required_dlp_template"]
    db.flush()
    return risky_ids


def _seed_sdk_approvals(db: Session, limit: int = 10) -> int:
    ensure_action_policy(db, "send_email")
    rows: List[Tuple[RiskScore, Agent]] = (
        db.query(RiskScore, Agent)
        .join(Agent, Agent.agent_id == RiskScore.agent_id)
        .filter(RiskScore.band == "red")
        .order_by(RiskScore.score.desc())
        .limit(limit)
        .all()
    )
    created = 0
    for score, agent in rows:
        policy = action_policy_decision(db, "send_email", score.band or "unknown")
        if policy and policy.get("allowed") and not policy.get("approval_required"):
            # No approval needed under current policy
            continue
        existing = (
            db.query(Approval)
            .filter(
                Approval.agent_id == agent.agent_id,
                Approval.action == "send_email",
            )
            .order_by(Approval.requested_at.desc())
            .first()
        )
        if existing and existing.status == "pending":
            # Pending request already exists; let reviewer handle it.
            continue
        sig = (
            db.query(AgentSignal)
            .filter(AgentSignal.agent_id == agent.agent_id)
            .order_by(AgentSignal.updated_at.desc())
            .first()
        )
        signals_payload = {
            "data_class": sig.data_class if sig else agent.data_class,
            "output_scope": sig.output_scope if sig else agent.output_scope,
            "reach": sig.reach if sig else None,
            "autonomy": sig.autonomy if sig else agent.autonomy,
            "external_tools": sig.external_tools if sig else agent.tags,
        }
        reason = {
            "request": {
                "prompt": "Send an email with confidential customer spend details to finance leadership.",
                "metadata": {"contains_pii": True, "channel": "email"},
                "action": "send_email",
            },
            "signals": signals_payload,
            "reasons": json.loads(score.reasons or "[]"),
            "violations": [
                "Confidential data with external API but no DLP template",
                "Autonomous high-reach action",
            ],
        }
        approval = Approval(
            agent_id=agent.agent_id,
            action="send_email",
            risk_band=score.band,
            status="pending",
            requested_by="demo.sdk@acme.example",
            reason=json.dumps(reason),
        )
        db.add(approval)
        created += 1
    db.commit()
    return created


def _simulate_agent_drift(db: Session) -> str | None:
    agents = (
        db.query(Agent)
        .filter(Agent.project_id == "acme-ml-trusted")
        .order_by(func.random())
        .limit(1)
        .all()
    )
    if not agents:
        return None
    agent = agents[0]
    agent.data_class = "confidential"
    agent.output_scope = '["api_external"]'
    agent.autonomy = "auto_action"
    agent.dlp_template = None
    agent.tags = json.dumps(["zendesk", "salesforce"])

    override = (
        db.query(ClassificationMap)
        .filter(
            ClassificationMap.selector_type == "agent",
            ClassificationMap.selector_value == agent.agent_id,
        )
        .one_or_none()
    )
    override_scope = json.dumps(["api_external"])
    if override is None:
        override = ClassificationMap(
            selector_type="agent",
            selector_value=agent.agent_id,
            data_class="confidential",
            default_output_scope=override_scope,
            required_dlp_template=None,
        )
        db.add(override)
    else:
        override.data_class = "confidential"
        override.default_output_scope = override_scope
        override.required_dlp_template = None

    return agent.agent_id


def _run_watchdog(db: Session) -> Dict[str, object]:
    red_before_rows = db.query(RiskScore.agent_id).filter(RiskScore.band == "red").all()
    red_before = {row[0] for row in red_before_rows}
    summary = recompute_all_signals(db)
    red_after_rows = db.query(RiskScore.agent_id).filter(RiskScore.band == "red").all()
    red_after = {row[0] for row in red_after_rows}
    new_red = sorted(red_after - red_before)
    resolved = sorted(red_before - red_after)
    run = WatchdogRun(
        rescored=summary.get("agents_processed", 0),
        changes=len(new_red) + len(resolved),
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    summary.update(
        {
            "red_before": len(red_before),
            "red_after": len(red_after),
            "new_red_agents": new_red,
            "resolved_red_agents": resolved,
            "watchdog_run_id": run.id,
        }
    )
    return summary


def _generate_events(db: Session, vertex_count: int, copilot_count: int) -> Dict[str, int]:
    random.seed(1337)
    for idx in range(vertex_count):
        _insert_event(db, _make_vertex_event(idx))
    for idx in range(copilot_count):
        _insert_event(db, _make_copilot_event(idx))
    db.commit()
    return {"vertex": vertex_count, "copilot": copilot_count}


@demo_router.post("/generate_logs")
def demo_generate_logs(db: Session = Depends(get_db)) -> Dict[str, int]:
    _reset_tables(db)
    summary = _generate_events(db, vertex_count=800, copilot_count=200)
    return summary


@demo_router.post("/run_adapter")
def demo_run_adapter(db: Session = Depends(get_db)) -> Dict[str, object]:
    events_total = db.query(EventCanonical).count()
    agents_total = db.query(Agent).count()
    return {"ingested_events": events_total, "agents_registered": agents_total}


@demo_router.post("/apply_scoring")
def demo_apply_scoring(db: Session = Depends(get_db)) -> Dict[str, object]:
    _seed_classification_rules(db)
    _seed_project_audience(db)
    db.commit()
    summary = recompute_all_signals(db)
    return summary


@demo_router.post("/sdk_seed")
def demo_sdk_seed(db: Session = Depends(get_db)) -> Dict[str, object]:
    created = _seed_sdk_approvals(db, limit=15)
    pending = db.query(Approval).filter(Approval.status == "pending").count()
    return {"approvals_created": created, "pending_total": pending}


@demo_router.post("/simulate_drift")
def demo_simulate_drift(db: Session = Depends(get_db)) -> Dict[str, object]:
    agent_id = _simulate_agent_drift(db)
    db.commit()
    if agent_id is None:
        return {"status": "no_agents_available"}
    return {
        "status": "agent_modified",
        "agent_id": agent_id,
        "description": "Confidential auto-action change applied to trigger watchdog",
    }


@demo_router.post("/watchdog")
def demo_watchdog(db: Session = Depends(get_db)) -> Dict[str, object]:
    summary = _run_watchdog(db)
    return summary


@demo_router.post("/flag_high_risk")
def demo_flag_high_risk(db: Session = Depends(get_db)) -> Dict[str, object]:
    risky_ids = _flag_high_risk_agents(db, limit=10)
    summary = recompute_all_signals(db)
    summary["flagged_high_risk"] = len(risky_ids)
    summary["agent_ids"] = risky_ids
    return summary


@demo_router.post("/clear")
def demo_clear(db: Session = Depends(get_db)) -> Dict[str, str]:
    _reset_tables(db)
    return {"status": "reset"}
