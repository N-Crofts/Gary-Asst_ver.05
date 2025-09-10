from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_api_key_guard_blocks_when_configured(monkeypatch):
    monkeypatch.setenv("API_KEY", "secret123")
    r = client.get("/digest/preview")
    assert r.status_code == 401
    assert "api key" in r.json()["detail"].lower()

    r2 = client.get("/digest/preview", headers={"x-api-key": "secret123"})
    assert r2.status_code == 200
    # The preview endpoint now returns HTML by default, so check content type
    assert r2.headers["content-type"].startswith("text/html")


