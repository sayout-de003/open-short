"""
clip_selector.py - Selects, ranks, and bounds viral video highlights.
"""
from __future__ import annotations

import os
from typing import Dict, List, Optional
from .vision_analyzer import VisionAnalyzer
from .frame_sampler import FrameSampler


class ClipSelector:
    """Selects best candidate clip intervals from composite timeline."""

    def __init__(
        self,
        min_duration: float = 15.0,
        max_duration: float = 59.0,
        max_clips: int = 5,
        min_gap_sec: float = 10.0,
    ):
        self.min_duration = min_duration
        self.max_duration = max_duration
        self.max_clips = max_clips
        self.min_gap_sec = min_gap_sec

    def select_clips(
        self,
        timeline: List[Dict[str, any]],
        video_path: Optional[str] = None,
        vision_analyzer: Optional[VisionAnalyzer] = None,
        profile_name: str = "gaming",
    ) -> List[Dict[str, any]]:
        """
        Finds highest scoring non-overlapping intervals of length [min_duration, max_duration].
        Returns list of structured shorts.
        """
        if not timeline or len(timeline) < int(self.min_duration):
            # Fallback if video is extremely short: take full duration
            dur = timeline[-1]["timestamp"] if timeline else self.min_duration
            return [{
                "start": 0.0,
                "end": max(self.min_duration, dur),
                "virality_score": 8,
                "title": f"Epic {profile_name.capitalize()} Moment",
                "hook": "Wait until you see this!",
                "reason": "High density moment across available timeline"
            }]

        step_sec = timeline[1]["timestamp"] - timeline[0]["timestamp"] if len(timeline) > 1 else 1.0
        min_steps = max(1, int(self.min_duration / step_sec))
        max_steps = max(min_steps, int(self.max_duration / step_sec))

        scores = [t["composite_score"] for t in timeline]
        n = len(scores)

        # Sliding window evaluation for different candidate lengths
        candidates = []
        # Test candidate durations: min, mid, max
        durations = list({min_steps, (min_steps + max_steps) // 2, max_steps})

        for window_len in durations:
            if window_len > n:
                continue
            # Compute running sum
            current_sum = sum(scores[:window_len])
            candidates.append((0, window_len, current_sum / window_len))

            for i in range(1, n - window_len + 1):
                current_sum = current_sum - scores[i - 1] + scores[i + window_len - 1]
                avg_score = current_sum / window_len
                candidates.append((i, i + window_len, avg_score))

        # Sort candidates descending by score
        candidates.sort(key=lambda x: x[2], reverse=True)

        selected_windows = []
        for start_idx, end_idx, avg_score in candidates:
            start_ts = timeline[start_idx]["timestamp"]
            end_ts = timeline[min(end_idx - 1, n - 1)]["timestamp"]

            # Overlap check
            overlap = False
            for s_start, s_end in selected_windows:
                # Disallow overlap within min_gap_sec
                if not (end_ts + self.min_gap_sec < s_start or start_ts > s_end + self.min_gap_sec):
                    overlap = True
                    break

            if not overlap:
                selected_windows.append((start_ts, end_ts))
                if len(selected_windows) >= self.max_clips:
                    break

        # Sort by chronological order
        selected_windows.sort(key=lambda x: x[0])

        # Convert to OpenShorts compatible format
        shorts = []
        sampler = FrameSampler() if video_path and vision_analyzer else None

        for idx, (s_start, s_end) in enumerate(selected_windows):
            clip_dur = s_end - s_start
            center_ts = (s_start + s_end) / 2.0

            # Find matching hooks from timeline
            hook = ""
            for t in timeline:
                if s_start <= t["timestamp"] <= s_end and t.get("hook"):
                    hook = t["hook"]
                    break

            # Vision description for silent video or gaming visual context
            vision_desc = ""
            if not hook and video_path and vision_analyzer and os.path.exists(video_path):
                try:
                    tmp_out = os.path.join(os.path.dirname(video_path), f".vision_tmp_{idx}")
                    frames = sampler.extract_key_frames(video_path, [center_ts], tmp_out)
                    if frames:
                        f_info = vision_analyzer.describe_frame(frames[0][1], "Identify the main action or subject.")
                        vision_desc = f_info.get("description", "")
                    # Clean up
                    if os.path.exists(tmp_out):
                        import shutil
                        shutil.rmtree(tmp_out, ignore_errors=True)
                except Exception:
                    pass

            if not hook:
                if vision_desc:
                    hook = vision_desc[:50]
                else:
                    hook = f"Top {profile_name.capitalize()} Highlight #{idx + 1}"

            title = f"{profile_name.capitalize()} Action #{idx + 1}"
            if vision_desc and len(vision_desc) > 5:
                title = vision_desc[:40].capitalize()

            # Virality score on 1-10 scale
            # Find max composite in this window
            sub_scores = [t["composite_score"] for t in timeline if s_start <= t["timestamp"] <= s_end]
            max_c = max(sub_scores) if sub_scores else 0.5
            viral_score = max(5, min(10, int(round(max_c * 10))))

            # Generate viral social media captions & hashtags
            tags = {
                "gaming": "#gaming #gameplay #twitch #gamingclips #fyp #viralshorts",
                "podcast": "#podcast #interview #insights #wisdom #trending #shorts",
                "educational": "#education #learning #career #jobs #tips #knowledge",
                "commentary": "#commentary #opinion #reaction #trends #viral #shorts"
            }.get(profile_name.lower(), "#shorts #viral #trending #reels #fyp")

            tiktok_caption = f"{hook}. Watch till the end! {tags}"
            instagram_caption = f"{hook}\n\nWhat are your thoughts on this? Drop a comment below! 👇\n\n{tags}"

            shorts.append({
                "start": round(s_start, 2),
                "end": round(s_end, 2),
                "virality_score": viral_score,
                "title": title,
                "video_title_for_youtube_short": title,
                "hook": hook,
                "viral_hook_text": hook,
                "video_description_for_tiktok": tiktok_caption,
                "video_description_for_instagram": instagram_caption,
                "reason": f"High multi-modal energy in {profile_name} mode ({clip_dur:.1f}s)",
                "reason_for_virality": f"High multi-modal energy in {profile_name} mode ({clip_dur:.1f}s)",
                "visual_context": vision_desc
            })

        return shorts
