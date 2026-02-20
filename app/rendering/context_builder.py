import os
import re
import logging
import uuid
import time
from datetime import datetime
from typing import Dict, Any, Literal, Optional, List, Tuple
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from fastapi import HTTPException

from app.calendar.provider import select_calendar_provider
from app.calendar.types import Event, Attendee
from app.data.sample_digest import SAMPLE_MEETINGS, STUB_MEETINGS_RAW_GRAPH
from app.rendering.digest_renderer import _today_et_str, _format_date_et_str, _get_timezone
from app.enrichment.service import enrich_meetings
from app.profile.store import get_profile
from app.memory.service import attach_memory_to_meetings
from app.research.config import (
    MAX_TAVILY_CALLS_PER_REQUEST,
    MAX_RESEARCH_SOURCES,
    ResearchBudget,
    get_confidence_min,
)
from app.research.query_safety import sanitize_research_query, is_query_usable_after_sanitization
from app.research.trace import (
    build_research_trace,
    query_hash_prefix,
    ResearchOutcome,
    SkipReason,
    AnchorType,
    AnchorSource,
)
from app.research.confidence import (
    compute_confidence,
    is_domain_generic,
    is_domain_ambiguous_short,
    is_meeting_like_test,
)
from app.research.anchor_utils import (
    is_consumer_domain,
    domain_to_org_name,
    looks_like_personal_domain,
    looks_like_assistant_domain,
    DOMAIN_ORG_OVERRIDES,
)

logger = logging.getLogger(__name__)


def _normalize_url_for_dedup(url: str) -> str:
    """
    Normalize URL for deduplication: trim, lowercase scheme/host, remove trailing slash.
    Returns normalized string for comparison.
    """
    if not url:
        return ""
    url = url.strip()
    if not url:
        return ""
    url_lower = url.lower()
    # Normalize http/https to http for comparison (treat as equivalent)
    if url_lower.startswith("https://"):
        url_lower = "http://" + url_lower[8:]
    # Remove trailing slash
    if url_lower.endswith("/"):
        url_lower = url_lower[:-1]
    return url_lower


def _dedupe_and_cap_sources(sources: List[Dict[str, Any]], max_items: int = 5) -> List[Dict[str, Any]]:
    """
    Deduplicate sources by normalized URL and cap to max_items (preserve order).
    
    Args:
        sources: List of source dicts with 'title' and 'url' keys
        max_items: Maximum number of sources to return (default 5)
        
    Returns:
        Deduplicated and capped list of sources
    """
    if not sources:
        return []
    seen = set()
    deduped = []
    for s in sources:
        if not isinstance(s, dict):
            continue
        url = s.get("url", "").strip()
        title = s.get("title", "").strip()
        if not url or not title:
            continue
        normalized = _normalize_url_for_dedup(url)
        if normalized and normalized not in seen:
            seen.add(normalized)
            deduped.append({"title": title, "url": url})
            if len(deduped) >= max_items:
                break
    return deduped


def _host_from_url(url: str) -> str:
    """Return lowercase hostname from URL (no port, no path). Empty if parse fails."""
    if not url or not isinstance(url, str):
        return ""
    try:
        parsed = urlparse(url.strip())
        host = (parsed.hostname or "").strip().lower()
        return host
    except Exception:
        return ""


def _result_domain_match_host_based(
    sources: List[Dict[str, Any]], expected_domain: str
) -> Tuple[bool, Optional[str], List[str]]:
    """
    Strict host-based domain match: hostname must equal expected_domain or end with .expected_domain.
    Returns (matched, first_matching_hostname_or_none, top_source_hosts up to 5).
    """
    if not expected_domain or not isinstance(expected_domain, str):
        return False, None, []
    domain_lower = expected_domain.strip().lower()
    if not domain_lower:
        return False, None, []
    hosts: List[str] = []
    first_matching_host: Optional[str] = None
    for s in sources:
        if not isinstance(s, dict):
            continue
        url = (s.get("url") or "").strip()
        host = _host_from_url(url)
        if not host:
            continue
        if len(hosts) < 5:
            hosts.append(host)
        if host == domain_lower or (domain_lower.startswith(".") and host.endswith(domain_lower)) or (
            not domain_lower.startswith(".") and host.endswith("." + domain_lower)
        ):
            if first_matching_host is None:
                first_matching_host = host
    matched = first_matching_host is not None
    return matched, first_matching_host, hosts


def _is_ambiguous_acronym_domain(expected_domain: str) -> bool:
    """True if leftmost segment (e.g. 'smg' from 'smg.com') has length <= 4."""
    if not expected_domain or not isinstance(expected_domain, str):
        return False
    d = expected_domain.strip().lower()
    segment = d.split(".", 1)[0] if "." in d else d
    return len(segment) <= 4


# Negative terms that indicate off-target (e.g. Scotts Miracle-Gro ticker) for ambiguous acronym guardrail
_NEGATIVE_TERMS_AMBIGUOUS = ("scotts", "miracle-gro", "stock", "ticker")


def _negative_term_hit_in_sources(
    research_result: Dict[str, Any],
    terms: Tuple[str, ...] = _NEGATIVE_TERMS_AMBIGUOUS,
    top_n: int = 5,
) -> bool:
    """True if any of the terms appear (case-insensitive) in summary, key_points, or top N source titles."""
    texts: List[str] = []
    summary = (research_result.get("summary") or "").strip()
    if summary:
        texts.append(summary)
    for kp in (research_result.get("key_points") or [])[:top_n]:
        if isinstance(kp, str) and kp.strip():
            texts.append(kp.strip())
    for s in (research_result.get("sources") or [])[:top_n]:
        if isinstance(s, dict):
            t = (s.get("title") or "").strip()
            if t:
                texts.append(t)
    combined = " ".join(texts).lower()
    return any(term in combined for term in terms)


def _entity_match_in_sources(
    research_result: Dict[str, Any],
    anchor_display: str,
    org_display: str,
    top_n: int = 5,
    require_org_for_ambiguous: bool = False,
) -> bool:
    """
    True if anchor_display or org_display appears in top N source titles, summary, or key_points (case-insensitive).
    Used for ambiguous acronym domains to avoid wrong-entity (e.g. SMG ticker vs Service Management Group).
    When require_org_for_ambiguous=True, only org_display is considered (short anchor e.g. "SMG" is ignored).
    """
    texts: List[str] = []
    summary = (research_result.get("summary") or "").strip()
    if summary:
        texts.append(summary)
    for kp in (research_result.get("key_points") or [])[:top_n]:
        if isinstance(kp, str) and kp.strip():
            texts.append(kp.strip())
    sources = research_result.get("sources") or []
    for s in sources[:top_n]:
        if isinstance(s, dict):
            t = (s.get("title") or "").strip()
            if t:
                texts.append(t)
    anchor_lower = (anchor_display or "").strip().lower()
    org_lower = (org_display or "").strip().lower()
    # For ambiguous acronym domains we require full org name; short anchor (e.g. "SMG") must not count
    allow_anchor = not require_org_for_ambiguous or (len((anchor_display or "").strip()) > 4)
    for block in texts:
        bl = block.lower()
        if allow_anchor and anchor_lower and anchor_lower in bl:
            return True
        if org_lower and org_lower in bl:
            return True
    return False


