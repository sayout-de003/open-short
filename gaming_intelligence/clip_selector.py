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
        min_duration: float = 25.0,
        max_duration: float = 60.0,
        max_clips: int = 5,
        min_gap_sec: float = 8.0,
    ):
        self.min_duration = float(min_duration)
        self.max_duration = float(max_duration)
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
            title = f"Epic {profile_name.capitalize()} Moment"
            hook = "Wait until you see this!"
            tags = {
                "gaming": "#gaming #gameplay #twitch #gamingclips #fyp #viralshorts",
                "podcast": "#podcast #interview #insights #wisdom #trending #shorts",
                "educational": "#education #learning #career #jobs #tips #knowledge",
                "commentary": "#commentary #opinion #reaction #trends #viral #shorts"
            }.get(profile_name.lower(), "#shorts #viral #trending #reels #fyp")
            return [{
                "start": 0.0,
                "end": max(self.min_duration, dur),
                "virality_score": 8,
                "title": title,
                "video_title_for_youtube_short": title,
                "hook": hook,
                "viral_hook_text": hook,
                "video_description_for_tiktok": f"{hook} 🔥 Watch till the end! {tags}",
                "video_description_for_instagram": f"{hook}\n\nWhat are your thoughts on this? Drop a comment below! 👇\n\n{tags}",
                "reason": "High density moment across available timeline",
                "reason_for_virality": "High density moment across available timeline"
            }]

        step_sec = timeline[1]["timestamp"] - timeline[0]["timestamp"] if len(timeline) > 1 else 1.0
        total_duration = (timeline[-1]["timestamp"] - timeline[0]["timestamp"]) if timeline else 0.0

        # Adjust duration window bounds if total video duration is tight for the requested max_clips
        effective_min = self.min_duration
        effective_max = self.max_duration
        effective_gap = self.min_gap_sec
        if total_duration > 0 and self.max_clips > 0:
            avg_slot = total_duration / self.max_clips
            if avg_slot < self.max_duration:
                effective_max = max(15.0, min(self.max_duration, avg_slot * 1.15))
            if avg_slot < self.min_duration:
                effective_min = max(15.0, min(self.min_duration, avg_slot * 0.90))
            if avg_slot < (self.min_duration + self.min_gap_sec):
                effective_gap = max(1.0, min(self.min_gap_sec, avg_slot * 0.12))

        min_steps = max(1, int(effective_min / step_sec))
        max_steps = max(min_steps, int(effective_max / step_sec))

        scores = [t["composite_score"] for t in timeline]
        n = len(scores)

        # Test candidate durations across the range
        candidate_durations = sorted(list({
            min_steps,
            int(min_steps + (max_steps - min_steps) * 0.33),
            int(min_steps + (max_steps - min_steps) * 0.66),
            max_steps
        }))
        durations = [d for d in candidate_durations if d <= n]
        if not durations:
            durations = [min(n, min_steps)]

        # Sliding window evaluation for different candidate lengths
        candidates = []
        for window_len in durations:
            if window_len > n:
                continue
            # Length-balanced scoring: reward sustained interest and context
            # Pure average (sum / L) always selects the absolute minimum window.
            # Scaling with (window_len / min_steps) ** 0.45 balances intensity with storytelling depth.
            length_factor = (window_len / max(1, min_steps)) ** 0.45
            current_sum = sum(scores[:window_len])
            balanced_score = (current_sum / window_len) * length_factor
            candidates.append((0, window_len, balanced_score))

            for i in range(1, n - window_len + 1):
                current_sum = current_sum - scores[i - 1] + scores[i + window_len - 1]
                balanced_score = (current_sum / window_len) * length_factor
                candidates.append((i, i + window_len, balanced_score))

        # Sort candidates descending by score
        candidates.sort(key=lambda x: x[2], reverse=True)

        # Pass 1: Select highest-scoring windows with standard min_gap_sec
        selected_windows = []
        for start_idx, end_idx, avg_score in candidates:
            start_ts = timeline[start_idx]["timestamp"]
            end_idx_clamped = min(end_idx, n)
            end_ts = round(start_ts + (end_idx_clamped - start_idx) * step_sec, 2)
            if timeline and end_idx_clamped < n:
                end_ts = min(end_ts, timeline[-1]["timestamp"])

            # Overlap check
            overlap = False
            for s_start, s_end in selected_windows:
                # Disallow overlap within effective_gap
                if not (end_ts + effective_gap < s_start or start_ts > s_end + effective_gap):
                    overlap = True
                    break

            if not overlap:
                selected_windows.append((start_ts, end_ts))
                if len(selected_windows) >= self.max_clips:
                    break

        # Pass 2: Adaptive filling with relaxed gaps (down to 2.0s and 0.5s) if quota not reached
        if len(selected_windows) < self.max_clips:
            for relaxed_gap in [2.0, 0.5]:
                if len(selected_windows) >= self.max_clips:
                    break
                for start_idx, end_idx, avg_score in candidates:
                    start_ts = timeline[start_idx]["timestamp"]
                    end_idx_clamped = min(end_idx, n)
                    end_ts = round(start_ts + (end_idx_clamped - start_idx) * step_sec, 2)
                    if timeline and end_idx_clamped < n:
                        end_ts = min(end_ts, timeline[-1]["timestamp"])

                    overlap = False
                    for s_start, s_end in selected_windows:
                        if not (end_ts + relaxed_gap < s_start or start_ts > s_end + relaxed_gap):
                            overlap = True
                            break

                    if not overlap:
                        selected_windows.append((start_ts, end_ts))
                        if len(selected_windows) >= self.max_clips:
                            break

        # Pass 3: Gap backfill with 15s-25s shorts to guarantee target clip count
        if len(selected_windows) < self.max_clips and timeline:
            selected_windows.sort(key=lambda x: x[0])
            gaps = []
            prev_end = timeline[0]["timestamp"]
            for w_start, w_end in selected_windows:
                if w_start - prev_end >= 15.0:
                    gaps.append((prev_end, w_start))
                prev_end = max(prev_end, w_end)
            if timeline[-1]["timestamp"] - prev_end >= 15.0:
                gaps.append((prev_end, timeline[-1]["timestamp"]))

            for g_start, g_end in gaps:
                if len(selected_windows) >= self.max_clips:
                    break
                gap_dur = g_end - g_start
                clip_dur = min(gap_dur, max(15.0, min(self.min_duration, gap_dur)))
                clip_steps = max(1, int(clip_dur / step_sec))
                g_start_idx = max(0, int((g_start - timeline[0]["timestamp"]) / step_sec))
                g_end_idx = min(n, int((g_end - timeline[0]["timestamp"]) / step_sec))
                
                best_sub_idx = g_start_idx
                best_sub_sum = -1.0
                for si in range(g_start_idx, max(g_start_idx + 1, g_end_idx - clip_steps + 1)):
                    s_sum = sum(scores[si : si + clip_steps])
                    if s_sum > best_sub_sum:
                        best_sub_sum = s_sum
                        best_sub_idx = si
                
                c_start = timeline[best_sub_idx]["timestamp"]
                c_end = min(timeline[-1]["timestamp"], round(c_start + clip_dur, 2))
                selected_windows.append((c_start, c_end))

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
