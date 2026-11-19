"""
tests/test_api_templates_and_context.py - Test suite for /api/templates and content classification endpoints.
"""
import pytest
from starlette.testclient import TestClient
from app import app


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


def test_api_config_profiles(client):
    resp = client.get("/api/config")
    assert resp.status_code == 200
    data = resp.json()
    assert "profiles" in data
    profiles = data["profiles"]
    assert "auto" in profiles
    assert "gaming" in profiles
    assert "educational" in profiles
    assert "podcast" in profiles


def test_list_templates(client):
    resp = client.get("/api/templates")
    assert resp.status_code == 200
    data = resp.json()
    assert "templates" in data
    templates = data["templates"]
    assert len(templates) >= 30

    # Filter by category
    resp_gaming = client.get("/api/templates?category=gaming")
    assert resp_gaming.status_code == 200
    gaming_tmpls = resp_gaming.json()["templates"]
    assert len(gaming_tmpls) >= 6
    for t in gaming_tmpls:
        assert t["category"] == "gaming"


def test_get_single_template(client):
    resp = client.get("/api/templates/gaming_cinematic")
    assert resp.status_code == 200
    tmpl = resp.json()
    assert tmpl["id"] == "gaming_cinematic"
    assert tmpl["name"] == "Gaming Cinematic"
    assert tmpl["layout"] == "gameplay_center"
    assert tmpl["is_builtin"] is True

    # 404 for unknown
    resp_404 = client.get("/api/templates/unknown_template_123")
    assert resp_404.status_code == 404


def test_template_crud_endpoints(client):
    new_template = {
        "id": "test_e2e_template",
        "name": "E2E Template Test",
        "category": "education",
        "style": "step_by_step",
        "layout": "split",
        "caption_preset": "bullet",
        "transition_preset": "slide",
        "audio_preset": "voice",
        "aspect_ratios": ["9:16"],
        "duration_range": [15, 60],
        "effects": ["zoom"],
    }
    # Create
    resp_create = client.post("/api/templates", json=new_template)
    assert resp_create.status_code == 200
    assert resp_create.json()["success"] is True

    # Get
    resp_get = client.get("/api/templates/test_e2e_template")
    assert resp_get.status_code == 200
    assert resp_get.json()["name"] == "E2E Template Test"

    # Delete
    resp_del = client.delete("/api/templates/test_e2e_template")
    assert resp_del.status_code == 200

    # Verify deleted
    resp_del_verify = client.get("/api/templates/test_e2e_template")
    assert resp_del_verify.status_code == 404


def test_classify_endpoint(client):
    payload = {
        "title": "Insane GTA 6 High Speed Police Pursuit and Stunts",
        "duration": 420.0,
    }
    resp = client.post("/api/content/classify", json=payload)
    assert resp.status_code == 200
    res = resp.json()
    assert res["primary_profile"] == "gaming"
    assert res["confidence"] >= 0.70
    assert len(res["evidence"]) > 0
