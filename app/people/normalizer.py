"""
People Intel Normalizer

Extracts and normalizes person-level metadata from meeting attendees
to build search hints for finding relevant news articles.
"""

from typing import List, Optional, Dict, Any
from dataclasses import dataclass
import re


@dataclass
class PersonHint:
    """
    Person-level metadata extracted from meeting attendees.
    Used to build targeted search queries for finding relevant news.
    """
    name: str
    email: Optional[str] = None
    domain: Optional[str] = None
    company: Optional[str] = None
    title: Optional[str] = None
    co_attendee_domains: List[str] = None
    keywords: List[str] = None

    def __post_init__(self):
        """Initialize default values after dataclass creation."""
        if self.co_attendee_domains is None:
            self.co_attendee_domains = []
        if self.keywords is None:
            self.keywords = []

    @property
    def normalized_name(self) -> str:
        """Return name with common variations normalized."""
        if not self.name:
            return ""

        # Remove common prefixes/suffixes
        name = self.name.strip()
        name = re.sub(r'\b(Dr\.?|Mr\.?|Ms\.?|Mrs\.?|Prof\.?)\s+', '', name, flags=re.IGNORECASE)
        name = re.sub(r'\s+(Jr\.?|Sr\.?|III|IV|V)\b', '', name, flags=re.IGNORECASE)

        # Remove trailing periods
        name = name.rstrip('.')

        return name.strip()

    @property
    def search_name(self) -> str:
        """Return name optimized for search queries."""
        name = self.normalized_name

        # For search, use first name + last name only
        parts = name.split()
        if len(parts) >= 2:
            return f"{parts[0]} {parts[-1]}"
        return name

    @property
    def has_domain(self) -> bool:
        """Check if we have a domain for targeted search."""
        return bool(self.domain and self.domain != "unknown")

    @property
    def has_company(self) -> bool:
        """Check if we have company information."""
        return bool(self.company and self.company.strip())

    def get_search_queries(self) -> List[str]:
        """
        Generate search queries for this person.

        Returns:
            List of search query strings optimized for news search
        """
        queries = []

        # Query A: Site-specific search if we have domain
        if self.has_domain:
            site_query = f'site:{self.domain}'
            if self.search_name:
                site_query += f' "{self.search_name}"'
            queries.append(site_query)

        # Query B: Name + (domain OR company)
        if self.search_name:
            name_query = f'"{self.search_name}"'

            # Add domain if available
            if self.has_domain:
                name_query += f' "{self.domain}"'

            # Add company if available and different from domain
            if self.has_company and self.company != self.domain:
                name_query += f' "{self.company}"'

            queries.append(name_query)

        return queries

    def get_confidence_anchors(self) -> List[str]:
        """
        Get terms that should boost confidence when found in search results.

        Returns:
            List of terms that indicate this is the right person
        """
        anchors = []

        if self.domain:
            anchors.append(self.domain)

        if self.company:
            anchors.append(self.company)

        # Add normalized company name variations
        if self.company:
            # Remove common corporate suffixes
            company_base = re.sub(r'\s+(Inc\.?|LLC|Corp\.?|Ltd\.?|Co\.?)$', '', self.company, flags=re.IGNORECASE)
            if company_base != self.company:
                anchors.append(company_base)

        # Add co-attendee domains as weak anchors
        anchors.extend(self.co_attendee_domains)

        return anchors

    def get_negative_keywords(self) -> List[str]:
        """
        Get terms that should reduce confidence when found in search results.

        Returns:
            List of terms that suggest this might be the wrong person
        """
        negatives = []

        # Common false positive patterns
        negatives.extend([
            "obituary", "death", "died", "funeral", "memorial",
            "arrest", "charged", "convicted", "sentenced",
            "scandal", "fraud", "lawsuit", "settlement"
        ])

        # Add person-specific negatives if available
        # This could be extended with profile overrides
        negatives.extend(self.keywords)

        return negatives


def extract_domain_from_email(email: str) -> Optional[str]:
    """
    Extract domain from email address.

    Args:
        email: Email address string

    Returns:
        Domain string or None if invalid
    """
    if not email or '@' not in email:
        return None

    try:
        domain = email.split('@')[1].lower().strip()
        # Basic validation
        if '.' in domain and len(domain) > 3:
            return domain
    except (IndexError, AttributeError):
        pass

    return None


def normalize_company_name(company: str) -> str:
    """
    Normalize company name for better matching.

    Args:
        company: Raw company name

    Returns:
        Normalized company name
    """
    if not company:
        return ""

    # Remove common corporate suffixes (only if they're actual suffixes)
    # Be more conservative to avoid removing legitimate company name parts
    normalized = re.sub(r'\s+(Inc\.?|LLC|Ltd\.?|Co\.?)$', '', company, flags=re.IGNORECASE)
    # Only remove "Corp" if it's clearly a suffix (like "Company Corp" -> "Company")
    # Don't remove "Corp" from names like "Example Corp" as it's part of the name

    # Remove extra whitespace
    normalized = re.sub(r'\s+', ' ', normalized).strip()

    return normalized


def build_person_hint(
    attendee: Dict[str, Any],
    meeting_context: Dict[str, Any]
) -> PersonHint:
    """
    Build a PersonHint from attendee data and meeting context.

    Args:
        attendee: Attendee data dictionary
        meeting_context: Meeting context with other attendees, keywords, etc.

    Returns:
        PersonHint object with extracted metadata
    """
    name = attendee.get("name", "").strip()
    email = attendee.get("email", "").strip()
    company = attendee.get("company", "").strip()
    title = attendee.get("title", "").strip()

    # Extract domain from email
    domain = extract_domain_from_email(email) if email else None

    # Normalize company name
    company_normalized = normalize_company_name(company) if company else None

    # Extract co-attendee domains
    co_attendee_domains = []
    if "attendees" in meeting_context:
        for other_attendee in meeting_context["attendees"]:
            if other_attendee.get("name") != name:  # Don't include self
                other_email = other_attendee.get("email", "")
                other_domain = extract_domain_from_email(other_email)
                if other_domain and other_domain != domain:
                    co_attendee_domains.append(other_domain)

    # Extract keywords from meeting context
    keywords = []
    if "subject" in meeting_context:
        # Extract potential keywords from meeting subject
        subject = meeting_context["subject"]
        # Simple keyword extraction - could be enhanced
        words = re.findall(r'\b[A-Z][a-z]+\b', subject)
        keywords.extend(words[:3])  # Limit to first 3 capitalized words

    return PersonHint(
        name=name,
        email=email,
        domain=domain,
        company=company_normalized,
        title=title,
        co_attendee_domains=co_attendee_domains,
        keywords=keywords
    )


def is_internal_attendee(person_hint: PersonHint, internal_domains: List[str] = None) -> bool:
    """
    Check if an attendee is internal (company employee).

    Args:
        person_hint: PersonHint object
        internal_domains: List of internal company domains

    Returns:
        True if attendee appears to be internal
    """
    if not internal_domains:
        internal_domains = ["rpck.com", "rpckllp.com"]  # Default internal domains

    if person_hint.domain:
        return person_hint.domain.lower() in [d.lower() for d in internal_domains]

    return False
