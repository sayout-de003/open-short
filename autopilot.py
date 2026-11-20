#!/usr/bin/env python3
"""CLI entry point for Zero-Touch Daily Gaming Autopilot."""
from __future__ import annotations

import argparse
import json
import sys

from autopilot.config import AutopilotConfig
from autopilot.orchestrator import AutopilotOrchestrator


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="OpenShorts Zero-Touch Gaming Autopilot")
    sub = parser.add_subparsers(dest="command", required=True)

    p_disc = sub.add_parser("discover", help="Discover and rank Top-N gaming streams and VODs")
    p_disc.add_argument("--query", type=str, default=None, help="Game or search query (e.g. 'GTA 6')")

    p_run = sub.add_parser("run", help="Run one autopilot cycle")
    p_run.add_argument("--query", type=str, default=None, help="Game or search query")
    p_run.add_argument("--dry-run", action="store_true", help="Discover and rank without downloading or posting")
    p_run.add_argument("--max-vods", type=int, default=None, help="Override MAX_VODS_PER_RUN")
    p_run.add_argument("--max-live", type=int, default=None, help="Override MAX_LIVE_STREAMS")

    sub.add_parser("reconcile", help="Reconcile Buffer post statuses and delete published local clips")
    sub.add_parser("status", help="Show autopilot queue, storage, and publishing metrics")
    sub.add_parser("cleanup", help="Delete expired local media older than CLIP_RETENTION_HOURS")

    p_retry = sub.add_parser("retry", help="Requeue a failed job by ID")
    p_retry.add_argument("job_id", type=str, help="Job ID to retry")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    cfg = AutopilotConfig.from_env()
    orch = AutopilotOrchestrator(cfg)

    if args.command == "discover":
        candidates = orch.discover_and_rank(query=args.query)
        out = [
            {
                "rank": idx + 1,
                "platform": c.platform,
                "type": c.source_type,
                "source_id": c.source_id,
                "score": c.score,
                "eligible": c.eligible,
                "title": c.title,
                "url": c.url,
            }
            for idx, c in enumerate(candidates)
        ]
        print(json.dumps(out, indent=2, ensure_ascii=False))
        return 0

    if args.command == "run":
        res = orch.run_once(
            query=args.query,
            dry_run=args.dry_run,
            max_vods=args.max_vods,
            max_live=args.max_live,
        )
        print(json.dumps(res, indent=2, ensure_ascii=False))
        return 0

    if args.command == "reconcile":
        res = orch.publisher.reconcile_pending_posts()
        print(json.dumps(res, indent=2))
        return 0

    if args.command == "cleanup":
        deleted = orch.storage.cleanup_expired_media()
        print(json.dumps({"deleted_expired_clips": deleted}, indent=2))
        return 0

    if args.command == "status":
        print(json.dumps(orch.status(), indent=2, ensure_ascii=False))
        return 0

    if args.command == "retry":
        status = orch.recovery.manual_retry(args.job_id)
        print(json.dumps({"job_id": args.job_id, "status": status.value}, indent=2))
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
