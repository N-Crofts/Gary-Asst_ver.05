from fastapi.testclient import TestClient
from app.main import app


client = TestClient(app)


def test_health_ok():
    r = client.get("/")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_digest_send_returns_html():
    r = client.post("/digest/send")
    assert r.status_code == 200
    data = r.json()
    assert data.get("ok") is True
    html = data.get("html", "")
    # Basic shape checks
    assert isinstance(html, str) and len(html) > 100
    # Sanity checks against our stub template/content
    assert "<!DOCTYPE html>" in html
    assert "Morning Briefing" in html
    assert "Acme Capital" in html
    assert "Talking points" in html
    assert "Smart questions" in html
