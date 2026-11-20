"""
test_live_hype_benchmark.py - Live end-to-end benchmark measuring actual p50 and p95 latencies.
"""
import asyncio
import os
import sys
import time
import subprocess
import pytest

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from gaming_intelligence.live.pipeline import LiveHypePipeline
from gaming_intelligence.live.models import ChatMessage, Platform


@pytest.mark.asyncio
async def test_live_pipeline_e2e_benchmark(tmp_path):
    buffer_dir = str(tmp_path / "buffer")
    output_dir = str(tmp_path / "output")
    import shutil
    ffmpeg_bin = shutil.which("ffmpeg") or "ffmpeg"

    # 1. Initialize Pipeline with fast pre-roll/post-roll for testing
    pipeline = LiveHypePipeline(
        buffer_dir=buffer_dir,
        output_dir=output_dir,
        pre_roll_sec=4.0,
        post_roll_sec=2.0
    )

    # 2. Generate 4 two-second real video segments
    seg_files = []
    for i in range(4):
        seg_file = os.path.join(buffer_dir, f"seg_{i:05d}.ts")
        cmd = [
            ffmpeg_bin, "-y", "-nostdin",
            "-f", "lavfi", "-i", f"testsrc=size=1280x720:rate=30",
            "-f", "lavfi", "-i", "sine=frequency=1000:sample_rate=44100",
            "-t", "2.0",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            seg_file
        ]
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        seg_files.append(seg_file)
        pipeline.buffer.register_segment(i, seg_file, start_time=i * 2.0, end_time=(i + 1) * 2.0)

    # 3. Simulate low-traffic baseline chat
    now = time.time()
    for i in range(10):
        pipeline.ingest_message(ChatMessage(
            timestamp=now - (10 - i),
            user_id=f"user_{i}",
            text="just watching",
            platform=Platform.TWITCH
        ))

    # 4. Trigger Hype Burst
    burst_time = time.time()
    for u in range(15):
        pipeline.ingest_message(ChatMessage(
            timestamp=burst_time,
            user_id=f"burst_user_{u}",
            text="W LETS GOOO POGGERS INSANE PLAY 🔥🔥🔥",
            platform=Platform.TWITCH
        ))

    # Wait for the scheduler async task to complete post-roll, Stage A, and Stage B
    for _ in range(50):
        if pipeline.completed_jobs:
            break
        await asyncio.sleep(0.2)

    assert len(pipeline.completed_jobs) >= 1
    job = pipeline.completed_jobs[0]
    assert job.status == "complete"
    assert os.path.exists(job.draft_path)
    assert os.path.exists(job.final_path)

    stats = pipeline.get_latency_stats()
    print("\n" + "=" * 60)
    print("🎯 LIVE HYPE AUTO-CLIPPING BENCHMARK RESULTS (Actual Target Machine)")
    print("=" * 60)
    for metric, vals in stats.items():
        print(f"  ⚡ {metric:<26}: p50 = {vals['p50']} | p95 = {vals['p95']} ({vals['count']} runs)")
    print("=" * 60 + "\n")