def _compute_meeting_anchor_and_query(
    meeting_data: Dict[str, Any],
    exec_name: str,
    exec_mailbox: Optional[str],
    _domain_from_email,
    _normalize_attendee,
    extract_counterparty_from_subject,
    extract_org_from_subject,
    org_from_email_domain,
    compute_confidence,
    sanitize_research_query,
    is_query_usable_after_sanitization,
    is_domain_generic,
    is_domain_ambiguous_short,
    get_confidence_min,
) -> Optional[Dict[str, Any]]:
    """
    Compute anchor and query for a meeting (person-first). Never returns no_anchor when
    there is at least one external non-consumer domain among attendees; uses domain
    fallback ladder and only returns query_sanitized_empty when sanitization empties the query.

    Returns:
        Dict with chosen_query, anchor_type_str, anchor_source_str, chosen_confidence, primary_domain on success;
        Dict with skip_reason (e.g. query_sanitized_empty) and no chosen_query on failure when domains exist;
        None only when there are zero external non-consumer domains (no_anchor).
    """
    subject = (meeting_data.get("subject") or meeting_data.get("title") or "").strip()
    exec_name_lower = exec_name.strip().lower() if exec_name else ""
    exec_mailbox_lower = (exec_mailbox or "").strip().lower()
    subject_tokens = set(re.findall(r"\w+", subject.lower())) if subject else set()

    anchor = ""
    org_context = ""
    anchor_type_str: Optional[str] = None
    anchor_source_str: Optional[str] = None
    primary_domain = ""
    has_attendee_display_name = False
    person_name_for_fallback = ""
    anchor_from_subject = False

    org = meeting_data.get("organizer")
    org_domain = _domain_from_email(org)
    is_org_external_non_consumer = (
        org_domain and org_domain != "rpck.com" and not is_consumer_domain(org_domain)
    )

    # Build external attendees (non-internal, non-consumer only) and domain counts
    external_attendees: List[Dict[str, Any]] = []
    domain_counts: Dict[str, int] = {}
    for a in meeting_data.get("attendees") or []:
        ad = _normalize_attendee(a)
        if not isinstance(ad, dict):
            continue
        dom = _domain_from_email(ad.get("email") or ad.get("address"))
        if not dom or dom == "rpck.com" or is_consumer_domain(dom):
            continue
        domain_counts[dom] = domain_counts.get(dom, 0) + 1
        display_name = (ad.get("display_name") or ad.get("name") or "").strip()
        if display_name:
            has_attendee_display_name = True
            if not person_name_for_fallback:
                person_name_for_fallback = display_name
        external_attendees.append({"name": display_name, "domain": dom, "data": ad})

    if is_org_external_non_consumer:
        domain_counts[org_domain] = domain_counts.get(org_domain, 0) + 1

    def _domain_score(d: str) -> int:
        """Score domain for primary selection; higher = prefer. Avoids personal/assistant domains."""
        segment = d.split(".", 1)[0].lower().replace("-", "").replace("_", "") if "." in d else d.lower()
        tld = d.split(".")[-1].lower() if "." in d else ""
        count = domain_counts.get(d, 0)
        score = count * 10
        if segment in DOMAIN_ORG_OVERRIDES:
            score += 50
        if looks_like_personal_domain(d):
            score -= 40
        if looks_like_assistant_domain(d):
            score -= 30
        if tld == "org":
            score += 5
        if tld == "com":
            score += 3
        return score

    def _pick_primary_domain() -> str:
        """Choose primary_domain by score (prefer known orgs, avoid personal/assistant); tie-break: organizer, subject, alphabetical."""
        if not domain_counts:
            return primary_domain or ""
        scored = [(d, _domain_score(d)) for d in domain_counts]
        best_score = max(s for _, s in scored)
        candidates = [d for d, s in scored if s == best_score]
        if len(candidates) == 1:
            return candidates[0]
        if is_org_external_non_consumer and org_domain in candidates:
            return org_domain
        for d in sorted(candidates):
            segment = d.split(".", 1)[0].lower() if "." in d else d.lower()
            if segment in subject_tokens:
                return d
        return sorted(candidates)[0]

    if not primary_domain and domain_counts:
        primary_domain = _pick_primary_domain()
    if is_org_external_non_consumer and not primary_domain:
        primary_domain = org_domain

    # Person-first only when exactly one external non-consumer domain AND one such attendee
    external_non_consumer_domain_count = len(domain_counts)
    allow_person_first = (
        external_non_consumer_domain_count == 1 and len(external_attendees) == 1
    )
    is_one_on_one = len(external_attendees) == 1 and external_attendees[0]["name"]

    # a) Counterparty from subject (person anchor) — only when person-first allowed
    counterparty_from_subject = extract_counterparty_from_subject(subject)
    if allow_person_first and counterparty_from_subject and counterparty_from_subject.lower() != exec_name_lower:
        anchor = counterparty_from_subject.strip()
        anchor_type_str = AnchorType.PERSON.value
        anchor_source_str = AnchorSource.SUBJECT_COUNTERPARTY.value
        anchor_from_subject = True
        if not person_name_for_fallback:
            person_name_for_fallback = anchor

    # b) Single external attendee with name (person anchor) — only when person-first allowed
    if not anchor and allow_person_first and is_one_on_one:
        person_data = external_attendees[0]
        person_name = person_data["name"]
        if person_name:
            candidate_lower = person_name.lower()
            if not (exec_name_lower and candidate_lower == exec_name_lower):
                if not exec_mailbox_lower or exec_mailbox_lower not in (candidate_lower or ""):
                    anchor = person_name
                    anchor_type_str = AnchorType.PERSON.value
                    anchor_source_str = AnchorSource.ATTENDEE.value
                    person_domain_org = org_from_email_domain(person_data["domain"])
                    if person_domain_org:
                        org_context = person_domain_org
                    person_name_for_fallback = person_name
                    if not primary_domain:
                        primary_domain = person_data["domain"]

    # c) Org from subject
    if not anchor:
        org_from_subj = extract_org_from_subject(subject)
        if org_from_subj:
            anchor = org_from_subj
            anchor_type_str = AnchorType.ORG.value
            anchor_source_str = AnchorSource.SUBJECT_ORG.value
            anchor_from_subject = True

    # If anchor came only from subject and ALL domains are personal/assistant, avoid wrong-entity: clear anchor
    if anchor and anchor_from_subject and domain_counts:
        all_risky_subject = all(
            looks_like_personal_domain(d) or looks_like_assistant_domain(d)
            for d in domain_counts
        )
        if all_risky_subject:
            anchor = ""
            anchor_type_str = None
            anchor_source_str = None
            anchor_from_subject = False

    # d) Organizer external non-consumer
    if not anchor and is_org_external_non_consumer:
        anchor = org_from_email_domain(org_domain)
        anchor_type_str = AnchorType.DOMAIN.value
        anchor_source_str = AnchorSource.ORGANIZER_DOMAIN.value
        if not primary_domain:
            primary_domain = org_domain

    # e) First external attendee (person or domain); skip when only risky domains (avoid wrong-entity).
    # When multiple external non-consumer domains: use only org/domain anchor, never person name.
    all_risky_for_attendees = all(
        looks_like_personal_domain(d) or looks_like_assistant_domain(d)
        for d in domain_counts
    ) if domain_counts else False
    if not anchor:
        for person_data in external_attendees:
            dom = person_data["domain"]
            if all_risky_for_attendees and (looks_like_personal_domain(dom) or looks_like_assistant_domain(dom)):
                continue
            display_name = person_data["name"]
            candidate_lower = (display_name or "").lower()
            if exec_name_lower and candidate_lower == exec_name_lower:
                continue
            if exec_mailbox_lower and display_name and exec_mailbox_lower in candidate_lower:
                continue
            attendee_org = org_from_email_domain(dom)
            if allow_person_first:
                if display_name:
                    anchor = display_name
                    if attendee_org:
                        org_context = attendee_org
                    anchor_type_str = AnchorType.PERSON.value
                    anchor_source_str = AnchorSource.ATTENDEE.value
                    person_name_for_fallback = display_name
                else:
                    anchor = attendee_org
                    anchor_type_str = AnchorType.DOMAIN.value
                    anchor_source_str = AnchorSource.ATTENDEE.value
            else:
                # Multiple domains: only domain-level anchor; skip personal/assistant domains
                if looks_like_personal_domain(dom) or looks_like_assistant_domain(dom):
                    continue
                if attendee_org:
                    anchor = attendee_org
                    anchor_type_str = AnchorType.DOMAIN.value
                    anchor_source_str = AnchorSource.ATTENDEE.value
            if anchor and not primary_domain:
                primary_domain = dom
            if anchor:
                break

    # Domain fallback: when we have external non-consumer domains but no anchor yet, pick primary and build org query
    if not anchor and domain_counts:
        primary_domain = _pick_primary_domain()
        # Prefer skipping over wrong-entity anchors: if ALL domains are personal-like or assistant-like, do not anchor
        all_risky = all(
            looks_like_personal_domain(d) or looks_like_assistant_domain(d)
            for d in domain_counts
        )
        if not all_risky:
            org_name = domain_to_org_name(primary_domain)
            # Use anchor only if chosen primary is not personal/assistant (scoring already prefers orgs)
            if org_name and not looks_like_personal_domain(primary_domain) and not looks_like_assistant_domain(primary_domain):
                anchor = org_name
                anchor_type_str = AnchorType.DOMAIN.value
                anchor_source_str = AnchorSource.ATTENDEE.value

    # No external non-consumer domain at all -> no_anchor (caller will set NO_ANCHOR)
    if not anchor:
        return None

    CONF_MIN = get_confidence_min()
    has_external = bool(primary_domain and primary_domain != "rpck.com")

    primary_conf = compute_confidence(
        meeting_data=meeting_data,
        anchor_type=anchor_type_str or "person",
        has_org_context=bool(org_context),
        primary_domain=primary_domain,
        anchor_from_subject=anchor_from_subject,
        has_external_domain=has_external,
        has_attendee_display_name=has_attendee_display_name,
        mailbox=exec_mailbox or None,
    )

    has_comma_first_last = "," in anchor and len(anchor.split(",")) == 2
    anchor_has_spaces = " " in anchor
    is_org_like = anchor_has_spaces and not has_comma_first_last

    if is_org_like:
        primary_query_raw = f"{anchor} (organization, leadership, business, recent news)"
    else:
        primary_query_raw = (f"{anchor} {org_context}".strip() + " (role, company, recent news)").strip()
    if len(primary_query_raw) > 120:
        primary_query_raw = primary_query_raw[:117] + "..."
    primary_query = sanitize_research_query(primary_query_raw)

    if not is_query_usable_after_sanitization(primary_query):
        # We have domain(s) but query sanitized empty -> signal so caller can set query_sanitized_empty
        if domain_counts:
            return {"skip_reason": SkipReason.QUERY_SANITIZED_EMPTY.value, "primary_domain": primary_domain}
        return None

    chosen_query: Optional[str] = None
    chosen_confidence = primary_conf

    if primary_conf >= CONF_MIN:
        chosen_query = primary_query

    # Fallback A: ambiguous short domain + person name -> person query
    if chosen_query is None and anchor_type_str in (AnchorType.ORG.value, AnchorType.DOMAIN.value) and primary_domain and is_domain_ambiguous_short(primary_domain) and person_name_for_fallback:
        fallback_a_raw = f"{person_name_for_fallback} {primary_domain} (company, role, recent news)".strip()
        if len(fallback_a_raw) > 120:
            fallback_a_raw = fallback_a_raw[:117] + "..."
        fallback_a_query = sanitize_research_query(fallback_a_raw)
        if is_query_usable_after_sanitization(fallback_a_query):
            conf_fallback_a = compute_confidence(
                meeting_data=meeting_data,
                anchor_type=AnchorType.PERSON.value,
                has_org_context=True,
                primary_domain=primary_domain,
                anchor_from_subject=anchor_from_subject,
                has_external_domain=has_external,
                has_attendee_display_name=has_attendee_display_name,
                mailbox=exec_mailbox or None,
            )
            if conf_fallback_a >= CONF_MIN:
                chosen_query = fallback_a_query
                chosen_confidence = conf_fallback_a

    # Fallback B: person anchor, no org_context -> domain/org query (use domain_to_org_name for display)
    if chosen_query is None and anchor_type_str == AnchorType.PERSON.value and not org_context and primary_domain and not is_domain_generic(primary_domain) and not is_domain_ambiguous_short(primary_domain):
        domain_org_name = domain_to_org_name(primary_domain) or org_from_email_domain(primary_domain)
        if domain_org_name:
            fallback_b_raw = f"{domain_org_name} (organization, leadership, business, recent news)"
            if len(fallback_b_raw) > 120:
                fallback_b_raw = fallback_b_raw[:117] + "..."
            fallback_b_query = sanitize_research_query(fallback_b_raw)
            if is_query_usable_after_sanitization(fallback_b_query):
                conf_fallback_b = compute_confidence(
                    meeting_data=meeting_data,
                    anchor_type=AnchorType.DOMAIN.value,
                    has_org_context=False,
                    primary_domain=primary_domain,
                    anchor_from_subject=anchor_from_subject,
                    has_external_domain=has_external,
                    has_attendee_display_name=has_attendee_display_name,
                    mailbox=exec_mailbox or None,
                )
                if conf_fallback_b >= CONF_MIN:
                    chosen_query = fallback_b_query
                    chosen_confidence = conf_fallback_b

    # Final domain-only fallback: we have anchor/primary_domain but confidence failed; try org-only query
    if chosen_query is None and primary_domain and domain_counts:
        domain_org_name = domain_to_org_name(primary_domain) or org_from_email_domain(primary_domain)
        if domain_org_name:
            fallback_d_raw = f"{domain_org_name} (organization, leadership, business, recent news)"
            if len(fallback_d_raw) > 120:
                fallback_d_raw = fallback_d_raw[:117] + "..."
            fallback_d_query = sanitize_research_query(fallback_d_raw)
            if not is_query_usable_after_sanitization(fallback_d_query):
                return {"skip_reason": SkipReason.QUERY_SANITIZED_EMPTY.value, "primary_domain": primary_domain}
            conf_fallback_d = compute_confidence(
                meeting_data=meeting_data,
                anchor_type=AnchorType.DOMAIN.value,
                has_org_context=False,
                primary_domain=primary_domain,
                anchor_from_subject=anchor_from_subject,
                has_external_domain=True,
                has_attendee_display_name=has_attendee_display_name,
                mailbox=exec_mailbox or None,
            )
            if conf_fallback_d >= CONF_MIN:
                chosen_query = fallback_d_query
                chosen_confidence = conf_fallback_d
                anchor_type_str = AnchorType.DOMAIN.value
                anchor_source_str = AnchorSource.ATTENDEE.value

    if chosen_query is None:
        # We have external non-consumer domain(s) but confidence failed -> caller will set low_confidence_anchor
        return None

    return {
        "chosen_query": chosen_query,
        "anchor_type_str": anchor_type_str,
        "anchor_source_str": anchor_source_str,
        "chosen_confidence": chosen_confidence,
        "primary_domain": primary_domain,
        "anchor_display": anchor,
    }


