"""Data models and validated state machine for the autopilot queue."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Optional, Set


class JobStatus(str, Enum):
    DISCOVERED = "DISCOVERED"
    QUEUED = "QUEUED"
    PROCESSING = "PROCESSING"
    CLIPS_GENERATED = "CLIPS_GENERATED"
    QUALITY_APPROVED = "QUALITY_APPROVED"
    UPLOADED = "UPLOADED"
    SCHEDULED = "SCHEDULED"
    PUBLISHED = "PUBLISHED"
    FAILED = "FAILED"


VALID_TRANSITIONS: Dict[JobStatus, Set[JobStatus]] = {
    JobStatus.DISCOVERED: {JobStatus.QUEUED, JobStatus.FAILED},
    JobStatus.QUEUED: {JobStatus.PROCESSING, JobStatus.FAILED},
    JobStatus.PROCESSING: {JobStatus.CLIPS_GENERATED, JobStatus.QUEUED, JobStatus.FAILED},
    JobStatus.CLIPS_GENERATED: {JobStatus.QUALITY_APPROVED, JobStatus.FAILED},
    JobStatus.QUALITY_APPROVED: {JobStatus.UPLOADED, JobStatus.FAILED},
    JobStatus.UPLOADED: {JobStatus.SCHEDULED, JobStatus.FAILED},
    JobStatus.SCHEDULED: {JobStatus.PUBLISHED, JobStatus.FAILED},
    JobStatus.PUBLISHED: set(),
    # Retryable failures return to QUEUED (or PROCESSING/UPLOADED/SCHEDULED via explicit recovery)
    JobStatus.FAILED: {JobStatus.QUEUED},
}


class PublicationStatus(str, Enum):
    PENDING_SUBMIT = "PENDING_SUBMIT"
    CREATED = "CREATED"
    SCHEDULED = "SCHEDULED"
    PUBLISHED = "PUBLISHED"
    FAILED = "FAILED"


def validate_transition(current: JobStatus | str, target: JobStatus | str) -> JobStatus:
    cur = JobStatus(current)
    nxt = JobStatus(target)
    if nxt not in VALID_TRANSITIONS[cur]:
        raise ValueError(f"Invalid job state transition: {cur.value} -> {nxt.value}")
    return nxt


@dataclass
class DiscoveredSource:
    platform: str
    source_id: str
    source_type: str  # "live" | "vod"
    url: str
    title: str
    channel_id: str
    channel_name: str
    view_count: int = 0
    concurrent_viewers: int = 0
    like_count: int = 0
    comment_count: int = 0
    duration_sec: float = 0.0
    published_at: Optional[str] = None
    game_name: Optional[str] = None
    metadata_confidence: float = 100.0
    score: float = 0.0
    score_breakdown: Dict[str, float] = field(default_factory=dict)
    eligible: bool = True
    eligibility_reason: str = "approved"


@dataclass
class ProcessingJob:
    id: str
    source_pk: int
    platform: str
    source_id: str
    job_type: str  # "vod" | "live"
    status: JobStatus
    priority: float = 0.0
    attempt_count: int = 0
    max_attempts: int = 3
    next_retry_at: Optional[str] = None
    locked_at: Optional[str] = None
    worker_id: Optional[str] = None
    last_error: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    completed_at: Optional[str] = None
