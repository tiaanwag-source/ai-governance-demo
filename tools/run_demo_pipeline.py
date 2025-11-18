#!/usr/bin/env python3
"""
Fire every /demo endpoint in sequence so the entire See → Score → Safeguard run
is ready with a single command.

Usage:
    python tools/run_demo_pipeline.py
"""

from __future__ import annotations

import json
import os
from typing import Dict, Any

import requests

API_BASE = os.getenv("AI_GOV_API_BASE", "http://localhost:8000").rstrip("/")

STEPS = [
    ("generate_logs", "Generate synthetic logs"),
    ("run_adapter", "Run adapter (ingest canonical events)"),
    ("apply_scoring", "Apply risk scoring + enrichment"),
    ("flag_high_risk", "Flag high-risk agents"),
    ("sdk_seed", "Seed SDK approvals"),
    ("simulate_drift", "Simulate agent drift"),
    ("watchdog", "Run watchdog"),
]


def call_step(endpoint: str) -> Dict[str, Any]:
    resp = requests.post(f"{API_BASE}/demo/{endpoint}", timeout=30)
    resp.raise_for_status()
    return resp.json()


def main() -> None:
    summaries = []
    for endpoint, label in STEPS:
        try:
            result = call_step(endpoint)
            summaries.append({"step": label, "result": result})
        except Exception as exc:
            summaries.append({"step": label, "error": str(exc)})
            break
    print(json.dumps({"pipeline": summaries}, indent=2))


if __name__ == "__main__":
    main()