def _transform_research_to_meeting_fields(research_result: Dict[str, Any]) -> Dict[str, Any]:
    """
    Transform research_result into per-meeting fields: context_summary, news, industry_signal,
    strategic_angles, high_leverage_questions. All output is scannable bullets/links, no paragraphs.
    
    Args:
        research_result: Dict with 'summary', 'key_points', 'sources' keys
        
    Returns:
        Dict with context_summary (str or None), news (list), industry_signal (str or None),
        strategic_angles (list), high_leverage_questions (list)
    """
    key_points = research_result.get("key_points", []) or []
    sources = research_result.get("sources", []) or []
    
    # context_summary: 1-2 bullets from key_points
    context_summary = None
    if key_points:
        bullets = []
        for kp in key_points[:2]:
            if isinstance(kp, str) and kp.strip():
                bullets.append(kp.strip())
        if bullets:
            context_summary = " • ".join(bullets)
    
    # news: up to 4 sources as {title, url} list
    news = []
    for src in sources[:4]:
        if isinstance(src, dict):
            url = src.get("url", "").strip()
            title = src.get("title", "").strip()
            if not url:
                continue
            if not title:
                # Derive title from URL host
                try:
                    from urllib.parse import urlparse
                    parsed = urlparse(url)
                    host = parsed.netloc or parsed.path.split("/")[0] if parsed.path else ""
                    title = host.replace("www.", "") if host else "Source"
                except:
                    title = "Source"
            news.append({"title": title[:100], "url": url})
    
    # industry_signal: optional 1 bullet (only if non-speculative from key_points)
    industry_signal = None
    # V1: skip industry_signal for now (can be added later with better heuristics)
    
    # strategic_angles: 2-4 bullets from key_points (action-oriented, concise)
    strategic_angles = []
    for kp in key_points[:4]:
        if isinstance(kp, str) and kp.strip():
            # Keep concise (max 120 chars per bullet)
            bullet = kp.strip()[:120]
            if bullet:
                strategic_angles.append(bullet)
    
    # high_leverage_questions: 3-6 questions generated deterministically from key_points
    high_leverage_questions = []
    # V1: Generate simple questions from key_points (no LLM)
    for kp in key_points[:6]:
        if isinstance(kp, str) and kp.strip():
            # Convert statement to question if possible
            kp_lower = kp.lower()
            if "recent" in kp_lower or "announced" in kp_lower:
                high_leverage_questions.append(f"What are the implications of {kp.strip()[:80]}?")
            elif "raised" in kp_lower or "funding" in kp_lower:
                high_leverage_questions.append(f"How will this funding impact their strategy?")
            elif "partnership" in kp_lower or "acquisition" in kp_lower:
                high_leverage_questions.append(f"What does this mean for their market position?")
            elif len(kp.strip()) > 20:
                # Generic: "What should we know about [first 40 chars]?"
                preview = kp.strip()[:40]
                high_leverage_questions.append(f"What should we know about {preview}?")
            if len(high_leverage_questions) >= 6:
                break
    
    return {
        "context_summary": context_summary,
        "news": news,
        "industry_signal": industry_signal,
        "strategic_angles": strategic_angles,
        "high_leverage_questions": high_leverage_questions,
    }


