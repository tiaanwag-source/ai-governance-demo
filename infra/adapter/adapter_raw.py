import json
import sys
import time
import hashlib
from typing import Iterable, Dict

import requests
from dateutil import parser as dtp

API = "http://api:8000"
BATCH_SLEEP = 0.0005  # tiny pause to avoid hammering api
FIRST_ERROR_LOGGED = False


def sha1(s: str) -> str:
    return hashlib.sha1(s.encode("utf-8"), usedforsecurity=False).hexdigest()[:12]


def parse_time(val: str | None) -> str:
    if not val:
        return dtp.now().isoformat()
    try:
        return dtp.parse(val).isoformat()
    except Exception:
        return dtp.now().isoformat()


def coalesce(d: Dict, *keys: str, default=None):
    """Simple helper: returns first non-empty value for dotted paths."""
    for k in keys:
        cur = d
        ok = True
        for part in k.split("."):
            if isinstance(cur, dict) and part in cur:
                cur = cur[part]
            else:
                ok = False
                break
        if ok and cur not in (None, "", []):
            return cur
    return default


def iter_jsonl(path: str) -> Iterable[Dict]:
    """Read a JSONL file line-by-line and yield JSON objects."""
    with open(path, "r", encoding="utf-8") as f:
        for i, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError as e:
                global FIRST_ERROR_LOGGED
                if not FIRST_ERROR_LOGGED:
                    FIRST_ERROR_LOGGED = True
                    print(
                        json.dumps(
                            {
                                "error": "json_decode_failed",
                                "path": path,
                                "line_number": i,
                                "message": str(e),
                                "line_sample": line[:200],
                            }
                        )
                    )
                # skip bad line
                continue


def map_vertex(raw: Dict) -> Dict:
    """Map a synthetic Vertex log record into canonical event shape."""
    etime = coalesce(raw, "timestamp", "protoPayload.timestamp")
    owner = coalesce(
        raw,
        "protoPayload.authenticationInfo.principalEmail",
        "authenticationInfo.principalEmail",
        default=None,
    )
    project = coalesce(
        raw, "resource.labels.project_id", "projectId", default="acme-ml-trusted"
    )
    location = coalesce(
        raw, "resource.labels.location", "location", default="us-central1"
    )

    # Build a synthetic agent id from resource labels
    agent_name = coalesce(
        raw, "resource.labels.agent_id", default="vertex-generic-agent"
    )

    # Fall back: derive agent id from project + region + hash
    if agent_name == "vertex-generic-agent":
        agent_name = (
            f"projects/{project}/locations/{location}/agents/"
            f"{sha1(json.dumps(raw, sort_keys=True)[:256])}"
        )

    method = coalesce(
        raw, "protoPayload.methodName", "methodName", default="agent.update"
    )

    base_for_eid = f"{agent_name}|{method}|{etime or ''}|{owner or ''}"
    eid = sha1(base_for_eid)

    return {
        "event_id": eid,
        "event_type": method,
        "event_time": parse_time(etime),
        "agent_id": agent_name,
        "platform": "vertex",
        "project_id": project,
        "location": location,
        "owner_email": owner,
        "payload_json": json.dumps(raw, separators=(",", ":")),
    }


def map_copilot(raw: Dict) -> Dict:
    """Map a synthetic Microsoft Copilot audit record into canonical event shape."""
    etime = coalesce(raw, "CreationTime", "TimeCreated")
    user = coalesce(raw, "UserId", "UserKey", "User")
    org = coalesce(raw, "OrganizationId", "TenantId", default="acme.example")
    workload = coalesce(raw, "Workload", default="MicrosoftCopilot")
    op = coalesce(raw, "Operation", default="CopilotEvent")
    app = coalesce(
        raw, "App", "Application", "AppName", "Resource", default="UnknownApp"
    )

    # stable-ish agent id based on workload, app, org and user
    agent = f"m365-{workload}-{app}-{sha1((org or 'unknown') + '-' + (user or 'unknown'))}"

    base_for_eid = f"{agent}|{op}|{etime or ''}|{user or ''}"
    eid = sha1(base_for_eid)

    return {
        "event_id": eid,
        "event_type": op,
        "event_time": parse_time(etime),
        "agent_id": agent,
        "platform": "m365_copilot",
        "project_id": "m365",
        "location": "global",
        "owner_email": user,
        "payload_json": json.dumps(raw, separators=(",", ":")),
    }


def post_event(ev: Dict) -> bool:
    """POST one canonical event to the API, log first failure."""
    global FIRST_ERROR_LOGGED
    try:
        resp = requests.post(f"{API}/ingest/canonical", json=ev, timeout=5)
    except Exception as e:
        if not FIRST_ERROR_LOGGED:
            FIRST_ERROR_LOGGED = True
            print(
                json.dumps(
                    {
                        "error": "post_failed",
                        "message": str(e),
                        "event_id": ev.get("event_id"),
                    }
                )
            )
        return False

    if resp.status_code >= 300:
        if not FIRST_ERROR_LOGGED:
            FIRST_ERROR_LOGGED = True
            # try to show response text if any
            body = None
            try:
                body = resp.text
            except Exception:
                body = "<no-body>"
            print(
                json.dumps(
                    {
                        "error": "http_failure",
                        "status": resp.status_code,
                        "body": body,
                        "event_id": ev.get("event_id"),
                    }
                )
            )
        return False

    return True


def load_file(path: str, source: str) -> dict:
    """Read one JSONL file and send everything to /ingest/canonical."""
    sent = 0
    skipped = 0

    for raw in iter_jsonl(path):
        try:
            if source == "vertex":
                ev = map_vertex(raw)
            elif source == "m365_copilot":
                ev = map_copilot(raw)
            else:
                skipped += 1
                continue
        except Exception as e:
            # mapping failed
            global FIRST_ERROR_LOGGED
            if not FIRST_ERROR_LOGGED:
                FIRST_ERROR_LOGGED = True
                print(
                    json.dumps(
                        {
                            "error": "mapping_failed",
                            "source": source,
                            "message": str(e),
                        }
                    )
                )
            skipped += 1
            continue

        if not post_event(ev):
            skipped += 1
            continue

        sent += 1
        # slight backoff to avoid hammering local API
        if sent % 100 == 0:
            time.sleep(BATCH_SLEEP)

    return {"sent": sent, "skipped": skipped}


def main(argv: list[str]) -> None:
    if len(argv) != 3:
        print(
            json.dumps(
                {
                    "error": "usage",
                    "message": "adapter_raw.py /data/vertex_big.jsonl /data/copilot_big.jsonl",
                }
            )
        )
        sys.exit(1)

    vertex_path = argv[1]
    copilot_path = argv[2]

    total_sent = 0
    total_skipped = 0

    v_stats = load_file(vertex_path, "vertex")
    total_sent += v_stats["sent"]
    total_skipped += v_stats["skipped"]

    c_stats = load_file(copilot_path, "m365_copilot")
    total_sent += c_stats["sent"]
    total_skipped += c_stats["skipped"]

    print(json.dumps({"sent": total_sent, "skipped": total_skipped}))


if __name__ == "__main__":
    main(sys.argv)