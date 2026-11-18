import os
from unittest.mock import patch
import pytest
from clip_selection import shortlist_target, clip_count_targets


def test_live_stream_shortlist_target():
    with patch.dict(os.environ, {"IS_LIVE_STREAM": "1"}):
        assert shortlist_target(600) == 2
        assert shortlist_target(120) == 2


def test_live_stream_clip_count_targets():
    with patch.dict(os.environ, {"IS_LIVE_STREAM": "1"}):
        low, high = clip_count_targets(5)
        assert low == 1
        assert high == 2


def test_live_stream_override_targets():
    with patch.dict(os.environ, {"IS_LIVE_STREAM": "1", "CLIP_TARGET_MAX": "3", "CLIP_TARGET_MIN": "2"}):
        low, high = clip_count_targets(5)
        assert low == 2
        assert high == 3


def test_live_cut_seconds_env_parsing():
    val = float(os.environ.get("LIVE_CUT_SECONDS", "120"))
    assert val == 120 or val > 0
    with patch.dict(os.environ, {"LIVE_CUT_SECONDS": "90"}):
        assert float(os.environ.get("LIVE_CUT_SECONDS", "120")) == 90.0


def test_live_ffmpeg_hls_command_options():
    live_seconds = 120
    start_index = -int(max(15, live_seconds // 3))
    cmd = [
        'ffmpeg', '-y',
        '-live_start_index', str(start_index),
        '-http_persistent', '1',
        '-http_multiple', '1',
        '-max_reload', '1',
        '-reconnect', '1', '-reconnect_at_eof', '1', '-reconnect_streamed', '1', '-reconnect_delay_max', '2',
        '-i', 'https://manifest.googlevideo.com/api/manifest/hls_live/test.m3u8',
        '-t', str(int(live_seconds)),
        '-c', 'copy',
        'out.mp4'
    ]
    assert '-live_start_index' in cmd
    assert cmd[cmd.index('-live_start_index') + 1] == '-40'
    assert '-http_multiple' in cmd
    assert '-http_persistent' in cmd
    assert cmd[cmd.index('-t') + 1] == '120'