def _format_time_for_display(iso_time: str) -> str:
    """Format ISO time string for display in digest."""
    try:
        # Extract time part (HH:MM)
        time_part = iso_time.split("T")[1].split("-")[0][:5]
        hour, minute = time_part.split(":")
        hour_int = int(hour)

        # Convert to 12-hour format
        if hour_int == 0:
            return f"12:{minute} AM ET"
        elif hour_int < 12:
            return f"{hour_int}:{minute} AM ET"
        elif hour_int == 12:
            return f"12:{minute} PM ET"
        else:
            return f"{hour_int - 12}:{minute} PM ET"
    except (ValueError, IndexError):
        # Fallback to original time if parsing fails
        return iso_time


def _apply_company_aliases(meetings: list[dict], aliases: Dict[str, List[str]]) -> list[dict]:
    """Apply company aliases to canonicalize company names for enrichment."""
    if not aliases:
        return meetings

    # Create reverse lookup: alias -> canonical name
    alias_to_canonical = {}
    for canonical, alias_list in aliases.items():
        for alias in alias_list:
            alias_to_canonical[alias.lower()] = canonical.lower()

    for meeting in meetings:
        # Check company field
        if meeting.get("company") and isinstance(meeting["company"], dict):
            company_name = meeting["company"].get("name", "").lower()
            if company_name in alias_to_canonical:
                meeting["company"]["name"] = alias_to_canonical[company_name].title()

        # Check attendees for company names
        for attendee in meeting.get("attendees", []):
            if attendee.get("company"):
                company_name = attendee["company"].lower()
                if company_name in alias_to_canonical:
                    attendee["company"] = alias_to_canonical[company_name].title()

    return meetings


def _trim_meeting_sections(meetings: list, max_items: Dict[str, int]) -> list:
    """Trim meeting sections to respect max_items limits."""
    for meeting in meetings:
        # Handle both dict and Pydantic model
        if hasattr(meeting, 'model_dump'):
            # Pydantic model - convert to dict, trim, then back to model
            meeting_dict = meeting.model_dump()
            for section, max_count in max_items.items():
                if section in meeting_dict and isinstance(meeting_dict[section], list):
                    meeting_dict[section] = meeting_dict[section][:max_count]

            # Update the model with trimmed data
            for section, max_count in max_items.items():
                if section in meeting_dict and isinstance(meeting_dict[section], list):
                    setattr(meeting, section, meeting_dict[section])
        else:
            # Regular dict
            for section, max_count in max_items.items():
                if section in meeting and isinstance(meeting[section], list):
                    meeting[section] = meeting[section][:max_count]

    return meetings


def _convert_raw_graph_to_events(raw_graph_events: List[dict]) -> List[Event]:
    """
    Convert raw Microsoft Graph API event shapes to Event objects.
    
    This mimics the conversion logic in MSGraphAdapter.fetch_events_between
    to ensure stub mode exercises the same transformation pipeline.
    
    Args:
        raw_graph_events: List of raw Graph API event dicts
        
    Returns:
        List of Event objects
    """
    et_tz = ZoneInfo("America/New_York")
    events = []
    
    for item in raw_graph_events:
        # Skip cancelled events (same as adapter)
        if item.get("isCancelled", False):
            continue
        
        try:
            # Parse start/end times (same logic as adapter)
            start_obj = item.get("start", {})
            start_dt_str = start_obj.get("dateTime", "")
            start_tz_str = start_obj.get("timeZone", "America/New_York")
            
            end_obj = item.get("end", {})
            end_dt_str = end_obj.get("dateTime", "")
            end_tz_str = end_obj.get("timeZone", "America/New_York")
            
            if not start_dt_str or not end_dt_str:
                continue
            
            # Parse datetime strings
            start_dt = datetime.fromisoformat(start_dt_str)
            end_dt = datetime.fromisoformat(end_dt_str)
            
            # Apply timezone if naive
            if start_dt.tzinfo is None:
                start_dt = start_dt.replace(tzinfo=ZoneInfo(start_tz_str))
            if end_dt.tzinfo is None:
                end_dt = end_dt.replace(tzinfo=ZoneInfo(end_tz_str))
            
            # Convert to ET
            start_dt_et = start_dt.astimezone(et_tz)
            end_dt_et = end_dt.astimezone(et_tz)
            
            # Normalize attendees (same logic as adapter)
            attendees = []
            for attendee in item.get("attendees", []):
                email_address = attendee.get("emailAddress", {})
                name = email_address.get("name", "")
                email = email_address.get("address", "")
                
                # Extract company from email domain
                company = None
                if "@" in email:
                    domain = email.split("@")[1]
                    if domain and domain != "rpck.com":
                        company = domain.split(".")[0].title()
                
                attendees.append(Attendee(
                    name=name or email,
                    email=email,
                    company=company
                ))
            
            # Add organizer to attendees if not already there
            organizer = item.get("organizer", {}).get("emailAddress", {})
            organizer_email = organizer.get("address", "")
            organizer_name = organizer.get("name", "")
            
            if organizer_email:
                organizer_in_attendees = any(
                    (a.email or "").lower() == organizer_email.lower()
                    for a in attendees
                )
                if not organizer_in_attendees:
                    company = None
                    if "@" in organizer_email:
                        domain = organizer_email.split("@")[1]
                        if domain and domain != "rpck.com":
                            company = domain.split(".")[0].title()
                    attendees.append(Attendee(
                        name=organizer_name or organizer_email,
                        email=organizer_email,
                        company=company
                    ))
            
            # Extract location
            location = item.get("location", {}).get("displayName")
            
            # Extract notes
            notes = item.get("bodyPreview", "")
            if notes:
                notes = notes.strip()[:500]
            
            # Create Event object
            event = Event(
                subject=item.get("subject", ""),
                start_time=start_dt_et.isoformat(),
                end_time=end_dt_et.isoformat(),
                location=location,
                attendees=attendees,
                notes=notes,
                id=item.get("id"),
                organizer=organizer_email
            )
            
            events.append(event)
            
        except Exception as e:
            # Skip events that fail to parse (same as adapter)
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"Failed to parse stub event: {e}")
            continue
    
    return events


def _map_events_to_meetings(events: list[dict] | list) -> list[dict]:
    meetings: list[dict] = []
    for e in events:
        # e is a pydantic model dict-like; support both dict and model
        subject = getattr(e, "subject", None) or e.get("subject", "")
        start_time = getattr(e, "start_time", None) or e.get("start_time", "")
        location = getattr(e, "location", None) or e.get("location")
        organizer = getattr(e, "organizer", None) or e.get("organizer")
        attendees_raw = getattr(e, "attendees", None) or e.get("attendees", [])
        attendees = []
        for a in attendees_raw:
            name = getattr(a, "name", None) or a.get("name", "")
            title = getattr(a, "title", None) or a.get("title")
            company = getattr(a, "company", None) or a.get("company")
            email = getattr(a, "email", None) or a.get("email")
            attendees.append({"name": name, "title": title, "company": company, "email": email})

        meetings.append(
            {
                "subject": subject,
                # For MVP, show only time component in ET readable form; use ISO string's time
                "start_time": _format_time_for_display(start_time) if "T" in start_time else start_time,
                "location": location,
                "organizer": organizer,
                "attendees": attendees,
                "company": None,
                "news": [],
                "talking_points": [],
                "smart_questions": [],
                "context_summary": None,
                "industry_signal": None,
                "strategic_angles": [],
                "high_leverage_questions": [],
            }
        )
    return meetings


