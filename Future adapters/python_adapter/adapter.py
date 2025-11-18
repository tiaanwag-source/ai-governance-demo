#!/usr/bin/env python3
import argparse, json, os
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests

def post_line(api_base, api_key, source, payload, session):
    r = session.post(
        f"{api_base}/events/ingest",
        params={"source": source},
        headers={"X-API-Key": api_key, "Content-Type":"application/json"} if api_key else {"Content-Type":"application/json"},
        json=payload,
        timeout=10
    )
    r.raise_for_status()
    return 1

def stream_jsonl(path: Path):
    with path.open("r", encoding="utf-8") as f:
        for ln in f:
            ln = ln.strip()
            if not ln:
                continue
            try:
                yield json.loads(ln)
            except json.JSONDecodeError:
                continue

def run(api_base, api_key, source, file, workers=12, limit=None):
    total = 0
    with requests.Session() as s, ThreadPoolExecutor(max_workers=workers) as ex:
        futs = []
        for i, payload in enumerate(stream_jsonl(file), 1):
            if limit and i > limit: break
            futs.append(ex.submit(post_line, api_base, api_key, source, payload, s))
        for fut in as_completed(futs):
            fut.result()
            total += 1
    return total

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--api_base", default=os.getenv("API_BASE","http://api:8000"))
    ap.add_argument("--api_key", default=os.getenv("API_KEY",""))
    ap.add_argument("--source", required=True, choices=["vertex","copilot"])
    ap.add_argument("--file", required=True, type=Path)
    ap.add_argument("--workers", type=int, default=12)
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()
    c = run(args.api_base, args.api_key, args.source, args.file, args.workers, args.limit)
    print(f"Ingested {c} normalized events from {args.file}")