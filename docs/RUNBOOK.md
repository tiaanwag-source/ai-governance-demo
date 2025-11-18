# AI Governance Demo Runbook

Use this handbook when you are narrating the story to stakeholders. It explains what each panel simulates and the order to follow.

## 0. Start the environment

```
./scripts/bootstrap_demo.sh
```

Keep that terminal open (it runs Docker + the UI). Open `http://localhost:5173`.

## 1. Pipeline tab – See → Score → Safeguard → Watch

| Step | Button | Simulates | Talking points |
|------|--------|-----------|----------------|
| 1 | **Generate synthetic logs** | Raw Copilot + Vertex log dumps landing in object storage | Resets all tables and creates 1k mixed events |
| 2 | **Run adapter** | Log adapter normalises events into the canonical registry | Populates `events_canonical`, registers agents |
| 3 | **Apply scoring** | Classification + enrichment job deriving 5 signals then computing risk bands | Shows signal derivation + risk scoring outputs |
| 4 | **Flag high-risk agents** | Governance override that tightens policies on a handful of agents | Creates red-band agents so dashboards/approvals are interesting |
| 5 | **Seed approvals** | SDK safecall generating approval requests for risky actions | Requests are persisted with prompt, signals, violations |
| 6 | **Simulate drift** | Human changes an agent configuration in production | Watchdog will later detect the change |
| 7 | **Run watchdog** | Scheduled rescoring job | Compares red list before/after, records run |
| 8 | **Reset demo** | Purges everything | Useful before the next meeting |

The right-hand card in the Pipeline tab contains the SDK tester (see section 4).

## 2. Dashboard (default tab)

### Hero metrics

- Agents in registry, canonical events, pending approvals, policy violations, watchdog runs.
- Emphasise “single glass” view for governance.

### Risk posture + Approvals workload

- Left card: stacked risk-band bar + Top risky agents table.
- Right card: approval donut + latency, processed volume.

### Signals & policy impact

- Signal completeness bars for reach/autonomy/tools.
- Data-class-by-platform chips.
- Events ingested in the last 7 days.
- Action policy impact table shows every verb, allow/approval matrix, pending/recent agents, last-seen timestamp, and a “Needs review” badge.

### Timeline + lists

- Recent events timeline (watchdog runs + approval decisions + policy changes).
- Violations table (what rule was broken).
- Approvals queue table.

Remind users they can click the sidebar tabs for Agents, Approvals, Pipeline, Policies.

## 3. Policies tab

Three columns: Risk scoring weights, Classification rules, Action policies.

- Adjust weights to show how risk scoring is tunable.
- Classification rules mimic production selectors (project/agent).
- Action policies: toggles per risk band for Allow vs Approval Required plus “Mark as reviewed”.
  - Editing a verb automatically expires old approvals for that action.
  - Needs review badge disappears after the button is clicked.

## 4. SDK policy tester

Found at the bottom of the Pipeline page.

1. Select an action verb (populated from the same catalog as the Policies tab).
2. Optional: pick from the list of agents that recently triggered this verb.
3. Click **Run SDK check**. The JSON response mirrors `/sdk/check_and_header`.

Demonstrate that changing the action policy (e.g., block amber) alters the SDK response (blocked/approval required) and creates new approvals/violations.

## 5. Agents & Approvals tabs

- **Agents tab** lists every agent with data class, scope, autonomy, reach, tools, risk score, and *Recent actions* (verbs gleaned from telemetry + approvals). Use it to show discoverability.
- **Approvals tab** is a dedicated reviewer surface (same data as the dashboard table but with pagination/actions). Approve or reject one to show status cycling.

## 6. Resetting between demos

Either:

- Click “Reset demo” on the Pipeline tab, **or**
- Run `curl -X POST http://localhost:8000/demo/clear` and refresh the UI, **or**
- `docker compose -f infra/docker-compose.yml down -v` followed by rerunning `./scripts/bootstrap_demo.sh`.

## 7. Troubleshooting talking points

- If policies are edited, approvals may disappear—explain the “policy-expired” logic.
- If SDK tester still shows allowed after policy changes, verify there isn’t an existing approval already granted; the new logic expires it when the risk band or policy shifts.
- “No action verbs yet” means the pipeline hasn’t run Steps 1–4.

Use this script to narrate the value chain: ingest → classification → scoring → policies → SDK guardrails → monitoring.
