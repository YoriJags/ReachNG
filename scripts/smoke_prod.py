"""Post-deploy smoke test — hit the LIVE app and fail loud if it's unhealthy.

Run after a Railway deploy (or locally against the prod URL) to catch a broken
boot before a client does:

    python scripts/smoke_prod.py                      # uses APP_BASE_URL / default
    python scripts/smoke_prod.py https://reachng.ng   # explicit base

Checks (no auth needed — all public):
  1. GET /health        -> 200, JSON status "ok", db True
  2. GET /portal/demo   -> 200 (the public investor/demo portal renders)
  3. GET /manifest...   -> 200 (PWA assets are served)

Exit code 0 = healthy, 1 = something is wrong (prints what). Designed to be the
last step of a deploy pipeline.
"""
from __future__ import annotations

import sys

import httpx


def _base_url(argv: list[str]) -> str:
    if len(argv) > 1 and argv[1].startswith("http"):
        return argv[1].rstrip("/")
    import os
    return os.environ.get("APP_BASE_URL", "https://reachng.ng").rstrip("/")


def main() -> int:
    base = _base_url(sys.argv)
    print(f"smoke: {base}")
    failures: list[str] = []

    with httpx.Client(timeout=20.0, follow_redirects=True) as c:
        # 1. health
        try:
            r = c.get(f"{base}/health")
            body = r.json()
            if r.status_code != 200:
                failures.append(f"/health returned {r.status_code}")
            elif body.get("status") != "ok" or not body.get("db"):
                failures.append(f"/health unhealthy: {body}")
            else:
                sched = body.get("scheduler", {})
                print(f"  ok  /health  db=True scheduler={sched} sentry={body.get('sentry')} env={body.get('env')}")
        except Exception as e:
            failures.append(f"/health unreachable: {e}")

        # 2. public demo portal
        try:
            r = c.get(f"{base}/portal/demo")
            if r.status_code != 200:
                failures.append(f"/portal/demo returned {r.status_code}")
            else:
                print("  ok  /portal/demo")
        except Exception as e:
            failures.append(f"/portal/demo unreachable: {e}")

        # 3. PWA manifest is served
        try:
            r = c.get(f"{base}/static/manifest.webmanifest")
            if r.status_code != 200:
                failures.append(f"/static/manifest.webmanifest returned {r.status_code}")
            else:
                print("  ok  /static/manifest.webmanifest")
        except Exception as e:
            failures.append(f"manifest unreachable: {e}")

    if failures:
        print("\nSMOKE FAILED:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("\nsmoke passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
