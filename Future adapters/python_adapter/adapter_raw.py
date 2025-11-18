#!/usr/bin/env python3
import argparse, json
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests

def post_line(api_base, source, payload, session):
    r = session.post(
        f"{api_base}/events/ingest_raw",
        params={"source": source},
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

def run(api_base, source, file, workers=8, limit=None):
    total = 0
    with requests.Session() as s, ThreadPoolExecutor(max_workers=workers) as ex:
        futures = []
        for i, payload in enumerate(stream_jsonl(file), 1):
            if limit and i > limit:
                break
            futures.append(ex.submit(post_line, api_base, source, payload, s))
        for fut in as_completed(futures):
            fut.result()
            total += 1
    return total

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--api_base", default="http://api:8000")  # container-to-container
    ap.add_argument("--source", required=True, choices=["vertex","copilot"])
    ap.add_argument("--file", required=True, type=Path)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()
    count = run(args.api_base, args.source, args.file, args.workers, args.limit)
    print(f"Ingested {count} raw events from {args.file}")