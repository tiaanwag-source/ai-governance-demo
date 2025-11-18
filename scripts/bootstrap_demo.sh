#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo ">> Starting API + Postgres via docker compose"
docker compose -f infra/docker-compose.yml up -d --build db api

echo ">> Installing UI dependencies"
pushd ui >/dev/null
npm install
echo ">> Launching Vite dev server on http://localhost:5173"
npm run dev -- --host 0.0.0.0 --port 5173
popd >/dev/null
