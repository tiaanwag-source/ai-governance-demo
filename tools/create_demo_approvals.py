#!/usr/bin/env python3
"""
Kick off SDK guardrail checks for high-risk agents so the approvals console
is populated with realistic pending actions.

    python tools/create_demo_approvals.py

Environment (optional):
    DATABASE_URL         - defaults to postgres on localhost:5432
    AI_GOV_API_BASE      - defaults to http://localhost:8000
    DEMO_APPROVAL_LIMIT  - how many agents to target (default: 30)
"""

from __future__ import annotations

import os
import sys
import json
from pathlib import Path
from typing import List

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT / "api"))

os.environ.setdefault(
    "DATABASE_URL", "postgresql+psycopg2://ai_gov:ai_gov@localhost:5432/registry"
)

from app.db import SessionLocal  # type: ignore  # noqa: E402
from app.models import Agent  # type: ignore  # noqa: E402


def select_risky_agents(limit: int) -> List[str]:
    session = SessionLocal()
    try:
        rows = (
            session.query(Agent.agent_id)
            .filter(
                Agent.data_class == "confidential",
                Agent.autonomy == "auto_action",
            )
            .order_by(Agent.updated_at.desc())
            .limit(limit)
            .all()
        )
        return [row[0] for row in rows]
    finally:
        session.close()


def main() -> None:
    limit = int(os.getenv("DEMO_APPROVAL_LIMIT", "30"))
    api_base = os.getenv("AI_GOV_API_BASE", "http://localhost:8000").rstrip("/")

    agent_ids = select_risky_agents(limit)
    if not agent_ids:
        print(json.dumps({"error": "no_risky_agents_found"}, indent=2))
        return

    results = []
    for agent_id in agent_ids:
        payload = {
            "agent_id": agent_id,
            "action": "send_email",
            "prompt": "Send an email with confidential customer spend details to finance leadership.",
            "metadata": {"contains_pii": True, "channel": "email"},
            "requested_by": "demo.sdk@acme.example",
        }
        try:
            resp = requests.post(
                f"{api_base}/sdk/check_and_header",
                json=payload,
                timeout=10,
            )
            resp.raise_for_status()
            body = resp.json()
        except Exception as exc:
            body = {"agent_id": agent_id, "error": str(exc)}
        results.append(body)

    print(json.dumps({"sdk_checks": results}, indent=2))


if __name__ == "__main__":
    main()
