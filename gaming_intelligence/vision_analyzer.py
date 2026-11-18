"""
vision_analyzer.py - Local vision analysis using Moondream 2 / Ollama Vision or CV heuristics.
"""
from __future__ import annotations

import base64
import os
from typing import Dict, List, Optional
import httpx


class VisionAnalyzer:
    """Analyzes candidate keyframes to provide semantic descriptions and visual scores."""

    def __init__(
        self,
        ollama_url: Optional[str] = None,
        vision_model: str = "moondream",
        timeout: float = 30.0,
    ):
        self.ollama_url = (ollama_url or os.getenv("LLM_BASE_URL") or "http://localhost:11434/v1").rstrip("/")
        # If /v1 is on the URL, normalize to Ollama base for native API or keep for chat
        if self.ollama_url.endswith("/v1"):
            self.api_base = self.ollama_url[:-3]
        else:
            self.api_base = self.ollama_url
        self.vision_model = os.getenv("VISION_MODEL") or vision_model
        self.timeout = timeout

    def is_vision_model_available(self) -> bool:
        """Checks if local vision model is installed in Ollama."""
        try:
            r = httpx.get(f"{self.api_base}/api/tags", timeout=3.0)
            if r.status_code == 200:
                models = [m.get("name", "") for m in r.json().get("models", [])]
                for m in models:
                    if self.vision_model in m or "moondream" in m:
                        return True
        except Exception:
            pass
        return False

    def describe_frame(self, image_path: str, prompt: str = "Describe what is happening in this video frame.") -> Dict[str, any]:
        """
        Sends frame to local vision model (Moondream) or falls back to heuristic tagging.
        """
        if not os.path.exists(image_path):
            return {"description": "", "confidence": 0.0, "source": "none"}

        # Attempt Ollama vision call
        try:
            with open(image_path, "rb") as f:
                img_b64 = base64.b64encode(f.read()).decode("utf-8")

            payload = {
                "model": self.vision_model,
                "prompt": prompt,
                "images": [img_b64],
                "stream": False,
            }
            resp = httpx.post(f"{self.api_base}/api/generate", json=payload, timeout=self.timeout)
            if resp.status_code == 200:
                data = resp.json()
                desc = data.get("response", "").strip()
                return {
                    "description": desc,
                    "confidence": 0.85,
                    "source": self.vision_model,
                }
        except Exception:
            pass

        # Heuristic fallback if local vision model is unavailable or busy
        return self._heuristic_frame_summary(image_path)

    def _heuristic_frame_summary(self, image_path: str) -> Dict[str, any]:
        """Fast fallback summary using basic image metrics."""
        import cv2
        img = cv2.imread(image_path)
        if img is None:
            return {"description": "frame", "confidence": 0.1, "source": "heuristic"}

        h, w = img.shape[:2]
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        brightness = float(gray.mean())
        contrast = float(gray.std())
        edges = float(cv2.Canny(gray, 100, 200).mean())

        tags = []
        if edges > 25.0:
            tags.append("high visual detail/action")
        if contrast > 50.0:
            tags.append("dynamic lighting")
        if brightness < 30.0:
            tags.append("dark scene")
        elif brightness > 200.0:
            tags.append("bright flash/scene")

        desc = f"Visual elements: {', '.join(tags) if tags else 'standard scene'} (contrast {contrast:.1f})"
        return {
            "description": desc,
            "confidence": 0.5,
            "source": "heuristic_cv",
            "metrics": {"brightness": brightness, "contrast": contrast, "edges": edges}
        }
