"""
test_live_hype_pipeline.py - Comprehensive unit & integration tests for ultra-low-latency live hype clipping.
"""
import os
import sys
import time
import subprocess
import pytest

# Ensure open-short is on sys.path
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from gaming_intelligence.live.models import ChatMessage, Platform, HypeEvent, ClipMode, LatencyMilestones
from gaming_intelligence.live.chat.normalizer import parse_twitch_irc_line, parse_youtube_chat_item
from gaming_intelligence.live.detection.features import tokenize_text, extract_message_features
from gaming_intelligence.live.detection.spam import SpamFilter
from gaming_intelligence.live.detection.hype import FastHypeDetector
from gaming_intelligence.live.recording.buffer import RollingSegmentBuffer
from gaming_intelligence.live.recording.timestamps import TimestampSynchronizer
from gaming_intelligence.live.clipping.extractor import FastClipExtractor
from gaming_intelligence.live.clipping.renderer import FastVerticalRenderer, detect_best_encoder


# --------------------------------------------------------------------------- #
# 1. Chat Normalization & Parsing Tests
# --------------------------------------------------------------------------- #
def test_parse_twitch_irc_line():
    raw_line = ":shroud!shroud@shroud.tmi.twitch.tv PRIVMSG #shroud :W LETS GOOO WHAT A SHOT!!!"
    msg = parse_twitch_irc_line(raw_line, timestamp=1700000000.0)
    assert msg is not None
    assert msg.user_id == "shroud"
    assert msg.text == "W LETS GOOO WHAT A SHOT!!!"
    assert msg.platform == Platform.TWITCH
    assert msg.timestamp == 1700000000.0

    # Non-message lines return None
    assert parse_twitch_irc_line(":tmi.twitch.tv 001 shroud :Welcome") is None
    assert parse_twitch_irc_line("PING :tmi.twitch.tv") is None


def test_parse_youtube_chat_item():
    item = {
        "snippet": {
            "displayMessage": "POGGERS THAT WAS INSANE 🔥",
            "superChatMessageDetails": {"amountMicros": 5000000}
        },
        "authorDetails": {
            "channelId": "UC_TEST123",
            "isChatSponsor": True
        }
    }
    msg = parse_youtube_chat_item(item, timestamp=1700000010.0)
    assert msg is not None
    assert msg.user_id == "UC_TEST123"
    assert msg.text == "POGGERS THAT WAS INSANE 🔥"
    assert msg.platform == Platform.YOUTUBE
    assert msg.is_subscriber is True
    assert msg.bits_or_superchat == 5.0


# --------------------------------------------------------------------------- #
# 2. Token Matching & Feature Extraction Tests (No Substring False Positives)
# --------------------------------------------------------------------------- #
def test_feature_extraction_no_false_positives():
    # "SWEET" contains "W" but must NOT trigger hype word "W"
    h_count, t_count, caps_ratio, chants = extract_message_features("SWEET POTATO")
    assert h_count == 0
    assert "W" not in chants

    # Exact hype words must match
    h_count, t_count, caps_ratio, chants = extract_message_features("WWWW POG KEKW INSANE 🔥")
    assert h_count == 5
    assert set(chants) == {"W", "POG", "KEKW", "INSANE", "🔥"}
    assert caps_ratio == 1.0


def test_caps_ratio_calculation():
    _, _, caps_ratio, _ = extract_message_features("OMG NO WAY")
    assert caps_ratio == 1.0

    _, _, caps_ratio_low, _ = extract_message_features("just chilling here")
    assert caps_ratio_low == 0.0


