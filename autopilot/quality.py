"""Quality gate for rendered vertical gaming clips."""
from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class QualityResult:
    passed: bool
    reason: str
    duration_sec: float = 0.0
    width: int = 0
    height: int = 0
    file_size_bytes: int = 0
    has_audio: bool = False


class ClipQualityValidator:
    """Validates MP4 container, decode, duration, 9:16 aspect ratio, audio stream, and size."""

    def __init__(
        self,
        min_duration: float = 30.0,
        max_duration: float = 40.0,
        min_file_bytes: int = 100_000,
        max_file_bytes: int = 250_000_000,
    ):
        self.min_duration = min_duration
        self.max_duration = max_duration
        self.min_file_bytes = min_file_bytes
        self.max_file_bytes = max_file_bytes

    def validate(self, file_path: Path | str, ffprobe_bin: Optional[str] = None) -> QualityResult:
        path = Path(file_path)
        if not path.exists() or not path.is_file():
            return QualityResult(False, "file_missing")

        size = path.stat().st_size
        if size < self.min_file_bytes:
            return QualityResult(False, f"file_too_small:{size}", file_size_bytes=size)
        if size > self.max_file_bytes:
            return QualityResult(False, f"file_too_large:{size}", file_size_bytes=size)

        probe = ffprobe_bin or shutil.which("ffprobe")
        if not probe:
            return QualityResult(False, "ffprobe_missing", file_size_bytes=size)

        cmd = [
            probe,
            "-v", "error",
            "-show_entries", "format=duration,format_name:stream=codec_type,width,height",
            "-of", "json",
            str(path),
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
        if res.returncode != 0:
            return QualityResult(False, f"ffprobe_error:{res.stderr.strip()[:120]}", file_size_bytes=size)

        try:
            data = json.loads(res.stdout)
        except json.JSONDecodeError:
            return QualityResult(False, "ffprobe_invalid_json", file_size_bytes=size)

        fmt = data.get("format") or {}
        streams = data.get("streams") or []
        duration = float(fmt.get("duration") or 0.0)

        video_streams = [s for s in streams if s.get("codec_type") == "video"]
        audio_streams = [s for s in streams if s.get("codec_type") == "audio"]

        if not video_streams:
            return QualityResult(False, "missing_video_stream", duration_sec=duration, file_size_bytes=size)
        if not audio_streams:
            return QualityResult(False, "missing_audio_stream", duration_sec=duration, file_size_bytes=size)

        width = int(video_streams[0].get("width") or 0)
        height = int(video_streams[0].get("height") or 0)
        if width <= 0 or height <= 0:
            return QualityResult(False, "invalid_dimensions", duration_sec=duration, file_size_bytes=size, has_audio=True)

        ratio = width / height
        if abs(ratio - (9.0 / 16.0)) > 0.08:
            return QualityResult(
                False,
                f"invalid_aspect_ratio:{width}x{height}",
                duration_sec=duration,
                width=width,
                height=height,
                file_size_bytes=size,
                has_audio=True,
            )

        min_allowed = max(10.0, self.min_duration - 15.0)
        max_allowed = max(self.max_duration + 30.0, 75.0)
        if duration < min_allowed or duration > max_allowed:
            return QualityResult(
                False,
                f"invalid_duration:{duration:.1f}s (allowed: {min_allowed:.1f}..{max_allowed:.1f}s)",
                duration_sec=duration,
                width=width,
                height=height,
                file_size_bytes=size,
                has_audio=True,
            )

        return QualityResult(
            True,
            "approved",
            duration_sec=duration,
            width=width,
            height=height,
            file_size_bytes=size,
            has_audio=True,
        )
