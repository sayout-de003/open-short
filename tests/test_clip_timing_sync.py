from unittest.mock import patch, MagicMock
from pathlib import Path
import os
import pytest

import ffmpeg_utils
from clip_selection import snap_clip_to_words
import camera_inset


def test_cut_clip_uses_accurate_duration_seeking(tmp_path: Path):
    dummy_input = tmp_path / "input.mp4"
    dummy_input.write_bytes(b"dummy")
    dummy_out = tmp_path / "out.mp4"

    captured_cmds = []

    def _mock_run(cmd, **kwargs):
        captured_cmds.append(cmd)
        dummy_out.write_bytes(b"X" * (ffmpeg_utils.MIN_CUT_BYTES + 10))
        res = MagicMock()
        res.returncode = 0
        res.stderr = ""
        return res

    with patch("subprocess.run", side_effect=_mock_run):
        ffmpeg_utils.cut_clip(str(dummy_input), str(dummy_out), 10.5, 42.5, 1)

    assert len(captured_cmds) >= 1
    cmd = captured_cmds[0]

    # Verify -ss is followed by -i and -t duration
    assert "-ss" in cmd
    ss_idx = cmd.index("-ss")
    assert cmd[ss_idx + 1] == "10.5"

    assert "-i" in cmd
    assert "-t" in cmd
    t_idx = cmd.index("-t")
    # Duration = 42.5 - 10.5 = 32.0
    assert cmd[t_idx + 1] == "32.0"
    assert "-accurate_seek" in cmd
    # -accurate_seek is an input option and must precede -i
    assert cmd.index("-accurate_seek") < cmd.index("-i")

    # Verify audio resample PTS sync is present in -af
    assert "-af" in cmd
    af_idx = cmd.index("-af")
    assert "aresample=async=1:first_pts=0" in cmd[af_idx + 1]


def test_snap_clip_to_words_adaptive_sentence_lookahead():
    # Word list where raw proposed end (18.0s) cuts off right before the punchline
    words = [
        {"w": "Welcome", "s": 0.5, "e": 1.2},
        {"w": "to", "s": 1.3, "e": 1.5},
        {"w": "the", "s": 1.6, "e": 1.8},
        {"w": "stream.", "s": 1.9, "e": 2.5},
        {"w": "Today", "s": 3.0, "e": 3.5},
        {"w": "we", "s": 3.6, "e": 3.8},
        {"w": "are", "s": 3.9, "e": 4.1},
        {"w": "going", "s": 4.2, "e": 4.6},
        {"w": "to", "s": 4.7, "e": 4.9},
        {"w": "pull", "s": 5.0, "e": 5.4},
        {"w": "off", "s": 5.5, "e": 5.8},
        {"w": "the", "s": 17.0, "e": 17.4},
        {"w": "craziest", "s": 17.5, "e": 18.0},  # Raw proposal cuts here (18.0)
        {"w": "heist", "s": 18.2, "e": 18.8},
        {"w": "ever!", "s": 18.9, "e": 19.5},    # Real sentence ending!
        {"w": "And", "s": 21.0, "e": 21.3},
    ]

    # Proposing 0.5 to 18.0 should look ahead and snap to "ever!" (end ~19.5 + tail)
    snapped_start, snapped_end = snap_clip_to_words(
        start=0.5, end=18.0, words=words, video_duration=60.0,
        min_duration=10.0, max_duration=30.0
    )

    # Must preserve complete punchline without cutting off "heist ever!"
    assert snapped_end >= 19.5
    assert snapped_start <= 0.5


def test_snap_clip_to_words_penalizes_conjunction_end():
    words = [
        {"w": "This", "s": 1.0, "e": 1.5},
        {"w": "is", "s": 1.6, "e": 1.8},
        {"w": "amazing.", "s": 1.9, "e": 2.5},
        {"w": "And", "s": 2.8, "e": 3.2},
    ]

    # Proposing 1.0 to 3.0: should avoid ending on "And"
    snapped_start, snapped_end = snap_clip_to_words(
        start=1.0, end=3.0, words=words, video_duration=30.0,
        min_duration=1.0, max_duration=10.0
    )

    # Should snap to "amazing." rather than stopping on "And"
    assert snapped_end < 3.2


def test_camera_inset_detect_caching(tmp_path: Path):
    dummy_vid = tmp_path / "stream_mock.mp4"
    dummy_vid.write_bytes(b"dummy_video_bytes")

    with patch("cv2.VideoCapture") as mock_cap_cls:
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True
        mock_cap.get.side_effect = lambda prop: 100 if prop == 7 else 1920 if prop == 3 else 1080
        mock_cap.read.return_value = (False, None)
        mock_cap_cls.return_value = mock_cap

        # First call
        res1 = camera_inset.detect(str(dummy_vid), samples=5)
        # Second call should hit cache and not re-create VideoCapture
        cap_call_count = mock_cap_cls.call_count
        res2 = camera_inset.detect(str(dummy_vid), samples=5)
        assert mock_cap_cls.call_count == cap_call_count
        assert res1 == res2
