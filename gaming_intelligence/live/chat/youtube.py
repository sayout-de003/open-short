"""
youtube.py - Asynchronous YouTube Live Chat ingestion.
Supports YouTube Data API v3 or public live chat polling.
"""
from __future__ import annotations

import asyncio
import json
import logging
import urllib.parse
import urllib.request
from typing import Callable, Optional
from .normalizer import parse_youtube_chat_item
from ..models import ChatMessage, Platform

try:
    import httpx
except ImportError:
    httpx = None

logger = logging.getLogger("live.youtube")


class YouTubeChatListener:
    """Asynchronously polls/streams messages from a YouTube Live stream chat."""

    def __init__(
        self,
        video_id_or_url: str,
        on_message: Callable[[ChatMessage], None],
        api_key: Optional[str] = None,
        poll_interval: float = 1.5,
    ):
        self.video_id = self._extract_video_id(video_id_or_url)
        self.on_message = on_message
        self.api_key = api_key
        self.poll_interval = poll_interval
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._live_chat_id: Optional[str] = None
        self._next_page_token: Optional[str] = None

    @staticmethod
    def _extract_video_id(url_or_id: str) -> str:
        url_or_id = url_or_id.strip()
        if "youtu" in url_or_id:
            parsed = urllib.parse.urlparse(url_or_id)
            if "youtube.com" in parsed.netloc:
                qs = urllib.parse.parse_qs(parsed.query)
                if "v" in qs:
                    return qs["v"][0]
                # /live/VIDEO_ID format
                parts = parsed.path.strip("/").split("/")
                if len(parts) >= 2 and parts[0] == "live":
                    return parts[1]
            elif "youtu.be" in parsed.netloc:
                return parsed.path.strip("/").split("/")[0]
        return url_or_id

    async def start(self):
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._poll_loop())

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _fetch_json(self, url: str) -> Optional[dict]:
        if httpx is not None:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(url, headers={"User-Agent": "OpenShorts/2.0"})
                resp.raise_for_status()
                return resp.json()
        loop = asyncio.get_running_loop()
        req = urllib.request.Request(url, headers={"User-Agent": "OpenShorts/2.0"})
        raw = await loop.run_in_executor(None, lambda: urllib.request.urlopen(req, timeout=10).read())
        return json.loads(raw.decode("utf-8"))

    async def _resolve_live_chat_id(self) -> Optional[str]:
        if not self.api_key:
            return None
        url = (
            f"https://www.googleapis.com/youtube/v3/videos"
            f"?part=liveStreamingDetails&id={self.video_id}&key={self.api_key}"
        )
        try:
            data = await self._fetch_json(url) or {}
            items = data.get("items", [])
            if items:
                details = items[0].get("liveStreamingDetails", {})
                return details.get("activeLiveChatId")
        except Exception as e:
            logger.warning(f"Failed to resolve YouTube liveChatId: {e}")
        return None

    async def _fetch_messages_api(self) -> list:
        if not self._live_chat_id or not self.api_key:
            return []
        url = (
            f"https://www.googleapis.com/youtube/v3/liveChat/messages"
            f"?liveChatId={self._live_chat_id}&part=snippet,authorDetails&key={self.api_key}"
        )
        if self._next_page_token:
            url += f"&pageToken={self._next_page_token}"

        try:
            data = await self._fetch_json(url) or {}
            self._next_page_token = data.get("nextPageToken")
            interval_ms = data.get("pollingIntervalMillis", 2000)
            self.poll_interval = max(0.5, interval_ms / 1000.0)
            return data.get("items", [])
        except Exception as e:
            logger.warning(f"Error fetching YouTube live chat messages: {e}")
            return []

    async def _poll_loop(self):
        if self.api_key:
            self._live_chat_id = await self._resolve_live_chat_id()

        while self._running:
            try:
                if self._live_chat_id and self.api_key:
                    items = await self._fetch_messages_api()
                    for item in items:
                        msg = parse_youtube_chat_item(item)
                        if msg:
                            self.on_message(msg)
                await asyncio.sleep(self.poll_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"YouTube chat listener error: {e}")
                await asyncio.sleep(2.0)
