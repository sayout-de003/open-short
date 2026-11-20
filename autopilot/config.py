"""Centralized configuration for the Zero-Touch Daily Gaming Autopilot."""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional
from urllib.parse import urlparse

from .exceptions import ConfigError

BASE_DIR = Path(__file__).resolve().parent.parent


def _load_dotenv_into_env(env_path: Path) -> None:
    """Load key=value pairs from .env without overriding already-set env vars."""
    if not env_path.exists():
        return
    try:
        from dotenv import load_dotenv
        load_dotenv(env_path, override=False)
        return
    except ImportError:
        pass
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        if k and k not in os.environ:
            os.environ[k] = v


def _env_bool(name: str, default: bool) -> bool:
    val = os.getenv(name)
    if val is None or not val.strip():
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")


def _env_int(name: str, default: int) -> int:
    val = os.getenv(name)
    if val is None or not val.strip():
        return default
    try:
        return int(val.strip())
    except ValueError as e:
        raise ConfigError(f"Invalid integer for {name}: {val!r}") from e


def _env_list(name: str, default: List[str]) -> List[str]:
    val = os.getenv(name)
    if val is None or not val.strip():
        return list(default)
    return [item.strip() for item in val.split(",") if item.strip()]


@dataclass
class AutopilotConfig:
    base_dir: Path
    output_dir: Path
    clips_dir: Path
    temp_dir: Path
    logs_dir: Path
    database_path: Path

    buffer_access_token: Optional[str] = None
    public_api_url: Optional[str] = None
    youtube_api_key: Optional[str] = None
    twitch_client_id: Optional[str] = None
    twitch_client_secret: Optional[str] = None

    # Feature toggles
    youtube_discovery_enabled: bool = True
    twitch_discovery_enabled: bool = True
    buffer_enabled: bool = True
    live_capture_enabled: bool = True

    # Discovery
    gaming_categories: List[str] = field(
        default_factory=lambda: ["GTA 6", "Valorant", "Minecraft", "Fortnite"]
    )
    discovery_top_n: int = 10
    discovery_max_age_hours: int = 72

    # Processing & Quotas
    max_vods_per_run: int = 3
    max_live_streams: int = 2
    max_clips_per_source: int = 2
    max_clips_per_day: int = 6
    buffer_posts_per_channel_per_day: int = 2
    buffer_platforms: List[str] = field(default_factory=lambda: ["youtube", "instagram"])
    buffer_scheduling_mode: str = "smart_jitter"

    # Video
    clip_min_duration: int = 30
    clip_max_duration: int = 40

    # Live detection
    live_clip_cooldown_seconds: int = 180
    live_monitor_window_minutes: int = 60

    # Cleanup & Recovery
    clip_retention_hours: int = 24
    delete_clip_after_publish: bool = True
    stale_lock_minutes: int = 45
    max_job_attempts: int = 3
    timezone: str = "UTC"

    @classmethod
    def from_env(cls, env_path: Optional[Path | str] = None) -> "AutopilotConfig":
        target_env = Path(env_path) if env_path else Path(
            os.getenv("OPENSHORT_ENV_PATH", str(BASE_DIR / ".env"))
        )
        if not target_env.is_absolute():
            target_env = BASE_DIR / target_env
        _load_dotenv_into_env(target_env)

        output_dir = Path(os.getenv("OPENSHORT_OUTPUT_DIR", str(BASE_DIR / "output")))
        if not output_dir.is_absolute():
            output_dir = BASE_DIR / output_dir

        db_url = os.getenv("AUTOPILOT_DATABASE_URL", "").strip()
        if db_url.startswith("sqlite:///"):
            raw_db = Path(db_url[len("sqlite:///"):])
            database_path = raw_db if raw_db.is_absolute() else BASE_DIR / raw_db
        elif db_url:
            raise ConfigError(f"Unsupported AUTOPILOT_DATABASE_URL: {db_url!r}; only sqlite:/// is supported")
        else:
            database_path = output_dir / "autopilot.db"

        return cls(
            base_dir=BASE_DIR,
            output_dir=output_dir,
            clips_dir=output_dir / "clips",
            temp_dir=output_dir / "temp",
            logs_dir=output_dir / "logs",
            database_path=database_path,
            buffer_access_token=os.getenv("BUFFER_ACCESS_TOKEN", "").strip() or None,
            public_api_url=os.getenv("PUBLIC_API_URL", "").strip().rstrip("/") or None,
            youtube_api_key=os.getenv("YOUTUBE_API_KEY", "").strip() or None,
            twitch_client_id=os.getenv("TWITCH_CLIENT_ID", "").strip() or None,
            twitch_client_secret=os.getenv("TWITCH_CLIENT_SECRET", "").strip() or None,
            youtube_discovery_enabled=_env_bool("YOUTUBE_DISCOVERY_ENABLED", True),
            twitch_discovery_enabled=_env_bool("TWITCH_DISCOVERY_ENABLED", True),
            buffer_enabled=_env_bool("BUFFER_ENABLED", True),
            live_capture_enabled=_env_bool("LIVE_CAPTURE_ENABLED", True),
            gaming_categories=_env_list("GAMING_CATEGORIES", ["GTA 6", "Valorant", "Minecraft", "Fortnite"]),
            discovery_top_n=_env_int("DISCOVERY_TOP_N", 10),
            discovery_max_age_hours=_env_int("DISCOVERY_MAX_AGE_HOURS", 72),
            max_vods_per_run=_env_int("MAX_VODS_PER_RUN", 3),
            max_live_streams=_env_int("MAX_LIVE_STREAMS", 2),
            max_clips_per_source=_env_int("MAX_CLIPS_PER_SOURCE", 2),
            max_clips_per_day=_env_int("MAX_CLIPS_PER_DAY", 6),
            buffer_posts_per_channel_per_day=_env_int("BUFFER_POSTS_PER_CHANNEL_PER_DAY", 2),
            buffer_platforms=_env_list("BUFFER_PLATFORMS", ["youtube", "instagram"]),
            buffer_scheduling_mode=os.getenv("BUFFER_SCHEDULING_MODE", "smart_jitter").strip() or "smart_jitter",
            clip_min_duration=_env_int("CLIP_MIN_DURATION", 30),
            clip_max_duration=_env_int("CLIP_MAX_DURATION", 40),
            live_clip_cooldown_seconds=_env_int("LIVE_CLIP_COOLDOWN_SECONDS", 180),
            live_monitor_window_minutes=_env_int("LIVE_MONITOR_WINDOW_MINUTES", 60),
            clip_retention_hours=_env_int("CLIP_RETENTION_HOURS", 24),
            delete_clip_after_publish=_env_bool("DELETE_CLIP_AFTER_PUBLISH", True),
            stale_lock_minutes=_env_int("STALE_LOCK_MINUTES", 45),
            max_job_attempts=_env_int("MAX_JOB_ATTEMPTS", 3),
            timezone=os.getenv("AUTOPILOT_TIMEZONE", "UTC").strip() or "UTC",
        )

    def ensure_directories(self) -> None:
        for d in (self.output_dir, self.clips_dir, self.temp_dir, self.logs_dir, self.database_path.parent):
            d.mkdir(parents=True, exist_ok=True)

    def validate(self, require_publish: bool = False, require_discovery: bool = False) -> None:
        """Validate bounds, directory writability, and required credentials for enabled modes."""
        if self.clip_min_duration <= 0 or self.clip_max_duration < self.clip_min_duration:
            raise ConfigError(
                f"Invalid clip duration range: {self.clip_min_duration}..{self.clip_max_duration}s"
            )
        if self.buffer_posts_per_channel_per_day < 1:
            raise ConfigError("BUFFER_POSTS_PER_CHANNEL_PER_DAY must be >= 1")
        if self.clip_retention_hours < 1:
            raise ConfigError("CLIP_RETENTION_HOURS must be >= 1")
        if self.max_clips_per_source < 1 or self.max_clips_per_day < 1:
            raise ConfigError("MAX_CLIPS_PER_SOURCE and MAX_CLIPS_PER_DAY must be >= 1")

        self.ensure_directories()
        for d in (self.output_dir, self.clips_dir, self.temp_dir, self.logs_dir):
            if not os.access(d, os.W_OK):
                raise ConfigError(f"Output directory is not writable: {d}")

        if require_publish and self.buffer_enabled:
            if not self.buffer_access_token:
                raise ConfigError("BUFFER_ACCESS_TOKEN is required when BUFFER_ENABLED=true")
            if not self.public_api_url:
                raise ConfigError("PUBLIC_API_URL is required when BUFFER_ENABLED=true")
            parsed = urlparse(self.public_api_url)
            if parsed.scheme != "https" or not parsed.netloc:
                raise ConfigError(f"PUBLIC_API_URL must be a valid https:// URL, got {self.public_api_url!r}")

        if require_discovery:
            if self.twitch_discovery_enabled and (not self.twitch_client_id or not self.twitch_client_secret):
                raise ConfigError("TWITCH_CLIENT_ID and TWITCH_CLIENT_SECRET are required when TWITCH_DISCOVERY_ENABLED=true")
            if self.youtube_discovery_enabled and not self.youtube_api_key:
                logging.getLogger("autopilot.config").warning(
                    "YOUTUBE_API_KEY is not set; YouTube discovery will use yt-dlp fallback with lower confidence."
                )


def configure_logging(logs_dir: Path, level: int = logging.INFO) -> logging.Logger:
    """Configure structured console + file logging for autopilot."""
    logs_dir.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("autopilot")
    logger.setLevel(level)
    if not logger.handlers:
        fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
        sh = logging.StreamHandler()
        sh.setFormatter(fmt)
        fh = logging.FileHandler(logs_dir / "autopilot.log", encoding="utf-8")
        fh.setFormatter(fmt)
        logger.addHandler(sh)
        logger.addHandler(fh)
    return logger
