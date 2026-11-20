"""Source eligibility and creator rights policy gate."""
from __future__ import annotations

import datetime
from typing import Tuple

from autopilot.database import AutopilotDatabase
from autopilot.models import DiscoveredSource


class EligibilityGate:
    """Checks creator allow/deny policies before a discovered source can enter the queue."""

    def __init__(self, db: AutopilotDatabase, require_allowlist: bool = False):
        self.db = db
        self.require_allowlist = require_allowlist

    def set_policy(self, platform: str, channel_id: str, policy: str, reason: str = "") -> None:
        if policy not in ("allow", "deny"):
            raise ValueError(f"Invalid policy: {policy!r}")
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        with self.db.transaction(immediate=True) as conn:
            conn.execute(
                """
                INSERT INTO source_policies (platform, channel_id, policy, reason, created_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(platform, channel_id)
                DO UPDATE SET policy = excluded.policy, reason = excluded.reason
                """,
                (platform.lower(), channel_id, policy, reason, now_iso),
            )

    def check(self, source: DiscoveredSource) -> Tuple[bool, str]:
        if not source.channel_id:
            return False, "missing_channel_id"

        with self.db.transaction() as conn:
            row = conn.execute(
                "SELECT policy, reason FROM source_policies WHERE platform = ? AND channel_id = ?",
                (source.platform.lower(), source.channel_id),
            ).fetchone()

        if row is not None:
            if row["policy"] == "deny":
                return False, row["reason"] or "creator_opt_out"
            if row["policy"] == "allow":
                return True, row["reason"] or "creator_allowlisted"

        if self.require_allowlist:
            return False, "not_on_allowlist"

        return True, "approved_with_attribution"

    def apply(self, source: DiscoveredSource) -> DiscoveredSource:
        ok, reason = self.check(source)
        source.eligible = ok
        source.eligibility_reason = reason
        return source
