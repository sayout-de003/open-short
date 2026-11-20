"""
resource_guard.py - Lightweight, cross-platform system RAM monitoring & admission guard.

Uses psutil when installed and falls back to /proc/meminfo (Linux) or
sysctl + vm_stat (macOS) so it works in minimal environments too.
"""
from __future__ import annotations

import asyncio
import os
import re
import subprocess
import sys
import time
from typing import Callable, Dict, Optional

_CACHE_TTL_SEC = 1.5
_ram_cache: Dict[str, object] = {"at": 0.0, "stats": None}


def _read_psutil_ram() -> Optional[Dict[str, float]]:
    try:
        import psutil  # type: ignore

        vm = psutil.virtual_memory()
        total_mb = round(vm.total / (1024 * 1024), 1)
        avail_mb = round(vm.available / (1024 * 1024), 1)
        used_mb = round(max(0.0, total_mb - avail_mb), 1)
        return {
            "total_mb": total_mb,
            "available_mb": avail_mb,
            "used_mb": used_mb,
            "used_percent": round(vm.percent, 1),
        }
    except Exception:
        return None


def _read_linux_proc_meminfo() -> Optional[Dict[str, float]]:
    if not os.path.exists("/proc/meminfo"):
        return None
    try:
        vals: Dict[str, int] = {}
        with open("/proc/meminfo", "r", encoding="utf-8") as f:
            for line in f:
                parts = line.split(":", 1)
                if len(parts) != 2:
                    continue
                key = parts[0].strip()
                if key in ("MemTotal", "MemAvailable", "MemFree", "Buffers", "Cached"):
                    num = parts[1].strip().split()[0]
                    vals[key] = int(num)  # kB
        total_kb = vals.get("MemTotal")
        if not total_kb:
            return None
        avail_kb = vals.get("MemAvailable")
        if avail_kb is None:
            avail_kb = vals.get("MemFree", 0) + vals.get("Buffers", 0) + vals.get("Cached", 0)
        total_mb = round(total_kb / 1024.0, 1)
        avail_mb = round(avail_kb / 1024.0, 1)
        used_mb = round(max(0.0, total_mb - avail_mb), 1)
        pct = round((used_mb / total_mb) * 100.0, 1) if total_mb > 0 else 0.0
        return {
            "total_mb": total_mb,
            "available_mb": avail_mb,
            "used_mb": used_mb,
            "used_percent": pct,
        }
    except Exception:
        return None


def _read_macos_ram() -> Optional[Dict[str, float]]:
    if sys.platform != "darwin":
        return None
    try:
        total_out = subprocess.run(
            ["sysctl", "-n", "hw.memsize"],
            capture_output=True, text=True, timeout=2,
        )
        vm_out = subprocess.run(
            ["vm_stat"],
            capture_output=True, text=True, timeout=2,
        )
        if total_out.returncode != 0 or vm_out.returncode != 0:
            return None
        total_bytes = int(total_out.stdout.strip())
        page_match = re.search(r"page size of (\d+) bytes", vm_out.stdout)
        page_size = int(page_match.group(1)) if page_match else 16384

        def _pages(label: str) -> int:
            m = re.search(rf"^{re.escape(label)}:\s+(\d+)\.", vm_out.stdout, re.MULTILINE)
            return int(m.group(1)) if m else 0

        # Free + inactive + speculative + purgeable approximates reclaimable/available RAM on macOS.
        avail_pages = _pages("Pages free") + _pages("Pages inactive") + _pages("Pages speculative") + _pages("Pages purgeable")
        avail_bytes = avail_pages * page_size
        total_mb = round(total_bytes / (1024 * 1024), 1)
        avail_mb = round(min(total_bytes, avail_bytes) / (1024 * 1024), 1)
        used_mb = round(max(0.0, total_mb - avail_mb), 1)
        pct = round((used_mb / total_mb) * 100.0, 1) if total_mb > 0 else 0.0
        return {
            "total_mb": total_mb,
            "available_mb": avail_mb,
            "used_mb": used_mb,
            "used_percent": pct,
        }
    except Exception:
        return None


def ram_stats(use_cache: bool = True) -> Dict[str, Optional[float]]:
    """Return current system RAM statistics in MiB."""
    now = time.monotonic()
    if use_cache and _ram_cache["stats"] is not None and (now - float(_ram_cache["at"])) < _CACHE_TTL_SEC:
        return dict(_ram_cache["stats"])  # type: ignore[arg-type]

    stats = _read_psutil_ram() or _read_linux_proc_meminfo() or _read_macos_ram()
    if stats is None:
        stats = {"total_mb": None, "available_mb": None, "used_mb": None, "used_percent": None}
    _ram_cache["at"] = now
    _ram_cache["stats"] = stats
    return dict(stats)


def available_ram_mb(use_cache: bool = True) -> Optional[float]:
    """Return available system RAM in MiB, or None if unavailable."""
    return ram_stats(use_cache=use_cache).get("available_mb")


def ram_has_room(min_free_mb: int, active_count: int = 0, avail_mb: Optional[float] = None) -> bool:
    """Return True if a new workload can start under the free-RAM threshold.

    When active_count == 0, fails open so an idle machine can never deadlock.
    """
    if active_count == 0 or min_free_mb <= 0:
        return True
    if avail_mb is None:
        avail_mb = available_ram_mb()
    if avail_mb is None:
        return True
    return avail_mb >= float(min_free_mb)


async def wait_for_ram(
    min_free_mb: int,
    active_count_fn: Optional[Callable[[], int]] = None,
    timeout_sec: float = 120.0,
    poll_sec: float = 2.0,
) -> bool:
    """Wait asynchronously until system RAM has at least min_free_mb available.

    Returns True if room is available (or check is disabled/idle), False on timeout.
    """
    if min_free_mb <= 0:
        return True
    loop = asyncio.get_running_loop()
    waited = 0.0
    while True:
        active = active_count_fn() if active_count_fn else 1
        avail = await loop.run_in_executor(None, lambda: available_ram_mb(use_cache=False))
        if ram_has_room(min_free_mb, active, avail):
            return True
        if waited >= timeout_sec:
            return False
        await asyncio.sleep(poll_sec)
        waited += poll_sec
