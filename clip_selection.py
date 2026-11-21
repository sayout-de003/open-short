"""
Pure helpers for the Gemini clip-selection pipeline.

Standard-library only so both main.py and gemini_worker.py can import it and
the logic stays unit-testable without the heavy video dependencies.
"""
import math
import os

# USD per 1M tokens (input, output incl. thinking), from ai.google.dev pricing.
MODEL_PRICES = {
    "gemini-3.5-flash": (1.50, 9.00),
    "gemini-3.1-flash-lite": (0.25, 1.50),
    "gemini-3-flash-preview": (0.50, 3.00),
    "gemini-2.5-flash-lite": (0.10, 0.40),
    "gemini-2.5-flash": (0.30, 2.50),
    "gemini-2.0-flash": (0.10, 0.40),  # deprecated (shut down 2026-06-01)
}


def lookup_model_prices(model_name):
    """Longest-prefix match against MODEL_PRICES; None if unknown."""
    name = str(model_name or "").lower()
    best_key = None
    for key in MODEL_PRICES:
        if name.startswith(key) and (best_key is None or len(key) > len(best_key)):
            best_key = key
    return MODEL_PRICES[best_key] if best_key else None


def clip_count_targets(n_windows):
    """How many clips to ask the detail pass for, given the shortlist size.

    Measured on prod 3-ago-2026: 408 of 429 jobs (95%) delivered 3 clips or
    fewer, the mode being ONE, while the prompt was free to return one per
    shortlisted window. Users who received 1-3 clips came back a second day
    0.4% of the time; those who received 4-9 came back 16.1% — so the clip
    count, not the clip quality, is what the retention curve hangs on.

    The old prompt biased hard the other way ("prefer one great clip per
    candidate window") and handed the model two unbounded licences to drop
    clips (the 2-second rule and STANDS ALONE both end in "or skip it"), with
    no floor to stop it collapsing to a single clip. This puts a floor and a
    realistic ceiling on it instead.

    ``CLIP_TARGET_MIN`` / ``CLIP_TARGET_MAX`` override both for A/B runs
    without a deploy (the reframe-testing harness drives them).
    """
    import os

    n = max(1, int(n_windows or 1))
    low = max(2, min(6, n // 2 + 2))
    high = min(12, max(4, n * 2))
    low = min(low, high)

    def _override(name, current):
        raw = os.environ.get(name)
        if not raw:
            return current
        try:
            return max(1, int(raw))
        except ValueError:
            return current

    low = _override("CLIP_TARGET_MIN", low)
    high = _override("CLIP_TARGET_MAX", high)
    target_env = os.environ.get("TARGET_CLIP_COUNT")
    if target_env:
        try:
            target_val = int(target_env)
            if target_val > 0:
                low = min(low, target_val)
                high = max(high, target_val)
        except ValueError:
            pass
    return low, max(low, high)


def shortlist_target(video_duration):
    """How many scored windows the detail pass should get.

    Scales with duration so a long video surfaces more candidates without
    exploding the detail call, floored at 3 so a short one still gets a
    choice. ``score_batches`` exists to make this number reachable.
    """
    try:
        seconds = float(video_duration or 0)
    except (TypeError, ValueError):
        seconds = 0.0
    return max(3, min(10, int(seconds // 90) + 2))


def score_batches(windows, batch_size):
    """Split ``windows`` into near-equal scoring batches.

    Two things were wrong with the old ``range(0, n, batch_size)`` walk plus a
    prompt that said "choose up to 3 windows from this batch".

    The cap made the shortlist unreachable. Its real ceiling was
    ``3 * n_batches``, not ``shortlist_target``: measured 22-sep-2026 on a
    9:10 source, 9 windows batched 8 + 1 returned 3 + 1 = 4 windows against a
    target of 8. ``clip_count_targets`` then derives the clip floor from that
    halved shortlist, so the detail pass was asked for 4-8 clips instead of
    6-12 and the job delivered 4 (3 in prod on the same video). Every source
    under ~30 minutes was starved the same way, which is the mechanism behind
    "95% of jobs deliver 3 clips or fewer" — the clip count the retention
    curve hangs on (see clip_count_targets). The prompt now scores every
    window it is given and the shortlist is the global top ``target``, so the
    selection happens where the scores can actually be compared.

    Per-batch selection also threw away the ranking it was computing: a batch
    holding five great moments could only contribute three, while a batch of
    filler still contributed its own three.

    The remainder was its own bug: a trailing batch of one window came back
    with that window whatever its score, because a cap of 3 cannot filter a
    batch of 1 — the tail of the video entered the shortlist by arithmetic
    rather than merit (``window_009`` did exactly that on the measured run).
    Near-equal batches keep that from happening and also keep each score
    comparable, since a window judged alone is judged against nothing.
    """
    windows = list(windows or [])
    n = len(windows)
    if not n:
        return []
    size = max(1, int(batch_size or 1))
    n_batches = max(1, -(-n // size))       # ceil
    base, extra = divmod(n, n_batches)

    out = []
    start = 0
    for index in range(n_batches):
        take = base + (1 if index < extra else 0)
        batch = windows[start:start + take]
        start += take
        if batch:
            out.append(batch)
    return out


def trim_to_best(shorts, max_clips):
    """Cut an over-long detail-pass result down to ``max_clips`` BY SCORE.

    The detail pass hands its clips back in transcript order, batch after
    batch, so slicing the list keeps the EARLIEST clips rather than the best
    ones. On a 9-minute walkthrough that quietly threw away everything past
    minute three: the model proposed clips across the whole video, and the
    ones covering the demo, the MCP walkthrough and the close were the tail
    that got dropped. Worse, the failure scales the wrong way — the more
    generous the model is, the more of the video disappears.

    That sabotages the windowing: get_viral_clips builds scoring windows
    precisely because "a single call over the whole transcript clusters picks
    near the start", and a positional slice puts the clustering right back.

    Ranking is by ``predicted_score`` (the detail prompt already asks for it,
    and nothing else was reading it here). Ties keep transcript order, and the
    survivors come back in transcript order too, so clip numbering still runs
    front to back the way every caller downstream expects.
    """
    max_clips = max(1, int(max_clips or 1))
    if len(shorts) <= max_clips:
        return list(shorts)

    def score(item):
        try:
            return float(item[1].get("predicted_score") or 0)
        except (TypeError, ValueError, AttributeError):
            return 0.0

    indexed = list(enumerate(shorts))
    best = sorted(indexed, key=score, reverse=True)[:max_clips]
    return [item for _, item in sorted(best, key=lambda pair: pair[0])]


def vision_segments(video_duration, segment_seconds, max_segments):
    """Split a silent source into near-equal ``(start, end)`` stretches for
    the vision pass, each at most ``segment_seconds`` long.

    The vision pass sends Gemini the footage itself at ~300 tokens/second, so
    an hour (~1.08M tokens) no longer fits a 1M-token window and a silent
    multi-hour capture failed at the model. Near-equal stretches, not fixed
    ones: a 41-minute source split at 40 minutes would leave a one-minute
    tail that the prompt has to fill with 3+ clips. A source that fits in one
    stretch returns one stretch, so short videos take the single-upload path
    unchanged. Past ``max_segments`` the source is truncated (the caller logs
    it) rather than spending without bound on one job.
    """
    duration = max(0.0, float(video_duration or 0))
    seg = max(60.0, float(segment_seconds))
    if duration <= seg:
        return [(0.0, round(duration, 3))]
    n = int(math.ceil(duration / seg))
    n_kept = max(1, min(n, int(max_segments)))
    step = duration / n
    return [(round(i * step, 3), round(min(duration, (i + 1) * step), 3))
            for i in range(n_kept)]


def clip_duration_bounds():
    """The clip length band (seconds) the selection prompts and word-snapping
    enforce. ``CLIP_MIN_SECONDS`` / ``CLIP_MAX_SECONDS`` override the classic
    15-60 — set per job by /api/process when the user asks for a specific
    length, or by hand for A/B runs. Values are clamped to platform-sane
    limits and re-ordered so bad input degrades instead of breaking the job.
    """
    import os

    def _read(name, default):
        try:
            return float(os.environ.get(name, ""))
        except ValueError:
            return default

    lo = _read("CLIP_MIN_SECONDS", 30.0)
    hi = _read("CLIP_MAX_SECONDS", 60.0)
    lo = min(max(lo, 5.0), 175.0)
    hi = min(max(hi, 10.0), 180.0)
    if hi < lo + 5.0:  # keep a real band: degenerate ranges starve the model
        hi = min(180.0, lo + 5.0)
    return round(lo, 3), round(hi, 3)


def compact_words(words, precision=2):
    """Round word timestamps for prompts — full float precision wastes tokens."""
    return [
        {
            "w": w.get("w", ""),
            "s": round(float(w.get("s", 0)), precision),
            "e": round(float(w.get("e", 0)), precision),
        }
        for w in words
    ]


def build_transcript_windows(transcript_result, video_duration,
                             window_seconds=90, overlap_seconds=30):
    """
    Build scoring windows aligned to Whisper segment boundaries, so a sentence
    (and usually a viral moment) is never cut in half mid-window. Windows grow
    segment by segment to roughly window_seconds (up to 1.25x for the closing
    segment) and the next window starts ~overlap_seconds before the previous
    end, also snapped to a segment start.
    """
    segments = []
    for segment in transcript_result.get("segments", []):
        text = str(segment.get("text") or "").strip()
        if not text:
            continue
        segments.append((float(segment.get("start", 0)), float(segment.get("end", 0)), text))

    windows = []
    window_index = 1
    i = 0
    n = len(segments)
    while i < n:
        w_start = segments[i][0]
        j = i
        # Extend while the NEXT segment still fits within a tolerant cap, so the
        # window closes on a segment boundary near window_seconds.
        while j + 1 < n and segments[j + 1][1] - w_start <= window_seconds * 1.25:
            j += 1
            if segments[j][1] - w_start >= window_seconds:
                break
        w_end = segments[j][1]
        windows.append({
            "id": f"window_{window_index:03d}",
            "start": round(w_start, 3),
            "end": round(w_end, 3),
            "text": " ".join(seg[2] for seg in segments[i:j + 1]),
        })
        window_index += 1

        if j >= n - 1:
            break
        # Next window starts at the first segment beginning after (end - overlap),
        # but always makes progress.
        target = w_end - overlap_seconds
        k = i + 1
        while k <= j and segments[k][0] < target:
            k += 1
        i = max(k, i + 1)

    if not windows:
        windows.append({
            "id": "window_001",
            "start": 0.0,
            "end": round(float(video_duration), 3),
            "text": str(transcript_result.get("text", "") or ""),
        })
    return windows


def dedupe_overlapping(shorts, ratio=None):
    """Drop clips that overlap an already-kept clip by ``ratio`` of the
    shorter one, keeping the higher ``predicted_score`` (earlier on a tie).

    Default ratio 0.40 allows distinct clips that share context (e.g. action
    followed by reaction) to survive while still dropping near-duplicate cuts.
    Can be adjusted via CLIP_DEDUPE_RATIO.
    """
    if ratio is None:
        try:
            ratio = float(os.environ.get("CLIP_DEDUPE_RATIO", "0.40"))
        except (ValueError, TypeError):
            ratio = 0.40
    def _score(c):
        try:
            return float(c.get("predicted_score") or 0)
        except (TypeError, ValueError, AttributeError):
            return 0.0

    def _span(c):
        try:
            return float(c.get("start", 0)), float(c.get("end", 0))
        except (TypeError, ValueError, AttributeError):
            return 0.0, 0.0

    indexed = list(enumerate(shorts))
    kept = []
    for idx, clip in sorted(indexed, key=lambda p: (-_score(p[1]), p[0])):
        s, e = _span(clip)
        clash = False
        for _, other in kept:
            os_, oe = _span(other)
            overlap = min(e, oe) - max(s, os_)
            shorter = max(1e-6, min(e - s, oe - os_))
            if overlap > 0 and overlap / shorter >= ratio:
                clash = True
                break
        if not clash:
            kept.append((idx, clip))
    return [c for _, c in sorted(kept, key=lambda p: p[0])]


def _clean_word_text(w):
    return str(w or "").strip().lower()


def _is_sentence_terminal(w):
    clean = str(w or "").strip()
    return clean.endswith(('.', '!', '?', '."', '!"', '?"', '…', '—'))


def _is_clause_terminal(w):
    clean = str(w or "").strip()
    return clean.endswith((',', ';', ':', ',"', ';"'))


def _is_conjunction_or_filler(w):
    clean = "".join(ch for ch in str(w or "").lower() if ch.isalnum())
    return clean in {"and", "but", "so", "or", "because", "well", "like", "uh", "um", "actually"}


def snap_clip_to_words(start, end, words, video_duration,
                       min_duration=15.0, max_duration=60.0,
                       search_window=1.8, max_lead=0.45, max_tail=0.55):
    """
    Snap proposed clip boundaries onto real word and sentence boundaries
    with natural acoustic lead/tail margins.

    Avoids mid-sentence, mid-word cuts and keeps full punchlines intact
    instead of cutting off abruptly on hard duration limits.
    """
    original = (round(float(start), 3), round(float(end), 3))
    if not words:
        return original

    starts = [float(w.get("s", 0)) for w in words]
    ends = [float(w.get("e", 0)) for w in words]
    n_words = len(words)

    # START: snap to the nearest word start, favoring sentence openings over conjunctions
    new_start = float(start)
    start_candidates = [i for i, s in enumerate(starts) if abs(s - new_start) <= search_window]
    if start_candidates:
        # Prefer a clean sentence start (previous word was terminal or had a pause)
        best_i = start_candidates[0]
        min_dist = float("inf")
        for i in start_candidates:
            w_text = words[i].get("w", "")
            s_val = starts[i]
            dist = abs(s_val - new_start)
            # Check if this word is preceded by sentence termination or natural pause >= 0.35s
            is_sentence_start = False
            if i > 0:
                prev_w = words[i - 1].get("w", "")
                prev_e = ends[i - 1]
                if _is_sentence_terminal(prev_w) or (s_val - prev_e >= 0.35):
                    is_sentence_start = True
            elif i == 0:
                is_sentence_start = True

            # If it's a conjunction/filler and not a true sentence start, slightly penalize
            weight = dist
            if _is_conjunction_or_filler(w_text) and not is_sentence_start:
                weight += 0.4
            elif is_sentence_start:
                weight -= 0.3

            if weight < min_dist:
                min_dist = weight
                best_i = i

        word_start = starts[best_i]
        prev_ends = [e for e in ends if e <= word_start]
        if prev_ends:
            gap = max(0.0, word_start - max(prev_ends))
            lead = min(max_lead, gap / 2.0) if gap > 0.05 else 0.0
        else:
            lead = min(max_lead, word_start / 2.0) if word_start > 0.05 else 0.0
        new_start = max(0.0, word_start - lead)

    # END: snap to the nearest word end, favoring sentence or clause completions
    new_end = float(end)
    # Adaptive lookahead: if candidate is mid-clause, search forward up to 3.5s
    # (bounded by max_duration) to keep punchlines and full sentences intact.
    max_lookahead = max(0.8, min(3.5, max_duration - (new_end - new_start)))
    end_candidates = [
        i for i, e in enumerate(ends)
        if (e >= new_end and (e - new_end) <= search_window + max_lookahead) or
           (e < new_end and (new_end - e) <= search_window)
    ]
    if end_candidates:
        best_end_i = end_candidates[0]
        min_end_dist = float("inf")
        for i in end_candidates:
            w_text = words[i].get("w", "")
            e_val = ends[i]
            dist = abs(e_val - new_end)
            # Bonus for sentence end punctuation or pause after word
            has_pause_after = False
            if i + 1 < n_words:
                next_s = starts[i + 1]
                has_pause_after = (next_s - e_val >= 0.35)
            else:
                has_pause_after = True

            weight = dist
            if _is_sentence_terminal(w_text):
                weight -= 2.2  # Decisive bonus for complete sentences and punchlines
            elif _is_clause_terminal(w_text):
                weight -= 1.0
            elif has_pause_after:
                weight -= 0.8
            else:
                # Active speech continuation - penalize severing an unfinished phrase
                weight += 2.0

            if _is_conjunction_or_filler(w_text):
                weight += 1.5  # Never end on unfinished conjunctions ("and", "so", "but")

            if weight < min_end_dist:
                min_end_dist = weight
                best_end_i = i

        word_end = ends[best_end_i]
        next_starts = [s for s in starts if s >= word_end]
        if next_starts:
            gap = max(0.0, min(next_starts) - word_end)
            tail = min(max_tail, max(0.30, gap * 0.75)) if gap >= 0.30 else min(max_tail, max(0.18, gap))
        else:
            tail = max_tail
        new_end = min(float(video_duration), word_end + tail)

    # REPAIR DURATION BOUNDS WITHOUT CHOPPING WORDS OR PUNCHLINES
    dur = new_end - new_start
    if dur > max_duration:
        target_max = new_start + max_duration
        valid_words = [(i, w) for i, w in enumerate(words) if new_start + min_duration <= float(w.get("e", 0)) <= target_max]
        if valid_words:
            # Find best sentence or clause ending before target_max
            sentence_ends = [(i, w) for i, w in valid_words if _is_sentence_terminal(w.get("w", ""))]
            if sentence_ends:
                chosen_i, chosen_w = sentence_ends[-1]
            else:
                clause_ends = [(i, w) for i, w in valid_words if _is_clause_terminal(w.get("w", ""))]
                chosen_i, chosen_w = clause_ends[-1] if clause_ends else valid_words[-1]

            chosen_e = float(chosen_w.get("e", 0))
            next_s = starts[chosen_i + 1] if chosen_i + 1 < n_words else chosen_e + 1.0
            gap = max(0.0, next_s - chosen_e)
            tail = min(max_tail, max(0.25, gap * 0.75)) if gap >= 0.25 else min(max_tail, gap)
            new_end = min(float(video_duration), chosen_e + tail)
        else:
            return original

    dur = new_end - new_start
    if dur < min_duration:
        target_min = new_start + min_duration
        target_max = new_start + max_duration
        later_words = [(i, w) for i, w in enumerate(words) if target_min <= float(w.get("e", 0)) <= target_max]
        if later_words:
            sentence_ends = [(i, w) for i, w in later_words if _is_sentence_terminal(w.get("w", ""))]
            chosen_i, chosen_w = sentence_ends[0] if sentence_ends else later_words[0]
            chosen_e = float(chosen_w.get("e", 0))
            next_s = starts[chosen_i + 1] if chosen_i + 1 < n_words else chosen_e + 1.0
            gap = max(0.0, next_s - chosen_e)
            tail = min(max_tail, max(0.25, gap * 0.75)) if gap >= 0.25 else min(max_tail, gap)
            new_end = min(float(video_duration), chosen_e + tail)
        else:
            return original

    if new_end <= new_start or new_end - new_start < min_duration:
        return original
    return (round(new_start, 3), round(new_end, 3))


def extract_action_peaks(video_path, duration=None, sample_fps=1.0, threshold=0.45):
    """
    Extract high-energy action intervals (motion peaks and audio spikes/reactions)
    from video using gaming_intelligence detectors.
    Returns list of dicts: [{'start': float, 'end': float, 'intensity': float, 'type': str}]
    """
    if not video_path or not os.path.isfile(video_path):
        return []

    try:
        from gaming_intelligence.frame_sampler import FrameSampler
        from gaming_intelligence.motion_detector import MotionDetector
        from gaming_intelligence.audio_event_detector import AudioEventDetector
    except Exception:
        return []

    try:
        sampler = FrameSampler(target_fps=sample_fps)
        sampled = list(sampler.sample_generator(video_path, end_sec=duration))
        motion_events = MotionDetector().analyze_frames(sampled) if sampled else []
    except Exception:
        motion_events = []

    try:
        audio_events = AudioEventDetector().analyze_audio(video_path)
    except Exception:
        audio_events = []

    if not motion_events and not audio_events:
        return []

    motion_by_sec = {int(round(e["timestamp"])): float(e.get("motion_score", 0.0)) for e in motion_events}
    audio_by_sec = {int(round(e["timestamp"])): float(e.get("peak_score", 0.0)) for e in audio_events}

    all_secs = sorted(set(motion_by_sec.keys()) | set(audio_by_sec.keys()))
    if not all_secs:
        return []

    peaks = []
    current_start = None
    current_end = None
    max_intensity = 0.0
    dominant_type = "action_moment"

    for sec in all_secs:
        m_val = motion_by_sec.get(sec, 0.0)
        a_val = audio_by_sec.get(sec, 0.0)
        composite = 0.55 * m_val + 0.45 * a_val
        is_peak = composite >= threshold or m_val >= 0.70 or a_val >= 0.70

        if is_peak:
            action_type = "action_climax" if (m_val >= 0.65 and a_val >= 0.65) else ("motion_peak" if m_val > a_val else "audio_spike")
            intensity = max(composite, m_val, a_val)
            if current_start is None:
                current_start = sec
                current_end = sec + 1.0
                max_intensity = intensity
                dominant_type = action_type
            else:
                if sec <= current_end + 2.0:
                    current_end = max(current_end, sec + 1.0)
                    if intensity > max_intensity:
                        max_intensity = intensity
                        dominant_type = action_type
                else:
                    peaks.append({
                        "start": round(float(current_start), 2),
                        "end": round(float(current_end), 2),
                        "intensity": round(float(max_intensity), 2),
                        "type": dominant_type
                    })
                    current_start = sec
                    current_end = sec + 1.0
                    max_intensity = intensity
                    dominant_type = action_type

    if current_start is not None:
        peaks.append({
            "start": round(float(current_start), 2),
            "end": round(float(current_end), 2),
            "intensity": round(float(max_intensity), 2),
            "type": dominant_type
        })

    peaks.sort(key=lambda p: p["intensity"], reverse=True)
    return peaks


def fuse_action_peaks_into_windows(windows, action_peaks):
    """
    Attaches overlapping action moments and composite action intensity
    to each candidate scoring window.
    """
    if not windows:
        return windows

    peaks = list(action_peaks or [])

    for w in windows:
        w_start = float(w.get("start", 0))
        w_end = float(w.get("end", 0))

        matching = []
        for p in peaks:
            p_start = float(p.get("start", 0))
            p_end = float(p.get("end", 0))
            overlap = min(w_end, p_end) - max(w_start, p_start)
            if overlap > 0:
                matching.append(p)

        if matching:
            w["action_moments"] = matching[:5]
            w["action_intensity"] = round(max(float(p.get("intensity", 0.0)) for p in matching), 2)
        else:
            w["action_moments"] = []
            w["action_intensity"] = 0.0

    return windows


def generate_clips_from_windows_and_peaks(
    windows, action_peaks, words, video_duration,
    min_clips=1, max_clips=5, min_secs=30.0, max_secs=60.0,
    is_gaming=True
):
    """
    Deterministically generates structured viral clips from candidate windows and action/audio peaks
    when LLM inference times out or is unavailable. Snaps boundaries to word/sentence boundaries.
    """
    if not windows:
        return []

    high_energy_keywords = {
        "omg", "what", "no way", "insane", "crazy", "wow", "kill", "win", "fail",
        "secret", "never", "always", "how", "why", "died", "look", "run", "fast",
        "unbelievable", "huge", "holy", "dude", "bro", "epic", "legendary", "cut", "shot"
    }

    scored_windows = []
    for w in windows:
        w_int = float(w.get("action_intensity", 0.0))
        n_moments = len(w.get("action_moments", []))
        text = str(w.get("text", "")).lower()
        k_hits = sum(1 for k in high_energy_keywords if k in text)
        score = 50 + int(w_int * 35) + min(10, n_moments * 3) + min(5, k_hits * 1)
        scored_windows.append((min(98, score), w))

    scored_windows.sort(key=lambda x: x[0], reverse=True)

    target_count = max(min_clips, min(max_clips, 5))

    # Collect candidate moment seeds from all detected peaks and windows
    candidate_seeds = []
    seen_centers = []

    # First, collect from windows' action moments or standalone action_peaks
    all_peaks = list(action_peaks or [])
    for _, w in scored_windows:
        for m in w.get("action_moments", []):
            if m not in all_peaks:
                all_peaks.append(m)

    all_peaks.sort(key=lambda p: float(p.get("intensity", 0.0)), reverse=True)

    for p in all_peaks:
        p_start = float(p.get("start", 0.0))
        p_end = float(p.get("end", p_start + min_secs))
        center = (p_start + p_end) / 2.0
        # Ensure at least 15s distance between seed centers
        if not any(abs(center - c) < 15.0 for c in seen_centers):
            seen_centers.append(center)
            candidate_seeds.append({
                "center": center,
                "peak_type": p.get("type", "action_climax"),
                "intensity": float(p.get("intensity", 0.8)),
                "window": next((w for _, w in scored_windows if float(w.get("start", 0)) <= center <= float(w.get("end", video_duration))), scored_windows[0][1]),
            })
            if len(candidate_seeds) >= target_count:
                break

    # If still fewer seeds than target_count, backfill from remaining window centers
    if len(candidate_seeds) < target_count:
        for _, w in scored_windows:
            w_start = float(w.get("start", 0.0))
            w_end = float(w.get("end", video_duration))
            center = (w_start + w_end) / 2.0
            if not any(abs(center - c) < 15.0 for c in seen_centers):
                seen_centers.append(center)
                candidate_seeds.append({
                    "center": center,
                    "peak_type": "action_highlight",
                    "intensity": float(w.get("action_intensity", 0.6)),
                    "window": w,
                })
                if len(candidate_seeds) >= target_count:
                    break

    # If video is long enough, split available timeline into segments to hit target_count
    if len(candidate_seeds) < target_count and video_duration > min_secs:
        step = max(min_secs, video_duration / max(1, target_count))
        cur = 0.0
        while cur + min_secs <= video_duration and len(candidate_seeds) < target_count:
            center = cur + min_secs / 2.0
            if not any(abs(center - c) < 15.0 for c in seen_centers):
                seen_centers.append(center)
                candidate_seeds.append({
                    "center": center,
                    "peak_type": "highlight",
                    "intensity": 0.6,
                    "window": scored_windows[0][1],
                })
            cur += step

    raw_clips = []
    default_tags = "#gaming #gameplay #twitch #viralshorts #fyp" if is_gaming else "#shorts #viral #trending #reels"

    for idx, seed in enumerate(candidate_seeds):
        w = seed["window"]
        center = seed["center"]
        peak_type = seed["peak_type"]
        intensity = seed["intensity"]

        desired_duration = min(max_secs, max(min_secs, (min_secs + max_secs) / 2.0))
        raw_start = max(0.0, center - desired_duration / 2.0)
        raw_end = min(video_duration, raw_start + desired_duration)
        if raw_end - raw_start < min_secs:
            raw_start = max(0.0, raw_end - min_secs)

        # Snap to sentence / word boundaries
        snapped_start, snapped_end = snap_clip_to_words(
            raw_start, raw_end, words, video_duration,
            min_duration=min_secs, max_duration=max_secs
        )

        hook = ""
        span_words = [item["w"] for item in words if snapped_start <= item["s"] <= snapped_end]
        if span_words:
            first_words = " ".join(span_words[:6]).strip()
            if len(first_words) > 5:
                hook = first_words.capitalize()

        if not hook:
            hook = f"Wait till the end of this {peak_type.replace('_', ' ')}!"

        if is_gaming:
            title_labels = [
                "Insane Gameplay Clutch",
                "High Speed Action Stunt",
                "Wild Streamer Reaction",
                "Epic Game Physics Moment",
                "Can't Believe This Happened",
            ]
            title = title_labels[idx % len(title_labels)]
        else:
            title = f"Viral Moment #{idx + 1}"

        score_val = 80 + min(18, int(w.get("action_intensity", 0.5) * 15) + (idx % 3))

        raw_clips.append({
            "start": round(snapped_start, 2),
            "end": round(snapped_end, 2),
            "source_window_id": str(w.get("id", f"local_{idx}")),
            "predicted_score": score_val,
            "virality_score": max(7, min(10, int(round(score_val / 10)))),
            "title": title,
            "video_title_for_youtube_short": title,
            "hook": hook,
            "viral_hook_text": hook,
            "video_description_for_tiktok": f"{hook} 🔥 Watch till the end! {default_tags}",
            "video_description_for_instagram": f"{hook}\n\nWhat are your thoughts on this? Drop a comment below! 👇\n\n{default_tags}",
            "why": f"High energy {peak_type.replace('_', ' ')} with audio reaction spike.",
            "caption": hook,
            "hashtags": default_tags.split(),
        })

    deduped = dedupe_overlapping(raw_clips)
    return deduped or raw_clips


def best_cut_around_moment(
    words: list,
    window_len: float,
    event_t: float,
    min_len: float = 15.0,
    max_len: float = 45.0,
    hype_curve: list[float] | None = None,
    audio_energy: list[float] | None = None,
) -> tuple[float, float, float]:
    """Pick the best [start, end] cut inside a window around `event_t`.

    Snaps boundaries to sentence starts/ends or >0.5s silences and scores:
    0.5 * hype + 0.3 * audio_energy + 0.2 * speech_coverage, while ensuring
    `event_t` remains inside [start, end].
    """
    if window_len <= 0:
        return 0.0, 0.0, 0.0

    norm_words = []
    for w in words or []:
        ws = float(w.get("s", w.get("start", 0.0)) if isinstance(w, dict) else getattr(w, "start", 0.0))
        we = float(w.get("e", w.get("end", ws)) if isinstance(w, dict) else getattr(w, "end", ws))
        wt = str(w.get("w", w.get("word", w.get("text", ""))) if isinstance(w, dict) else getattr(w, "text", getattr(w, "word", ""))).strip()
        if wt:
            norm_words.append((ws, we, wt))

    starts = {0.0}
    ends = {round(window_len, 2)}
    if norm_words:
        starts.add(round(max(0.0, norm_words[0][0] - 0.15), 2))
        for idx, (ws, we, wt) in enumerate(norm_words):
            if idx + 1 < len(norm_words):
                next_ws = norm_words[idx + 1][0]
                if wt.endswith((".", "!", "?")) or (next_ws - we) > 0.5:
                    mid = 0.5 * (we + next_ws)
                    ends.add(round(min(window_len, we + 0.25), 2))
                    starts.add(round(max(0.0, next_ws - 0.15), 2))
                    if (next_ws - we) > 0.5:
                        starts.add(round(mid, 2))
                        ends.add(round(mid, 2))
        ends.add(round(min(window_len, norm_words[-1][1] + 0.25), 2))

    cand_starts = sorted(x for x in starts if 0.0 <= x < window_len)
    cand_ends = sorted(x for x in ends if 0.0 < x <= window_len)
    eff_min = min(float(min_len), window_len)
    eff_max = max(eff_min, float(max_len))

    hype_total = sum(max(0.0, float(v)) for v in (hype_curve or [])) or 1e-6
    best: tuple[float, float, float] | None = None

    for st in cand_starts:
        for en in cand_ends:
            dur = en - st
            if dur < eff_min or dur > eff_max or not (st <= event_t <= en):
                continue
            if hype_curve:
                i0 = max(0, int(st))
                i1 = min(len(hype_curve), max(i0 + 1, int(math.ceil(en))))
                hype_val = sum(max(0.0, float(v)) for v in hype_curve[i0:i1]) / hype_total
            else:
                hype_val = 0.5
            if audio_energy:
                e0 = max(0, int(st))
                e1 = min(len(audio_energy), max(e0 + 1, int(math.ceil(en))))
                seg_e = audio_energy[e0:e1]
                energy_val = (sum(seg_e) / len(seg_e)) if seg_e else 0.0
            else:
                energy_val = 0.5
            spoken = sum(max(0.0, min(we, en) - max(ws, st)) for ws, we, _ in norm_words)
            coverage = min(1.0, spoken / max(dur, 1e-6))
            score = 0.5 * hype_val + 0.3 * energy_val + 0.2 * coverage + 0.02 * (dur / eff_max)
            if best is None or score > best[2]:
                best = (st, en, round(score, 4))

    if best is None:
        dur = min(eff_max, window_len)
        st = min(max(event_t - dur * 0.66, 0.0), max(0.0, window_len - dur))
        return round(st, 2), round(st + dur, 2), 0.0
    return best

