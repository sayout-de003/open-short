"""Tests for 20/80 layout, Median+MAD hype detection, live monitor callback, best_cut, and vod_hype."""
import json
from pathlib import Path

import camera_inset
import clip_selection
from gaming_intelligence.live.detection.features import extract_message_features
from gaming_intelligence.live.detection.hype import FastHypeDetector
from gaming_intelligence.live.models import ChatMessage, ClipJob, HypeEvent, Platform
from gaming_intelligence import vod_hype


def test_inset_filtergraph_20_80_preserves_aspect_ratio():
    graph = camera_inset.inset_filtergraph(
        1920, 1080, 1080, 1920, (1500, 800, 320, 180),
        camera_ratio=0.20, cam_position="top", add_divider=True, fill_screen=True,
    )
    assert "scale=1080:384[cam]" in graph
    assert "scale=1080:1536[screen]" in graph
    assert "[cam][screen]vstack" in graph

    # Narrow/edge-clamped webcam box that can't widen to 2.8125x uses aspect-preserving crop
    clamped = camera_inset.inset_filtergraph(
        1080, 1920, 1080, 1920, (0, 0, 200, 600),
        camera_ratio=0.20, cam_position="top", add_divider=True, fill_screen=True,
    )
    assert "force_original_aspect_ratio=increase,crop=1080:384[cam]" in clamped


def test_multiword_hype_phrase_matching():
    h_count, _, _, matched = extract_message_features("NO WAY CLIP IT RIGHT NOW!!")
    assert h_count >= 2
    assert "NO WAY" in matched
    assert "CLIP IT" in matched


def test_median_mad_detector_recovers_after_big_spike():
    triggered = []
    det = FastHypeDetector(
        short_window_sec=5,
        baseline_window_sec=60,
        z_score_threshold=2.5,
        min_mps=1.6,
        min_unique_users=2,
        cooldown_sec=10.0,
        on_hype_event=lambda ev: triggered.append(ev),
    )
    # 20 seconds of quiet baseline (1 msg/sec)
    for t in range(1, 21):
        det.add_message(ChatMessage(user_id=f"u{t % 5}", text="hi", platform=Platform.TWITCH, timestamp=float(t)))
    # First monster spike at t=22..24
    for i in range(15):
        det.add_message(ChatMessage(user_id=f"s1_{i}", text="CLIP IT KEKW", platform=Platform.TWITCH, timestamp=23.0 + i * 0.05))
    assert len(triggered) == 1

    # Return to quiet baseline for 20 seconds, then second spike at t=45
    for t in range(26, 44):
        det.add_message(ChatMessage(user_id=f"q{t % 5}", text="ok", platform=Platform.TWITCH, timestamp=float(t)))
    for i in range(12):
        det.add_message(ChatMessage(user_id=f"s2_{i}", text="NO WAY W", platform=Platform.TWITCH, timestamp=45.0 + i * 0.05))
    assert len(triggered) == 2


def test_best_cut_snaps_to_sentence_and_contains_event():
    words = [
        {"s": 0.5, "e": 1.0, "w": "Intro"},
        {"s": 1.0, "e": 1.5, "w": "talk."},
        {"s": 2.2, "e": 3.0, "w": "Watch"},
        {"s": 3.0, "e": 4.0, "w": "this"},
        {"s": 4.0, "e": 5.0, "w": "clutch!"},
        {"s": 16.0, "e": 17.0, "w": "That"},
        {"s": 17.0, "e": 18.0, "w": "was"},
        {"s": 18.0, "e": 19.0, "w": "insane."},
        {"s": 22.0, "e": 23.0, "w": "Next"},
        {"s": 23.0, "e": 24.0, "w": "round."},
    ]
    st, en, sc = clip_selection.best_cut_around_moment(
        words=words,
        window_len=30.0,
        event_t=15.0,
        min_len=15.0,
        max_len=25.0,
    )
    assert st <= 15.0 <= en
    assert 15.0 <= (en - st) <= 25.0
    assert sc > 0


def test_vod_hype_detects_spikes_and_excludes_history(tmp_path: Path):
    msgs = [vod_hype.VodChatMsg(float(t), f"u{t % 4}", "ok") for t in range(1, 100)]
    for i in range(25):
        msgs.append(vod_hype.VodChatMsg(50.0 + i * 0.08, f"h{i}", "CLIP IT KEKW"))
    msgs.sort(key=lambda m: m.t)

    spikes = vod_hype.detect_chat_spikes(msgs, duration=120.0, max_clips=3)
    assert len(spikes) >= 1
    assert any(45.0 <= sp.peak <= 55.0 for sp in spikes)

    hist_file = tmp_path / "hist.json"
    vod_hype.remember_clip_ranges("https://youtube.com/watch?v=abc", [(30.0, 65.0)], history_path=hist_file)
    excl = vod_hype.load_clip_history("https://youtube.com/watch?v=abc", history_path=hist_file)
    spikes2 = vod_hype.detect_chat_spikes(msgs, duration=120.0, max_clips=3, exclude=excl)
    assert not any(sp.start < 65.0 and sp.end > 30.0 for sp in spikes2)


def test_live_chat_hype_monitor_callback_no_attribute_error(tmp_path: Path):
    final_mp4 = tmp_path / "short_1.mp4"
    final_mp4.write_bytes(b"fake")

    ev = HypeEvent(
        event_id="ev1",
        detected_at=100.0,
        event_timestamp=97.0,
        peak_velocity=5.5,
        z_score=4.2,
        top_chants=["CLIP IT", "W"],
        confidence=0.95,
    )
    job = ClipJob(
        job_id="ev1",
        event=ev,
        clip_start_time=72.0,
        clip_end_time=107.0,
        status="complete",
        final_path=str(final_mp4),
    )

    clip_start = round(float(getattr(job, "clip_start_time", 0.0) or 0.0), 2)
    clip_end = round(float(getattr(job, "clip_end_time", 0.0) or 0.0), 2)
    assert clip_start == 72.0
    assert clip_end == 107.0
    assert round(max(0.0, clip_end - clip_start), 2) == 35.0
    assert ev.z_score == 4.2
    assert ev.top_chants == ["CLIP IT", "W"]
