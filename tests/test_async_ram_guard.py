"""
tests/test_async_ram_guard.py - Tests for cross-platform RAM guard,
multi-monitor live pipeline, non-blocking stream capture, and async clip/crop/edit tasks.
"""
import asyncio
import json
import os
import sys
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import resource_guard
from gaming_intelligence.live.clipping.scheduler import ClipScheduler
from gaming_intelligence.live.models import HypeEvent, Platform
from gaming_intelligence.live.recording.buffer import RollingSegmentBuffer
from gaming_intelligence.live.recording.timestamps import TimestampSynchronizer


# --------------------------------------------------------------------------- #
# 1. resource_guard unit tests
# --------------------------------------------------------------------------- #
def test_ram_stats_returns_expected_keys():
    stats = resource_guard.ram_stats(use_cache=False)
    assert set(stats.keys()) == {"total_mb", "available_mb", "used_mb", "used_percent"}


def test_ram_has_room_thresholds():
    # Idle host (active_count=0) always fails open
    assert resource_guard.ram_has_room(min_free_mb=999999, active_count=0, avail_mb=100.0) is True
    # Disabled (min_free_mb=0) always allows
    assert resource_guard.ram_has_room(min_free_mb=0, active_count=3, avail_mb=50.0) is True
    # Below threshold with active work -> False
    assert resource_guard.ram_has_room(min_free_mb=2048, active_count=1, avail_mb=1024.0) is False
    # Above threshold -> True
    assert resource_guard.ram_has_room(min_free_mb=2048, active_count=1, avail_mb=4096.0) is True


@pytest.mark.asyncio
async def test_wait_for_ram_recovers_and_times_out():
    calls = {"n": 0}

    def fake_avail(use_cache=False):
        calls["n"] += 1
        return 500.0 if calls["n"] < 2 else 3000.0

    with patch.object(resource_guard, "available_ram_mb", side_effect=fake_avail):
        ok = await resource_guard.wait_for_ram(
            min_free_mb=2048,
            active_count_fn=lambda: 1,
            timeout_sec=2.0,
            poll_sec=0.05,
        )
        assert ok is True
        assert calls["n"] >= 2

    with patch.object(resource_guard, "available_ram_mb", return_value=256.0):
        ok = await resource_guard.wait_for_ram(
            min_free_mb=2048,
            active_count_fn=lambda: 1,
            timeout_sec=0.1,
            poll_sec=0.05,
        )
        assert ok is False


# --------------------------------------------------------------------------- #
# 2. ClipScheduler bounded concurrency + RAM check
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_live_scheduler_bounds_concurrent_renders(tmp_path):
    buf = RollingSegmentBuffer(str(tmp_path / "buf"))
    sync = TimestampSynchronizer(stream_start_wall_clock=time.time() - 5.0)
    buf.register_segment(0, str(tmp_path / "buf" / "seg_00000.ts"), 0.0, 10.0)

    extractor = MagicMock()
    renderer = MagicMock()

    peak_concurrent = 0
    current_concurrent = 0

    def slow_extract(segs, job_id):
        nonlocal peak_concurrent, current_concurrent
        current_concurrent += 1
        peak_concurrent = max(peak_concurrent, current_concurrent)
        time.sleep(0.05)
        current_concurrent -= 1
        return str(tmp_path / f"draft_{job_id}.mp4")

    def slow_render(draft_path, out_filename, target_duration=None):
        return str(tmp_path / out_filename)

    extractor.extract_draft_preview.side_effect = slow_extract
    renderer.render_vertical_short.side_effect = slow_render

    sched = ClipScheduler(
        buffer=buf,
        sync=sync,
        extractor=extractor,
        renderer=renderer,
        pre_roll_sec=5.0,
        post_roll_sec=0.0,
        max_concurrent_renders=1,
        min_free_ram_mb=0,
    )

    try:
        t0 = time.time()
        for i in range(3):
            ev = HypeEvent(
                event_id=f"ev_{i}",
                detected_at=t0,
                event_timestamp=t0 - 1.0,
                peak_velocity=10.0,
                z_score=5.0,
                top_chants=["W"],
            )
            sched.on_hype_event(ev)

        await asyncio.sleep(0.9)
        assert peak_concurrent == 1
        assert all(j.status == "complete" for j in sched.active_jobs.values())
    finally:
        sched.close()


# --------------------------------------------------------------------------- #
# 3. FastAPI async endpoints: resources, multi-monitor, async_mode tasks
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_system_resources_and_multi_monitor_and_async_tasks(tmp_path):
    import httpx
    import app as app_mod

    transport = httpx.ASGITransport(app=app_mod.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. System resources endpoint reports RAM
        r = await client.get("/api/system/resources")
        assert r.status_code == 200
        data = r.json()
        assert "ram" in data
        assert "edits_running" in data
        assert "live_monitors" in data

        # 2. Multi-monitor live start/status/stop (YouTube + Twitch concurrently)
        with patch("gaming_intelligence.live.pipeline.LiveHypePipeline.start_youtube", new=AsyncMock()), \
             patch("gaming_intelligence.live.pipeline.LiveHypePipeline.start_twitch", new=AsyncMock()), \
             patch("gaming_intelligence.live.pipeline.LiveHypePipeline.stop", new=AsyncMock()):
            r1 = await client.post("/api/intelligence/live/start", json={
                "url_or_channel": "https://www.youtube.com/watch?v=abc123",
                "platform": "youtube",
                "monitor_id": "yt_main",
            })
            assert r1.status_code == 200
            assert "yt_main" in r1.json()["active_monitors"]

            r2 = await client.post("/api/intelligence/live/start", json={
                "url_or_channel": "shroud",
                "platform": "twitch",
                "monitor_id": "twitch_side",
            })
            assert r2.status_code == 200
            assert set(["yt_main", "twitch_side"]).issubset(set(r2.json()["active_monitors"]))

            st = await client.get("/api/intelligence/live/status?monitor_id=yt_main")
            assert st.status_code == 200
            assert st.json()["active"] is True
            assert "ram" in st.json()

            stop_all = await client.post("/api/intelligence/live/stop")
            assert stop_all.status_code == 200

        # 3. Non-blocking async stream capture task
        with patch("gaming_intelligence.stream_recorder.StreamRecorder.capture_youtube_live",
                   return_value=str(tmp_path / "yt_live.mp4")):
            cap = await client.post("/api/intelligence/stream", json={
                "url": "https://youtube.com/watch?v=xyz",
                "platform": "youtube",
                "duration_seconds": 10,
                "async_mode": True,
            })
            assert cap.status_code == 200
            task_id = cap.json()["task_id"]

            for _ in range(20):
                t_res = await client.get(f"/api/tasks/{task_id}")
                if t_res.json()["status"] in ("completed", "failed"):
                    break
                await asyncio.sleep(0.05)

            assert t_res.json()["status"] == "completed"
            assert t_res.json()["result"]["filename"] == "yt_live.mp4"
