"""
transcript_analyzer.py - Analyzes speech transcripts using local LLM (Qwen3 1.7B).
"""
from __future__ import annotations

import json
import os
import re
from typing import Dict, List, Optional
import httpx


class TranscriptAnalyzer:
    """Evaluates speech transcripts for engaging moments, questions, drama, and stories."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        model_name: str = "qwen3:1.7b",
        timeout: float = 60.0,
    ):
        self.base_url = (base_url or os.getenv("LLM_BASE_URL") or "http://localhost:11434/v1").rstrip("/")
        self.model_name = os.getenv("LLM_MODEL") or model_name
        self.timeout = timeout

    def score_transcript_segments(
        self, segments: List[Dict[str, any]], mode: str = "gaming"
    ) -> List[Dict[str, any]]:
        """
        Takes list of {'start': float, 'end': float, 'text': str}.
        Assigns viral transcript scores [0.0, 1.0].
        """
        if not segments:
            return []

        # If LLM endpoint is active, query it in small batches
        try:
            return self._llm_score(segments, mode)
        except Exception as e:
            # Fallback to deterministic NLP heuristic scoring
            return self._heuristic_score(segments)

    def _llm_score(self, segments: List[Dict[str, any]], mode: str) -> List[Dict[str, any]]:
        results = []
        batch_text = "\n".join(
            [f"[{i}] ({s['start']:.1f}s - {s['end']:.1f}s): {s.get('text', '').strip()}"
             for i, s in enumerate(segments[:15])]  # process up to 15 at once for small models
        )

        prompt = (
            f"You are a short-form video editor specializing in {mode} content. "
            "Rate each segment below on a scale of 0 to 10 for audience engagement and viral clip potential. "
            "Return JSON only in this format: {\"scores\": [{\"index\": 0, \"score\": 7, \"hook\": \"catchy title\"}]}\n\n"
            f"Segments:\n{batch_text}"
        )

        url = f"{self.base_url}/chat/completions"
        payload = {
            "model": self.model_name,
            "messages": [
                {"role": "system", "content": "You output valid JSON only."},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.2,
            "stream": False,
        }

        resp = httpx.post(url, json=payload, timeout=self.timeout)
        if resp.status_code == 200:
            content = resp.json()["choices"][0]["message"]["content"]
            # Extract JSON block
            match = re.search(r"\{.*\}", content, re.DOTALL)
            if match:
                data = json.loads(match.group(0))
                score_map = {item["index"]: item for item in data.get("scores", [])}
                for i, s in enumerate(segments):
                    scored = score_map.get(i, {})
                    raw_s = float(scored.get("score", 5)) / 10.0
                    results.append({
                        "start": s["start"],
                        "end": s["end"],
                        "text": s.get("text", ""),
                        "transcript_score": min(1.0, max(0.0, raw_s)),
                        "hook": scored.get("hook", "")
                    })
                return results

        return self._heuristic_score(segments)

    def _heuristic_score(self, segments: List[Dict[str, any]]) -> List[Dict[str, any]]:
        """Fast heuristic scoring based on exclamation, questions, and high-energy words."""
        high_energy_words = {
            "omg", "what", "no way", "insane", "crazy", "wow", "kill", "win", "fail",
            "secret", "never", "always", "how", "why", "died", "look", "run", "fast",
            "unbelievable", "huge", "holy", "dude", "bro", "epic", "legendary"
        }
        results = []
        for s in segments:
            text = s.get("text", "").lower()
            score = 0.35  # baseline
            if "?" in text:
                score += 0.2
            if "!" in text:
                score += 0.25
            for w in high_energy_words:
                if w in text:
                    score += 0.15
                    break
            results.append({
                "start": s.get("start", 0.0),
                "end": s.get("end", 0.0),
                "text": s.get("text", ""),
                "transcript_score": min(1.0, round(score, 4)),
                "hook": s.get("text", "")[:40]
            })
        return results
