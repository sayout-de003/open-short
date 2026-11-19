"""
normalizer.py - Normalizes chat lines from Twitch and YouTube into standardized ChatMessage objects.
Zero DB dependencies, minimal allocations.
"""
from __future__ import annotations

import re
import time
from typing import Optional
from ..models import ChatMessage, Platform

# Regex to parse Twitch IRC PRIVMSG
# Example: :username!username@username.tmi.twitch.tv PRIVMSG #channel :message text here
_TWITCH_PRIVMSG_RE = re.compile(r"^:([^!]+)![^ ]+ PRIVMSG #[^ ]+ :(.*)$")


def parse_twitch_irc_line(line: str, timestamp: Optional[float] = None) -> Optional[ChatMessage]:
    """Extracts username and message text from a raw Twitch IRC line in O(1)."""
    line = line.strip()
    if not line:
        return None

    match = _TWITCH_PRIVMSG_RE.match(line)
    if not match:
        return None

    user = match.group(1)
    text = match.group(2)
    now = timestamp or time.time()

    return ChatMessage(
        timestamp=now,
        user_id=user,
        text=text,
        platform=Platform.TWITCH
    )


def parse_youtube_chat_item(item: dict, timestamp: Optional[float] = None) -> Optional[ChatMessage]:
    """Parses a YouTube Live Chat JSON message item into a ChatMessage."""
    try:
        snippet = item.get("snippet", {})
        author = item.get("authorDetails", {})
        user_id = author.get("channelId") or author.get("displayName") or "unknown"

        # Check for superchat or standard text
        display_message = snippet.get("displayMessage") or ""
        superchat_details = snippet.get("superChatMessageDetails")
        amount = 0.0
        if superchat_details:
            amount_micros = superchat_details.get("amountMicros", 0)
            amount = float(amount_micros) / 1_000_000.0

        is_sub = bool(author.get("isChatSponsor", False))
        now = timestamp or time.time()

        return ChatMessage(
            timestamp=now,
            user_id=str(user_id),
            text=display_message,
            platform=Platform.YOUTUBE,
            is_subscriber=is_sub,
            bits_or_superchat=amount
        )
    except Exception:
        return None