# --------------------------------------------------------------------------- #
# 3. Spam & Rate Limiter Tests
# --------------------------------------------------------------------------- #
def test_spam_filter():
    sf = SpamFilter(max_user_mps=3, window_sec=2.0)
    t = 1000.0
    # User sends 3 messages in same window -> allowed
    assert sf.is_spam("user1", t, "W") is False
    assert sf.is_spam("user1", t + 0.1, "W") is False
    assert sf.is_spam("user1", t + 0.2, "W") is False
    # 4th message in 2.0s -> dropped as spam
    assert sf.is_spam("user1", t + 0.3, "W") is True

    # Different user is not blocked
    assert sf.is_spam("user2", t + 0.3, "W") is False

    # After window advances, user1 can message again
    assert sf.is_spam("user1", t + 2.5, "W") is False


# --------------------------------------------------------------------------- #
# 4. O(1) Hype Detector & Burst Z-Score Tests
# --------------------------------------------------------------------------- #
def test_fast_hype_detector_burst_trigger():
    triggered_events = []

    detector = FastHypeDetector(
        short_window_sec=3,
        baseline_window_sec=20,
        z_score_threshold=2.0,
        min_mps=2.0,
        min_unique_users=2,
        cooldown_sec=5.0,
        on_hype_event=lambda e: triggered_events.append(e)
    )

    t = 1000.0
    # 1. Warm up baseline with low activity (1 msg every 2s)
    for i in range(15):
        detector.add_message(ChatMessage(
            timestamp=t + i,
            user_id=f"idle_{i}",
            text="hello chat",
            platform=Platform.TWITCH
        ))

    assert len(triggered_events) == 0

    # 2. Inject massive hype burst at t=1016 (multiple users shouting chants)
    burst_t = t + 16.0
    for u in range(12):
        detector.add_message(ChatMessage(
            timestamp=burst_t,
            user_id=f"hype_user_{u}",
            text="W LETS GOOO POGGERS 🔥🔥🔥",
            platform=Platform.TWITCH
        ))

    # Evaluate metrics
    metrics = detector.compute_metrics(int(burst_t))
    assert metrics.velocity_mps >= 4.0
    assert metrics.chant_density > 0.3
    assert metrics.z_score >= 2.0

    # Verify event fired immediately on crossing threshold
    assert len(triggered_events) == 1
    event = triggered_events[0]
    assert event.peak_velocity >= 2.0
    assert "POGGERS" in event.top_chants or "W" in event.top_chants


# --------------------------------------------------------------------------- #
# 5. Rolling Segment Buffer & Pinning Tests
# --------------------------------------------------------------------------- #
def test_rolling_segment_buffer_pinning(tmp_path):
    buf_dir = str(tmp_path / "buffer")
    buf = RollingSegmentBuffer(buf_dir, max_retention_sec=10.0)

    # Create dummy segment files
    seg_files = []
    for i in range(10):
        p = os.path.join(buf_dir, f"seg_{i:03d}.ts")
        with open(p, "w") as f:
            f.write(f"data_{i}")
        seg_files.append(p)
        # Each segment covers 2.0s: [0, 2], [2, 4], [4, 6]...
        buf.register_segment(i, p, start_time=i * 2.0, end_time=(i + 1) * 2.0)

    # Pin segments overlapping [4.0, 10.0]
    pinned = buf.pin_range(4.0, 10.0, job_id="job_42")
    # Overlapping indices: 2 (4-6), 3 (6-8), 4 (8-10)
    pinned_indices = {s.segment_index for s in pinned}
    assert pinned_indices == {2, 3, 4}

    # Advancing stream time to 25.0s (retention 10.0s -> cutoff 15.0s):
    # Segments with end_time < 15.0s are expired:
    # Segments 0, 1, 5, 6 are UNPINNED and expired -> deleted (4 segments).
    # Segments 2, 3, 4 are PINNED -> must NOT be deleted!
    deleted = buf.clean_expired(current_stream_time=25.0)
    assert deleted == 4  # seg 0, 1, 5, 6 deleted

    assert not os.path.exists(seg_files[0])
    assert not os.path.exists(seg_files[1])
    assert not os.path.exists(seg_files[5])
    assert os.path.exists(seg_files[2])  # Preserved because pinned!
    assert os.path.exists(seg_files[3])  # Preserved because pinned!
    assert os.path.exists(seg_files[4])  # Preserved because pinned!

    # Unpin job
    buf.unpin("job_42")
    assert buf.is_pinned(2) is False

    # Now clean_expired will clean the 3 previously pinned segments (2, 3, 4)
    deleted_after = buf.clean_expired(current_stream_time=25.0)
    assert deleted_after == 3
    assert not os.path.exists(seg_files[2])


