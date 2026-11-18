"""
pipeline.py - Unified multi-modal local clipping engine.
"""
from __future__ import annotations

import os
import cv2
from typing import Dict, List, Optional, Tuple

from .frame_sampler import FrameSampler
from .motion_detector import MotionDetector
from .scene_detector import SceneBoundaryDetector
from .audio_event_detector import AudioEventDetector
from .vision_analyzer import VisionAnalyzer
from .transcript_analyzer import TranscriptAnalyzer
from .event_scorer import EventScorer
from .clip_selector import ClipSelector


class LocalIntelligencePipeline:
    """Executes the full local analysis pipeline across vision, audio, and speech."""

    def __init__(
        self,
        profile_name: str = "gaming",
        target_fps: float = 1.0,
        min_clip_sec: float = 15.0,
        max_clip_sec: float = 59.0,
        max_clips: int = 5,
        llm_base_url: Optional[str] = None,
    ):
        self.profile_name = profile_name
        self.sampler = FrameSampler(target_fps=target_fps)
        self.motion_detector = MotionDetector()
        self.scene_detector = SceneBoundaryDetector()
        self.audio_detector = AudioEventDetector()
        self.vision_analyzer = VisionAnalyzer(ollama_url=llm_base_url)
        self.transcript_analyzer = TranscriptAnalyzer(base_url=llm_base_url)
        self.scorer = EventScorer(profile_name=profile_name)
        self.selector = ClipSelector(
            min_duration=min_clip_sec,
            max_duration=max_clip_sec,
            max_clips=max_clips,
        )

    def process_video(
        self,
        video_path: str,
        video_duration: Optional[float] = None,
        transcript_segments: Optional[List[Dict[str, any]]] = None,
    ) -> Tuple[List[Dict[str, any]], Dict[str, any]]:
        """
        Runs multi-modal analysis and returns (shorts, metadata).
        """
        if not os.path.exists(video_path):
            raise FileNotFoundError(f"Video file not found: {video_path}")

        # Determine duration if not provided
        if video_duration is None or video_duration <= 0:
            cap = cv2.VideoCapture(video_path)
            fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
            frames = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0
            video_duration = frames / fps if fps > 0 else 0.0
            cap.release()

        print(f"🎮 [Local Intelligence] Analyzing video '{os.path.basename(video_path)}' (Duration: {video_duration:.1f}s, Profile: {self.profile_name})")

        # 1. Sample frames at 1 fps
        sampled = list(self.sampler.sample_generator(video_path, end_sec=video_duration))
        print(f"   🖼️ Sampled {len(sampled)} visual frames at {self.sampler.target_fps} fps")

        # 2. Motion and scene analysis
        motion_events = self.motion_detector.analyze_frames(sampled)
        scene_cuts = self.scene_detector.detect_cuts(sampled)
        print(f"   ⚡ Detected {len(motion_events)} motion checkpoints, {sum(1 for c in scene_cuts if c['is_cut'])} scene transitions")

        # 3. Audio energy analysis
        audio_events = self.audio_detector.analyze_audio(video_path)
        print(f"   🔊 Evaluated {len(audio_events)} audio windows for spikes and energy peaks")

        # 4. Transcript analysis (if audio speech exists)
        scored_transcripts = []
        if transcript_segments:
            scored_transcripts = self.transcript_analyzer.score_transcript_segments(
                transcript_segments, mode=self.profile_name
            )
            print(f"   📝 Analyzed {len(scored_transcripts)} transcript segments")

        # 5. Multi-modal timeline scoring: S = w_v*V + w_a*A + w_t*T + w_c*C
        timeline = self.scorer.score_timeline(
            duration=video_duration,
            motion_events=motion_events,
            audio_events=audio_events,
            transcript_events=scored_transcripts,
            scene_cuts=scene_cuts,
        )

        # 6. Clip selection and ranking
        shorts = self.selector.select_clips(
            timeline=timeline,
            video_path=video_path,
            vision_analyzer=self.vision_analyzer if not transcript_segments else None,
            profile_name=self.profile_name,
        )
        print(f"   🎯 Extracted and ranked {len(shorts)} viral highlights")

        metadata = {
            "profile": self.profile_name,
            "weights": self.scorer.weights,
            "duration": video_duration,
            "sampled_frames_count": len(sampled),
            "clip_count": len(shorts),
            "local_pipeline": True,
        }

        return shorts, metadata
