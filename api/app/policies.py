from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict

from sqlalchemy.orm import Session
from sqlalchemy import text

from .models import (
    PolicySetting,
    ActionPolicy,
    ClassificationMap,
    Agent,
    AgentSignal,
    EventCanonical,
    Approval,
)

DEFAULT_RISK_CONFIG = {
    "weights": {
        "data_class": {"confidential": 40, "internal": 10},
        "output_scope": {"api_external": 30, "internal_only": 5},
        "autonomy": {"auto_action": 20, "readonly": 5},
        "reach": {"org_wide": 20, "department": 10, "team": 5},
        "external_tools": {"has_tools": 10, "none": 0},
    },
    "band_thresholds": {"red": 80, "amber": 40},
}


def _get_setting(db: Session, key: str) -> str | None:
    row = db.query(PolicySetting).filter(PolicySetting.key == key).one_or_none()
    if row:
        return row.value
    return None


def _set_setting(db: Session, key: str, value: str) -> None:
    row = db.query(PolicySetting).filter(PolicySetting.key == key).one_or_none()
    if row is None:
        row = PolicySetting(key=key, value=value)
        db.add(row)
    else:
        row.value = value
    db.flush()


def get_risk_config(db: Session) -> Dict[str, Any]:
    raw = _get_setting(db, "risk_scoring")
    if raw:
        try:
            return json.loads(raw)
        except Exception:
            pass
    return DEFAULT_RISK_CONFIG


def save_risk_config(db: Session, config: Dict[str, Any]) -> Dict[str, Any]:
    _set_setting(db, "risk_scoring", json.dumps(config))
    db.commit()
    return config


def list_classifications(db: Session) -> Dict[str, Any]:
    rules = [
        {
            "id": row.id,
            "selector_type": row.selector_type,
            "selector_value": row.selector_value,
            "data_class": row.data_class,
            "default_output_scope": json.loads(row.default_output_scope),
            "required_dlp_template": row.required_dlp_template,
        }
        for row in db.query(ClassificationMap).order_by(ClassificationMap.id).all()
    ]
    audience = [
        {"project_id": r[0], "reach_count": r[1]}
        for r in db.execute(
            text("SELECT project_id, reach_count FROM project_audience ORDER BY project_id")
        ).fetchall()
    ]
    return {"rules": rules, "project_audience": audience}


def overwrite_classifications(db: Session, payload: Dict[str, Any]) -> Dict[str, Any]:
    rules = payload.get("rules", [])
    audience = payload.get("project_audience", [])
    db.query(ClassificationMap).delete()
    for rule in rules:
        db.add(
            ClassificationMap(
                selector_type=rule["selector_type"],
                selector_value=rule["selector_value"],
                data_class=rule["data_class"],
                default_output_scope=json.dumps(rule.get("default_output_scope", [])),
                required_dlp_template=rule.get("required_dlp_template"),
            )
        )
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
    db.execute(text("DELETE FROM project_audience"))
    for row in audience:
        db.execute(
            text(
                "INSERT INTO project_audience (project_id, reach_count) VALUES (:project_id, :reach)"
            ),
            {"project_id": row["project_id"], "reach": row["reach_count"]},
        )
    db.commit()
    return list_classifications(db)


def ensure_action_policy(db: Session, action_name: str) -> ActionPolicy:
    policy = (
        db.query(ActionPolicy)
        .filter(ActionPolicy.action_name == action_name)
        .one_or_none()
    )
    now = datetime.now(timezone.utc)
    if policy is None:
        policy = ActionPolicy(
            action_name=action_name,
            description=f"Auto-discovered action {action_name}",
            status="needs_review",
            allow_green=1,
            allow_amber=1,
            allow_red=0,
            approve_green=0,
            approve_amber=1,
            approve_red=1,
            last_seen_at=now,
        )
        db.add(policy)
        db.flush()
    else:
        policy.last_seen_at = now
    return policy


