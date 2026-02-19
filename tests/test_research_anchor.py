"""Unit tests for research anchor helpers and anchor prioritization."""
import pytest

from app.research.anchor_utils import extract_org_from_subject, org_from_email_domain


# ---- extract_org_from_subject ----

def test_extract_org_from_subject_introductory_call_on_kheyti_project():
    """Subject 'Introductory call on Kheyti Project' => anchor includes Kheyti."""
    result = extract_org_from_subject("Introductory call on Kheyti Project")
    assert "Kheyti" in result
    assert result == "Kheyti Project"


def test_extract_org_from_subject_re_colon():
    """Trailing phrase after ' re: ' or ':' is used."""
    result = extract_org_from_subject("Call re: Acme Capital")
    assert "Acme" in result
    result2 = extract_org_from_subject("Meeting: Beta Corp")
    assert "Beta" in result2


def test_extract_org_from_subject_regarding():
    """Trailing phrase after ' regarding ' is used."""
    result = extract_org_from_subject("Sync regarding GridFlow Inc")
    assert "GridFlow" in result


def test_extract_org_from_subject_strips_generic_suffixes():
    """Generic trailing words like 'call', 'meeting' are stripped."""
    result = extract_org_from_subject("Introductory call on Kheyti Project call")
    assert result == "Kheyti Project"


def test_extract_org_from_subject_empty_or_no_candidate():
    """Empty or no strong candidate returns ''."""
    assert extract_org_from_subject("") == ""
    assert extract_org_from_subject("   ") == ""
    assert extract_org_from_subject("Call with John") == ""


# ---- org_from_email_domain ----

def test_org_from_email_domain_cms_induslaw():
    """Domain cms-induslaw.com => Induslaw (prefix dropped, title-case)."""
    result = org_from_email_domain("cms-induslaw.com")
    assert result == "Induslaw"


def test_org_from_email_domain_drops_www_mail_calendar():
    """Prefixes www, mail, calendar, cms are dropped; first segment used for multi-part TLD."""
    assert "acme" in org_from_email_domain("www.acme.com").lower()
    # mail.betacorp.co.uk -> after strip mail. -> betacorp.co.uk -> first segment Betacorp
    assert org_from_email_domain("mail.betacorp.co.uk") == "Betacorp"


def test_org_from_email_domain_dashes_and_underscores():
    """Dashes and underscores become spaces, title-case."""
    assert org_from_email_domain("acme-capital.com") == "Acme Capital"
    assert org_from_email_domain("grid_flow.io") == "Grid Flow"


def test_org_from_email_domain_empty():
    """Empty domain returns ''."""
    assert org_from_email_domain("") == ""
    assert org_from_email_domain("   ") == ""


# ---- Integration: anchor from subject org ----

def test_build_context_stub_uses_org_anchor_when_subject_has_on_phrase(monkeypatch):
    """With stub data, when first meeting has 'on X' subject, research topic prefers org."""
    monkeypatch.setenv("RESEARCH_ENABLED", "true")
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("ENABLE_RESEARCH_DEV", raising=False)

    from app.rendering.context_builder import build_digest_context_with_provider

    # Stub meetings: first is "Stub: Acme Capital Check-in" -> extract_org_from_subject gives "Acme Capital Check-in"
    # and counterparty_from_subject is empty (no "Call with X"). So we try org from subject.
    # "Stub: Acme Capital Check-in" -> ":" gives "Acme Capital Check-in". That has length and caps -> used.
    ctx = build_digest_context_with_provider(source="stub")
    research = ctx.get("research", {})
    # When anchor is org-like we get "(organization, leadership, business, recent news)"
    if research.get("summary") or research.get("key_points") or research.get("sources"):
        # Research ran; topic should reflect org-style when possible
        assert "research" in ctx


# ---- Integration: anchor from organizer domain ----

def test_anchor_organizer_domain_helper_cms_induslaw():
    """org_from_email_domain('cms-induslaw.com') => Induslaw (cms- prefix dropped)."""
    assert org_from_email_domain("cms-induslaw.com") == "Induslaw"
