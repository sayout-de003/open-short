"""
twitch.py - Asynchronous Twitch IRC chat ingestion using pure asyncio socket.
Zero credentials required (anonymous justinfan).
"""
from __future__ import annotations

import asyncio
import random
import logging
from typing import Callable, Optional
from .normalizer import parse_twitch_irc_line
from ..models import ChatMessage

logger = logging.getLogger("live.twitch")


class TwitchChatListener:
    """Asynchronously streams messages from a public Twitch channel's chat."""

    IRC_HOST = "irc.chat.twitch.tv"
    IRC_PORT = 6667

    def __init__(self, channel: str, on_message: Callable[[ChatMessage], None]):
        self.channel = channel.lower().lstrip("#").strip()
        self.on_message = on_message
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._reader: Optional[asyncio.StreamReader] = None
        self._writer: Optional[asyncio.StreamWriter] = None

    async def start(self):
        """Starts the chat listening loop in the background."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._listen_loop())

    async def stop(self):
        """Stops the chat listener."""
        self._running = False
        if self._writer:
            try:
                self._writer.close()
                await self._writer.wait_closed()
            except Exception:
                pass
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _listen_loop(self):
        retry_delay = 1.0
        while self._running:
            try:
                self._reader, self._writer = await asyncio.open_connection(
                    self.IRC_HOST, self.IRC_PORT
                )
                nick = f"justinfan{random.randint(10000, 99999)}"
                self._writer.write(f"PASS SCHMOOPIE\r\nNICK {nick}\r\nJOIN #{self.channel}\r\n".encode("utf-8"))
                await self._writer.drain()
                logger.info(f"Connected to Twitch IRC for #{self.channel} as {nick}")
                retry_delay = 1.0

                while self._running:
                    line_bytes = await self._reader.readline()
                    if not line_bytes:
                        break
                    line = line_bytes.decode("utf-8", errors="replace").strip()

                    # Handle Twitch PING/PONG heartbeats
                    if line.startswith("PING"):
                        self._writer.write(f"PONG {line[5:]}\r\n".encode("utf-8"))
                        await self._writer.drain()
                        continue

                    msg = parse_twitch_irc_line(line)
                    if msg:
                        self.on_message(msg)

            except asyncio.CancelledError:
                break
            except Exception as e:
                if self._running:
                    logger.warning(f"Twitch chat connection dropped ({e}), retrying in {retry_delay:.1f}s...")
                    await asyncio.sleep(retry_delay)
                    retry_delay = min(30.0, retry_delay * 1.5)
