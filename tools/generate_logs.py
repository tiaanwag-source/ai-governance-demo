#!/usr/bin/env python3
import json, uuid, random, argparse
from pathlib import Path
from datetime import datetime, timedelta, timezone

def iso(ts):
    return ts.replace(microsecond=0).isoformat().replace("+00:00","Z")

def gen_vertex(n, out_path):
    now = datetime.now(timezone.utc)
    projects  = ["acme-ml-dev","acme-ml-trusted","acme-ml-sandbox","acme-ml-prod"]
    locations = ["us-central1","europe-west4","australia-southeast1"]
    methods   = [
        "google.cloud.aiplatform.v1.AgentService.CreateAgent",
        "google.cloud.aiplatform.v1.AgentService.UpdateAgent",
        "google.cloud.aiplatform.v1.AgentService.DeleteAgent",
        "google.cloud.aiplatform.v1.PredictionService.Predict",
        "google.cloud.aiplatform.v1.PredictionService.StreamGenerateContent",
    ]
    users = [
        "alex.ryan@acme.example","tina.shah@acme.example","mike.lee@acme.example",
        "sara.kim@acme.example","jason.ng@acme.example","dan.cho@acme.example"
    ]
    with open(out_path, "w", encoding="utf-8") as f:
        for i in range(n):
            ts        = now - timedelta(seconds=i*11)
            project   = random.choice(projects)
            location  = random.choice(locations)
            method    = random.choice(methods)
            agent_id  = uuid.uuid4().hex[:12]
            insert_id = uuid.uuid4().hex[:16]
            row = {
                "timestamp": iso(ts),
                "insertId": insert_id,
                "logName": f"projects/{project}/logs/cloudaudit.googleapis.com%2Factivity",
                "resource": {
                    "type": "aiplatform.googleapis.com/Agent",
                    "labels": {"project_id": project, "location": location}
                },
                "protoPayload": {
                    "serviceName": "aiplatform.googleapis.com",
                    "methodName": method,
                    "resourceName": f"projects/{project}/locations/{location}/agents/{agent_id}",
                    "authenticationInfo": {"principalEmail": random.choice(users)},
                    "request": {"name": f"projects/{project}/locations/{location}/agents/{agent_id}"},
                    "response": {"status": "OK"}
                }
            }
            f.write(json.dumps(row) + "\n")

def gen_copilot(n, out_path):
    now = datetime.now(timezone.utc)
    apps = ["Word","Excel","PowerPoint","Outlook","Teams","SharePoint"]
    ops  = [
        "CopilotSessionStarted","CopilotPromptSent","CopilotResponseGenerated",
        "CopilotActionSuggested","CopilotActionExecuted","CopilotSessionEnded"
    ]
    users = [
        "alex.ryan@acme.example","tina.shah@acme.example","mike.lee@acme.example",
        "sara.kim@acme.example","jason.ng@acme.example","dan.cho@acme.example"
    ]
    with open(out_path, "w", encoding="utf-8") as f:
        for i in range(n):
            ts         = now - timedelta(seconds=i*9 + 3)
            session_id = uuid.uuid4().hex
            app        = random.choice(apps)
            op         = random.choice(ops)
            user       = random.choice(users)
            row = {
                "CreationTime": iso(ts),
                "RecordType": "MicrosoftCopilotAudit",
                "Operation": op,
                "Workload": "MicrosoftCopilot",
                "UserId": user,
                "ClientIP": f"203.0.113.{random.randint(1,254)}",
                "SessionId": session_id,
                "App": app,
                "OrganizationId": "acme.example",
                "ObjectId": f"{app}:{uuid.uuid4().hex[:12]}",
                "Parameters": {"UserAgent":"Mozilla/5.0","LatencyMs": random.randint(30,1200)}
            }
            f.write(json.dumps(row) + "\n")

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--vertex_count", type=int, default=10000)
    p.add_argument("--copilot_count", type=int, default=10000)
    p.add_argument("--out_dir", type=Path, default=Path.home()/"ai_governance_demo/data/samples")
    args = p.parse_args()

    args.out_dir.mkdir(parents=True, exist_ok=True)
    v_path = args.out_dir / "vertex_big.jsonl"
    c_path = args.out_dir / "copilot_big.jsonl"

    gen_vertex(args.vertex_count, v_path)
    gen_copilot(args.copilot_count, c_path)

    print("Wrote:")
    print(v_path, v_path.stat().st_size, "bytes")
    print(c_path, c_path.stat().st_size, "bytes")