"""Extract contact information from emails."""

import re
from dataclasses import dataclass, field
from typing import Optional

from .country_detector import CountryDetector


@dataclass
class ExtractedContact:
    """Container for extracted contact information."""

    name: str = ""
    email: str = ""
    company: str = ""
    title: str = ""
    phone: str = ""
    additional_emails: list[str] = field(default_factory=list)
    country: str = ""
    country_code: str = ""
    country_source: str = ""
    company_source: str = ""  # signature, website, ai


class ContactExtractor:
    """Extract contact information from email headers and body."""

    def __init__(self):
        self.country_detector = CountryDetector()

    # Common signature delimiters
    SIGNATURE_DELIMITERS = [
        r"^--\s*$",
        r"^---\s*$",
        r"^_{3,}\s*$",
        r"^-{3,}\s*$",
        r"^Best\s*(?:regards|wishes)?,?\s*$",
        r"^Kind\s+regards?,?\s*$",
        r"^Regards?,?\s*$",
        r"^Thanks?,?\s*$",
        r"^Thank\s+you,?\s*$",
        r"^Cheers?,?\s*$",
        r"^Sincerely,?\s*$",
        r"^Warm\s+regards?,?\s*$",
        r"^All\s+the\s+best,?\s*$",
        r"^Sent\s+from\s+my\s+",
    ]

    # Phone number patterns
    PHONE_PATTERNS = [
        r"\+?1?[-.\s]?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}",  # US format
        r"\+\d{1,3}[-.\s]?\d{1,4}[-.\s]?\d{1,4}[-.\s]?\d{1,9}",  # International
        r"\(\d{3}\)\s*\d{3}[-.\s]?\d{4}",  # (xxx) xxx-xxxx
        r"\d{3}[-.\s]\d{3}[-.\s]\d{4}",  # xxx-xxx-xxxx
    ]

    # Email pattern
    EMAIL_PATTERN = r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"

    # Job title keywords
    TITLE_KEYWORDS = [
        "manager",
        "director",
        "coordinator",
        "specialist",
        "executive",
        "officer",
        "president",
        "vp",
        "vice president",
        "head of",
        "lead",
        "senior",
        "junior",
        "associate",
        "assistant",
        "pr ",
        "public relations",
        "communications",
        "media relations",
        "press",
        "marketing",
        "brand",
        "account",
        "consultant",
        "strategist",
        "analyst",
        "editor",
        "writer",
        "publicist",
        "founder",
        "ceo",
        "coo",
        "cmo",
        "chief",
    ]

    # Common PR agency indicators
    AGENCY_INDICATORS = [
        "pr",
        "public relations",
        "communications",
        "agency",
        "consulting",
        "media",
        "marketing",
        "group",
        "partners",
        "associates",
    ]

    # Company legal suffix patterns (strong indicator it's a company, not title)
    COMPANY_SUFFIXES = [
        r"\bInc\.?$",
        r"\bLLC\.?$",
        r"\bLtd\.?$",
        r"\bLimited$",
        r"\bCorp\.?$",
        r"\bCorporation$",
        r"\bGmbH$",
        r"\bPLC$",
        r"\bAgency$",
        r"\bGroup$",
        r"\bHoldings?$",
        r"\bEnterprises?$",
        r"\bCompany$",
        r"\bCo\.?$",
        r"\bL\.?L\.?C\.?$",
        r"\bFZE$",
        r"\bFZC$",
        r"\bFZ-LLC$",
        r"\bW\.?L\.?L\.?$",  # With Limited Liability (Middle East)
    ]

    # Title suffix patterns (strong indicator it's a title, not company)
    TITLE_SUFFIXES = [
        r"Manager$",
        r"Director$",
        r"Executive$",
        r"Consultant$",
        r"Specialist$",
        r"Coordinator$",
        r"Lead$",
        r"Officer$",
        r"President$",
        r"Analyst$",
        r"Strategist$",
        r"Advisor$",
        r"Administrator$",
        r"Supervisor$",
        r"Representative$",
    ]

    # False positive phrases to filter out
    FALSE_POSITIVE_PHRASES = [
        "unsubscribe",
        "click here",
        "click below",
        "view in browser",
        "view online",
        "privacy policy",
        "terms of service",
        "terms and conditions",
        "manage preferences",
        "update preferences",
        "opt out",
        "opt-out",
        "forward to a friend",
        "sent from my",
        "powered by",
        "this email was sent",
        "to stop receiving",
        "copyright",
        "all rights reserved",
        "if you no longer",
        "log in",
        "login",
        "sign in",
        "sign up",
        "register",
        "download",
        "read more",
        "learn more",
        "follow us",
        "connect with us",
        "visit our",
        "disclaimer",
        "confidential",
        "this message",
        "intended recipient",
        "legal notice",
    ]

    # Invalid company names
    INVALID_COMPANY_NAMES = [
        "the team",
        "team",
        "unsubscribe",
        "subscribe",
        "share",
        "forward",
        "reply",
        "contact",
        "email",
        "phone",
        "mobile",
        "office",
        "direct",
        "website",
        "address",
        "price",
        "notes to",
        "about",
    ]

    # Patterns that indicate NOT a valid title (article headlines, etc.)
    INVALID_TITLE_PATTERNS = [
        r"how to",
        r"step-by-step",
        r"guide",
        r"tips for",
        r"ways to",
        r"things you",
        r"what you need",
        r"why you should",
        r"introducing",
        r"announcing",
        r"breaking:",
        r"exclusive:",
        r"new:",
        r"notes to editors",
        r"about the",
        r"about us",
        r"for immediate",
        r"press release",
        r"©",
        r"<[a-z]",  # HTML tags
        r"&[a-z]+;",  # HTML entities
    ]

    def extract_from_email(self, email_data: dict) -> ExtractedContact:
        """
        Extract contact information from an email.

        Args:
            email_data: Dictionary with from_name, from_email, body

        Returns:
            ExtractedContact with extracted information
        """
        contact = ExtractedContact(
            name=email_data.get("from_name", ""),
            email=email_data.get("from_email", ""),
        )

        body = email_data.get("body", "")
        signature = ""
        if body:
            # Extract signature block
            signature = self._extract_signature(body)

            if signature:
                # Extract phone
                phone = self._extract_phone(signature)
                if phone:
                    contact.phone = phone

                # Extract title
                title = self._extract_title(signature)
                if title:
                    contact.title = title

                # Extract company
                company = self._extract_company(signature, contact.name)
                if company:
                    contact.company = company
                    contact.company_source = "signature"

                # Extract additional emails
                additional_emails = self._extract_emails(signature, contact.email)
                contact.additional_emails = additional_emails

        # Detect country from phone, email, or signature
        country_result = self.country_detector.detect(
            phone=contact.phone,
            email=contact.email,
            signature=signature,
        )
        if country_result:
            contact.country = country_result.country
            contact.country_code = country_result.country_code
            contact.country_source = country_result.source

        # Clean up name
        contact.name = self._clean_name(contact.name)

        return contact

    def _extract_signature(self, body: str) -> str:
        """Extract the signature block from email body."""
        lines = body.split("\n")

        # Find signature delimiter
        sig_start = None
        for i, line in enumerate(lines):
            for pattern in self.SIGNATURE_DELIMITERS:
                if re.match(pattern, line.strip(), re.IGNORECASE):
                    sig_start = i
                    break
            if sig_start is not None:
                break

        # If no delimiter found, try last 15 lines
        if sig_start is None:
            # Look for name-like line followed by title/company patterns
            for i in range(max(0, len(lines) - 15), len(lines)):
                line = lines[i].strip()
                # Skip empty lines and quoted text
                if not line or line.startswith(">"):
                    continue
                # Check if this looks like start of signature
                if self._looks_like_signature_start(line, lines[i:]):
                    sig_start = i
                    break

        if sig_start is not None:
            return "\n".join(lines[sig_start:])

        # Fall back to last 10 lines
        return "\n".join(lines[-10:])

    def _looks_like_signature_start(self, line: str, remaining_lines: list[str]) -> bool:
        """Check if a line looks like the start of a signature."""
        # Check remaining lines for signature indicators
        remaining_text = "\n".join(remaining_lines[:10]).lower()

        # Look for typical signature elements
        has_phone = any(re.search(p, remaining_text) for p in self.PHONE_PATTERNS)
        has_email = re.search(self.EMAIL_PATTERN, remaining_text) is not None
        has_title = any(kw in remaining_text for kw in self.TITLE_KEYWORDS)

        return has_phone or (has_email and has_title)

    def _extract_phone(self, text: str) -> str:
        """Extract phone number from text."""
        # Split text into lines and check each line
        for line in text.split("\n"):
            line_lower = line.lower()

            # Skip lines with false positive phrases
            if any(fp in line_lower for fp in self.FALSE_POSITIVE_PHRASES):
                continue

            # Skip lines that look like URLs or IDs
            if "http" in line_lower or "www." in line_lower:
                continue

            for pattern in self.PHONE_PATTERNS:
                match = re.search(pattern, line)
                if match:
                    phone = match.group()
                    # Clean up the phone number
                    phone = re.sub(r"[^\d+\-().\s]", "", phone).strip()

                    # Validate: must have some formatting characters or start with +
                    # This filters out random digit sequences
                    digits_only = re.sub(r"[^\d]", "", phone)
                    has_formatting = (
                        "+" in phone
                        or "-" in phone
                        or "(" in phone
                        or "." in phone
                        or " " in phone.strip()
                    )

                    # Accept if properly formatted OR if it's a reasonable length with +
                    if has_formatting and 7 <= len(digits_only) <= 15:
                        return phone

        return ""

    def _extract_title(self, signature: str) -> str:
        """Extract job title from signature."""
        lines = signature.split("\n")

        for line in lines:
            line = line.strip()
            if not line:
                continue

            line_lower = line.lower()

            # Skip false positive phrases
            if any(fp in line_lower for fp in self.FALSE_POSITIVE_PHRASES):
                continue

            # Skip invalid title patterns (headlines, articles, etc.)
            if any(re.search(p, line_lower) for p in self.INVALID_TITLE_PATTERNS):
                continue

            # Skip lines with URLs
            if "http" in line_lower or "www." in line_lower:
                continue

            # Skip lines with HTML
            if "<" in line and ">" in line:
                continue

            # Skip lines that are too long (probably not a title)
            if len(line) > 60:
                continue

            # Skip lines that are too short
            if len(line) < 5:
                continue

            # Skip if line ends with a company suffix (it's a company, not title)
            if any(re.search(pattern, line, re.IGNORECASE) for pattern in self.COMPANY_SUFFIXES):
                continue

            # Check if line ends with a title suffix (high confidence it's a title)
            if any(re.search(pattern, line, re.IGNORECASE) for pattern in self.TITLE_SUFFIXES):
                title = re.sub(r"^[|\-•]\s*", "", line)
                title = re.sub(r"\s*[|\-•]\s*$", "", title)
                title = title.strip()
                if len(title) >= 5:
                    return title

            # Check for title keywords
            for keyword in self.TITLE_KEYWORDS:
                if keyword in line_lower:
                    # Clean up the title
                    # Remove common prefixes/suffixes
                    title = re.sub(r"^[|\-•]\s*", "", line)
                    title = re.sub(r"\s*[|\-•]\s*$", "", title)
                    title = title.strip()

                    # Additional validation
                    # Title should have at least 2 words
                    words = title.split()
                    if len(words) < 2:
                        continue

                    # Title should not have too many words
                    if len(words) > 8:
                        continue

                    # Title should not contain obvious non-title patterns
                    if any(fp in title.lower() for fp in self.FALSE_POSITIVE_PHRASES):
                        continue

                    # Title shouldn't end with punctuation that indicates a headline
                    if title.endswith(":") or title.endswith("?") or title.endswith("!"):
                        continue

                    return title

        return ""

    def _extract_company(self, signature: str, contact_name: str) -> str:
        """Extract company name from signature."""
        lines = signature.split("\n")
        contact_name_lower = contact_name.lower() if contact_name else ""

        for line in lines:
            line = line.strip()
            if not line or len(line) < 3:
                continue

            # Skip lines that are the contact's name
            if contact_name_lower and line.lower() == contact_name_lower:
                continue

            # Skip lines with phone numbers or emails
            if re.search(self.EMAIL_PATTERN, line):
                continue
            if any(re.search(p, line) for p in self.PHONE_PATTERNS):
                continue

            line_lower = line.lower()

            # Skip false positive phrases
            if any(fp in line_lower for fp in self.FALSE_POSITIVE_PHRASES):
                continue

            # Skip invalid company names
            if any(line_lower == inv or line_lower.startswith(inv + " ") or line_lower.endswith(":" ) for inv in self.INVALID_COMPANY_NAMES):
                continue

            # Skip lines with URLs
            if "http" in line_lower or "www." in line_lower:
                continue

            # Skip lines with HTML
            if "<" in line and ">" in line:
                continue

            # Skip lines with HTML entities or copyright symbols
            if "©" in line or "&" in line:
                continue

            # Skip lines that look like awards or date references
            if re.search(r"\b20\d{2}\b", line):  # Contains a year like 2024, 2023, etc.
                continue

            # Skip lines that are too long
            if len(line) > 50:
                continue

            # Check if line ends with a company suffix (high confidence)
            if any(re.search(pattern, line, re.IGNORECASE) for pattern in self.COMPANY_SUFFIXES):
                company = re.sub(r"^[|\-•]\s*", "", line)
                company = re.sub(r"\s*[|\-•]\s*$", "", company)
                company = company.strip()
                if len(company) >= 3:
                    return company

            # Skip if it ends with a title suffix (it's a job title, not company)
            if any(re.search(pattern, line, re.IGNORECASE) for pattern in self.TITLE_SUFFIXES):
                continue

            # Check for agency indicators
            for indicator in self.AGENCY_INDICATORS:
                if indicator in line_lower:
                    # Clean up company name
                    company = re.sub(r"^[|\-•]\s*", "", line)
                    company = re.sub(r"\s*[|\-•]\s*$", "", company)
                    company = company.strip()

                    # Skip if it matches a title keyword more strongly
                    title_matches = sum(1 for kw in self.TITLE_KEYWORDS if kw in company.lower())
                    if title_matches > 0 and indicator in ["media", "communications", "marketing"]:
                        # Could be a title like "Media Relations Manager"
                        continue

                    if len(company) >= 3 and len(company) < 50:
                        return company

        return ""

    def _extract_emails(self, text: str, primary_email: str) -> list[str]:
        """Extract additional email addresses from text."""
        emails = re.findall(self.EMAIL_PATTERN, text)
        primary_lower = primary_email.lower() if primary_email else ""

        # Filter out primary email and common false positives
        additional = []
        for email in emails:
            email_lower = email.lower()
            if email_lower == primary_lower:
                continue
            # Skip common non-personal emails
            if any(x in email_lower for x in ["noreply", "no-reply", "support@", "info@", "hello@", "contact@"]):
                continue
            if email_lower not in [e.lower() for e in additional]:
                additional.append(email)

        return additional

    def _clean_name(self, name: str) -> str:
        """Clean up a contact name."""
        if not name:
            return ""

        # Remove common suffixes
        name = re.sub(r"\s*\([^)]+\)\s*$", "", name)  # Remove (Company)
        name = re.sub(r"\s*<[^>]+>\s*$", "", name)  # Remove <email>
        name = re.sub(r'^"(.+)"$', r"\1", name)  # Remove quotes

        # Remove common prefixes
        name = re.sub(r"^PR:\s*", "", name, flags=re.IGNORECASE)
        name = re.sub(r"^RE:\s*", "", name, flags=re.IGNORECASE)

        return name.strip()
