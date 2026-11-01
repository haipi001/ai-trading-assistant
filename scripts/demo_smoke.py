#!/usr/bin/env python3

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request


BACKEND_URL = os.environ.get("BACKEND_URL", "http://localhost:8000").rstrip("/")


def request_json(path: str, *, method: str = "GET") -> dict:
    req = urllib.request.Request(f"{BACKEND_URL}{path}", method=method)
    with urllib.request.urlopen(req, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def main() -> int:
    try:
        health = request_json("/health")
        seed = request_json("/demo/seed", method="POST")
        status = request_json("/demo/status")
        drafts = request_json("/orders/drafts?limit=20")
    except urllib.error.URLError as exc:
        print(f"[smoke] request failed: {exc}", file=sys.stderr)
        return 1

    if health.get("status") != "ok":
        print("[smoke] backend health is not ok", file=sys.stderr)
        return 1

    seeded = seed.get("status", {}).get("seeded") is True and status.get("seeded") is True
    if not seeded:
        print("[smoke] demo seed did not report seeded=true", file=sys.stderr)
        return 1

    has_pending = any(draft.get("approval_status") == "pending" for draft in drafts)
    has_paper_ready = any(
        draft.get("approval_status") == "approved" and draft.get("execution_status") != "paper_filled"
        for draft in drafts
    )
    has_rejected = any(draft.get("approval_status") == "rejected" for draft in drafts)
    has_paper = any(draft.get("execution_status") == "paper_filled" for draft in drafts)
    completed_walkthrough = (
        status.get("current_workflow_stage") == "monthly_review_ready"
        or status.get("counts", {}).get("monthly_reviews", 0) > 0
    )
    has_actionable_or_completed_official_flow = has_pending or has_paper_ready or completed_walkthrough
    if not (has_actionable_or_completed_official_flow and has_rejected and has_paper):
        print("[smoke] draft samples are incomplete", file=sys.stderr)
        return 1

    print("[smoke] health=ok")
    print(f"[smoke] workflow_stage={status.get('current_workflow_stage')}")
    print(f"[smoke] risk={status.get('global_risk_status')} automation={status.get('automation_level')}")
    print(
        "[smoke] counts="
        f"holdings:{status.get('counts', {}).get('holdings', 0)} "
        f"theses:{status.get('counts', {}).get('theses', 0)} "
        f"drafts:{status.get('counts', {}).get('drafts', 0)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
