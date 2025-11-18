# api/app/main.py

from datetime import datetime, timedelta
from typing import Optional, Any, List, Dict, Literal
import json

from fastapi import FastAPI, Depends, HTTPException, APIRouter
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import func, desc, or_
from sqlalchemy.dialects.postgresql import insert

from .db import get_db, engine
from .models import (
    Base,
    EventCanonical,
    Agent,
    ClassificationMap,
    AgentSignal,
    RiskScore,
    Approval,
    WatchdogRun,
    ActionPolicy,
)
from .signals import recompute_all_signals
from .policy import (
    build_agent_context,
    evaluate_policies,
    list_policy_violations,
    deterministic_tools,
)
from .policies import (
    get_risk_config,
    save_risk_config,
    list_classifications,
    overwrite_classifications,
    list_action_policies,
    update_action_policy,
    ensure_action_policy,
    action_policy_decision,
)
from .demo import demo_router


# -------------------------------------------------------------------
# FastAPI app setup
# -------------------------------------------------------------------

AUTO_ACTION_EVENTS = {
    "agent.action",
    "agent.predict",
    "pipeline.run",
    "CopilotActionExecuted",
    "CopilotActionSuggested",
}


def _derive_autonomy(current: Optional[str], event_type: str) -> str:
    if current == "auto_action":
        return "auto_action"
    if event_type in AUTO_ACTION_EVENTS:
        return "auto_action"
    return current or "readonly"


def _ensure_tags(agent_id: str, tags: Optional[str]) -> str:
    if tags:
        try:
            parsed = json.loads(tags)
            if isinstance(parsed, list) and parsed:
                return tags
        except Exception:
            pass
    derived = deterministic_tools(agent_id)
    return json.dumps(derived)


def _serialize_approval(row: Approval) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    try:
        payload = json.loads(row.reason or "{}")
    except Exception:
        payload = {}

    violations = payload.get("violations") or []
    reasons = payload.get("reasons") or []
    signals = payload.get("signals") or {}
    request_meta = payload.get("request") or {}
    admin_note = payload.get("admin_note")

    return {
        "id": row.id,
        "agent_id": row.agent_id,
        "action": row.action,
        "risk_band": row.risk_band,
        "status": row.status,
        "requested_by": row.requested_by,
        "requested_at": row.requested_at,
        "decided_by": row.decided_by,
        "decided_at": row.decided_at,
        "violations": violations,
        "reasons": reasons,
        "signals": signals,
        "request": request_meta,
        "admin_note": admin_note,
    }


def _ensure_pending_approval(
    db: Session,
    *,
    agent_id: str,
    action: str,
    requested_by: Optional[str],
    request_payload: dict[str, Any],
    decision_reasons: List[str],
    decision_violations: List[str],
    decision_signals: dict[str, Any],
    risk_band: Optional[str],
) -> tuple[Approval, bool]:
    existing = (
        db.query(Approval)
        .filter(
            Approval.agent_id == agent_id,
            Approval.action == action,
            Approval.status == "pending",
        )
        .order_by(Approval.requested_at.desc())
        .first()
    )
    if existing:
        return existing, False

    payload = {
        "request": request_payload,
        "reasons": decision_reasons,
        "violations": decision_violations,
        "signals": decision_signals,
    }

    approval = Approval(
        agent_id=agent_id,
        action=action,
        risk_band=risk_band or "unknown",
        status="pending",
        requested_by=requested_by or "sdk",
        reason=json.dumps(payload),
    )
    db.add(approval)
    db.flush()
    db.refresh(approval)
    return approval, True