# --------------------------------------------------------------------------- #
# 6. Two-Stage Fast Video Extraction & Vertical Rendering Tests
# --------------------------------------------------------------------------- #
def test_two_stage_rendering_and_hardware_encoder(tmp_path):
    out_dir = str(tmp_path / "out")
    buf_dir = str(tmp_path / "buf")
    os.makedirs(out_dir, exist_ok=True)
    os.makedirs(buf_dir, exist_ok=True)

    # Generate a real 3-second test MP4 video using ffmpeg lavfi testsrc
    import shutil
    ffmpeg_bin = shutil.which("ffmpeg") or "ffmpeg"
    sample_mp4 = os.path.join(buf_dir, "sample.mp4")
    gen_cmd = [
        ffmpeg_bin, "-y", "-nostdin",
        "-f", "lavfi", "-i", "testsrc=size=1280x720:rate=30",
        "-f", "lavfi", "-i", "sine=frequency=1000:sample_rate=44100",
        "-t", "3",
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        sample_mp4
    ]
    subprocess.run(gen_cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    assert os.path.exists(sample_mp4)

    # Create dummy segment referencing the sample
    from gaming_intelligence.live.models import VideoSegment
    seg = VideoSegment(
        segment_index=0,
        filepath=sample_mp4,
        start_time=0.0,
        end_time=3.0,
        duration=3.0,
        created_at=time.time()
    )

    # Stage A: Fast Draft Extraction
    extractor = FastClipExtractor(output_dir=out_dir)
    t0 = time.time()
    draft_path = extractor.extract_draft_preview([seg], job_id="test_job")
    extract_duration = time.time() - t0

    assert os.path.exists(draft_path)
    assert extract_duration < 2.0  # Must be under 2s target

    # Stage B: Vertical 9:16 Render
    renderer = FastVerticalRenderer(output_dir=out_dir)
    t1 = time.time()
    final_path = renderer.render_vertical_short(draft_path, "test_short_916.mp4", target_duration=3.0)
    render_duration = time.time() - t1

    assert os.path.exists(final_path)
    assert render_duration < 15.0  # Allow CPU encoding variance on VPS

    # Verify 9:16 aspect ratio with ffprobe
    ffprobe_bin = shutil.which("ffprobe") or "ffprobe"
    probe_cmd = [
        ffprobe_bin, "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=width,height",
        "-of", "csv=s=x:p=0",
        final_path
    ]
    res = subprocess.run(probe_cmd, stdout=subprocess.PIPE, text=True)
    dims = res.stdout.strip()
    assert dims == "1080x1920"


# --------------------------------------------------------------------------- #
# 7. Latency Milestones & Percentile Statistics
# --------------------------------------------------------------------------- #
def test_latency_milestones():
    m = LatencyMilestones(
        chat_received_at=100.0,
        hype_detected_at=100.05,
        pre_roll_pinned_at=100.08,
        extract_started_at=105.0,
        extract_completed_at=106.2,
        render_started_at=106.3,
        render_completed_at=109.8
    )
    d = m.to_dict()
    assert d["detection_latency_ms"] == 50.0
    assert d["pinning_latency_ms"] == 30.0
    assert d["extraction_latency_ms"] == 1200.0
    assert d["render_latency_ms"] == 3500.0
    assert d["total_time_to_clip_sec"] == 9.75
