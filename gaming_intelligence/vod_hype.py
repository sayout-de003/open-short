"""VOD chat-replay spike detection, no-chat loudness+scene hype, sparse section download & repeat exclusion."""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from gaming_intelligence.live.detection.features import extract_message_features


@dataclass
class VodChatMsg:
    t: float
    user: str
    text: str


@dataclass
class HypeSpike:
    peak: float
    z: float
    rate: float
    start: float
    end: float
    top_messages: List[str]
    kind: str = "chat"


def _ytdlp() -> List[str]:
    return ["yt-dlp"] if shutil.which("yt-dlp") else [sys.executable, "-m", "yt_dlp"]


def _message_weight(text: str) -> float:
    h_count, _, caps_ratio, _ = extract_message_features(text)
    bonus = min(4.0, h_count * 1.5)
    if caps_ratio > 0.7 and len(text) >= 4:
        bonus += 0.5
    return 1.0 + bonus


def fetch_vod_chat(url: str, out_dir: Path) -> List[VodChatMsg]:
    """Fetch VOD chat replay via chat-downloader or yt-dlp live_chat subtitles."""
    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        from chat_downloader import ChatDownloader  # type: ignore

        msgs = [
            VodChatMsg(
                float(m.get("time_in_seconds", 0)),
                (m.get("author") or {}).get("name", "?"),
                m.get("message") or "",
            )
            for m in ChatDownloader().get_chat(url)
            if m.get("time_in_seconds") is not None
        ]
        if msgs:
            msgs.sort(key=lambda m: m.t)
            return msgs
    except Exception:
        pass

    base = out_dir / "vod_chat"
    subprocess.run(
        _ytdlp() + ["--skip-download", "--write-subs", "--sub-langs", "live_chat", "-o", str(base), url],
        capture_output=True,
        check=False,
    )
    found = list(out_dir.glob("vod_chat*.live_chat.json"))
    if not found:
        return []
    msgs: List[VodChatMsg] = []
    with open(found[0], encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except ValueError:
                continue
            act = obj.get("replayChatItemAction")
            if not act:
                continue
            offset = float(act.get("videoOffsetTimeMsec", 0)) / 1000.0
            for a in act.get("actions", []):
                item = (a.get("addChatItemAction") or {}).get("item", {})
                r = item.get("liveChatTextMessageRenderer") or item.get("liveChatPaidMessageRenderer")
                if not r:
                    continue
                runs = (r.get("message") or {}).get("runs", [])
                text = "".join(x.get("text") or (x.get("emoji", {}).get("shortcuts") or [""])[0] for x in runs)
                user = (r.get("authorName") or {}).get("simpleText", "?")
                if text:
                    msgs.append(VodChatMsg(offset, user, text))
    msgs.sort(key=lambda m: m.t)
    return msgs


def _median_mad_zscores(smooth: List[float], baseline_sec: int = 60, smooth_sec: int = 3) -> List[float]:
    n = len(smooth)
    z = [0.0] * n
    for i in range(n):
        lo = max(0, i - baseline_sec)
        hi = max(lo, i - smooth_sec)
        hist = smooth[lo:hi]
        if len(hist) < 10:
            continue
        s_hist = sorted(hist)
        mid = len(s_hist) // 2
        mu = s_hist[mid] if len(s_hist) % 2 else 0.5 * (s_hist[mid - 1] + s_hist[mid])
        devs = sorted(abs(x - mu) for x in s_hist)
        mad = devs[mid] if len(devs) % 2 else 0.5 * (devs[mid - 1] + devs[mid])
        sd = max(0.5, 1.4826 * mad)
        z[i] = (smooth[i] - mu) / sd
    return z


def _pick_peaks(
    smooth: List[float],
    z: List[float],
    duration: Optional[float],
    max_clips: int = 5,
    z_threshold: float = 2.8,
    min_rate: float = 1.5,
    pre_sec: float = 20.0,
    post_sec: float = 10.0,
    min_clip: float = 15.0,
    min_gap: float = 30.0,
    exclude: Optional[List[Tuple[float, float]]] = None,
    top_fn=None,
    kind: str = "chat",
) -> List[HypeSpike]:
    gap = max(min_gap, pre_sec + post_sec)
    excl = exclude or []

    def _window(i: int) -> Tuple[float, float]:
        a = max(0.0, float(i) - pre_sec)
        b = float(i) + post_sec
        return a, (min(b, duration) if duration else b)

    def _free(i: int) -> bool:
        a, b = _window(i)
        if b - a < min_clip:
            return False
        return all(b <= x or a >= y for x, y in excl)

    peaks = [
        i for i in range(1, len(smooth) - 1)
        if smooth[i] > 0 and smooth[i] >= smooth[i - 1] and smooth[i] >= smooth[i + 1]
    ]
    strong = sorted(
        (i for i in peaks if z[i] >= z_threshold and smooth[i] >= min_rate),
        key=lambda i: z[i] * smooth[i],
        reverse=True,
    )
    strong_set = set(strong)
    weak = sorted(
        (i for i in peaks if i not in strong_set),
        key=lambda i: (max(z[i], 0.0) + 1.0) * smooth[i],
        reverse=True,
    )

    chosen: List[int] = []
    for i in strong + weak:
        if len(chosen) >= max_clips:
            break
        if _free(i) and all(abs(i - j) >= gap for j in chosen):
            chosen.append(i)

    out: List[HypeSpike] = []
    for i in sorted(chosen):
        a, b = _window(i)
        out.append(
            HypeSpike(
                peak=float(i),
                z=float(z[i]),
                rate=float(smooth[i]),
                start=a,
                end=b,
                top_messages=top_fn(float(i)) if top_fn else [],
                kind=kind,
            )
        )
    return out


def detect_chat_spikes(
    msgs: List[VodChatMsg],
    duration: Optional[float] = None,
    max_clips: int = 5,
    z_threshold: float = 2.8,
    min_rate: float = 1.5,
    exclude: Optional[List[Tuple[float, float]]] = None,
    smooth_sec: int = 3,
) -> List[HypeSpike]:
    """Detect chat hype spikes using a Median + MAD rolling baseline."""
    if not msgs:
        return []
    end = duration if duration else (msgs[-1].t + 1.0)
    n = max(int(end) + 2, 1)
    counts = [0.0] * n
    for m in msgs:
        idx = int(m.t)
        if 0 <= idx < n:
            counts[idx] += _message_weight(m.text)

    k = max(1, int(smooth_sec))
    half = k // 2
    smooth = []
    for i in range(n):
        lo = max(0, i - half)
        hi = min(n, lo + k)
        smooth.append(sum(counts[lo:hi]) / float(k))

    z = _median_mad_zscores(smooth, smooth_sec=k)

    def _top(peak: float) -> List[str]:
        near = [m.text for m in msgs if peak - 3.0 <= m.t <= peak + 3.0]
        near.sort(key=_message_weight, reverse=True)
        return near[:8]

    return _pick_peaks(
        smooth, z, duration,
        max_clips=max_clips, z_threshold=z_threshold, min_rate=min_rate,
        exclude=exclude, top_fn=_top, kind="chat",
    )


def download_vod_section(url: str, start_sec: float, end_sec: float, out_path: Path) -> Path:
    """Download only a specific [start_sec, end_sec] window from a VOD."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if out_path.exists() and out_path.stat().st_size > 0:
        return out_path
    a = max(0.0, start_sec)
    b = max(a + 1.0, end_sec)
    subprocess.run(
        _ytdlp() + [
            "-q", "--no-warnings",
            "-f", "bv*[height<=1080]+ba/b[height<=1080]/b",
            "--download-sections", f"*{a:.0f}-{b:.0f}",
            "--force-keyframes-at-cuts",
            "--merge-output-format", "mp4",
            "-o", str(out_path),
            url,
        ],
        check=True,
    )
    return out_path


_HISTORY_PATH = Path(os.environ.get("OPENSHORTS_CLIP_HISTORY", str(Path.home() / ".openshorts" / "clip_history.json")))


def load_clip_history(source: str, history_path: Path = _HISTORY_PATH) -> List[Tuple[float, float]]:
    key = source.split("&")[0].rstrip("/").lower()
    try:
        data = json.loads(history_path.read_text(encoding="utf-8"))
        return [(float(r[0]), float(r[1])) for r in data.get(key, []) if len(r) >= 2]
    except Exception:
        return []


def remember_clip_ranges(source: str, ranges: List[Tuple[float, float]], history_path: Path = _HISTORY_PATH) -> None:
    if not ranges:
        return
    key = source.split("&")[0].rstrip("/").lower()
    try:
        data = json.loads(history_path.read_text(encoding="utf-8"))
    except Exception:
        data = {}
    data.setdefault(key, []).extend([[round(a, 2), round(b, 2)] for a, b in ranges])
    history_path.parent.mkdir(parents=True, exist_ok=True)
    history_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