app = FastAPI(title="AI Governance Demo API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def init_db():
    # Make sure tables exist at startup
    Base.metadata.create_all(bind=engine)


@app.get("/health")
def health() -> dict[str, Any]:
    return {"ok": True}


# -------------------------------------------------------------------
# Canonical ingest (from adapter)
# -------------------------------------------------------------------

class CanonicalEventIn(BaseModel):
    event_id: str = Field(..., min_length=3, max_length=128)
    event_type: str = Field(..., min_length=2, max_length=64)
    event_time: datetime
    agent_id: str = Field(..., min_length=3, max_length=256)
    platform: str = Field(..., min_length=2, max_length=64)
    project_id: Optional[str] = None
    location: Optional[str] = None
    owner_email: Optional[str] = None
    payload_json: str = Field(..., min_length=2)


@app.post("/ingest/canonical")
def ingest_canonical(ev: CanonicalEventIn, db: Session = Depends(get_db)) -> JSONResponse:
    """
    Adapter posts canonical events here.

    Responsibilities:
      - Insert into events_canonical
      - Upsert or update agent row with basic metadata
    """
    try:
        stmt = (
            insert(EventCanonical)
            .values(
                event_id=ev.event_id,
                event_type=ev.event_type,
                event_time=ev.event_time,
                agent_id=ev.agent_id,
                platform=ev.platform,
                project_id=ev.project_id,
                location=ev.location,
                owner_email=ev.owner_email,
                payload_json=ev.payload_json,
            )
            .on_conflict_do_nothing(index_elements=["event_id"])
        )
        result = db.execute(stmt)
        inserted = result.rowcount if result is not None else 0

        ensure_action_policy(db, ev.event_type)

        agent = db.query(Agent).filter(Agent.agent_id == ev.agent_id).one_or_none()
        if agent is None:
            agent = Agent(
                agent_id=ev.agent_id,
                platform=ev.platform,
                project_id=ev.project_id,
                location=ev.location,
                owner_email=ev.owner_email,
                data_class="internal",
                output_scope='["internal_only"]',
                autonomy=_derive_autonomy("readonly", ev.event_type),
                dlp_template=None,
                tags=_ensure_tags(ev.agent_id, None),
            )
            db.add(agent)
        else:
            agent.platform = ev.platform
            agent.project_id = ev.project_id or agent.project_id
            agent.location = ev.location or agent.location
            agent.owner_email = ev.owner_email or agent.owner_email
            agent.autonomy = _derive_autonomy(agent.autonomy, ev.event_type)
            agent.tags = _ensure_tags(agent.agent_id, agent.tags)

        db.commit()
        if inserted == 0:
            return JSONResponse({"status": "duplicate", "event_id": ev.event_id})
        return JSONResponse({"status": "ok", "event_id": ev.event_id})
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"ingest_failed: {type(e).__name__}: {e}")


# -------------------------------------------------------------------
# Admin router (metrics + recompute)
# -------------------------------------------------------------------

admin_router = APIRouter(prefix="/admin", tags=["admin"])

class ApprovalDecisionIn(BaseModel):
    status: Literal["approved", "rejected"]
    decided_by: str = Field(..., min_length=3, max_length=256)
    note: Optional[str] = None


class RiskConfigPayload(BaseModel):
    config: Dict[str, Any]


class ClassificationRuleIn(BaseModel):
    selector_type: str
    selector_value: str
    data_class: str
    default_output_scope: List[str]
    required_dlp_template: Optional[str] = None


class ProjectAudienceIn(BaseModel):
    project_id: str
    reach_count: int


class ClassificationPayload(BaseModel):
    rules: List[ClassificationRuleIn]
    project_audience: List[ProjectAudienceIn]


class ActionPolicyUpdate(BaseModel):
    description: Optional[str] = None
    status: Optional[str] = None
    allow: Optional[Dict[str, bool]] = None
    approval: Optional[Dict[str, bool]] = None


