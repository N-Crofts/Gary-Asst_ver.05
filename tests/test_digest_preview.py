from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_preview_html_endpoint():
    r = client.get("/digest/preview")
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    assert "<!DOCTYPE html>" in data["html"]
    assert "Morning Briefing" in data["html"]


def test_preview_json_endpoint():
    r = client.get("/digest/preview.json")
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    assert isinstance(data["meetings"], list)
    assert data["source"] in ("sample", "live")


