from __future__ import annotations

import json
import hashlib
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from .models import Agent, AgentSignal, RiskScore, Approval


def _parse_list(value: Optional[str]) -> List[str]:
    if not value:
        return []
    try:
        parsed = json.loads(value)
        if isinstance(parsed, list):
            return parsed
    except Exception:
        pass
    return []


def _latest_signal(db: Session, agent_id: str) -> Optional[AgentSignal]:
    return (
        db.query(AgentSignal)
        .filter(AgentSignal.agent_id == agent_id)
        .order_by(AgentSignal.updated_at.desc())
        .first()
    )


def _latest_score(db: Session, agent_id: str) -> Optional[RiskScore]:
    return (
        db.query(RiskScore)
        .filter(RiskScore.agent_id == agent_id)
        .order_by(RiskScore.computed_at.desc())
        .first()
    )


def _latest_approval(db: Session, agent_id: str) -> Optional[Approval]:
    return (
        db.query(Approval)
        .filter(Approval.agent_id == agent_id)
        .order_by(Approval.requested_at.desc())
        .first()
    )


@dataclass
class AgentContext:
    agent: Agent
    signals: Dict[str, Any]
    risk_band: Optional[str]
    risk_score: Optional[int]
    risk_reasons: List[str]


@dataclass
class PolicyDecision:
    agent_id: str
    risk_band: Optional[str]
    risk_score: Optional[int]
    approval_required: bool
    blocked: bool
    violations: List[str]
    reasons: List[str]
    system_header: str
    signals: Dict[str, Any]


BASE_HEADER = (
    "SYSTEM: You operate under ACME AI Guardrails. "
    "Never handle policy-violating requests, redact PII, "
    "and escalate anything uncertain."
)

EXTERNAL_TOOL_POOL = [
    "slack",
    "jira",
    "github",
    "snowflake",
    "zendesk",
    "salesforce",
]


def deterministic_tools(agent_id: str) -> List[str]:
    digest = hashlib.sha1(agent_id.encode("utf-8"), usedforsecurity=False).digest()
    picks: List[str] = []
    for idx, tool in enumerate(EXTERNAL_TOOL_POOL):
        if digest[idx % len(digest)] % 3 == 0:
            picks.append(tool)
    if not picks:
        picks.append(EXTERNAL_TOOL_POOL[digest[0] % len(EXTERNAL_TOOL_POOL)])
    return picks


def build_agent_context(db: Session, agent_id: str) -> Optional[AgentContext]:
    agent = db.query(Agent).filter(Agent.agent_id == agent_id).one_or_none()
    if agent is None:
        return None
    sig = _latest_signal(db, agent_id)
    score = _latest_score(db, agent_id)

    signals: Dict[str, Any] = {}
    if sig:
        try:
            scope = json.loads(sig.output_scope) if sig.output_scope else []
            if not isinstance(scope, list):
                scope = []
        except Exception:
            scope = []
        try:
            tools = json.loads(sig.external_tools) if sig.external_tools else []
            if not isinstance(tools, list):
                tools = []
        except Exception:
            tools = []
        signals = {
            "data_class": sig.data_class,
            "output_scope": scope,
            "reach": sig.reach,
            "autonomy": sig.autonomy,
            "external_tools": tools,
        }

    reasons: List[str] = []
    if score and score.reasons:
        try:
            parsed = json.loads(score.reasons)
            if isinstance(parsed, list):
                reasons = [str(r) for r in parsed]
        except Exception:
            pass

    return AgentContext(
        agent=agent,
        signals=signals,
        risk_band=score.band if score else None,
        risk_score=score.score if score else None,
        risk_reasons=reasons,
    )


def evaluate_policies(ctx: AgentContext, action: Optional[str] = None) -> PolicyDecision:
    violations: List[str] = []
    approval_required = False
    blocked = False

    agent = ctx.agent
    scope = _parse_list(agent.output_scope)
    tools = _parse_list(agent.tags)
    if not tools:
        tools = deterministic_tools(agent.agent_id)
    signals = {
        "data_class": ctx.signals.get("data_class") or agent.data_class,
        "output_scope": scope,
        "reach": ctx.signals.get("reach") or "individual",
        "autonomy": ctx.signals.get("autonomy") or agent.autonomy or "readonly",
        "external_tools": ctx.signals.get("external_tools") or tools,
    }

    risk_band = ctx.risk_band or "unknown"
    risk_score = ctx.risk_score

    if (
        signals["data_class"] == "confidential"
        and "api_external" in scope
        and not agent.dlp_template
    ):
        violations.append("Confidential data with external API but no DLP template")
        approval_required = True

    if (
        signals["autonomy"] == "auto_action"
        and signals["reach"] in ("org_wide", "department")
    ):
        violations.append("Autonomous agent with high reach requires approval")
        approval_required = True

    if risk_band == "red" and signals["autonomy"] == "auto_action":
        violations.append("Red-band autonomous agent is blocked for action")
        blocked = True

    if action and "delete" in action.lower() and risk_band != "green":
        violations.append("Destructive action requested on non-green agent")
        approval_required = True

    header_lines = [BASE_HEADER]
    if signals["data_class"] == "confidential":
        header_lines.append(
            "Handle all content as CONFIDENTIAL. Mask PII and restrict sharing."
        )
    if "api_external" in scope:
        header_lines.append(
            "External API egress is limited to approved integrations only."
        )
    else:
        header_lines.append("Outputs must remain within internal systems.")

    if signals["external_tools"]:
        header_lines.append(
            "Allowed tools: " + ", ".join(signals["external_tools"][:4])
        )

    if risk_band == "red":
        header_lines.append("Escalate responses for human review.")

    system_header = "\n".join(header_lines)

    reasons = ctx.risk_reasons[:]
    if approval_required:
        reasons.append("human approval required")
    if blocked:
        reasons.append("blocked by policy")

    return PolicyDecision(
        agent_id=agent.agent_id,
        risk_band=ctx.risk_band,
        risk_score=risk_score,
        approval_required=approval_required,
        blocked=blocked,
        violations=violations,
        reasons=reasons,
        system_header=system_header,
        signals=signals,
    )


def list_policy_violations(db: Session) -> List[Dict[str, Any]]:
    violations: List[Dict[str, Any]] = []
    agents = db.query(Agent).all()
    for agent in agents:
        ctx = build_agent_context(db, agent.agent_id)
        if ctx is None:
            continue
        latest = _latest_approval(db, agent.agent_id)
        if latest and latest.status in ("approved", "rejected"):
            continue
        decision = evaluate_policies(ctx)
        if not decision.violations:
            continue
        violations.append(
            {
                "agent_id": agent.agent_id,
                "platform": agent.platform,
                "data_class": agent.data_class,
                "output_scope": _parse_list(agent.output_scope),
                "dlp_template": agent.dlp_template,
                "risk_band": decision.risk_band,
                "risk_score": decision.risk_score,
                "rule": "; ".join(decision.violations),
            }
        )
    return violations
