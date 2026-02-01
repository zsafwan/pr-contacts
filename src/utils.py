"""Utility functions for PR Contacts Extractor."""

import re
from datetime import datetime


def clean_email(email: str) -> str:
    """Clean and normalize an email address."""
    if not email:
        return ""
    return email.lower().strip()


def clean_name(name: str) -> str:
    """Clean and normalize a contact name."""
    if not name:
        return ""

    # Remove quotes
    name = re.sub(r'^["\']|["\']$', "", name)

    # Remove email addresses
    name = re.sub(r"<[^>]+>", "", name)

    # Remove extra whitespace
    name = " ".join(name.split())

    return name.strip()


def truncate_text(text: str, max_length: int = 500) -> str:
    """Truncate text to max length, preserving word boundaries."""
    if not text or len(text) <= max_length:
        return text

    truncated = text[:max_length]
    # Find last space to avoid cutting words
    last_space = truncated.rfind(" ")
    if last_space > max_length * 0.8:
        truncated = truncated[:last_space]

    return truncated + "..."


def format_phone(phone: str) -> str:
    """Format a phone number for display."""
    if not phone:
        return ""

    # Remove all non-digit characters except +
    digits = re.sub(r"[^\d+]", "", phone)

    # Format US numbers
    if len(digits) == 10:
        return f"({digits[:3]}) {digits[3:6]}-{digits[6:]}"
    elif len(digits) == 11 and digits[0] == "1":
        return f"+1 ({digits[1:4]}) {digits[4:7]}-{digits[7:]}"

    # Return cleaned but unformatted for international
    return phone


def is_valid_email(email: str) -> bool:
    """Check if string is a valid email address."""
    if not email:
        return False

    pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
    return bool(re.match(pattern, email))


def format_datetime(dt: datetime) -> str:
    """Format datetime for display."""
    if not dt:
        return ""
    return dt.strftime("%Y-%m-%d %H:%M")


def format_date(dt: datetime) -> str:
    """Format date for display."""
    if not dt:
        return ""
    return dt.strftime("%Y-%m-%d")


def parse_email_domain(email: str) -> str:
    """Extract domain from email address."""
    if not email or "@" not in email:
        return ""
    return email.split("@")[1].lower()


def is_personal_email(email: str) -> bool:
    """Check if email is from a personal email provider."""
    personal_domains = [
        "gmail.com",
        "yahoo.com",
        "hotmail.com",
        "outlook.com",
        "aol.com",
        "icloud.com",
        "me.com",
        "mac.com",
        "live.com",
        "msn.com",
    ]

    domain = parse_email_domain(email)
    return domain in personal_domains


def progress_bar(current: int, total: int, width: int = 50) -> str:
    """Create a text progress bar."""
    if total == 0:
        return "[" + "=" * width + "] 100%"

    progress = current / total
    filled = int(width * progress)
    bar = "=" * filled + "-" * (width - filled)
    percent = int(progress * 100)

    return f"[{bar}] {percent}% ({current}/{total})"


def get_second_level_domain(email: str) -> str:
    """
    Extract second-level domain from email address.

    Handles subdomains and compound TLDs like .co.uk

    Examples:
        john@pr.edelman.com -> edelman.com
        jane@company.co.uk -> company.co.uk
        user@example.com -> example.com
    """
    if not email or "@" not in email:
        return ""

    domain = email.split("@")[1].lower()
    parts = domain.split(".")

    if len(parts) < 2:
        return domain

    # Handle compound TLDs (.co.uk, .com.au, .co.za, etc.)
    compound_tlds = {"co", "com", "org", "net", "gov", "edu", "ac"}

    if len(parts) >= 3 and parts[-2] in compound_tlds:
        return ".".join(parts[-3:])

    return ".".join(parts[-2:])
