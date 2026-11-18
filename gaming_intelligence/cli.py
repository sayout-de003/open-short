"""
cli.py - Command-line interface for the Local AI Video Clipper.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time

from .pipeline import LocalIntelligencePipeline
from .stream_recorder import StreamRecorder


def parse_args():
    parser = argparse.ArgumentParser(
        description="Local AI Video Clipper: Gaming, Podcasts, YouTube, Twitch"
    )
    parser.add_argument(
        "--input", "-i", type=str, default=None, help="Path to input video file"
    )
    parser.add_argument(
        "--youtube", type=str, default=None, help="YouTube video or live stream URL"
    )
    parser.add_argument(
        "--twitch", type=str, default=None, help="Twitch channel or stream URL"
    )
    parser.add_argument(
        "--mode", "-m", type=str, default="gaming",
        choices=["gaming", "podcast", "commentary", "generic"],
        help="Intelligence mode profile (default: gaming)"
    )
    parser.add_argument(
        "--stream-duration", type=int, default=120,
        help="Recording duration in seconds for live streams (default: 120s)"
    )
    parser.add_argument(
        "--max-clips", type=int, default=5,
        help="Maximum clips to generate (default: 5)"
    )
    parser.add_argument(
        "--min-sec", type=float, default=15.0,
        help="Minimum clip duration in seconds (default: 15.0)"
    )
    parser.add_argument(
        "--max-sec", type=float, default=59.0,
        help="Maximum clip duration in seconds (default: 59.0)"
    )
    parser.add_argument(
        "--output-dir", "-o", type=str, default="output",
        help="Directory to save output clips and metadata"
    )
    parser.add_argument(
        "--render", action="store_true",
        help="Render 9:16 vertical MP4 video clips using FFmpeg"
    )
    return parser.parse_args()


def render_vertical_clip(input_video: str, start: float, end: float, output_path: str):
    """
    Renders 9:16 vertical cropped clip using CPU-efficient libx264.
    Preserves center gameplay while fitting 1080x1920.
    """
    duration = end - start
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    # 9:16 crop filter: crop=ih*(9/16):ih, scale=1080:1920
    vf_filter = "crop=ih*9/16:ih:(iw-ow)/2:0,scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2"

    cmd = [
        "ffmpeg", "-y", "-nostdin",
        "-ss", str(start),
        "-i", input_video,
        "-t", str(duration),
        "-vf", vf_filter,
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-crf", "23",
        "-c:a", "aac",
        "-b:a", "128k",
        "-movflags", "+faststart",
        output_path
    ]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)


def main():
    args = parse_args()
    os.makedirs(args.output_dir, exist_ok=True)

    input_file = args.input
    recorder = StreamRecorder(output_dir=os.path.join(args.output_dir, "captures"))

    # Ingestion handling
    if args.twitch:
        print(f"🔴 Capturing live Twitch stream: {args.twitch} ({args.stream_duration}s)...")
        input_file = recorder.capture_twitch_stream(args.twitch, duration_sec=args.stream_duration)
        print(f"✅ Stream saved to: {input_file}")
    elif args.youtube:
        if "live" in args.youtube.lower():
            print(f"🔴 Capturing live YouTube stream: {args.youtube} ({args.stream_duration}s)...")
            input_file = recorder.capture_youtube_live(args.youtube, duration_sec=args.stream_duration)
        else:
            print(f"📥 Ingesting YouTube video: {args.youtube}...")
            out_pattern = os.path.join(args.output_dir, "yt_source_%(id)s.%(ext)s")
            cmd = ["yt-dlp", "-f", "bv*+ba/b", "--merge-output-format", "mp4", "-o", out_pattern, args.youtube]
            subprocess.run(cmd, check=True)
            # Find the downloaded file
            import glob
            files = sorted(glob.glob(os.path.join(args.output_dir, "yt_source_*.mp4")), key=os.path.getmtime, reverse=True)
            if not files:
                sys.exit("❌ Failed to download YouTube video.")
            input_file = files[0]
        print(f"✅ Downloaded to: {input_file}")

    if not input_file or not os.path.exists(input_file):
        sys.exit("❌ Error: Please specify a valid video with --input, --youtube, or --twitch.")

    # Initialize Pipeline
    pipeline = LocalIntelligencePipeline(
        profile_name=args.mode,
        min_clip_sec=args.min_sec,
        max_clip_sec=args.max_sec,
        max_clips=args.max_clips,
    )

    print(f"🚀 Processing video with Local Intelligence (Mode: {args.mode})...")
    start_time = time.time()
    shorts, metadata = pipeline.process_video(input_file)
    elapsed = time.time() - start_time

    print(f"🎉 Pipeline completed in {elapsed:.1f}s. Found {len(shorts)} highlight clips:")
    for i, s in enumerate(shorts, 1):
        print(f"   [{i}] {s['start']:.1f}s - {s['end']:.1f}s | Virality: {s['virality_score']}/10 | Title: {s['title']}")
        if s.get("visual_context"):
            print(f"       Vision: {s['visual_context']}")

    # Save metadata JSON
    meta_path = os.path.join(args.output_dir, "metadata.json")
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump({"shorts": shorts, "metadata": metadata}, f, indent=2)
    print(f"💾 Metadata saved to: {meta_path}")

    # Render vertical clips if requested
    if args.render:
        print("🎬 Rendering vertical clips (9:16)...")
        rendered_clips = []
        for i, s in enumerate(shorts, 1):
            clip_name = f"clip_{i}_{args.mode}_{int(s['start'])}s_{int(s['end'])}s.mp4"
            clip_path = os.path.join(args.output_dir, clip_name)
            print(f"   Rendering [{i}/{len(shorts)}]: {clip_name}...")
            render_vertical_clip(input_file, s["start"], s["end"], clip_path)
            rendered_clips.append(clip_path)
        print(f"✨ Successfully rendered {len(rendered_clips)} clips in: {args.output_dir}")


if __name__ == "__main__":
    main()
