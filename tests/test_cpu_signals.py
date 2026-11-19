"""
tests/test_cpu_signals.py - Tests for CPU-optimized visual motion and audio RMS extractors.
"""
import os
import pytest
from intelligence.signals.visual_motion import VisualMotionDetector
from intelligence.signals.audio_energy import AudioEnergyDetector

DEMO_VIDEO = os.path.join(os.path.dirname(__file__), "..", "demo-openshorts.mp4")


@pytest.mark.skipif(not os.path.exists(DEMO_VIDEO), reason="demo-openshorts.mp4 not found")
def test_visual_motion_detector():
    detector = VisualMotionDetector(target_fps=1.0, scale_width=320)
    result = detector.analyze_video(DEMO_VIDEO, start_sec=0.0, max_duration=5.0)

    assert "average_intensity" in result
    assert "max_intensity" in result
    assert "motion_events" in result
    assert len(result["motion_events"]) >= 3
    for ev in result["motion_events"]:
        assert 0.0 <= ev["intensity"] <= 1.0


@pytest.mark.skipif(not os.path.exists(DEMO_VIDEO), reason="demo-openshorts.mp4 not found")
def test_audio_energy_detector():
    detector = AudioEnergyDetector(sample_rate=16000, window_sec=0.5)
    result = detector.analyze_audio(DEMO_VIDEO, start_sec=0.0, max_duration=5.0)

    assert "average_rms" in result
    assert "max_rms" in result
    assert "windows" in result
    assert len(result["windows"]) >= 5
    for w in result["windows"]:
        assert 0.0 <= w["rms"] <= 1.0


def test_file_not_found():
    v_det = VisualMotionDetector()
    with pytest.raises(FileNotFoundError):
        v_det.analyze_video("non_existent_file.mp4")

    a_det = AudioEnergyDetector()
    with pytest.raises(FileNotFoundError):
        a_det.analyze_audio("non_existent_file.mp4")
