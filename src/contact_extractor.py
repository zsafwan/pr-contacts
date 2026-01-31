"""Extract contact information from emails."""

import re
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ExtractedContact:
    """Container for extracted contact information."""

    name: str = ""
    email: str = ""
    company: str = ""
    title: str = ""
    phone: str = ""
    additional_emails: list[str] = field(default_factory=list)


class ContactExtractor:
    """Extract contact information from email headers and body."""

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

                # Extract additional emails
                additional_emails = self._extract_emails(signature, contact.email)
                contact.additional_emails = additional_emails

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
        for pattern in self.PHONE_PATTERNS:
            match = re.search(pattern, text)
            if match:
                phone = match.group()
                # Clean up the phone number
                phone = re.sub(r"[^\d+\-().\s]", "", phone).strip()
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

            # Check for title keywords
            for keyword in self.TITLE_KEYWORDS:
                if keyword in line_lower:
                    # Clean up the title
                    # Remove common prefixes/suffixes
                    title = re.sub(r"^[|\-•]\s*", "", line)
                    title = re.sub(r"\s*[|\-•]\s*$", "", title)
                    title = title.strip()

                    # Validate it's not too long (probably not a title)
                    if len(title) < 100:
                        return title

        return ""

    def _extract_company(self, signature: str, contact_name: str) -> str:
        """Extract company name from signature."""
        lines = signature.split("\n")
        contact_name_lower = contact_name.lower() if contact_name else ""

        for line in lines:
            line = line.strip()
            if not line or len(line) < 2:
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

            # Check for agency indicators
            for indicator in self.AGENCY_INDICATORS:
                if indicator in line_lower:
                    # Clean up company name
                    company = re.sub(r"^[|\-•]\s*", "", line)
                    company = re.sub(r"\s*[|\-•]\s*$", "", company)
                    company = company.strip()

                    if len(company) < 100:
                        return company

        # Try to find a capitalized line that might be company name
        for line in lines:
            line = line.strip()
            if not line or len(line) < 2 or len(line) > 50:
                continue

            # Skip if it's the name
            if contact_name_lower and line.lower() == contact_name_lower:
                continue

            # Skip lines with emails, phones, or URLs
            if re.search(self.EMAIL_PATTERN, line):
                continue
            if any(re.search(p, line) for p in self.PHONE_PATTERNS):
                continue
            if "http" in line.lower() or "www." in line.lower():
                continue

            # Check if line is mostly capitalized words (potential company)
            words = line.split()
            if len(words) >= 1 and len(words) <= 5:
                capitalized = sum(1 for w in words if w[0].isupper())
                if capitalized == len(words):
                    # Check it's not a title line
                    if not any(kw in line.lower() for kw in self.TITLE_KEYWORDS):
                        return line

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
