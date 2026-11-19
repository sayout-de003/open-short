"""Unit tests for content_classifier.py"""
from content_classifier import detect_content_type


def test_detect_gta_gaming():
    res = detect_content_type(title="GTA 6 Gameplay Walkthrough Part 1 - First Mission & Police Chase")
    assert res["profile"] == "gaming"
    assert res["confidence"] >= 0.70

    res2 = detect_content_type(title="INSANE 5 STAR POLICE ESCAPE in Grand Theft Auto 5!")
    assert res2["profile"] == "gaming"


def test_detect_podcast():
    res = detect_content_type(title="The Joe Rogan Experience #2100 - Deep Conversation with Guest")
    assert res["profile"] == "podcast"
    assert res["confidence"] >= 0.70

    res2 = detect_content_type(title="Lex Fridman Podcast Episode 450 Interview with Sam Altman")
    assert res2["profile"] == "podcast"


def test_detect_educational():
    res = detect_content_type(title="Python Full Course for Beginners - Step by Step Tutorial")
    assert res["profile"] == "educational"
    assert res["confidence"] >= 0.70

    res2 = detect_content_type(title="Quantum Physics Explained in 10 Minutes")
    assert res2["profile"] == "educational"


def test_detect_category_override():
    res = detect_content_type(title="Playing with friends", category="20")
    assert res["profile"] == "gaming"

    res2 = detect_content_type(title="How the universe works", category="27")
    assert res2["profile"] == "educational"


def test_fallback_ambiguous():
    res = detect_content_type(title="2026-11-19 10-00-00", duration=600)
    assert res["profile"] in ("generic", "gaming")