@admin_router.get("/metrics")
def admin_metrics(db: Session = Depends(get_db)) -> dict[str, Any]:
    """
    Aggregate KPIs for the dashboard.
    """
    def count(model):
        try:
            return db.query(func.count(model.id)).scalar() or 0
        except SQLAlchemyError:
            return 0

    def agent_count_by(column_name: str):
        try:
            col = getattr(Agent, column_name)
            rows = db.query(col, func.count(Agent.id)).group_by(col).all()
            return [{"key": r[0], "count": r[1]} for r in rows]
        except SQLAlchemyError:
            return []

    def risk_band_counts():
        try:
            rows = (
                db.query(RiskScore.band, func.count(RiskScore.id))
                .group_by(RiskScore.band)
                .all()
            )
            return [{"band": r[0], "count": r[1]} for r in rows]
        except SQLAlchemyError:
            return []

    def events_over_time(days: int = 7):
        try:
            rows = (
                db.query(
                    func.date(EventCanonical.event_time).label("day"),
                    func.count(EventCanonical.id),
                )
                .group_by(func.date(EventCanonical.event_time))
                .order_by(func.date(EventCanonical.event_time).desc())
                .limit(days)
                .all()
            )
            return [{"day": str(r[0]), "count": r[1]} for r in rows][::-1]
        except SQLAlchemyError:
            return []

    def approvals_stats():
        stats = {
            "pending": 0,
            "approved": 0,
            "rejected": 0,
            "avg_latency_minutes": 0.0,
            "processed_last_24h": 0,
        }
        try:
            stats["pending"] = (
                db.query(func.count(Approval.id))
                .filter(Approval.status == "pending")
                .scalar()
                or 0
            )
            stats["approved"] = (
                db.query(func.count(Approval.id))
                .filter(Approval.status == "approved")
                .scalar()
                or 0
            )
            stats["rejected"] = (
                db.query(func.count(Approval.id))
                .filter(Approval.status == "rejected")
                .scalar()
                or 0
            )
            latencies = (
                db.query(Approval.requested_at, Approval.decided_at)
                .filter(
                    Approval.status.in_(["approved", "rejected"]),
                    Approval.decided_at.isnot(None),
                )
                .order_by(Approval.decided_at.desc())
                .limit(100)
                .all()
            )
            if latencies:
                total_minutes = sum(
                    max(
                        (decided - requested).total_seconds() / 60.0,
                        0,
                    )
                    for requested, decided in latencies
                )
                stats["avg_latency_minutes"] = round(
                    total_minutes / len(latencies), 1
                )
            window_start = datetime.utcnow() - timedelta(hours=24)
            stats["processed_last_24h"] = (
                db.query(func.count(Approval.id))
                .filter(
                    Approval.status.in_(["approved", "rejected"]),
                    Approval.decided_at >= window_start,
                )
                .scalar()
                or 0
            )
        except SQLAlchemyError:
            pass
        return stats

    def top_risky_agents(limit: int = 5):
        try:
            rows = (
                db.query(
                    Agent.agent_id,
                    Agent.platform,
                    Agent.owner_email,
                    RiskScore.score,
                    RiskScore.band,
                )
                .join(RiskScore, RiskScore.agent_id == Agent.agent_id)
                .order_by(RiskScore.score.desc())
                .limit(limit)
                .all()
            )
            return [
                {
                    "agent_id": r.agent_id,
                    "platform": r.platform,
                    "owner_email": r.owner_email,
                    "score": r.score,
                    "band": r.band,
                }
                for r in rows
            ]
        except SQLAlchemyError:
            return []

    def signal_coverage():
        total_agents = count(Agent)
        coverage = {
            "reach_known": 0,
            "autonomy_known": 0,
            "external_tools_known": 0,
            "total_agents": total_agents,
        }
        if total_agents == 0:
            return coverage
        try:
            coverage["autonomy_known"] = (
                db.query(func.count(Agent.id))
                .filter(Agent.autonomy.isnot(None))
                .scalar()
                or 0
            )
            coverage["reach_known"] = (
                db.query(func.count(func.distinct(AgentSignal.agent_id)))
                .filter(AgentSignal.reach.isnot(None))
                .scalar()
                or 0
            )
            coverage["external_tools_known"] = (
                db.query(func.count(func.distinct(AgentSignal.agent_id)))
                .filter(
                    AgentSignal.external_tools.isnot(None),
                    AgentSignal.external_tools != "[]",
                )
                .scalar()
                or 0
            )
        except SQLAlchemyError:
            pass
        return coverage

    def data_class_by_platform():
        try:
            rows = (
                db.query(Agent.platform, Agent.data_class, func.count(Agent.id))
                .group_by(Agent.platform, Agent.data_class)
                .all()
            )
            return [
                {"platform": r[0], "data_class": r[1], "count": r[2]} for r in rows
            ]
        except SQLAlchemyError:
            return []

    def risk_trend(days: int = 7):
        try:
            rows = (
                db.query(
                    func.date(RiskScore.computed_at).label("day"),
                    RiskScore.band,
                    func.count(RiskScore.id),
                )
                .group_by(func.date(RiskScore.computed_at), RiskScore.band)
                .order_by(func.date(RiskScore.computed_at).desc())
                .limit(days * 3)
                .all()
            )
            buckets: Dict[str, Dict[str, int]] = {}
            for row in rows:
                day = str(row[0])
                band = row[1]
                count_value = row[2]
                buckets.setdefault(day, {}).update({band: count_value})
            series = []
            for day in sorted(buckets.keys()):
                series.append(
                    {
                        "day": day,
                        "red": buckets[day].get("red", 0),
                        "amber": buckets[day].get("amber", 0),
                        "green": buckets[day].get("green", 0),
                    }
                )
            return series[-days:]
        except SQLAlchemyError:
            return []

    def recent_events(limit: int = 10):
        events = []
        try:
            rows = (
                db.query(WatchdogRun)
                .order_by(WatchdogRun.started_at.desc())
                .limit(limit)
                .all()
            )
            for run in rows:
                events.append(
                    {
                        "timestamp": str(run.started_at),
                        "type": "watchdog",
                        "message": f"Watchdog run rescored {run.rescored} agents (changes: {run.changes})",
                    }
                )
        except SQLAlchemyError:
            pass
        try:
            rows = (
                db.query(Approval)
                .order_by(Approval.requested_at.desc())
                .limit(limit)
                .all()
            )
            for row in rows:
                if row.status == "pending":
                    message = f"Approval pending for {row.agent_id}"
                else:
                    message = f"Approval {row.status} for {row.agent_id}"
                events.append(
                    {
                        "timestamp": str(row.requested_at),
                        "type": "approval",
                        "message": message,
                    }
                )
        except SQLAlchemyError:
            pass
        events.sort(key=lambda e: e["timestamp"], reverse=True)
        return events[:limit]

    def action_policy_impacts(limit_agents: int = 3):
        try:
            event_subq = (
                db.query(
                    EventCanonical.event_type.label("event_type"),
                    func.count(func.distinct(EventCanonical.agent_id)).label("agent_count"),
                    func.max(EventCanonical.event_time).label("last_invoked_at"),
                )
                .group_by(EventCanonical.event_type)
                .subquery()
            )
            pending_rows = (
                db.query(Approval.action, Approval.agent_id)
                .filter(Approval.status == "pending")
                .order_by(Approval.requested_at.desc())
                .all()
            )
            pending_counts: Dict[str, int] = {}
            pending_agents: Dict[str, List[str]] = {}
            for action_name, agent_id in pending_rows:
                pending_counts[action_name] = pending_counts.get(action_name, 0) + 1
                lst = pending_agents.setdefault(action_name, [])
                if agent_id in lst or len(lst) >= limit_agents:
                    continue
                lst.append(agent_id)
            recent_agents_rows = (
                db.query(EventCanonical.event_type, EventCanonical.agent_id)
                .order_by(EventCanonical.event_time.desc())
                .limit(200)
                .all()
            )
            recent_agent_map: Dict[str, List[str]] = {}
            for action_name, agent_id in recent_agents_rows:
                lst = recent_agent_map.setdefault(action_name, [])
                if agent_id in lst or len(lst) >= limit_agents:
                    continue
                lst.append(agent_id)

            rows = (
                db.query(
                    ActionPolicy,
                    event_subq.c.agent_count,
                    event_subq.c.last_invoked_at,
                )
                .outerjoin(
                    event_subq, event_subq.c.event_type == ActionPolicy.action_name
                )
                .order_by(ActionPolicy.action_name)
                .all()
            )
            return [
                {
                    "id": policy.id,
                    "action_name": policy.action_name,
                    "status": policy.status,
                    "allow": {
                        "green": bool(policy.allow_green),
                        "amber": bool(policy.allow_amber),
                        "red": bool(policy.allow_red),
                    },
                    "approval": {
                        "green": bool(policy.approve_green),
                        "amber": bool(policy.approve_amber),
                        "red": bool(policy.approve_red),
                    },
                    "last_seen_at": policy.last_seen_at,
                    "agent_count": agent_count or 0,
                    "last_invoked_at": last_invoked_at,
                    "recent_agents": recent_agent_map.get(policy.action_name, []),
                    "pending_approvals": pending_counts.get(policy.action_name, 0),
                    "pending_agents": pending_agents.get(policy.action_name, []),
                }
                for policy, agent_count, last_invoked_at in rows
            ]
        except SQLAlchemyError:
            return []

    try:
        violations = list_policy_violations(db)
    except Exception:
        violations = []

    try:
        pending_approvals = (
            db.query(Approval)
            .filter(Approval.status == "pending")
            .order_by(Approval.requested_at.desc())
            .limit(8)
            .all()
        )
    except SQLAlchemyError:
        pending_approvals = []

    return {
        "canonical_total": count(EventCanonical),
        "agents_total": count(Agent),
        "classification_rules": count(ClassificationMap),
        "risk_scores": count(RiskScore),
        "approvals": count(Approval),
        "watchdog_runs": count(WatchdogRun),
        "agents_by_platform": agent_count_by("platform"),
        "agents_by_data_class": agent_count_by("data_class"),
        "agents_by_autonomy": agent_count_by("autonomy"),
        "risk_bands": risk_band_counts(),
        "violations_count": len(violations),
        "violations": violations,
        "pending_approvals": [_serialize_approval(a) for a in pending_approvals],
        "events_over_time": events_over_time(),
        "approvals_stats": approvals_stats(),
        "top_risky_agents": top_risky_agents(),
        "signal_coverage": signal_coverage(),
        "data_class_by_platform": data_class_by_platform(),
        "risk_trend": risk_trend(),
        "recent_events": recent_events(),
        "action_policy_impacts": action_policy_impacts(),
    }


