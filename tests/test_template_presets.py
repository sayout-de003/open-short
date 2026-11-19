"""
tests/test_template_presets.py - Test suite for SQLite TemplateStore and presets CRUD.
"""
import os
import tempfile
import pytest
from template_library.models import TemplateStore, BUILTIN_TEMPLATES


@pytest.fixture
def temp_store():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    store = TemplateStore(db_path=path)
    yield store
    if os.path.exists(path):
        os.remove(path)


def test_seed_builtins(temp_store):
    templates = temp_store.list_templates()
    assert len(templates) >= 30
    categories = {t["category"] for t in templates}
    # Check that key niches are represented
    assert "gaming" in categories
    assert "podcast" in categories
    assert "educational" in categories
    assert "commentary" in categories
    assert "fitness" in categories


def test_get_template(temp_store):
    tmpl = temp_store.get_template("gaming_cinematic")
    assert tmpl is not None
    assert tmpl["name"] == "Gaming Cinematic"
    assert tmpl["category"] == "gaming"
    assert tmpl["layout"] == "gameplay_center"
    assert "impact_zoom" in tmpl["effects"]


def test_filter_by_category(temp_store):
    gaming_tmpls = temp_store.list_templates(category="gaming")
    assert len(gaming_tmpls) >= 6
    for t in gaming_tmpls:
        assert t["category"] == "gaming"


def test_custom_template_crud(temp_store):
    custom_data = {
        "id": "my_custom_preset",
        "name": "My Custom Preset",
        "category": "gaming",
        "style": "custom_action",
        "layout": "stacked_gameplay",
        "caption_preset": "bold_pop",
        "transition_preset": "fast_zoom",
        "audio_preset": "boosted",
        "aspect_ratios": ["9:16"],
        "duration_range": [20.0, 50.0],
        "effects": ["shake"],
    }
    saved = temp_store.save_template(custom_data)
    assert saved["id"] == "my_custom_preset"
    assert saved["is_builtin"] is False

    # Fetch
    fetched = temp_store.get_template("my_custom_preset")
    assert fetched is not None
    assert fetched["name"] == "My Custom Preset"

    # Delete
    deleted = temp_store.delete_template("my_custom_preset")
    assert deleted is True
    assert temp_store.get_template("my_custom_preset") is None


def test_cannot_delete_builtin(temp_store):
    with pytest.raises(ValueError, match="Cannot delete built-in"):
        temp_store.delete_template("gaming_cinematic")
