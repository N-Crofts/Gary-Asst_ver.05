import os
from fastapi.testclient import TestClient

from app.main import app
from app.rendering.digest_renderer import render_digest_html
from app.data.sample_digest import SAMPLE_MEETINGS


client = TestClient(app)


def test_get_digest_default_renders_json():
    r = client.get("/digest/send")
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    assert data["action"] == "rendered"
    assert data["driver"] in ("console", "smtp", "sendgrid")


def test_post_send_true_console_driver_returns_sent(monkeypatch):
    monkeypatch.setenv("MAIL_DRIVER", "console")
    r = client.post("/digest/send", json={"send": True, "source": "sample"})
    assert r.status_code == 200
    data = r.json()
    assert data["action"] == "sent"
    assert isinstance(data.get("recipients"), list)


def test_render_contains_links_headings():
    html = render_digest_html(
        {
            "request": None,
            "meetings": SAMPLE_MEETINGS,
            "exec_name": "Biz Dev",
            "date_human": "Mon, Sep 8, 2025",
            "current_year": "2025",
        }
    )
    assert html.count("<a ") >= 3
    assert "Talking points" in html
    assert "Smart questions" in html


def test_missing_env_for_smtp(monkeypatch):
    monkeypatch.setenv("MAIL_DRIVER", "smtp")
    # Clear SMTP_HOST/SMTP_PORT to simulate missing config
    monkeypatch.delenv("SMTP_HOST", raising=False)
    monkeypatch.delenv("SMTP_PORT", raising=False)
    r = client.post("/digest/send", json={"send": True})
    assert r.status_code == 503
    assert "SMTP" in r.json()["detail"]


def test_recipient_override_ignored_by_default(monkeypatch):
    monkeypatch.setenv("ALLOW_RECIPIENT_OVERRIDE", "false")
    r = client.post("/digest/send", json={"recipients": ["bad@example.com"]})
    assert r.status_code == 400
    assert "override" in r.json()["detail"].lower()


def test_recipient_override_invalid_email_returns_400(monkeypatch):
    monkeypatch.setenv("ALLOW_RECIPIENT_OVERRIDE", "true")
    r = client.post("/digest/send", json={"recipients": ["not-an-email"]})
    assert r.status_code == 422  # Pydantic validation error for EmailStr


def test_source_sample_and_live_fallback(monkeypatch):
    # sample returns rendered
    r1 = client.post("/digest/send", json={"source": "sample"})
    assert r1.status_code == 200
    assert r1.json()["source"] == "sample"

    # live currently falls back to sample in our placeholder
    r2 = client.post("/digest/send", json={"source": "live"})
    assert r2.status_code == 200
    assert r2.json()["source"] == "live"


