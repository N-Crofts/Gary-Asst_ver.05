import os
from unittest.mock import patch

from app.enrichment.service import enrich_meetings


SAMPLE_MEETING = {
    "subject": "RPCK × Acme Capital — Portfolio Strategy Check-in",
    "start_time": "9:30 AM ET",
    "location": "Zoom",
    "attendees": [
        {"name": "Chintan Panchal", "title": "Managing Partner", "company": "RPCK"},
        {"name": "Carolyn", "title": "Chief of Staff", "company": "RPCK"},
        {"name": "A. Rivera", "title": "Partner", "company": "Acme Capital"}
    ],
    "company": {"name": "Acme Capital"}
}


def test_enrichment_disabled_returns_input_unmodified(monkeypatch):
    monkeypatch.setenv("ENRICHMENT_ENABLED", "false")
    out = enrich_meetings([SAMPLE_MEETING])
    assert len(out) == 1
    m = out[0]
    # When disabled, we don't attach extra items; fields exist but empty
    assert m.subject == SAMPLE_MEETING["subject"]
    assert m.news == []


def test_enrichment_enabled_attaches_fields(monkeypatch):
    monkeypatch.setenv("ENRICHMENT_ENABLED", "true")
    out = enrich_meetings([SAMPLE_MEETING])
    assert len(out) == 1
    m = out[0]
    assert len(m.news) >= 1
    assert len(m.talking_points) >= 1
    assert len(m.smart_questions) >= 1
    assert m.company is not None
    assert m.company.name.lower().startswith("acme")


def test_enrichment_timebox(monkeypatch):
    monkeypatch.setenv("ENRICHMENT_ENABLED", "true")
    monkeypatch.setenv("ENRICHMENT_TIMEOUT_MS", "1")  # 1ms budget to force early cutoff

    many = [dict(SAMPLE_MEETING, subject=f"Meeting {i}") for i in range(100)]

    with patch("time.perf_counter") as mock_clock:
        mock_clock.side_effect = [0.0, 0.01, 0.02, 0.03]  # advance quickly
        out = enrich_meetings(many, now=0.0, timeout_s=0.001)
        # Should have processed at least one, but not all 100
        assert 1 <= len(out) < 100


