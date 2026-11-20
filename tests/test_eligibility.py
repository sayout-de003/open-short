"""Unit tests for creator eligibility and rights policy gate."""
from __future__ import annotations

from pathlib import Path

from autopilot.database import AutopilotDatabase
from autopilot.eligibility import EligibilityGate
from autopilot.models import DiscoveredSource


def _src(channel_id: str = "ch_1") -> DiscoveredSource:
    return DiscoveredSource(
        platform="youtube",
        source_id="v1",
        source_type="vod",
        url="https://youtube.com/watch?v=v1",
        title="Test",
        channel_id=channel_id,
        channel_name="Creator",
    )


def test_eligibility_deny_and_allow_policies(tmp_path: Path) -> None:
    db = AutopilotDatabase(tmp_path / "autopilot.db")
    gate = EligibilityGate(db, require_allowlist=False)

    assert gate.check(_src("ch_1"))[0] is True

    gate.set_policy("youtube", "ch_1", "deny", reason="creator_requested_opt_out")
    ok, reason = gate.check(_src("ch_1"))
    assert ok is False
    assert reason == "creator_requested_opt_out"

    strict_gate = EligibilityGate(db, require_allowlist=True)
    assert strict_gate.check(_src("ch_2")) == (False, "not_on_allowlist")
    strict_gate.set_policy("youtube", "ch_2", "allow", reason="partner_creator")
    assert strict_gate.check(_src("ch_2")) == (True, "partner_creator")