def build_digest_context_with_provider(
    source: Literal["sample", "live", "stub"],
    date: Optional[str] = None,
    exec_name: Optional[str] = None,
    mailbox: Optional[str] = None,
    *,
    allow_research: bool = False,
    research_budget: Optional[ResearchBudget] = None,
    request_id: Optional[str] = None,
) -> Dict[str, Any]:
    logger = logging.getLogger(__name__)

    def _safe_research_extra(ctx: Dict[str, Any], rid: Optional[str]) -> Dict[str, Any]:
        trace = ctx.get("research_trace") or {}
        if not isinstance(trace, dict):
            trace = {"research_trace_type": str(type(trace))}
        return {**trace, "request_id": rid}

    requested_date = date
    if not requested_date:
        requested_date = datetime.now().strftime("%Y-%m-%d")

    # Load executive profile (use mailbox if provided)
    profile = get_profile(mailbox=mailbox)

    # Determine which user's calendar to fetch
    # Use explicit mailbox parameter, or fall back to profile's mailbox field
    user_mailbox = mailbox
    if not user_mailbox and hasattr(profile, 'mailbox') and profile.mailbox:
        user_mailbox = profile.mailbox

    actual_source = "live"
    meetings: list[dict] = []

    if source == "live":
        try:
            logger.info(f"Fetching live calendar events for date={requested_date}, user={user_mailbox}")
            provider = select_calendar_provider()
            provider_name = type(provider).__name__
            logger.info(f"Using calendar provider: {provider_name} (CALENDAR_PROVIDER={os.getenv('CALENDAR_PROVIDER', 'not set')})")
            # Pass mailbox/user to filter events for specific user
            events = provider.fetch_events(requested_date, user=user_mailbox)
            logger.info(f"Received {len(events)} events from provider {provider_name} for {requested_date}, mailbox={user_mailbox}")
            if events:
                meetings = _map_events_to_meetings([e.model_dump() for e in events])
                actual_source = "live"
                logger.info(f"Mapped to {len(meetings)} meetings")
            else:
                # No events for this date - meetings will be empty
                meetings = []
                actual_source = "live"
                logger.info(f"No events found for {requested_date}")
        except HTTPException:
            # Re-raise HTTPExceptions (e.g., 403, 401) so they propagate with correct status codes
            raise
        except Exception as e:
            # Provider error - log full exception with context
            logger.exception(
                "PREVIEW_FAILED",
                extra={
                    "source": source,
                    "date": requested_date,
                    "mailbox": user_mailbox,
                    "error_type": type(e).__name__,
                }
            )
            raise HTTPException(status_code=500, detail="preview failed: PREVIEW_FAILED")
    elif source == "stub":
        # Stub mode - convert raw Graph shapes to Event objects, then through mapping pipeline
        # This ensures stub mode exercises the same transformation as live mode
        logger.info(f"Using stub mode with {len(STUB_MEETINGS_RAW_GRAPH)} raw Graph events")
        
        # Convert raw Graph shapes to Event objects (same as adapter does)
        stub_events = _convert_raw_graph_to_events(STUB_MEETINGS_RAW_GRAPH)
        logger.info(f"Converted to {len(stub_events)} Event objects")
        
        # Pass through same mapping as live mode
        if stub_events:
            meetings = _map_events_to_meetings([e.model_dump() for e in stub_events])
            actual_source = "stub"
            logger.info(f"Mapped to {len(meetings)} meetings")
        else:
            meetings = []
            actual_source = "stub"
            logger.info("No valid stub events after conversion")
    else:
        # Sample mode - use sample data
        meetings = SAMPLE_MEETINGS
        actual_source = "sample"

    # Apply company aliases before enrichment
    meetings = _apply_company_aliases(meetings, profile.company_aliases)

    # Optionally enrich meetings
    meetings_enriched = enrich_meetings(meetings)

    # Apply profile max_items limits
    meetings_trimmed = _trim_meeting_sections(meetings_enriched, profile.max_items)

    # Attach memory data (past meetings) to each meeting
    meetings_with_memory = attach_memory_to_meetings(meetings_trimmed)

    # Format date_human based on requested date (or today if not specified)
    tz_name = _get_timezone()
    if requested_date:
        date_human = _format_date_et_str(requested_date, tz_name)
        # Extract year from requested date for current_year
        try:
            date_obj = datetime.strptime(requested_date, "%Y-%m-%d")
            current_year = date_obj.strftime("%Y")
        except ValueError:
            current_year = datetime.now().strftime("%Y")
    else:
        date_human = _today_et_str(tz_name)
        current_year = datetime.now().strftime("%Y")

    # Add dev flags for template gating
    app_env = (os.getenv("APP_ENV") or os.getenv("ENVIRONMENT") or "development").strip().lower()
    enable_research_dev = (os.getenv("ENABLE_RESEARCH_DEV") or "").strip().lower() in ("true", "1", "yes")
    
    context = {
        "meetings": meetings_with_memory,
        "date_human": date_human,
        "current_year": current_year,
        "exec_name": exec_name or profile.exec_name,  # Use profile default unless overridden
        "source": actual_source,
        "app_env": app_env,
        "enable_research_dev": enable_research_dev,
    }
    req_id = request_id or str(uuid.uuid4())

    # Endpoint/call-site gating: research only when allow_research=True (digest preview, run-digest, digest send)
    if not allow_research:
        context["research"] = {"summary": "", "key_points": [], "sources": []}
        context["research_trace"] = build_research_trace(
            attempted=False,
            outcome=ResearchOutcome.SKIPPED.value,
            skip_reason=SkipReason.ENDPOINT_GUARD.value,
        )
        context["_research_computed"] = True
        logger.info("RESEARCH_SKIPPED", extra={"reason": "endpoint_guard", "request_id": req_id})
        return context

    # Research computed once here and attached to context; no later step should call provider again
    budget = research_budget if research_budget is not None else ResearchBudget(MAX_TAVILY_CALLS_PER_REQUEST)
    context["_research_computed"] = False  # set True after we set context["research"]

    from app.research.selector import should_run_research, select_research_provider
    allowed, skip_reason = should_run_research()
    if not allowed:
        context["research"] = {"summary": "", "key_points": [], "sources": []}
        skip_reason_enum = SkipReason.DISABLED.value if skip_reason == "disabled" else SkipReason.DEV_GUARD.value
        context["research_trace"] = build_research_trace(
            attempted=False,
            outcome=ResearchOutcome.SKIPPED.value,
            skip_reason=skip_reason_enum,
        )
        context["_research_computed"] = True
        logger.info("RESEARCH_SKIPPED", extra={"reason": skip_reason, "request_id": req_id})
        return context

    selection_start = time.perf_counter()
    try:

            def _meeting_to_data(m: Any) -> Dict[str, Any]:
                """Normalize meeting to dict (handle Pydantic models)."""
                if hasattr(m, "model_dump"):
                    return m.model_dump()
                if hasattr(m, "dict"):
                    return m.dict()
                if isinstance(m, dict):
                    return m
                return {}

            def _domain_from_email(email: Any) -> str:
                """Extract domain from email string; empty if not present."""
                if not email:
                    return ""
                s = (email if isinstance(email, str) else str(email)).strip().lower()
                if "@" in s:
                    return s.split("@", 1)[1]
                return ""

            def _normalize_attendee(a: Any) -> Dict[str, Any]:
                """Normalize attendee to dict."""
                if isinstance(a, dict):
                    return a
                if hasattr(a, "model_dump"):
                    return a.model_dump()
                if hasattr(a, "dict"):
                    return a.dict()
                return {}

            def score_meeting_for_research(meeting_data: Dict[str, Any]) -> int:
                """Score meeting for research priority. Higher score = better candidate."""
                subject = (meeting_data.get("subject") or meeting_data.get("title") or "").strip().lower()
                
                # Skip internal/admin subjects
                skip_patterns = ["blocked time", "recap voice note", "complete forms", "admin", "internal hold"]
                if any(pattern in subject for pattern in skip_patterns):
                    return -9999
                
                score = 0
                
                # External organizer boost
                org = meeting_data.get("organizer")
                org_domain = _domain_from_email(org)
                has_external_org = org_domain and org_domain != "rpck.com"
                if has_external_org:
                    score += 30
                
                # External attendee boost (cap at +45 for 3+ external attendees)
                external_attendee_count = 0
                for a in meeting_data.get("attendees") or []:
                    ad = _normalize_attendee(a)
                    if not isinstance(ad, dict):
                        continue
                    email = ad.get("email") or ad.get("address")
                    dom = _domain_from_email(email)
                    if dom and dom != "rpck.com":
                        external_attendee_count += 1
                score += min(external_attendee_count * 15, 45)
                
                # Subject keyword boosts
                high_value_keywords = [
                    "intro", "introductory", "kickoff", "diligence", "closing",
                    "negotiation", "term sheet", "board", "investor", "financing",
                    "acquisition", "dispute", "arbitration"
                ]
                if any(kw in subject for kw in high_value_keywords):
                    score += 20
                
                if "call with" in subject or "meeting with" in subject:
                    score += 10
                
                negative_keywords = ["internal", "admin", "recap", "blocked", "hold"]
                if any(kw in subject for kw in negative_keywords):
                    score -= 15
                
                # Attendee count shaping
                attendee_count = len(meeting_data.get("attendees") or [])
                has_external = has_external_org or external_attendee_count > 0
                if 1 <= attendee_count <= 3 and has_external:
                    score += 10
                if attendee_count >= 8:
                    score -= 5
                
                return score

            def extract_counterparty_from_subject(subj: str) -> str:
                """Extract counterparty name from subject patterns like 'Call with X', 'Intro: X'."""
                if not subj or not subj.strip():
                    return ""
                subj = subj.strip()
                m = re.search(
                    r"^(?:call|meeting|intro|catch[- ]?up|1:1|one[- ]?on[- ]?one)\s+with\s+(.+)$",
                    subj,
                    re.IGNORECASE,
                )
                if m:
                    name = m.group(1).strip().rstrip(".,;:—-")
                    return name if name else ""
                m = re.search(r"^intro\s*[:\-]\s*(.+)$", subj, re.IGNORECASE)
                if m:
                    name = m.group(1).strip().rstrip(".,;:—-")
                    return name if name else ""
                return ""

            from app.research.anchor_utils import extract_org_from_subject, org_from_email_domain

            # Per-meeting research enrichment (V1: meeting-scoped research)
            # Hard cap: max 8 Tavily calls per digest request
            MAX_CALLS_PER_DIGEST = 8
            provider = select_research_provider()
            exec_name = (context.get("exec_name") or "").strip()
            exec_mailbox = (user_mailbox or "").strip() if user_mailbox else None
            
            # Dedupe cache: keyed by sanitized query, stores research_result
            research_cache: Dict[str, Dict[str, Any]] = {}
            calls_made = 0
            
            # Track research traces per meeting (for dev/debug, not rendered in prod)
            research_traces_by_meeting_id: Dict[str, Dict[str, Any]] = {}
            
            # Process each meeting
            for meeting_idx, meeting in enumerate(meetings_with_memory or []):
                meeting_data = _meeting_to_data(meeting)
                
                # Skip internal meetings (score < 0)
                score = score_meeting_for_research(meeting_data)
                if score < 0:
                    continue
                
                # Check for test meetings first (before computing anchor)
                meeting_id = meeting_data.get("id") or f"meeting_{meeting_idx}"
                if is_meeting_like_test(meeting_data, exec_mailbox):
                    trace = build_research_trace(
                        attempted=True,
                        outcome=ResearchOutcome.SKIPPED.value,
                        skip_reason=SkipReason.MEETING_MARKED_TEST.value,
                        timings_ms={"selection_ms": 0, "tavily_ms": 0, "summarize_ms": 0},
                    )
                    research_traces_by_meeting_id[meeting_id] = trace
                    # Attach trace to meeting for dev UI
                    if isinstance(meeting, dict):
                        meeting["research_trace"] = trace
                    elif hasattr(meeting, "__dict__"):
                        meeting.__dict__["research_trace"] = trace
                    continue
                
                # Compute anchor and query
                anchor_result = _compute_meeting_anchor_and_query(
                    meeting_data=meeting_data,
                    exec_name=exec_name,
                    exec_mailbox=exec_mailbox,
                    _domain_from_email=_domain_from_email,
                    _normalize_attendee=_normalize_attendee,
                    extract_counterparty_from_subject=extract_counterparty_from_subject,
                    extract_org_from_subject=extract_org_from_subject,
                    org_from_email_domain=org_from_email_domain,
                    compute_confidence=compute_confidence,
                    sanitize_research_query=sanitize_research_query,
                    is_query_usable_after_sanitization=is_query_usable_after_sanitization,
                    is_domain_generic=is_domain_generic,
                    is_domain_ambiguous_short=is_domain_ambiguous_short,
                    get_confidence_min=get_confidence_min,
                )
                
                # anchor_result can be: success dict (chosen_query), failure dict (skip_reason), or None
                if isinstance(anchor_result, dict) and anchor_result.get("skip_reason") and not anchor_result.get("chosen_query"):
                    skip_reason = anchor_result.get("skip_reason", SkipReason.NO_ANCHOR.value)
                    trace = build_research_trace(
                        attempted=True,
                        outcome=ResearchOutcome.SKIPPED.value,
                        skip_reason=skip_reason,
                        primary_domain=anchor_result.get("primary_domain"),
                        timings_ms={"selection_ms": 0, "tavily_ms": 0, "summarize_ms": 0},
                    )
                    research_traces_by_meeting_id[meeting_id] = trace
                    if isinstance(meeting, dict):
                        meeting["research_trace"] = trace
                    elif hasattr(meeting, "__dict__"):
                        meeting.__dict__["research_trace"] = trace
                    continue

                if not anchor_result:
                    # No usable anchor/query - LOW_CONFIDENCE_ANCHOR when we had external domains, else NO_ANCHOR
                    subject = (meeting_data.get("subject") or meeting_data.get("title") or "").strip()
                    org = meeting_data.get("organizer")
                    org_domain = _domain_from_email(org)
                    has_external_org = org_domain and org_domain != "rpck.com" and not is_consumer_domain(org_domain)
                    external_attendees = []
                    for a in meeting_data.get("attendees") or []:
                        ad = _normalize_attendee(a)
                        if isinstance(ad, dict):
                            email = ad.get("email") or ad.get("address")
                            dom = _domain_from_email(email)
                            if dom and dom != "rpck.com" and not is_consumer_domain(dom):
                                external_attendees.append({"name": ad.get("name"), "domain": dom})
                    skip_reason = SkipReason.LOW_CONFIDENCE_ANCHOR.value if (has_external_org or external_attendees) else SkipReason.NO_ANCHOR.value
                    trace = build_research_trace(
                        attempted=True,
                        outcome=ResearchOutcome.SKIPPED.value,
                        skip_reason=skip_reason,
                        timings_ms={"selection_ms": 0, "tavily_ms": 0, "summarize_ms": 0},
                    )
                    research_traces_by_meeting_id[meeting_id] = trace
                    if isinstance(meeting, dict):
                        meeting["research_trace"] = trace
                    elif hasattr(meeting, "__dict__"):
                        meeting.__dict__["research_trace"] = trace
                    continue

                chosen_query = anchor_result["chosen_query"]
                anchor_type_str = anchor_result["anchor_type_str"]
                anchor_source_str = anchor_result["anchor_source_str"]
                chosen_confidence = anchor_result["chosen_confidence"]
                primary_domain_from_anchor = anchor_result.get("primary_domain") or ""
                anchor_display = (anchor_result.get("anchor_display") or "").strip()
                org_display = domain_to_org_name(primary_domain_from_anchor or "") if primary_domain_from_anchor else ""
                expected_domain = (primary_domain_from_anchor or "").strip().lower()
                ambiguous_acronym = _is_ambiguous_acronym_domain(expected_domain)
                # For ambiguous acronym domains: primary query is person+org only (no site:) to avoid ticker noise
                if ambiguous_acronym and org_display:
                    query_for_call = (
                        f'"{anchor_display}" "{org_display}"'
                        if anchor_type_str == AnchorType.PERSON.value and anchor_display
                        else f'"{org_display}"'
                    )
                else:
                    query_for_call = chosen_query

                # Check dedupe cache first (cache hits don't consume budget)
                cache_key = query_for_call.strip().lower()
                tavily_ms = 0
                if cache_key in research_cache:
                    # Reuse cached result - DO NOT consume budget
                    research_result = research_cache[cache_key]
                    # Use cached tavily_ms if available, otherwise 0
                    tavily_ms = research_result.get("_cached_tavily_ms", 0)
                else:
                    # Not in cache - need to call provider
                    # Check hard cap (8 calls max)
                    if calls_made >= MAX_CALLS_PER_DIGEST:
                        meeting_id = meeting_data.get("id") or f"meeting_{meeting_idx}"
                        trace = build_research_trace(
                            attempted=True,
                            outcome=ResearchOutcome.SKIPPED.value,
                            skip_reason=SkipReason.BUDGET_EXHAUSTED.value,
                            anchor_type=anchor_type_str,
                            anchor_source=anchor_source_str,
                            primary_domain=primary_domain_from_anchor or None,
                            confidence=round(chosen_confidence, 4),
                            query_hash=query_hash_prefix(query_for_call),
                            query_len=len(query_for_call),
                            timings_ms={"selection_ms": 0, "tavily_ms": 0, "summarize_ms": 0},
                        )
                        research_traces_by_meeting_id[meeting_id] = trace
                        # Attach trace to meeting for dev UI
                        if isinstance(meeting, dict):
                            meeting["research_trace"] = trace
                        elif hasattr(meeting, "__dict__"):
                            meeting.__dict__["research_trace"] = trace
                        continue
                    
                    # Check budget right before actual provider call (if provided)
                    if not budget.consume_one_or_false():
                        meeting_id = meeting_data.get("id") or f"meeting_{meeting_idx}"
                        trace = build_research_trace(
                            attempted=True,
                            outcome=ResearchOutcome.SKIPPED.value,
                            skip_reason=SkipReason.BUDGET_EXHAUSTED.value,
                            anchor_type=anchor_type_str,
                            anchor_source=anchor_source_str,
                            primary_domain=primary_domain_from_anchor or None,
                            confidence=round(chosen_confidence, 4),
                            query_hash=query_hash_prefix(query_for_call),
                            query_len=len(query_for_call),
                            timings_ms={"selection_ms": 0, "tavily_ms": 0, "summarize_ms": 0},
                        )
                        research_traces_by_meeting_id[meeting_id] = trace
                        # Attach trace to meeting for dev UI
                        if isinstance(meeting, dict):
                            meeting["research_trace"] = trace
                        elif hasattr(meeting, "__dict__"):
                            meeting.__dict__["research_trace"] = trace
                        continue
                    
                    # Call provider - budget already consumed above
                    tavily_start = time.perf_counter()
                    try:
                        research_result = provider.get_research(query_for_call)
                    except Exception:
                        research_result = {"summary": "", "key_points": [], "sources": []}
                    tavily_ms = int((time.perf_counter() - tavily_start) * 1000)
                    if research_result.get("_duration_ms") is not None:
                        tavily_ms = research_result.pop("_duration_ms", tavily_ms)
                    
                    if research_result.get("sources"):
                        research_result["sources"] = _dedupe_and_cap_sources(
                            research_result["sources"], max_items=MAX_RESEARCH_SOURCES
                        )
                    
                    # Store tavily_ms in cache for trace purposes
                    research_result["_cached_tavily_ms"] = tavily_ms
                    
                    # Cache result
                    research_cache[cache_key] = research_result
                    calls_made += 1
                
                # Off-target guardrail: host-based domain match; for ambiguous acronym also entity + negative-term filter
                sources_list = research_result.get("sources") or []
                if expected_domain:
                    result_domain_match_host, domain_match_host, top_source_hosts = _result_domain_match_host_based(
                        sources_list, expected_domain
                    )
                else:
                    result_domain_match_host, domain_match_host = True, None
                    top_source_hosts = [_host_from_url((s.get("url") or "")) for s in sources_list[:5] if isinstance(s, dict)]
                    top_source_hosts = [h for h in top_source_hosts if h]
                entity_match_passed: Optional[bool] = None
                negative_hit = False
                mismatch_reason_candidate: Optional[str] = None
                if ambiguous_acronym:
                    entity_match_passed = _entity_match_in_sources(
                        research_result, anchor_display, org_display, require_org_for_ambiguous=True
                    )
                    negative_hit = _negative_term_hit_in_sources(research_result)
                    # For ambiguous: pass = entity match and no negative term (domain not required)
                    result_passed = entity_match_passed and not negative_hit
                    if negative_hit:
                        mismatch_reason_candidate = "negative_term_hit"
                    elif not entity_match_passed:
                        mismatch_reason_candidate = "entity_match_failed"
                else:
                    result_passed = result_domain_match_host
                    if not result_domain_match_host:
                        mismatch_reason_candidate = "expected_domain_not_found"
                # Host-based result for trace only (domain_match_passed = host match only)
                result_domain_match = result_domain_match_host
                retry_used = False
                final_result = research_result
                tavily_ms_final = tavily_ms
                final_domain_match_host = domain_match_host
                final_top_hosts = top_source_hosts
                final_entity_match = entity_match_passed
                final_mismatch_reason = mismatch_reason_candidate

                if not result_passed and (expected_domain or ambiguous_acronym):
                    # One retry: for ambiguous use LinkedIn/TheOrg; for non-ambiguous use site:expected_domain
                    if org_display and calls_made < MAX_CALLS_PER_DIGEST and budget.consume_one_or_false():
                        if ambiguous_acronym:
                            retry_query = (
                                f'"{anchor_display}" "{org_display}" (site:linkedin.com OR site:theorg.com)'
                                if anchor_type_str == AnchorType.PERSON.value and anchor_display
                                else f'"{org_display}" (site:linkedin.com OR site:theorg.com)'
                            )
                        else:
                            if anchor_type_str == AnchorType.PERSON.value and anchor_display:
                                retry_query = f'"{anchor_display}" "{org_display}" site:{expected_domain}'
                            else:
                                retry_query = f'"{org_display}" site:{expected_domain}'
                        tavily_start_retry = time.perf_counter()
                        try:
                            retry_result = provider.get_research(retry_query)
                        except Exception:
                            retry_result = {"summary": "", "key_points": [], "sources": []}
                        tavily_ms_retry = int((time.perf_counter() - tavily_start_retry) * 1000)
                        if retry_result.get("sources"):
                            retry_result["sources"] = _dedupe_and_cap_sources(
                                retry_result["sources"], max_items=MAX_RESEARCH_SOURCES
                            )
                        calls_made += 1
                        retry_used = True
                        if ambiguous_acronym:
                            retry_entity = _entity_match_in_sources(
                                retry_result, anchor_display, org_display, require_org_for_ambiguous=True
                            )
                            retry_negative = _negative_term_hit_in_sources(retry_result)
                            if retry_entity and not retry_negative:
                                final_result = retry_result
                                result_passed = True
                                tavily_ms_final = tavily_ms_retry
                                final_top_hosts = [_host_from_url((s.get("url") or "")) for s in (retry_result.get("sources") or [])[:5] if isinstance(s, dict)]
                                final_top_hosts = [h for h in final_top_hosts if h]
                                final_entity_match = True
                                final_mismatch_reason = None
                                # Trace: host-based match from accepted result (so domain_match_passed reflects actual sources)
                                retry_match, retry_host, _ = _result_domain_match_host_based(
                                    retry_result.get("sources") or [], expected_domain
                                )
                                if retry_match:
                                    result_domain_match = True
                                    final_domain_match_host = retry_host
                        else:
                            retry_match, retry_host, retry_hosts = _result_domain_match_host_based(
                                retry_result.get("sources") or [], expected_domain
                            )
                            if retry_match:
                                final_result = retry_result
                                result_passed = True
                                tavily_ms_final = tavily_ms_retry
                                final_domain_match_host = retry_host
                                final_top_hosts = retry_hosts
                                result_domain_match = True
                                final_mismatch_reason = None

                    if not result_passed:
                        meeting_id = meeting_data.get("id") or f"meeting_{meeting_idx}"
                        trace = build_research_trace(
                            attempted=True,
                            outcome=ResearchOutcome.SKIPPED.value,
                            skip_reason=SkipReason.OFF_TARGET_RESULTS.value,
                            anchor_type=anchor_type_str,
                            anchor_source=anchor_source_str,
                            primary_domain=primary_domain_from_anchor or None,
                            domain_match_passed=False,
                            domain_match_url=None,
                            top_source_hosts=final_top_hosts[:5] if final_top_hosts else None,
                            entity_match_passed=final_entity_match if ambiguous_acronym else None,
                            mismatch_reason=final_mismatch_reason or "expected_domain_not_found",
                            retry_used=retry_used,
                            confidence=round(chosen_confidence, 4),
                            query_hash=query_hash_prefix(query_for_call),
                            query_len=len(query_for_call),
                            timings_ms={"selection_ms": 0, "tavily_ms": tavily_ms_final, "summarize_ms": 0},
                        )
                        research_traces_by_meeting_id[meeting_id] = trace
                        if isinstance(meeting, dict):
                            meeting["research_trace"] = trace
                        elif hasattr(meeting, "__dict__"):
                            meeting.__dict__["research_trace"] = trace
                        continue
                
                # Populate from final_result (first call matched or retry matched)
                meeting_fields = _transform_research_to_meeting_fields(final_result)
                
                # Attach fields to meeting (works for both dicts and objects with __dict__)
                meeting_data_for_update = _meeting_to_data(meeting)
                meeting_data_for_update.update(meeting_fields)
                
                # If meeting is a dict, update it directly
                if isinstance(meeting, dict):
                    meeting.update(meeting_fields)
                # If meeting is a Pydantic model, update via model_dump and reconstruct
                elif hasattr(meeting, "model_dump") and hasattr(meeting, "model_validate"):
                    try:
                        updated_dict = meeting.model_dump()
                        updated_dict.update(meeting_fields)
                        # Note: This creates a new model instance, but we can't replace items in the list easily
                        # For now, update the dict representation which will be used when meetings are serialized
                        meeting.__dict__.update(updated_dict)
                    except Exception:
                        # Fallback: just update __dict__ if model_validate fails
                        if hasattr(meeting, "__dict__"):
                            meeting.__dict__.update(meeting_fields)
                
                # Store research_trace for dev/debug; domain_match_url only when domain_match_passed (host-based) is True
                meeting_id = meeting_data_for_update.get("id") or f"meeting_{meeting_idx}"
                sources_count = len(final_result.get("sources") or [])
                has_content = bool(final_result.get("summary") or final_result.get("key_points") or final_result.get("sources"))
                outcome = ResearchOutcome.SUCCESS.value if has_content else ResearchOutcome.ERROR.value
                trace = build_research_trace(
                    attempted=True,
                    outcome=outcome,
                    anchor_type=anchor_type_str,
                    anchor_source=anchor_source_str,
                    primary_domain=primary_domain_from_anchor or None,
                    domain_match_passed=result_domain_match if expected_domain else None,
                    domain_match_url=final_domain_match_host if result_domain_match and final_domain_match_host else None,
                    top_source_hosts=final_top_hosts[:5] if final_top_hosts else None,
                    entity_match_passed=final_entity_match if ambiguous_acronym else None,
                    retry_used=retry_used if retry_used else None,
                    confidence=round(chosen_confidence, 4),
                    query_hash=query_hash_prefix(query_for_call),
                    query_len=len(query_for_call),
                    timings_ms={"selection_ms": 0, "tavily_ms": tavily_ms_final, "summarize_ms": 0},
                    sources_count=sources_count,
                )
                research_traces_by_meeting_id[meeting_id] = trace
                # Attach trace to meeting for dev UI
                if isinstance(meeting, dict):
                    meeting["research_trace"] = trace
                elif hasattr(meeting, "__dict__"):
                    meeting.__dict__["research_trace"] = trace
            
            # Store research traces in context for dev/debug (not rendered in prod templates)
            context["research_traces_by_meeting_id"] = research_traces_by_meeting_id
            
            # Legacy: set empty global research (old global Research section will be gated/removed)
            context["research"] = {"summary": "", "key_points": [], "sources": []}
            context["research_trace"] = build_research_trace(
                attempted=True,
                outcome=ResearchOutcome.SUCCESS.value if research_traces_by_meeting_id else ResearchOutcome.SKIPPED.value,
                skip_reason=SkipReason.NO_CANDIDATE.value if not research_traces_by_meeting_id else None,
                timings_ms={"selection_ms": int((time.perf_counter() - selection_start) * 1000), "tavily_ms": 0, "summarize_ms": 0},
            )
            context["_research_computed"] = True
            
            # Log summary (non-PII)
            eligible_meetings = [m for m in meetings_with_memory or [] if score_meeting_for_research(_meeting_to_data(m)) >= 0]
            logger.info("RESEARCH_PER_MEETING_COMPLETE", extra={
                "meetings_processed": len(eligible_meetings),
                "calls_made": calls_made,
                "cache_hits": len(research_traces_by_meeting_id) - calls_made if len(research_traces_by_meeting_id) >= calls_made else 0,
                "request_id": req_id,
            })

    except Exception as e:
        logger.exception(
            "RESEARCH_CONTEXT_FAILURE",
            extra={"error_type": type(e).__name__, "request_id": req_id}
        )
        context["research"] = {"summary": "", "key_points": [], "sources": []}
        selection_ms = int((time.perf_counter() - selection_start) * 1000)
        context["research_trace"] = build_research_trace(
            attempted=True,
            outcome=ResearchOutcome.ERROR.value,
            timings_ms={"selection_ms": selection_ms, "tavily_ms": 0, "summarize_ms": 0},
        )
        context["_research_computed"] = True

    return context


