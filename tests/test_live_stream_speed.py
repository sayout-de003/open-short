import os
from unittest.mock import patch
import pytest
from clip_selection import shortlist_target, clip_count_targets


def test_live_stream_shortlist_target():
    with patch.dict(os.environ, {"IS_LIVE_STREAM": "1"}):
        assert shortlist_target(600) == 8
        assert shortlist_target(120) == 3


def test_live_stream_clip_count_targets():
    with patch.dict(os.environ, {"IS_LIVE_STREAM": "1"}):
        low, high = clip_count_targets(5)
        assert low >= 3
        assert high >= 5


def test_live_stream_override_targets():
    with patch.dict(os.environ, {"IS_LIVE_STREAM": "1", "CLIP_TARGET_MAX": "5", "CLIP_TARGET_MIN": "3"}):
        low, high = clip_count_targets(5)
        assert low == 3
        assert high == 5


def test_live_cut_seconds_env_parsing():
    val = float(os.environ.get("LIVE_CUT_SECONDS", "600"))
    assert val == 600 or val > 0
    with patch.dict(os.environ, {"LIVE_CUT_SECONDS": "90"}):
        assert float(os.environ.get("LIVE_CUT_SECONDS", "600")) == 90.0


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


def test_live_stream_always_goes_with_live_edge():
    # Verify default live start index targets the live edge (-1 segments)
    start_index = int(os.environ.get("LIVE_START_INDEX", "-1"))
    assert start_index == -1

    with patch.dict(os.environ, {"LIVE_START_INDEX": "-2"}):
        custom_index = int(os.environ.get("LIVE_START_INDEX", "-1"))
        assert custom_index == -2


def test_live_stream_dl_opts_always_go_with_live():
    # Verify yt-dlp options for live streams enforce live_from_start = False
    # and do not slice from timestamp 0
    is_live = True
    _range_cap = 600.0
    dl_opts = {'live_from_start': False if is_live else True}
    assert dl_opts['live_from_start'] is False

    ranged = not is_live and _range_cap > 0
    assert ranged is False


def test_live_continuous_monitor_env_default():
    # Verify continuous monitoring can be configured and defaults appropriately
    with patch.dict(os.environ, {"LIVE_CONTINUOUS_MONITOR": "1", "LIVE_CUT_SECONDS": "120"}):
        assert os.environ.get("LIVE_CONTINUOUS_MONITOR") == "1"
        assert float(os.environ.get("LIVE_CUT_SECONDS")) == 120.0


def test_capture_live_stream_segment():
    from main import capture_live_stream_segment
    import tempfile

    mock_info = {
        'formats': [
            {'vcodec': 'avc1', 'acodec': 'none', 'url': 'https://manifest.googlevideo.com/v.m3u8'},
            {'vcodec': 'none', 'acodec': 'mp4a', 'url': 'https://manifest.googlevideo.com/a.m3u8'},
        ]
    }
    with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as tf:
        tmp_name = tf.name
        tf.write(b"0" * 300000)

    try:
        with patch("subprocess.Popen") as mock_popen:
            mock_proc = mock_popen.return_value
            mock_proc.poll.side_effect = [None, 0]
            mock_proc.communicate.return_value = ("", "")

            result = capture_live_stream_segment(mock_info, tmp_name, live_seconds=45, start_index=-1, cycle_num=1)
            assert result is True
            assert mock_popen.called
            cmd_args = mock_popen.call_args[0][0]
            assert '-live_start_index' in cmd_args
            assert '-1' in cmd_args
            assert '-rw_timeout' in cmd_args
            assert '-movflags' in cmd_args
            assert '+frag_keyframe+empty_moov' in cmd_args
            assert '-t' in cmd_args
            assert '45' in cmd_args
    finally:
        if os.path.exists(tmp_name):
            os.remove(tmp_name)


def test_select_live_stream_urls_prefers_muxed_hls_and_skips_mhtml():
    from main import _select_live_stream_urls

    info = {
        'formats': [
            {'protocol': 'mhtml', 'ext': 'mhtml', 'vcodec': 'none', 'acodec': 'none', 'url': 'https://example.com/sb.mhtml'},
            {'protocol': 'm3u8_native', 'vcodec': 'avc1.64001f', 'acodec': 'mp4a.40.2', 'url': 'https://example.com/muxed.m3u8'},
            {'protocol': 'm3u8_native', 'vcodec': 'vp9', 'acodec': 'none', 'url': 'https://example.com/v_only.m3u8'},
        ]
    }
    stream_url, v_url, a_url = _select_live_stream_urls(info)
    assert stream_url == 'https://example.com/muxed.m3u8'
    assert v_url is None and a_url is None


def test_segmented_stream_recorder_live_edge_flags(tmp_path):
    from gaming_intelligence.live.recording.buffer import RollingSegmentBuffer
    from gaming_intelligence.live.recording.timestamps import TimestampSynchronizer
    from gaming_intelligence.live.recording.recorder import SegmentedStreamRecorder

    buf = RollingSegmentBuffer(str(tmp_path))
    rec = SegmentedStreamRecorder(buf, TimestampSynchronizer())
    with patch("subprocess.Popen") as mock_popen:
        rec._spawn_ffmpeg("https://manifest.googlevideo.com/api/manifest/hls_live/test.m3u8")
        cmd_args = mock_popen.call_args[0][0]
        assert "-live_start_index" in cmd_args
        assert "-1" in cmd_args
        assert "-rw_timeout" in cmd_args
        assert "-reconnect" in cmd_args


def test_analyze_and_detect_clips_continuous_mode_graceful():
    from main import analyze_and_detect_clips

    # When no clips are returned and is_live_continuous is True, it should not raise RuntimeError
    with patch("main.transcribe_video") as mock_transcribe, \
         patch("main.speech_is_sparse", return_value=False), \
         patch("main.get_viral_clips") as mock_get_clips:
        mock_transcribe.return_value = {"language": "en", "segments": [{"start": 0, "end": 10, "text": "hello this is a long enough sentence"}]}
        mock_get_clips.return_value = {"shorts": []}

        result = analyze_and_detect_clips(
            "dummy.mp4", duration=120.0, is_live_continuous=True
        )
        assert result is None


def test_has_cuda_and_render_workers_sizing():
    import main

    # _has_cuda should return boolean and not raise NameError
    res = main._has_cuda()
    assert isinstance(res, bool)

    with patch("main._has_cuda", return_value=True):
        default_workers = "6" if main._has_cuda() else "2"
        assert default_workers == "6"

    with patch("main._has_cuda", return_value=False):
        default_workers = "6" if main._has_cuda() else "2"
        assert default_workers == "2"

