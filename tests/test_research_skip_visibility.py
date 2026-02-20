"""
Tests for dev-only UI visibility of per-meeting research skips.
"""
import os
from unittest.mock import patch, MagicMock
import pytest

from app.rendering.digest_renderer import render_digest_html
from app.rendering.plaintext import render_plaintext
from app.research.provider import StubResearchProvider
from app.research.trace import ResearchOutcome, SkipReason


def test_research_skip_visible_in_dev_html():
    """Test that research skip reason is visible in HTML when in development mode."""
    with patch.dict(os.environ, {
        "APP_ENV": "development",
        "ENABLE_RESEARCH_DEV": "true",
    }, clear=False):
        context = {
            "meetings": [
                {
                    "subject": "Call with External Person",
                    "start_time": "2025-09-08T10:00:00-04:00",
                    "context_summary": None,
                    "news": [],
                    "strategic_angles": [],
                    "high_leverage_questions": [],
                    "industry_signal": None,
                    "research_trace": {
                        "outcome": ResearchOutcome.SKIPPED.value,
                        "skip_reason": SkipReason.LOW_CONFIDENCE_ANCHOR.value,
                    },
                },
            ],
            "date_human": "Monday, Sep 8, 2025",
            "exec_name": "Test User",
            "app_env": "development",
            "enable_research_dev": True,
        }
        
        html = render_digest_html(context)
        
        # Should contain dev-only anchor diagnostics and skip reason in dev mode
        assert "[Dev]" in html
        assert SkipReason.LOW_CONFIDENCE_ANCHOR.value in html


def test_research_skip_hidden_in_prod_html():
    """Test that research skip reason is NOT visible in HTML when not in development."""
    with patch.dict(os.environ, {
        "APP_ENV": "production",
        "ENABLE_RESEARCH_DEV": "false",
    }, clear=False):
        context = {
            "meetings": [
                {
                    "subject": "Call with External Person",
                    "start_time": "2025-09-08T10:00:00-04:00",
                    "context_summary": None,
                    "news": [],
                    "strategic_angles": [],
                    "high_leverage_questions": [],
                    "industry_signal": None,
                    "research_trace": {
                        "outcome": ResearchOutcome.SKIPPED.value,
                        "skip_reason": SkipReason.LOW_CONFIDENCE_ANCHOR.value,
                    },
                },
            ],
            "date_human": "Monday, Sep 8, 2025",
            "exec_name": "Test User",
            "app_env": "production",
            "enable_research_dev": False,
        }
        
        html = render_digest_html(context)
        
        # Should NOT contain dev-only diagnostics or skip reason in prod mode
        assert "[Dev]" not in html


def test_research_skip_visible_in_dev_plaintext():
    """Test that research skip reason is visible in plaintext when in development mode."""
    with patch.dict(os.environ, {
        "APP_ENV": "development",
        "ENABLE_RESEARCH_DEV": "true",
    }, clear=False):
        context = {
            "meetings": [
                {
                    "subject": "Call with External Person",
                    "start_time": "2025-09-08T10:00:00-04:00",
                    "context_summary": None,
                    "news": [],
                    "strategic_angles": [],
                    "high_leverage_questions": [],
                    "industry_signal": None,
                    "research_trace": {
                        "outcome": ResearchOutcome.SKIPPED.value,
                        "skip_reason": SkipReason.NO_ANCHOR.value,
                    },
                },
            ],
            "date_human": "Monday, Sep 8, 2025",
            "exec_name": "Test User",
            "app_env": "development",
            "enable_research_dev": True,
        }
        
        plaintext = render_plaintext(context)
        
        # Should contain dev-only anchor diagnostics and skip reason in dev mode
        assert "[Dev]" in plaintext
        assert SkipReason.NO_ANCHOR.value in plaintext


def test_research_skip_hidden_when_context_present():
    """Test that research skip reason is NOT shown when meeting has context."""
    with patch.dict(os.environ, {
        "APP_ENV": "development",
        "ENABLE_RESEARCH_DEV": "true",
    }, clear=False):
        context = {
            "meetings": [
                {
                    "subject": "Call with External Person",
                    "start_time": "2025-09-08T10:00:00-04:00",
                    "context_summary": "Some context",
                    "news": [],
                    "strategic_angles": [],
                    "high_leverage_questions": [],
                    "industry_signal": None,
                    "research_trace": {
                        "outcome": ResearchOutcome.SKIPPED.value,
                        "skip_reason": SkipReason.LOW_CONFIDENCE_ANCHOR.value,
                    },
                },
            ],
            "date_human": "Monday, Sep 8, 2025",
            "exec_name": "Test User",
            "app_env": "development",
            "enable_research_dev": True,
        }
        
        html = render_digest_html(context)
        
        # Dev diagnostics are shown for every meeting in dev (including when context present)
        assert "[Dev]" in html


def test_research_error_visible_in_dev():
    """Test that research error is visible in dev mode."""
    with patch.dict(os.environ, {
        "APP_ENV": "development",
        "ENABLE_RESEARCH_DEV": "true",
    }, clear=False):
        context = {
            "meetings": [
                {
                    "subject": "Call with External Person",
                    "start_time": "2025-09-08T10:00:00-04:00",
                    "context_summary": None,
                    "news": [],
                    "strategic_angles": [],
                    "high_leverage_questions": [],
                    "industry_signal": None,
                    "research_trace": {
                        "outcome": ResearchOutcome.ERROR.value,
                    },
                },
            ],
            "date_human": "Monday, Sep 8, 2025",
            "exec_name": "Test User",
            "app_env": "development",
            "enable_research_dev": True,
        }
        
        html = render_digest_html(context)
        plaintext = render_plaintext(context)
        
        # Should contain dev diagnostics and error outcome in dev mode
        assert "[Dev]" in html
        assert "outcome=error" in html
        assert "[Dev]" in plaintext
        assert "outcome=error" in plaintext