def expire_action_approvals(db: Session, action_name: str, reason: str = "policy_expired") -> None:
    rows = (
        db.query(Approval)
        .filter(
            Approval.action == action_name,
            Approval.status.in_(["pending", "approved"]),
        )
        .all()
    )
    for approval in rows:
        approval.status = reason
        meta: dict[str, Any] = {}
        try:
            meta = json.loads(approval.reason or "{}")
        except Exception:
            meta = {}
        meta.setdefault("meta", {})["expired_reason"] = reason
        approval.reason = json.dumps(meta)


def list_action_policies(db: Session) -> list[dict[str, Any]]:
    rows = db.query(ActionPolicy).order_by(ActionPolicy.action_name).all()
    if not rows:
        # Backfill policies for any existing event types so the UI has defaults
        event_types = (
            db.query(EventCanonical.event_type)
            .distinct()
            .order_by(EventCanonical.event_type)
            .all()
        )
        if event_types:
            for (event_type,) in event_types:
                ensure_action_policy(db, event_type)
            db.commit()
            rows = db.query(ActionPolicy).order_by(ActionPolicy.action_name).all()
    return [
        {
            "id": row.id,
            "action_name": row.action_name,
            "description": row.description,
            "status": row.status,
            "allow": {
                "green": bool(row.allow_green),
                "amber": bool(row.allow_amber),
                "red": bool(row.allow_red),
            },
            "approval": {
                "green": bool(row.approve_green),
                "amber": bool(row.approve_amber),
                "red": bool(row.approve_red),
            },
            "last_seen_at": row.last_seen_at,
        }
        for row in rows
    ]


def update_action_policy(db: Session, policy_id: int, payload: Dict[str, Any]) -> dict:
    row = db.query(ActionPolicy).filter(ActionPolicy.id == policy_id).one_or_none()
    if row is None:
        raise ValueError("action_policy_not_found")
    allow = payload.get("allow", {})
    approval = payload.get("approval", {})
    row.description = payload.get("description", row.description)
    row.status = payload.get("status", row.status)
    policy_changed = False
    if "green" in allow:
        row.allow_green = 1 if allow["green"] else 0
        policy_changed = True
    if "amber" in allow:
        row.allow_amber = 1 if allow["amber"] else 0
        policy_changed = True
    if "red" in allow:
        row.allow_red = 1 if allow["red"] else 0
        policy_changed = True
    if "green" in approval:
        row.approve_green = 1 if approval["green"] else 0
        policy_changed = True
    if "amber" in approval:
        row.approve_amber = 1 if approval["amber"] else 0
        policy_changed = True
    if "red" in approval:
        row.approve_red = 1 if approval["red"] else 0
        policy_changed = True
    if policy_changed:
        expire_action_approvals(db, row.action_name, reason="policy_expired")
    db.commit()
    return {
        "id": row.id,
        "action_name": row.action_name,
        "status": row.status,
        "allow": {
            "green": bool(row.allow_green),
            "amber": bool(row.allow_amber),
            "red": bool(row.allow_red),
        },
        "approval": {
            "green": bool(row.approve_green),
            "amber": bool(row.approve_amber),
            "red": bool(row.approve_red),
        },
        "description": row.description,
    }


def action_policy_decision(db: Session, action: str, risk_band: str) -> Dict[str, bool] | None:
    policy = (
        db.query(ActionPolicy)
        .filter(ActionPolicy.action_name == action)
        .one_or_none()
    )
    if policy is None:
        return None
    allow = {
        "green": bool(policy.allow_green),
        "amber": bool(policy.allow_amber),
        "red": bool(policy.allow_red),
    }
    approval = {
        "green": bool(policy.approve_green),
        "amber": bool(policy.approve_amber),
        "red": bool(policy.approve_red),
    }
    return {
        "allowed": allow.get(risk_band, True),
        "approval_required": approval.get(risk_band, False),
    }
