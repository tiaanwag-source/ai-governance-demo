# Demo Delivery Guide

This repo now ships with a single bootstrap script so you can hand the demo to a teammate (technical or not) and have them running in minutes.

## Prerequisites

| Tool | Version | Notes |
|------|---------|-------|
| Docker Desktop / Compose | v2+ | Starts the API + Postgres containers |
| Node.js + npm | Node 18+, npm 9+ | Powers the Svelte UI |
| Python 3.10+ | optional | Only needed if you want to run the CLI pipeline script |

Clone or unzip the repo on the target machine and open a terminal in the project root.

## One-command bootstrap

```bash
chmod +x scripts/bootstrap_demo.sh
./scripts/bootstrap_demo.sh
```

What the script does:

1. Runs `docker compose -f infra/docker-compose.yml up -d --build db api` (Fresh FastAPI + Postgres containers with the latest code).
2. Installs UI dependencies under `ui/`.
3. Launches the Vite dev server on `http://localhost:5173`.

Leave the script running; open the URL in a browser to use the dashboard. When finished, press `Ctrl+C` in that terminal and run `docker compose -f infra/docker-compose.yml down` to stop the containers.

## Optional helpers

- Seed the narrative automatically: `python tools/run_demo_pipeline.py` (runs generate logs → adapter → scoring → flag high-risk → approvals → drift → watchdog).
- Reset the environment: hit the “Reset demo” button on the Pipeline tab or run `curl -X POST http://localhost:8000/demo/clear`.

## Packaging / sharing the build

If you need a self-contained archive for the team:

```bash
git clean -fdx   # optional: remove local build artefacts
git archive --format=tar.gz --output ai_gov_demo.tar.gz HEAD
```

Share `ai_gov_demo.tar.gz`; the recipient extracts it, installs prerequisites, and runs `./scripts/bootstrap_demo.sh`.

## Smoke test checklist

1. Start the stack via `./scripts/bootstrap_demo.sh`.
2. Open `http://localhost:5173`, click “Generate synthetic logs”, “Run adapter”, “Apply scoring”, “Flag high-risk agents”.
3. Click “Seed approvals” then “Simulate drift” + “Run watchdog”.
4. Visit the Policies tab, toggle a verb, mark it reviewed, and see the Action Policy Impact table update.
5. Use the SDK tester to call the verb you just edited; confirm the JSON response aligns with the policy.
6. Optional: open the Agents tab and verify “Recent actions” lists `send_email`.

If all steps succeed, the demo is ready to hand off. Provide this document plus the runbook & production guide to your teammates.
