#!/usr/bin/env python3
import json
import uuid
import random
from pathlib import Path
from datetime import datetime, timedelta, timezone

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
DATA_DIR.mkdir(exist_ok=True)

USERS = [
    "dan.cho@acme.example",
    "tina.shah@acme.example",
    "sara.kim@acme.example",
    "mike.lee@acme.example",
    "alex.ryan@acme.example",
    "jason.ng@acme.example",
]

COPILOT_APPS = ["Word", "Excel", "Outlook", "PowerPoint", "Teams", "Loop"]
COPILOT_OPS = [
    "CopilotSessionStarted",
    "CopilotPromptSubmitted",
    "CopilotSessionEnded",
    "CopilotMessageGenerated",
]
COPILOT_ACTIONS = [
    "GenerateEmailDraft",
    "SummarizeThread",
    "RewriteDocument",
    "CreatePresentation",
    "SummarizeDocument",
]

VERTEX_ACTIONS = [
    "pipeline.create",
    "pipeline.run",
    "pipeline.failed",
    "agent.create",
    "agent.update",
    "agent.predict",
    "endpoint.predict",
]
VERTEX_REGIONS = ["us-central1", "europe-west4", "asia-east1"]
VERTEX_PROJECTS = ["acme-ml-dev", "acme-ml-trusted", "acme-ml-sandbox"]

NOW = datetime.now(timezone.utc)

def rand_time(offset_days=7):
    delta = timedelta(
        days=random.randint(0, offset_days),
        seconds=random.randint(0, 86400)
    )
    return (NOW - delta).isoformat()

def gen_copilot_event():
    user = random.choice(USERS)
    app = random.choice(COPILOT_APPS)
    op = random.choice(COPILOT_OPS)
    action = random.choice(COPILOT_ACTIONS)

    # add some noise: sometimes omit Parameters or ClientIP, etc
    base = {
        "CreationTime": rand_time(),
        "RecordType": "MicrosoftCopilotAudit",
        "Operation": op,
        "Workload": "MicrosoftCopilot",
        "UserId": user,
        "OrganizationId": "acme.example",
        "App": app,
        "SessionId": uuid.uuid4().hex,
        "ObjectId": f"{app}:{uuid.uuid4().hex[:12]}",
    }

    params = {
        "UserAgent": "Mozilla/5.0",
        "LatencyMs": random.randint(100, 2000),
        "ActionName": action,
        "TokenCount": random.randint(50, 2000),
    }
    if random.random() < 0.15:
        # sometimes include a redacted prompt snippet
        params["PromptSnippet"] = "[REDACTED_PROMPT_SNIPPET]"

    if random.random() < 0.9:
        base["Parameters"] = params

    if random.random() < 0.8:
        base["ClientIP"] = f"203.0.113.{random.randint(1,254)}"

    return base

def gen_vertex_event():
    user = random.choice(USERS)
    action = random.choice(VERTEX_ACTIONS)
    region = random.choice(VERTEX_REGIONS)
    project = random.choice(VERTEX_PROJECTS)
    job_id = f"vertex-job-{random.randint(10000,99999)}"
    agent_name = f"projects/{project}/locations/{region}/agents/{uuid.uuid4().hex[:8]}"

    # base Cloud Logging-like record
    base = {
        "timestamp": rand_time(),
        "severity": random.choice(["INFO", "NOTICE", "WARNING"]),
        "logName": f"projects/{project}/logs/aiplatform.googleapis.com%2F{action}",
        "resource": {
            "type": "aiplatform.googleapis.com/Agent",
            "labels": {
                "project_id": project,
                "location": region,
                "agent_id": agent_name,
            },
        },
        "protoPayload": {
            "serviceName": "aiplatform.googleapis.com",
            "methodName": f"aiplatform.{action}",
            "authenticationInfo": {
                "principalEmail": user,
            },
            "metadata": {
                "jobId": job_id,
                "generationTokens": random.randint(50, 2000),
                "latencyMs": random.randint(50, 3000),
            },
        },
    }

    # add some noise: sometimes include error or safety signals
    if action in ("pipeline.failed", "agent.predict") and random.random() < 0.1:
        base["protoPayload"]["status"] = {
            "code": random.choice([7, 13]),
            "message": random.choice([
                "PERMISSION_DENIED",
                "INTERNAL",
            ]),
        }

    if action == "agent.predict" and random.random() < 0.07:
        base["protoPayload"]["metadata"]["safety"] = {
            "flagged": True,
            "category": random.choice(["PII", "Toxic", "Violence"]),
        }

    return base

def main():
    vertex_file = DATA_DIR / "vertex_big.jsonl"
    copilot_file = DATA_DIR / "copilot_big.jsonl"

    vertex_n = 6000
    copilot_n = 4000

    with vertex_file.open("w") as vf:
        for _ in range(vertex_n):
            ev = gen_vertex_event()
            vf.write(json.dumps(ev) + "\n")

    with copilot_file.open("w") as cf:
        for _ in range(copilot_n):
            ev = gen_copilot_event()
            cf.write(json.dumps(ev) + "\n")

    print(f"Wrote {vertex_n} Vertex events to {vertex_file}")
    print(f"Wrote {copilot_n} Copilot events to {copilot_file}")

if __name__ == "__main__":
    main()