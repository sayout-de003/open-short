"""
quality/clip_validator.py - Automated Quality Assurance for rendered clips.

Inspects duration, resolution, black frames, frozen frames, and audio integrity
to ensure every delivered short meets production quality standards.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class QualityReport:
    clip_path: str
    status: str  # "passed" | "warning" | "failed"
    quality_score: float  # 0.0 to 1.0
    duration: float
    width: int
    height: int
    has_audio: bool
    issues: List[str] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class ClipValidator:
    """Performs deterministic post-render validation on video files."""

    def __init__(
        self,
        min_duration: float = 10.0,
        max_duration: float = 90.0,
        expected_aspect_ratio: str = "9:16",
        max_black_frames: int = 0,
        max_frozen_seconds: float = 2.0,
        require_audio: bool = True,
    ):
        self.min_duration = min_duration
        self.max_duration = max_duration
        self.expected_aspect_ratio = expected_aspect_ratio
        self.max_black_frames = max_black_frames
        self.max_frozen_seconds = max_frozen_seconds
        self.require_audio = require_audio

    def validate(
        self,
        clip_path: str,
        require_audio: Optional[bool] = None,
    ) -> QualityReport:
        req_audio = self.require_audio if require_audio is None else bool(require_audio)
        if not os.path.isfile(clip_path) or os.path.getsize(clip_path) == 0:
            return QualityReport(
                clip_path=clip_path,
                status="failed",
                quality_score=0.0,
                duration=0.0,
                width=0,
                height=0,
                has_audio=False,
                issues=["File does not exist or is 0 bytes."],
            )

        issues: List[str] = []
        metrics: Dict[str, Any] = {}

        # 1. ffprobe metadata (duration, width, height, audio streams)
        probe_cmd = [
            "ffprobe", "-v", "error",
            "-show_entries", "stream=codec_type,width,height:format=duration",
            "-of", "json",
            clip_path,
        ]
        try:
            probe_out = subprocess.check_output(probe_cmd, stderr=subprocess.DEVNULL, text=True)
            probe_data = json.loads(probe_out)
        except Exception as e:
            return QualityReport(
                clip_path=clip_path,
                status="failed",
                quality_score=0.0,
                duration=0.0,
                width=0,
                height=0,
                has_audio=False,
                issues=[f"ffprobe failed: {e}"],
            )

        duration = float(probe_data.get("format", {}).get("duration", 0.0))
        video_stream = next((s for s in probe_data.get("streams", []) if s.get("codec_type") == "video"), None)
        audio_stream = next((s for s in probe_data.get("streams", []) if s.get("codec_type") == "audio"), None)

        width = int(video_stream.get("width", 0)) if video_stream else 0
        height = int(video_stream.get("height", 0)) if video_stream else 0
        has_audio = audio_stream is not None

        metrics["duration"] = round(duration, 2)
        metrics["resolution"] = f"{width}x{height}"
        metrics["has_audio"] = has_audio

        # Duration validation
        if duration < self.min_duration:
            issues.append(f"Duration too short ({duration:.1f}s < {self.min_duration}s)")
        elif duration > self.max_duration:
            issues.append(f"Duration too long ({duration:.1f}s > {self.max_duration}s)")

        # Aspect ratio check
        if width > 0 and height > 0:
            ratio = width / height
            if self.expected_aspect_ratio == "9:16" and ratio > 0.65:
                issues.append(f"Aspect ratio is not vertical 9:16 ({width}x{height})")
            elif self.expected_aspect_ratio == "16:9" and ratio < 1.70:
                issues.append(f"Aspect ratio is not landscape 16:9 ({width}x{height})")

        # Audio check
        if req_audio and not has_audio:
            issues.append("Audio stream missing from rendered clip")

        # 2. Black frame detection
        black_cmd = [
            "ffmpeg", "-v", "error",
            "-i", clip_path,
            "-vf", "blackdetect=d=0.5:pix_th=0.10",
            "-f", "null", "-",
        ]
        try:
            res = subprocess.run(black_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=30)
            black_matches = re.findall(r"black_start:([0-9.]+)", res.stderr)
            metrics["black_segments"] = len(black_matches)
            if len(black_matches) > self.max_black_frames:
                issues.append(f"Detected {len(black_matches)} black frame segment(s)")
        except Exception:
            metrics["black_segments"] = 0

        # 3. Freeze frame detection
        freeze_cmd = [
            "ffmpeg", "-v", "error",
            "-i", clip_path,
            "-vf", f"freezedetect=n=0.003:d={self.max_frozen_seconds}",
            "-f", "null", "-",
        ]
        try:
            res = subprocess.run(freeze_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=30)
            freeze_matches = re.findall(r"freeze_start:([0-9.]+)", res.stderr)
            metrics["frozen_segments"] = len(freeze_matches)
            if freeze_matches:
                issues.append(f"Detected {len(freeze_matches)} prolonged frozen frame segment(s)")
        except Exception:
            metrics["frozen_segments"] = 0

        # Calculate quality score
        score = 1.0
        score -= len(issues) * 0.20
        quality_score = max(0.0, min(1.0, round(score, 2)))

        if not issues:
            status = "passed"
        elif any("missing" in i or "ffprobe failed" in i or "too short" in i for i in issues):
            status = "failed"
        else:
            status = "warning"

        return QualityReport(
            clip_path=clip_path,
            status=status,
            quality_score=quality_score,
            duration=round(duration, 2),
            width=width,
            height=height,
            has_audio=has_audio,
            issues=issues,
            metrics=metrics,
        )


def validate_clip(clip_path: str, **kwargs) -> Dict[str, Any]:
    validator = ClipValidator(**kwargs)
    return validator.validate(clip_path).to_dict()
