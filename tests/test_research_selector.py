"""Tests for research selector and dev guard (should_run_research)."""
import pytest

from app.research.selector import (
    should_run_research,
    is_research_effectively_enabled,
    select_research_provider,
)
from app.research.provider import StubResearchProvider


# ---- should_run_research() matrix ----

def test_should_run_research_dev_enable_dev_false_returns_false(monkeypatch):
    """dev + ENABLE_RESEARCH_DEV=false => false."""
    monkeypatch.setenv("RESEARCH_ENABLED", "true")
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("ENABLE_RESEARCH_DEV", "false")
    allowed, reason = should_run_research()
    assert allowed is False
    assert reason == "dev_guard"


def test_should_run_research_dev_enable_dev_true_returns_true(monkeypatch):
    """dev + ENABLE_RESEARCH_DEV=true (and research_enabled) => true."""
    monkeypatch.setenv("RESEARCH_ENABLED", "true")
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("ENABLE_RESEARCH_DEV", "true")
    allowed, reason = should_run_research()
    assert allowed is True
    assert reason is None


def test_should_run_research_prod_research_enabled_true_returns_true(monkeypatch):
    """prod + RESEARCH_ENABLED=true => true."""
    monkeypatch.setenv("RESEARCH_ENABLED", "true")
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("ENABLE_RESEARCH_DEV", raising=False)
    allowed, reason = should_run_research()
    assert allowed is True
    assert reason is None


def test_should_run_research_prod_research_enabled_false_returns_false(monkeypatch):
    """prod + RESEARCH_ENABLED=false => false."""
    monkeypatch.setenv("RESEARCH_ENABLED", "false")
    monkeypatch.setenv("APP_ENV", "production")
    allowed, reason = should_run_research()
    assert allowed is False
    assert reason == "disabled"


def test_should_run_research_disabled_reason(monkeypatch):
    """RESEARCH_ENABLED not truthy => (False, 'disabled')."""
    monkeypatch.setenv("RESEARCH_ENABLED", "false")
    monkeypatch.setenv("APP_ENV", "production")
    allowed, reason = should_run_research()
    assert allowed is False
    assert reason == "disabled"


def test_should_run_research_app_env_fallback_to_environment(monkeypatch):
    """APP_ENV takes precedence; fallback to ENVIRONMENT then development."""
    monkeypatch.setenv("RESEARCH_ENABLED", "true")
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.delenv("ENABLE_RESEARCH_DEV", raising=False)
    allowed, _ = should_run_research()
    assert allowed is True

    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.delenv("ENABLE_RESEARCH_DEV", raising=False)
    allowed, reason = should_run_research()
    assert allowed is False
    assert reason == "dev_guard"


# ---- is_research_effectively_enabled (backward compat) ----

def test_is_research_effectively_enabled_mirrors_should_run_research(monkeypatch):
    """is_research_effectively_enabled() == should_run_research()[0]."""
    monkeypatch.setenv("RESEARCH_ENABLED", "true")
    monkeypatch.setenv("APP_ENV", "production")
    assert is_research_effectively_enabled() is True

    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("ENABLE_RESEARCH_DEV", "false")
    assert is_research_effectively_enabled() is False


# ---- select_research_provider ----

def test_select_provider_returns_stub_when_not_allowed(monkeypatch):
    """When should_run_research is False, select_research_provider returns StubResearchProvider."""
    monkeypatch.setenv("RESEARCH_ENABLED", "true")
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("ENABLE_RESEARCH_DEV", "false")
    provider = select_research_provider()
    assert isinstance(provider, StubResearchProvider)


def test_select_provider_returns_stub_when_research_enabled_false(monkeypatch):
    """When RESEARCH_ENABLED=false, select_research_provider returns StubResearchProvider."""
    monkeypatch.setenv("RESEARCH_ENABLED", "false")
    monkeypatch.setenv("APP_ENV", "production")
    provider = select_research_provider()
    assert isinstance(provider, StubResearchProvider)
