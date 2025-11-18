# Production Implementation Guide

This document maps the demo’s behaviour to a production-ready architecture so engineering teams know what to build.

---

## 1. High-level architecture

| Layer | Demo implementation | Production guidance |
|-------|--------------------|---------------------|
| Data lake / ingest | `tools/generate_synthetic_logs.py`, `/demo/generate_logs` | Stream logs from Copilot/Vertex/LLM systems via Pub/Sub, Kafka, or Lakehouse ingestion. Persist raw JSON for replay. |
| Normaliser / adapter | `/demo/run_adapter`, `api/app/main.py::ingest_canonical` | Build stateless adapters that map vendor-specific logs into the canonical schema (`events_canonical`). Use managed queue for backpressure. |
| Registry + enrichment | FastAPI service + Postgres (`ai_gov` DB) | Use a managed Postgres/Spanner equivalent or combine with a columnar store. Replace synchronous recompute with a scheduled job / Beam pipeline. |
| Risk scoring | `api/app/signals.py`, `/admin/recompute_all` | Encapsulate as a batch or incremental worker. Externalise weights in a config service (e.g., Config Connector). |
| Policy config | `policy_settings`, `classification_map`, `action_policies` tables | Host policies in a dedicated service with RBAC, change history, and approvals. Synchronise to SDK caches via pub/sub. |
| Approvals workflow | `Approval` table, `/sdk/check_and_header`, `/admin/approvals` | Integrate with your corporate ticketing/workflow tool (Jira, ServiceNow) or a dedicated approval microservice. |
| UI | SvelteKit app hitting the FastAPI APIs | Wrap with your design system, add authentication (Google IAP, Okta, etc.), and deploy statically behind a CDN. |

## 2. Data model cheat sheet

| Table | Purpose | Important columns |
|-------|---------|------------------|
| `events_canonical` | Normalised telemetry | `event_id`, `event_type`, `event_time`, `agent_id`, payload JSON |
| `agent` | Registry of agents | metadata + tags |
| `agent_signals` | Derived governance signals | `data_class`, `output_scope`, `reach`, `autonomy`, `external_tools` |
| `risk_scores` | Latest score/band per agent | `score`, `band`, `reasons`, `computed_at` |
| `action_policies` | Allow/approval matrix per verb | `allow_*`, `approve_*`, `status`, `last_seen_at` |
| `policy_settings` | JSON configs (risk weights) | `key`, `value` |
| `classification_map` | Rules mapping selectors → data class/scope | `selector_type`, `selector_value`, `data_class`, `default_output_scope` |
| `approval` | Governance approvals | `status` (`pending`,`approved`,`rejected`,`policy_expired`,`risk_shift`), `reason` JSON payload |
| `watchdog_runs` | Drift audit trail | `started_at`, `rescored`, `changes` |

## 3. APIs to reproduce

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/ingest/canonical` | POST | Adapters push canonical events (idempotent) |
| `/admin/metrics` | GET | Aggregated KPIs for UI |
| `/admin/recompute_all` | POST | Trigger scoring job (in prod use scheduler/cron) |
| `/policies/risk_scoring` | GET/PUT | Fetch & update weight config |
| `/policies/classifications` | GET/PUT | Manage classification rules |
| `/policies/actions` | GET/PUT | Manage action policies; when PUT, expire active approvals |
| `/policies/apply` | POST | Re-run scoring after policy edits |
| `/sdk/check_and_header` | POST | SDK guardrail – returns allow/block/approval decision + injected system prompts |
| `/admin/approvals` | GET | Reviewer queue |
| `/admin/approvals/{id}/decision` | POST | Approve/reject |

Add authentication (OAuth/IAP), rate limiting, and audit logging for real deployments.

## 4. Signal + enrichment logic

1. **Classification rules** – Selectors at project/env/agent granularity assign `data_class`, default output scopes, required DLP templates.
2. **Project audience** – Provides user counts per project to derive `reach` buckets.
3. **Autonomy derivation** – Deterministic mapping from event types to `readonly` vs `auto_action` (see `AUTO_ACTION_EVENTS`).
4. **External tools** – Deterministic tags or enrichment from other systems (CRM, ticketing integrations).
5. **Risk scoring** – Weighted sum with band thresholds; reasons captured for UI.

Production tips:

- Track version history for every rule/policy and require approvals for edits.
- Use metrics/alerts when coverage drops (e.g., too many `unknown` reach values).

## 5. Policy + approval lifecycle

- Each action verb gets a default `allow_*` + `approve_*` config on first sighting.
- Editing the policy expires existing approvals (`policy_expired`) so the SDK re-requests permission under the new rule.
- SDK requests include agent context + action; the service:
  1. Loads latest signals, decisions, policy matrix.
  2. Checks for existing approvals—if the risk band changed, mark them `risk_shift`.
  3. If action is blocked ⇒ respond `blocked`.
  4. If approval required ⇒ create/return `pending` approval.
  5. Otherwise allow and provide the approved system header.

For production, add:

- TTLs and usage counts on approvals.
- Notification webhooks to alert reviewers.
- Integration with incident/ticketing tools for audit.

## 6. Dependencies / deployment

- **Backend**: FastAPI + SQLAlchemy + Postgres. Containerised via `infra/docker-compose.yml`. For prod, deploy on GKE/Cloud Run/App Engine with Cloud SQL.
- **UI**: Svelte + Vite. Static build can be hosted on Cloud Run, GCS + Cloud CDN, or any SPA host.
- **Scheduler**: Cloud Scheduler / Cron to trigger rescoring + watchdog.
- **Secrets/config**: store DB creds + API keys in Secret Manager; use Config Connector or similar for risk weights/classification rules.
- **Observability**: add structured logging, metrics (e.g., Prometheus), and tracing around ingest, approvals, SDK calls.

## 7. Data sources & enrichment inputs

- **Telemetry**: vendor log exports, app logs, audit logs, LLM gateway traces.
- **Identity**: HRIS/LDAP for owner email, audience size.
- **Tooling**: CRM, code hosts, ticketing to populate `external_tools`.
- **Policy**: import from existing governance programs (DLP templates, approval matrices).

## 8. Implementation steps

1. Stand up managed Postgres + FastAPI service (or reimplement in Go/Java if preferred) with the schemas above.
2. Integrate adapters (streaming or batch) that POST canonical events.
3. Implement classification + signal derivation worker reading `events_canonical`.
4. Build the risk scoring pipeline + watchers to keep `agent_signals` and `risk_scores` current.
5. Surface metrics/approvals/policies via APIs.
6. Port the Svelte UI or rebuild using your design system; hook it to the same APIs.
7. Harden with authn/z, audit logging, CI/CD, and observability.
8. Prepare integration tests for SDK responses vs policy settings.

## 9. Future enhancements

- Streaming approvals to Slack/Teams for reviewers.
- Add LLM call simulation with tokens/cost metrics.
- Multi-environment deployments (dev/stage/prod) with config promotion.
- Event sourcing or CDC for joining with other governance tools.

Use this guide as the blueprint when translating the demo assets into your production planning documents, RFCs, or backlog items.
