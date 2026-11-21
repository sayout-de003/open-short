"""
features.py - Fast in-memory tokenization and hype feature extraction.
Optimized for sub-millisecond per-message processing without regex or allocations.
"""
from __future__ import annotations

import string
from typing import Counter, List, Set, Tuple

# Pre-compiled set of viral gaming hype words, chants, and reaction emotes
HYPE_TOKENS: Set[str] = {
    # Chants & Reaction tokens
    "W", "L", "GG", "POG", "POGGERS", "POGU", "POGCHAMP", "KEKW", "KEK",
    "OMEGALUL", "LUL", "LULW", "PEPEGA", "PEPELAUGH", "MONKAS", "SADGE",
    "LETSGO", "LETSGOOO", "LETSGOOOOO", "HOLY", "NOOO", "NOOOO", "NOWAY",
    "CLIPIT", "CLIPTHAT", "CLIPPED", "CLIP", "INSANE", "LMAO", "LMFAO", "LOL",
    "WTF", "CLUTCH", "OMGG", "OMG", "HEBAITED", "SHEESH", "COOK", "COOKED",
    "HYPE", "YOOOO", "YOO", "WWWW", "WWW", "WW", "BROOO", "BRO", "CRAZY",
    "WASTED", "BUSTED", "RAGDOLL", "GLITCH", "BANGER", "GOAT", "EZ",
    # Hinglish
    "BHAI", "OP", "MAST", "PAGAL", "GAJAB",
    # Emotes & Emojis
    "🔥", "💀", "😱", "🐐", "👑", "🚀", "💥", "🎯", "🎉", "👀", "😂", "🤣", "🤯",
}

HYPE_PHRASES: Tuple[str, ...] = (
    "NO WAY", "CLIP IT", "CLIP THAT", "LETS GO", "LET'S GO", "5 STARS", "FIVE STARS",
)

# Translation table to strip punctuation except hype markers
_PUNCT_TABLE = str.maketrans({c: " " for c in string.punctuation if c not in ("!", "?")})


def tokenize_text(text: str) -> List[str]:
    """Tokenizes text into uppercase words while stripping common punctuation in O(N)."""
    # Quick normalize
    clean = text.translate(_PUNCT_TABLE).upper()
    return clean.split()


def extract_message_features(text: str) -> Tuple[int, int, float, List[str]]:
    """
    Extracts hype features from a single message.
    Returns:
        (hype_token_count, total_tokens, caps_ratio, matched_chants)
    """
    if not text:
        return 0, 0, 0.0, []

    # Calculate caps ratio on alphabetic characters
    alpha_chars = [c for c in text if c.isalpha()]
    total_alpha = len(alpha_chars)
    caps_ratio = (sum(1 for c in alpha_chars if c.isupper()) / total_alpha) if total_alpha > 0 else 0.0

    upper_text = " ".join(text.upper().split())
    tokens = tokenize_text(text)
    total_tokens = len(tokens)
    if not total_tokens:
        return 0, 0, caps_ratio, []

    matched = []
    for phrase in HYPE_PHRASES:
        if phrase in upper_text:
            matched.append(phrase)

    for token in tokens:
        # Normalize repeated Ws (e.g. W, WW, WWW, WWWW) to "W"
        if len(token) >= 1 and all(c == "W" for c in token):
            matched.append("W")
        # Normalize repeated LETSGOOO... to "LETSGO"
        elif len(token) >= 6 and token.startswith("LETSG") and all(c == "O" for c in token[5:]):
            matched.append("LETSGO")
        # Exact match in set (avoids substring false positives)
        elif token in HYPE_TOKENS:
            matched.append(token)

    return len(matched), total_tokens, caps_ratio, matched
