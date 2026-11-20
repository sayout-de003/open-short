"""
extractor.py - Stage A: Fast source remux and extraction.
Concatenates pinned segments into a draft preview MP4 using FFmpeg concat demuxer (-c copy) in < 1.5s.
"""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
import time
from typing import List, Optional
from ..models import VideoSegment

logger = logging.getLogger("live.extractor")


class FastClipExtractor:
    """Performs lightning-fast stream copy concat of pinned segments."""

    def __init__(self, output_dir: str):
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)
        self.ffmpeg_bin = shutil.which("ffmpeg") or "ffmpeg"

    def extract_draft_preview(
        self,
        segments: List[VideoSegment],
        job_id: str,
        start_trim_sec: float = 0.0,
        target_duration_sec: Optional[float] = None,
    ) -> str:
        """
        Concatenates segments into a draft MP4 without re-encoding (-c copy).
        Execution time: < 1.5 seconds.
        """
        if not segments:
            raise ValueError(f"Job {job_id}: No segments provided for extraction")

        out_path = os.path.join(self.output_dir, f"draft_{job_id}.mp4")
        concat_list_path = os.path.join(self.output_dir, f"concat_{job_id}.txt")

        # Sort segments chronologically
        sorted_segs = sorted(segments, key=lambda s: s.segment_index)

        # Write FFmpeg concat file list
        with open(concat_list_path, "w", encoding="utf-8") as f:
            for s in sorted_segs:
                if os.path.exists(s.filepath):
                    # Absolute path escaped for ffmpeg
                    f.write(f"file '{os.path.abspath(s.filepath)}'\n")

        cmd = [
            self.ffmpeg_bin, "-y", "-nostdin",
            "-f", "concat",
            "-safe", "0",
            "-i", concat_list_path,
            "-c", "copy",
            "-movflags", "+faststart",
            out_path
        ]

        t0 = time.time()
        res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        elapsed = time.time() - t0

        # Clean up temporary concat list
        try:
            if os.path.exists(concat_list_path):
                os.remove(concat_list_path)
        except OSError:
            pass

        if res.returncode != 0 or not os.path.exists(out_path) or os.path.getsize(out_path) == 0:
            err_msg = res.stderr.decode("utf-8", errors="replace")[-500:]
            raise RuntimeError(f"FFmpeg concat extraction failed: {err_msg}")

        logger.info(f"⚡ [Stage A] Fast Draft extracted in {elapsed:.3f}s: {out_path} ({os.path.getsize(out_path) / 1024:.1f} KB)")
        return out_path