@admin_router.get("/approvals")
def admin_list_approvals(
    status: Optional[str] = "pending",
    limit: int = 50,
    db: Session = Depends(get_db),
) -> List[dict[str, Any]]:
    query = db.query(Approval).order_by(Approval.requested_at.desc())
    if status:
        query = query.filter(Approval.status == status)
    rows = query.limit(limit).all()
    return [_serialize_approval(r) for r in rows]


@admin_router.post("/approvals/{approval_id}/decision")
def admin_decide_approval(
    approval_id: int,
    body: ApprovalDecisionIn,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    approval = db.query(Approval).filter(Approval.id == approval_id).one_or_none()
    if approval is None:
        raise HTTPException(status_code=404, detail="approval_not_found")
    if approval.status != "pending":
        raise HTTPException(status_code=400, detail="approval_already_decided")

    approval.status = body.status
    approval.decided_by = body.decided_by
    approval.decided_at = datetime.utcnow()

    payload: dict[str, Any] = {}
    try:
        payload = json.loads(approval.reason or "{}")
    except Exception:
        payload = {}
    if body.note:
        payload["admin_note"] = body.note
    approval.reason = json.dumps(payload)

    db.add(approval)
    db.commit()
    db.refresh(approval)
    return _serialize_approval(approval)


@admin_router.post("/recompute_all")
def admin_recompute_all(db: Session = Depends(get_db)):
    """
    SCORE step:
      - Read all agents
      - Derive 5 signals (data_class, output_scope, reach, autonomy, external_tools)
      - Compute risk band + score
      - Save into agent_signals + risk_scores
      - Push classifications back to agents
    """
    summary = recompute_all_signals(db)
    return summary


app.include_router(admin_router)
policy_router = APIRouter(prefix="/policies", tags=["policies"])


@policy_router.get("/risk_scoring")
def get_risk_policy(db: Session = Depends(get_db)):
    return get_risk_config(db)


@policy_router.put("/risk_scoring")
def update_risk_policy(payload: RiskConfigPayload, db: Session = Depends(get_db)):
    return save_risk_config(db, payload.config)


@policy_router.get("/classifications")
def get_classification_policy(db: Session = Depends(get_db)):
    return list_classifications(db)


@policy_router.put("/classifications")
def put_classification_policy(
    payload: ClassificationPayload, db: Session = Depends(get_db)
):
    return overwrite_classifications(
        db,
        {
            "rules": [r.dict() for r in payload.rules],
            "project_audience": [a.dict() for a in payload.project_audience],
        },
    )


@policy_router.get("/actions")
def get_action_policies(db: Session = Depends(get_db)):
    return list_action_policies(db)


@policy_router.put("/actions/{policy_id}")
def put_action_policy(
    policy_id: int, payload: ActionPolicyUpdate, db: Session = Depends(get_db)
):
    try:
        return update_action_policy(db, policy_id, payload.dict(exclude_none=True))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@policy_router.post("/apply")
def apply_policies(db: Session = Depends(get_db)):
    summary = recompute_all_signals(db)
    return summary


app.include_router(policy_router)
app.include_router(demo_router)


# -------------------------------------------------------------------
# SDK safeguard endpoints
# -------------------------------------------------------------------

sdk_router = APIRouter(prefix="/sdk", tags=["sdk"])


class SDKCheckRequest(BaseModel):
    agent_id: str
    action: Optional[str] = None
    prompt: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    requested_by: Optional[str] = None


class SDKCheckResponse(BaseModel):
    agent_id: str
    risk_band: Optional[str] = None
    risk_score: Optional[int] = None
    approval_required: bool
    blocked: bool
    system_header: str
    reasons: List[str] = []
    violations: List[str] = []
    signals: dict[str, Any] = {}
    approval_id: Optional[int] = None
    approval_status: Optional[str] = None


@sdk_router.post("/check_and_header", response_model=SDKCheckResponse)
def sdk_check(body: SDKCheckRequest, db: Session = Depends(get_db)) -> SDKCheckResponse:
    ctx = build_agent_context(db, body.agent_id)
    if ctx is None:
        raise HTTPException(status_code=404, detail="Agent not found")

    action = body.action or "unspecified"
    decision = evaluate_policies(ctx, action=action)

    policy_decision = action_policy_decision(db, action, decision.risk_band or "unknown")
    if policy_decision:
        if not policy_decision["allowed"]:
            decision.blocked = True
        if policy_decision["approval_required"]:
            decision.approval_required = True

    latest_approval = (
        db.query(Approval)
        .filter(Approval.agent_id == ctx.agent.agent_id, Approval.action == action)
        .order_by(Approval.requested_at.desc())
        .first()
    )

    approval_row: Optional[Approval] = None
    if latest_approval:
        def mark_expired(appr: Approval, status: str) -> None:
            appr.status = status
            payload: dict[str, Any] = {}
            try:
                payload = json.loads(appr.reason or "{}")
            except Exception:
                payload = {}
            payload.setdefault("meta", {})["expired_reason"] = status
            appr.reason = json.dumps(payload)
            db.commit()

        if latest_approval.status == "approved":
            if latest_approval.risk_band != decision.risk_band:
                mark_expired(latest_approval, "risk_shift")
            else:
                decision.approval_required = False
                decision.blocked = False
                decision.reasons.append(
                    "approved_by=" + (latest_approval.decided_by or "admin")
                )
                approval_row = latest_approval
        elif latest_approval.status == "rejected":
            decision.blocked = True
            decision.approval_required = False
            decision.reasons.append("rejected_by=" + (latest_approval.decided_by or "admin"))
            approval_row = latest_approval
        elif latest_approval.status == "pending":
            if latest_approval.risk_band != decision.risk_band:
                mark_expired(latest_approval, "risk_shift")
            else:
                approval_row = latest_approval
        else:
            # statuses like policy_expired/risk_band_changed fall through
            pass

    if latest_approval and latest_approval.status == "risk_shift":
        latest_approval = None
    if latest_approval and latest_approval.status == "policy_expired":
        latest_approval = None

    if latest_approval and latest_approval.status == "approved" and approval_row is None:
        # status flipped during expiration
        latest_approval = None

    if approval_row and approval_row.status == "policy_expired":
        approval_row = None
    if approval_row and approval_row.status == "risk_shift":
        approval_row = None

    if approval_row is None and latest_approval and latest_approval.status == "rejected":
        approval_row = latest_approval
    elif approval_row is None and latest_approval and latest_approval.status == "pending":
        approval_row = latest_approval
    elif approval_row is None and latest_approval and latest_approval.status == "approved":
        decision.approval_required = False
        decision.blocked = False
        decision.reasons.append("approved_by=" + (latest_approval.decided_by or "admin"))
        approval_row = latest_approval

    if (decision.approval_required or decision.blocked) and approval_row is None:
        approval_row, created = _ensure_pending_approval(
            db,
            agent_id=ctx.agent.agent_id,
            action=action,
            requested_by=body.requested_by,
            request_payload={
                "prompt": body.prompt,
                "metadata": body.metadata or {},
                "action": action,
            },
            decision_reasons=decision.reasons,
            decision_violations=decision.violations,
            decision_signals=decision.signals,
            risk_band=decision.risk_band,
        )
        if created:
            db.commit()

    return SDKCheckResponse(
        agent_id=decision.agent_id,
        risk_band=decision.risk_band,
        risk_score=decision.risk_score,
        approval_required=decision.approval_required,
        blocked=decision.blocked,
        system_header=decision.system_header,
        reasons=decision.reasons,
        violations=decision.violations,
        signals=decision.signals,
        approval_id=approval_row.id if approval_row else None,
        approval_status=approval_row.status if approval_row else None,
    )


app.include_router(sdk_router)


# -------------------------------------------------------------------
# Agent governance endpoint for SDK
# -------------------------------------------------------------------

class AgentGovernanceOut(BaseModel):
    agent_id: str
    platform: str
    project_id: Optional[str]
    location: Optional[str]
    owner_email: Optional[str]

    data_class: str
    output_scope: List[str]
    autonomy: str
    reach: str
    external_tools: List[str]

    band: str
    score: int
    reasons: List[str]


@app.get("/agents/{agent_id:path}/governance", response_model=AgentGovernanceOut)
def get_agent_governance(agent_id: str, db: Session = Depends(get_db)):
    """
    SEE + SCORE view for a single agent.

    Joins:
      - agents
      - agent_signals (5 signals)
      - risk_scores (most recent)
    """
    agent = db.query(Agent).filter(Agent.agent_id == agent_id).one_or_none()
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent not found")

    signals = (
        db.query(AgentSignal)
        .filter(AgentSignal.agent_id == agent_id)
        .order_by(desc(AgentSignal.updated_at))
        .first()
    )
    if signals is None:
        raise HTTPException(status_code=404, detail="Agent signals not found")

    score = (
        db.query(RiskScore)
        .filter(RiskScore.agent_id == agent_id)
        .order_by(desc(RiskScore.computed_at))
        .first()
    )
    if score is None:
        raise HTTPException(status_code=404, detail="Risk score not found")

    try:
        output_scope = json.loads(signals.output_scope) if signals.output_scope else []
    except Exception:
        output_scope = []

    try:
        external_tools = json.loads(signals.external_tools) if signals.external_tools else []
    except Exception:
        external_tools = []

    try:
        reasons = json.loads(score.reasons) if score.reasons else []
    except Exception:
        reasons = []

    return AgentGovernanceOut(
        agent_id=agent.agent_id,
        platform=agent.platform,
        project_id=agent.project_id,
        location=agent.location,
        owner_email=agent.owner_email,
        data_class=signals.data_class,
        output_scope=output_scope,
        autonomy=signals.autonomy,
        reach=signals.reach,
        external_tools=external_tools,
        band=score.band,
        score=score.score,
        reasons=reasons,
    )


class AgentSummaryOut(BaseModel):
    agent_id: str
    platform: str
    project_id: Optional[str]
    location: Optional[str]
    owner_email: Optional[str]
    data_class: Optional[str]
    output_scope: List[str]
    autonomy: Optional[str]
    reach: Optional[str]
    external_tools: List[str]
    risk_band: Optional[str]
    risk_score: Optional[int]
    updated_at: Optional[datetime]
    recent_actions: List[str] = []


def _agent_summary(agent: Agent, db: Session) -> AgentSummaryOut:
    signals = (
        db.query(AgentSignal)
        .filter(AgentSignal.agent_id == agent.agent_id)
        .order_by(desc(AgentSignal.updated_at))
        .first()
    )
    score = (
        db.query(RiskScore)
        .filter(RiskScore.agent_id == agent.agent_id)
        .order_by(desc(RiskScore.computed_at))
        .first()
    )

    def parse_json_list(value: Optional[str]) -> List[str]:
        if not value:
            return []
        try:
            parsed = json.loads(value)
            if isinstance(parsed, list):
                return parsed
        except Exception:
            pass
        return []

    if signals:
        scope = parse_json_list(signals.output_scope)
        tools = parse_json_list(signals.external_tools)
        reach = signals.reach
        autonomy = signals.autonomy
        data_class = signals.data_class
    else:
        scope = parse_json_list(agent.output_scope)
        tools = parse_json_list(agent.tags)
        reach = None
        autonomy = agent.autonomy
        data_class = agent.data_class

    action_rows = (
        db.query(EventCanonical.event_type)
        .filter(EventCanonical.agent_id == agent.agent_id)
        .order_by(desc(EventCanonical.event_time))
        .limit(5)
        .all()
    )
    approval_rows = (
        db.query(Approval.action)
        .filter(Approval.agent_id == agent.agent_id)
        .order_by(desc(Approval.requested_at))
        .limit(5)
        .all()
    )
    recent_actions = []
    for (event_type,) in action_rows:
        if event_type and event_type not in recent_actions:
            recent_actions.append(event_type)
    for (action_name,) in approval_rows:
        if action_name and action_name not in recent_actions:
            recent_actions.append(action_name)

    return AgentSummaryOut(
        agent_id=agent.agent_id,
        platform=agent.platform,
        project_id=agent.project_id,
        location=agent.location,
        owner_email=agent.owner_email,
        data_class=data_class,
        output_scope=scope,
        autonomy=autonomy,
        reach=reach,
        external_tools=tools,
        risk_band=score.band if score else None,
        risk_score=score.score if score else None,
        updated_at=agent.updated_at,
        recent_actions=recent_actions,
    )


@app.get("/agents", response_model=List[AgentSummaryOut])
def list_agents(
    limit: int = 100,
    search: Optional[str] = None,
    risk_band: Optional[str] = None,
    db: Session = Depends(get_db),
) -> List[AgentSummaryOut]:
    query = db.query(Agent).order_by(Agent.updated_at.desc())
    if search:
        like = f"%{search}%"
        query = query.filter(
            or_(
                Agent.agent_id.ilike(like),
                Agent.owner_email.ilike(like),
                Agent.platform.ilike(like),
            )
        )
    rows = query.limit(limit).all()
    out: List[AgentSummaryOut] = []
    for agent in rows:
        summary = _agent_summary(agent, db)
        if risk_band and summary.risk_band != risk_band:
            continue
        out.append(summary)
    return out


# -------------------------------------------------------------------
# Simple HTML UI for demo
# -------------------------------------------------------------------

@app.get("/ui", response_class=HTMLResponse)
def ui() -> str:
    return """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <title>AI Governance Demo</title>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <style>
    :root { color-scheme: dark; }
    body {
      font-family: system-ui, -apple-system, Segoe UI, sans-serif;
      margin: 24px;
      background: #020617;
      color: #e5e7eb;
    }
    h1 { font-size: 28px; margin-bottom: 4px; }
    h2 {
      font-size: 16px;
      margin: 16px 0 8px;
      text-transform: uppercase;
      letter-spacing: .06em;
      color: #9ca3af;
    }
    .grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 12px;
    }
    .card {
      background: #020617;
      border: 1px solid #1f2937;
      border-radius: 12px;
      padding: 16px;
    }
    .kpi { font-size: 28px; font-weight: 700; }
    .label {
      color: #9ca3af;
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: .06em;
    }
    button {
      background: #111827;
      border: 1px solid #374151;
      color: #e5e7eb;
      padding: 8px 12px;
      border-radius: 8px;
      cursor: pointer;
    }
    button:hover { background: #1f2937; }
    pre {
      background: #020617;
      border-radius: 8px;
      padding: 12px;
      overflow: auto;
      font-size: 12px;
    }
    .badge {
      display: inline-block;
      padding: 2px 8px;
      border-radius: 999px;
      font-size: 11px;
      font-weight: 600;
      margin-right: 6px;
    }
    .badge.red { background: rgba(239,68,68,.15); color:#fecaca; border:1px solid #ef4444;}
    .badge.green { background: rgba(34,197,94,.15); color:#bbf7d0; border:1px solid #22c55e;}
    .badge.amber { background: rgba(245,158,11,.15); color:#fed7aa; border:1px solid #f59e0b;}
  </style>
</head>
<body>
  <h1>AI Governance Demo</h1>
  <p class="label">Registry metrics</p>
  <div id="kpis" class="grid"></div>

  <h2>Risk bands</h2>
  <div id="risk-bands" class="grid"></div>

  <div class="card" style="margin-top:16px;">
    <button onclick="refresh()">Refresh</button>
    <span class="label" style="margin-left:8px">GET /admin/metrics</span>
  </div>

  <pre id="raw"></pre>

<script>
async function refresh(){
  const r = await fetch('/admin/metrics');
  const j = await r.json();
  document.getElementById('raw').textContent = JSON.stringify(j,null,2);

  const kpis = [
    ['Canonical total', j.canonical_total],
    ['Agents total', j.agents_total],
    ['Rules', j.classification_rules],
    ['Risk scores', j.risk_scores],
    ['Approvals', j.approvals],
    ['Watchdog runs', j.watchdog_runs],
  ];
  document.getElementById('kpis').innerHTML =
    kpis.map(k => `
      <div class="card">
        <div class="kpi">${k[1]}</div>
        <div class="label">${k[0]}</div>
      </div>
    `).join('');

  const bands = j.risk_bands || [];
  const colorClass = b => {
    if (!b) return '';
    const v = b.toLowerCase();
    if (v === 'red') return 'red';
    if (v === 'green') return 'green';
    if (v === 'amber' || v === 'yellow') return 'amber';
    return '';
  };
  document.getElementById('risk-bands').innerHTML =
    bands.map(b => `
      <div class="card">
        <div class="kpi">${b.count}</div>
        <div class="label">
          <span class="badge ${colorClass(b.band)}">${b.band}</span>
        </div>
      </div>
    `).join('');
}
refresh();
</script>
</body>
</html>
    """
