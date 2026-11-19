"""
intelligence/job_context.py - Immutable per-job configuration and context.

Eliminates process-wide environment mutation (such as os.environ['CLIPPING_PROFILE']),
preventing cross-job state leaks when jobs are processed concurrently.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


class ContentProfile:
    AUTO = "auto"
    GAMING = "gaming"
    PODCAST = "podcast"
    EDUCATIONAL = "educational"
    COMMENTARY = "commentary"
    GENERIC = "generic"

    ALL = {AUTO, GAMING, PODCAST, EDUCATIONAL, COMMENTARY, GENERIC}

    @classmethod
    def normalize(cls, val: Optional[str]) -> str:
        if not val:
            return cls.AUTO
        val_clean = str(val).strip().lower()
        if val_clean in cls.ALL:
            return val_clean
        # Map aliases
        aliases = {
            "game": cls.GAMING,
            "gameplay": cls.GAMING,
            "action": cls.GAMING,
            "talk": cls.PODCAST,
            "interview": cls.PODCAST,
            "tutorial": cls.EDUCATIONAL,
            "explainer": cls.EDUCATIONAL,
            "edu": cls.EDUCATIONAL,
            "vlog": cls.COMMENTARY,
            "reaction": cls.COMMENTARY,
        }
        return aliases.get(val_clean, cls.GENERIC)


@dataclass(frozen=True)
class JobContext:
    job_id: str
    content_type: str = ContentProfile.AUTO
    resolved_profile: str = ContentProfile.GENERIC
    profile_confidence: float = 1.0
    profile_reason: str = "User specified"
    aspect_ratio: str = "9:16"
    clip_count: int = 5
    min_duration: float = 15.0
    max_duration: float = 60.0
    template_id: Optional[str] = None
    caption_enabled: bool = True
    smart_reframe: bool = True
    custom_prompt: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def with_resolved_profile(
        self,
        profile: str,
        confidence: float = 1.0,
        reason: str = "Classified",
    ) -> JobContext:
        """Returns a new JobContext with resolved profile while keeping other fields immutable."""
        return JobContext(
            job_id=self.job_id,
            content_type=self.content_type,
            resolved_profile=ContentProfile.normalize(profile),
            profile_confidence=round(float(confidence), 2),
            profile_reason=str(reason),
            aspect_ratio=self.aspect_ratio,
            clip_count=self.clip_count,
            min_duration=self.min_duration,
            max_duration=self.max_duration,
            template_id=self.template_id,
            caption_enabled=self.caption_enabled,
            smart_reframe=self.smart_reframe,
            custom_prompt=self.custom_prompt,
            metadata=dict(self.metadata),
        )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> JobContext:
        content_type = ContentProfile.normalize(data.get("content_type") or data.get("clipping_profile"))
        resolved_profile = ContentProfile.normalize(data.get("resolved_profile") or content_type)
        return cls(
            job_id=str(data.get("job_id", "")),
            content_type=content_type,
            resolved_profile=resolved_profile,
            profile_confidence=float(data.get("profile_confidence", 1.0)),
            profile_reason=str(data.get("profile_reason", "Initialized")),
            aspect_ratio=str(data.get("aspect_ratio", "9:16")),
            clip_count=int(data.get("clip_count", 5)),
            min_duration=float(data.get("min_duration", 15.0)),
            max_duration=float(data.get("max_duration", 60.0)),
            template_id=data.get("template_id"),
            caption_enabled=bool(data.get("caption_enabled", True)),
            smart_reframe=bool(data.get("smart_reframe", True)),
            custom_prompt=data.get("custom_prompt"),
            metadata=dict(data.get("metadata") or {}),
        )

    def to_subprocess_env(self, base_env: Optional[Dict[str, str]] = None) -> Dict[str, str]:
        """Provides isolated environment dictionary for worker subprocesses without mutating os.environ."""
        env = dict(base_env or {})
        env["JOB_ID"] = self.job_id
        env["CONTENT_TYPE"] = self.content_type
        env["CLIPPING_PROFILE"] = self.resolved_profile
        env["PROFILE_CONFIDENCE"] = str(self.profile_confidence)
        env["PROFILE_REASON"] = self.profile_reason
        env["TARGET_ASPECT_RATIO"] = self.aspect_ratio
        env["TARGET_CLIP_COUNT"] = str(self.clip_count)
        if self.template_id:
            env["TEMPLATE_ID"] = self.template_id
        return env
