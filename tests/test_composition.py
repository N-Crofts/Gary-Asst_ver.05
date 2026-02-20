from datetime import datetime

from app.data.sample_digest import SAMPLE_MEETINGS
from app.rendering.composer import compose_digest_model, truncate, safe_join
from app.rendering.digest_renderer import render_digest_html


def test_compose_digest_includes_required_keys():
    ctx = compose_digest_model(SAMPLE_MEETINGS, exec_name="RPCK Biz Dev", now=datetime(2025, 9, 8))
    assert set(["date_human", "current_year", "exec_name", "meetings"]).issubset(set(ctx.keys()))
    assert ctx["date_human"].startswith("Mon, Sep 8, 2025")
    assert ctx["current_year"] == "2025"
    assert isinstance(ctx["meetings"], list)
    m = ctx["meetings"][0]
    for key in ["subject", "start_time", "attendees", "news", "talking_points", "smart_questions"]:
        assert key in m


def test_render_digest_markers_and_links_count():
    ctx = compose_digest_model(SAMPLE_MEETINGS, exec_name="RPCK Biz Dev", now=datetime(2025, 9, 8))
    html = render_digest_html({"request": None, **ctx})
    assert "Context Snapshot" in html
    assert "Recent developments" in html
    assert html.count('<a ') >= 3


def test_helpers_truncate_and_safe_join():
    assert truncate("abcdef", 3) == "ab…"
    assert truncate("ab", 3) == "ab"
    assert safe_join(["<a>", "&"], "; ") == "&lt;a&gt;; &amp;"


