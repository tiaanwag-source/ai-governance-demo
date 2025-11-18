from datetime import datetime, timezone

def _parse_ts(ts: str) -> datetime:
    if ts.endswith("Z"):
        ts = ts.replace("Z", "+00:00")
    return datetime.fromisoformat(ts)

def normalize_vertex(payload: dict) -> dict:
    pp = payload.get("protoPayload", {}) or {}
    res = payload.get("resource", {}) or {}
    labels = res.get("labels", {}) or {}
    rname = pp.get("resourceName") or ""

    # agent id
    agent_id = rname.split("/")[-1] if rname else "unknown"

    # event type
    method = pp.get("methodName", "") or ""
    if "CreateAgent" in method: etype = "agent.create"
    elif "UpdateAgent" in method: etype = "agent.update"
    elif "DeleteAgent" in method: etype = "agent.delete"
    elif "Predict" in method or "GenerateContent" in method: etype = "agent.predict"
    else: etype = "agent.event"

    # project and location
    project_id = labels.get("project_id")
    location = labels.get("location")
    if not location and rname:
        parts = rname.split("/")
        try:
            idx = parts.index("locations")
            location = parts[idx + 1]
        except ValueError:
            pass
        except IndexError:
            pass

    return {
        "event_id": payload.get("insertId") or rname or agent_id,
        "event_type": etype,
        "event_time": _parse_ts(payload["timestamp"]),
        "agent_id": agent_id,
        "platform": "vertex",
        "project_id": project_id,
        "location": location,
        "owner_email": (pp.get("authenticationInfo") or {}).get("principalEmail"),
        "payload": payload,
    }

def normalize_copilot(payload: dict) -> dict:
    ev_id = payload.get("SessionId") or payload.get("ObjectId") or "unknown"
    op = payload.get("Operation", "")
    if op == "CopilotSessionStarted": etype = "agent.session_start"
    elif op == "CopilotSessionEnded": etype = "agent.session_end"
    elif op == "CopilotActionExecuted": etype = "agent.action"
    elif op == "CopilotResponseGenerated": etype = "agent.response"
    else: etype = "agent.event"

    return {
        "event_id": ev_id,
        "event_type": etype,
        "event_time": _parse_ts(payload["CreationTime"]),
        "agent_id": f"m365-{payload.get('App','App')}-{ev_id[:12]}",
        "platform": "m365_copilot",
        "project_id": "m365",
        "location": None,
        "owner_email": payload.get("UserId"),
        "payload": payload,
    }