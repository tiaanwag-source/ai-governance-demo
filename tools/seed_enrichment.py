#!/usr/bin/env python3
"""
Seed demo enrichment data so the See → Score pipeline has realistic classifications.

Usage:
    python tools/seed_enrichment.py

Environment:
    DATABASE_URL (optional) - defaults to same as FastAPI app
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import List, Tuple
import os

from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT / "api"))

# Default to localhost when running outside Docker Compose
os.environ.setdefault(
    "DATABASE_URL", "postgresql+psycopg2://ai_gov:ai_gov@localhost:5432/registry"
)

from app.db import SessionLocal, engine  # type: ignore  # noqa: E402
from app.models import ClassificationMap, Agent  # type: ignore  # noqa: E402
from app.signals import recompute_all_signals  # type: ignore  # noqa: E402

CLASSIFICATION_RULES: List[Tuple[str, str, str, List[str], str | None]] = [
    ("project", "acme-ml-prod", "confidential", ["api_external"], None),
    ("project", "acme-ml-trusted", "internal", ["internal_only"], "dlp_tpl_finance_v2"),
]

PROJECT_AUDIENCE = [
    ("acme-ml-prod", 12500),
    ("acme-ml-trusted", 4200),
    ("acme-ml-sandbox", 180),
]

AUTO_ACTION_PROJECTS = {
    "acme-ml-prod": ["slack", "jira", "snowflake"],
    "acme-ml-trusted": ["github", "zendesk"],
}


def ensure_project_audience() -> None:
    with engine.connect() as conn:
        conn.execute(
            text(
                """
            CREATE TABLE IF NOT EXISTS project_audience (
                project_id TEXT PRIMARY KEY,
                reach_count INTEGER NOT NULL
            )
        """
            )
        )
        for project_id, reach in PROJECT_AUDIENCE:
            conn.execute(
                text(
                    """
                INSERT INTO project_audience (project_id, reach_count)
                VALUES (:project_id, :reach)
                ON CONFLICT (project_id) DO UPDATE SET reach_count = EXCLUDED.reach_count
            """
                ),
                {"project_id": project_id, "reach": reach},
            )
        conn.commit()


def seed_classification_rules(session) -> int:
    inserted = 0
    for selector_type, selector_value, data_class, scopes, dlp in CLASSIFICATION_RULES:
        row = (
            session.query(ClassificationMap)
            .filter(
                ClassificationMap.selector_type == selector_type,
                ClassificationMap.selector_value == selector_value,
            )
            .one_or_none()
        )
        scope_json = json.dumps(scopes)
        if row is None:
            session.add(
                ClassificationMap(
                    selector_type=selector_type,
                    selector_value=selector_value,
                    data_class=data_class,
                    default_output_scope=scope_json,
                    required_dlp_template=dlp,
                )
            )
            inserted += 1
        else:
            row.data_class = data_class
            row.default_output_scope = scope_json
            row.required_dlp_template = dlp
    return inserted


def tag_auto_action_agents(session) -> int:
    updates = 0
    for project_id, tools in AUTO_ACTION_PROJECTS.items():
        agents = (
            session.query(Agent)
            .filter(Agent.project_id == project_id)
            .order_by(Agent.updated_at.desc())
            .limit(5)
            .all()
        )
        for idx, agent in enumerate(agents):
            agent.autonomy = "auto_action" if idx % 2 == 0 else "readonly"
            agent.tags = json.dumps(tools)
            if project_id == "acme-ml-prod":
                agent.data_class = "confidential"
                agent.output_scope = json.dumps(["api_external"])
                agent.dlp_template = None
            updates += 1
    return updates


def main() -> None:
    ensure_project_audience()
    session = SessionLocal()
    try:
        inserted = seed_classification_rules(session)
        updates = tag_auto_action_agents(session)
        session.commit()
        summary = recompute_all_signals(session)
    finally:
        session.close()

    print(
        json.dumps(
            {
                "classification_rules_inserted_or_updated": inserted,
                "agents_updated": updates,
                "recompute_summary": summary,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
