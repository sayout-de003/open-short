"""Structured error hierarchy for autopilot retry and failure classification."""
from __future__ import annotations


class AutopilotError(Exception):
    """Base error for all autopilot operations."""


class ConfigError(AutopilotError):
    """Invalid or missing configuration."""


class RetryableError(AutopilotError):
    """Transient failure (network timeout, 5xx, temporary DB lock) eligible for backoff retry."""


class RateLimitError(RetryableError):
    """Provider rate limit hit; optionally carries retry_after_sec."""

    def __init__(self, message: str, retry_after_sec: float | None = None):
        super().__init__(message)
        self.retry_after_sec = retry_after_sec


class PermanentError(AutopilotError):
    """Non-retryable failure (invalid source, unsupported media, corrupt input)."""


class EligibilityError(PermanentError):
    """Source rejected by creator/rights eligibility policy; never auto-retry."""