def build_single_event_context(
    event_id: str,
    source: Literal["sample", "live"] = "sample",
    date: Optional[str] = None,
    exec_name: Optional[str] = None,
    mailbox: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Build context for a single event by ID.

    Args:
        event_id: The ID of the event to fetch
        source: Data source ("sample" or "live")
        date: Optional date for live data
        exec_name: Optional executive name override
        mailbox: Optional mailbox to determine profile

    Returns:
        Context dictionary with single meeting
    """
    requested_date = date
    if not requested_date:
        requested_date = datetime.now().strftime("%Y-%m-%d")

    # Load executive profile (use mailbox if provided)
    profile = get_profile(mailbox=mailbox)

    # Determine which user's calendar to fetch
    # Use explicit mailbox parameter, or fall back to profile's mailbox field
    user_mailbox = mailbox
    if not user_mailbox and hasattr(profile, 'mailbox') and profile.mailbox:
        user_mailbox = profile.mailbox

    actual_source = "sample"
    meeting: Optional[dict] = None

    if source == "live":
        try:
            provider = select_calendar_provider()
            # For now, we'll fetch all events and find by ID
            # In a real implementation, the provider would have a fetch_event_by_id method
            # Pass mailbox/user to filter events for specific user
            events = provider.fetch_events(requested_date, user=user_mailbox)
            if events:
                # Find event by ID (assuming event has an 'id' field)
                for event in events:
                    event_dict = event.model_dump() if hasattr(event, 'model_dump') else event
                    if event_dict.get('id') == event_id:
                        meetings = _map_events_to_meetings([event_dict])
                        if meetings:
                            meeting = meetings[0]
                            actual_source = "live"
                        break
        except HTTPException:
            # Re-raise HTTPExceptions (e.g., 403, 401) so they propagate with correct status codes
            raise
        except Exception as e:
            # Unexpected error - log and raise HTTPException
            import logging
            logger = logging.getLogger(__name__)
            logger.exception(
                "PREVIEW_FAILED",
                extra={
                    "source": source,
                    "date": requested_date,
                    "mailbox": user_mailbox,
                    "event_id": event_id,
                    "error_type": type(e).__name__,
                }
            )
            raise HTTPException(status_code=500, detail="preview failed: PREVIEW_FAILED")

    # If no meeting found in live data, try sample data
    if not meeting:
        # For sample data, we'll use a simple ID mapping
        # In a real implementation, sample data would have proper IDs
        if event_id == "sample-1" or event_id == "1":
            meeting = SAMPLE_MEETINGS[0].copy() if SAMPLE_MEETINGS else None
        else:
            # Create a basic meeting structure for unknown IDs
            meeting = {
                "subject": f"Meeting {event_id}",
                "start_time": "9:00 AM ET",
                "location": "Not specified",
                "attendees": [],
                "company": None,
                "news": [],
                "talking_points": [],
                "smart_questions": [],
                "context_summary": None,
                "industry_signal": None,
                "strategic_angles": [],
                "high_leverage_questions": [],
            }

    if not meeting:
        # Create a minimal meeting structure for missing events
        meeting = {
            "subject": "Meeting not found",
            "start_time": "Not available",
            "location": "Not available",
            "attendees": [],
            "company": None,
            "news": [],
            "talking_points": [],
            "smart_questions": [],
            "context_summary": None,
            "industry_signal": None,
            "strategic_angles": [],
            "high_leverage_questions": [],
        }

    # Apply company aliases before enrichment
    meetings = [meeting]
    meetings = _apply_company_aliases(meetings, profile.company_aliases)

    # Optionally enrich meetings
    meetings_enriched = enrich_meetings(meetings)

    # Apply profile max_items limits
    meetings_trimmed = _trim_meeting_sections(meetings_enriched, profile.max_items)

    # Attach memory data (past meetings) to each meeting
    meetings_with_memory = attach_memory_to_meetings(meetings_trimmed)

    # Format date_human based on requested date (or today if not specified)
    tz_name = _get_timezone()
    if requested_date:
        date_human = _format_date_et_str(requested_date, tz_name)
        # Extract year from requested date for current_year
        try:
            date_obj = datetime.strptime(requested_date, "%Y-%m-%d")
            current_year = date_obj.strftime("%Y")
        except ValueError:
            current_year = datetime.now().strftime("%Y")
    else:
        date_human = _today_et_str(tz_name)
        current_year = datetime.now().strftime("%Y")

    context = {
        "meetings": meetings_with_memory,
        "date_human": date_human,
        "current_year": current_year,
        "exec_name": exec_name or profile.exec_name,
        "source": actual_source,
        "event_id": event_id,  # Include event ID in context for reference
    }
    return context


