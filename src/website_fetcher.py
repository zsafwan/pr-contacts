"""Fetch company names from websites when not found in email signatures."""

import re
from typing import Optional
from functools import lru_cache

import requests
from requests.exceptions import RequestException


class WebsiteFetcher:
    """Fetch company names from corporate websites."""

    # User agent to avoid being blocked
    USER_AGENT = "Mozilla/5.0 (compatible; PRContactsBot/1.0)"

    # Request timeout in seconds
    TIMEOUT = 10

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": self.USER_AGENT})

    @lru_cache(maxsize=500)
    def fetch_company_name(self, domain: str) -> Optional[str]:
        """
        Fetch company name from a domain's website.

        Args:
            domain: The email domain (e.g., "edelman.com")

        Returns:
            Company name if found, None otherwise
        """
        if not domain or self._is_personal_domain(domain):
            return None

        # Try HTTPS first, fall back to HTTP
        for protocol in ["https", "http"]:
            url = f"{protocol}://{domain}"
            try:
                response = self.session.get(
                    url,
                    timeout=self.TIMEOUT,
                    allow_redirects=True,
                )
                response.raise_for_status()

                # Extract company name from HTML
                company = self._extract_company_from_html(response.text)
                if company:
                    return company

            except RequestException:
                continue

        return None

    def _extract_company_from_html(self, html: str) -> Optional[str]:
        """
        Extract company name from HTML content.

        Priority:
        1. og:site_name meta tag (most reliable)
        2. application-name meta tag
        3. title tag (cleaned)
        """
        # Try og:site_name meta tag first (most reliable)
        og_match = re.search(
            r'<meta\s+[^>]*property=["\']og:site_name["\'][^>]*content=["\']([^"\']+)["\']',
            html,
            re.IGNORECASE
        )
        if not og_match:
            # Try alternate order (content before property)
            og_match = re.search(
                r'<meta\s+[^>]*content=["\']([^"\']+)["\'][^>]*property=["\']og:site_name["\']',
                html,
                re.IGNORECASE
            )
        if og_match:
            name = self._clean_company_name(og_match.group(1))
            if name:
                return name

        # Try application-name meta tag
        app_match = re.search(
            r'<meta\s+[^>]*name=["\']application-name["\'][^>]*content=["\']([^"\']+)["\']',
            html,
            re.IGNORECASE
        )
        if not app_match:
            app_match = re.search(
                r'<meta\s+[^>]*content=["\']([^"\']+)["\'][^>]*name=["\']application-name["\']',
                html,
                re.IGNORECASE
            )
        if app_match:
            name = self._clean_company_name(app_match.group(1))
            if name:
                return name

        # Fall back to title tag
        title_match = re.search(r'<title[^>]*>([^<]+)</title>', html, re.IGNORECASE)
        if title_match:
            name = self._clean_title_to_company(title_match.group(1))
            if name:
                return name

        return None

    def _clean_company_name(self, name: str) -> Optional[str]:
        """Clean up an extracted company name."""
        if not name:
            return None

        # Decode HTML entities
        name = name.replace("&amp;", "&")
        name = name.replace("&quot;", '"')
        name = name.replace("&#39;", "'")
        name = name.replace("&nbsp;", " ")

        # Strip whitespace
        name = name.strip()

        # Skip if too short or too long
        if len(name) < 2 or len(name) > 100:
            return None

        # Skip generic names
        generic_names = [
            "home", "homepage", "welcome", "official site",
            "official website", "website", "page", "index",
        ]
        if name.lower() in generic_names:
            return None

        return name

    def _clean_title_to_company(self, title: str) -> Optional[str]:
        """
        Extract company name from a page title.

        Titles often have format: "Company Name | Tagline" or "Company Name - Description"
        """
        if not title:
            return None

        # Split on common delimiters and take the first part
        for delimiter in [" | ", " - ", " – ", " — ", " :: ", " : "]:
            if delimiter in title:
                parts = title.split(delimiter)
                # Usually company name is first, but sometimes last
                candidate = parts[0].strip()
                if len(candidate) >= 2:
                    return self._clean_company_name(candidate)

        # If no delimiter, use the whole title if it looks like a company name
        cleaned = self._clean_company_name(title)
        if cleaned and len(cleaned.split()) <= 5:
            return cleaned

        return None

    def _is_personal_domain(self, domain: str) -> bool:
        """Check if domain is a personal email provider."""
        personal_domains = {
            "gmail.com", "yahoo.com", "hotmail.com", "outlook.com",
            "aol.com", "icloud.com", "me.com", "mac.com", "live.com",
            "msn.com", "protonmail.com", "zoho.com", "yandex.com",
        }
        return domain.lower() in personal_domains

    def get_company_for_email(self, email: str) -> Optional[str]:
        """
        Convenience method to get company name from an email address.

        Args:
            email: Full email address (e.g., "john@edelman.com")

        Returns:
            Company name if found, None otherwise
        """
        if not email or "@" not in email:
            return None

        domain = email.split("@")[1].lower()
        return self.fetch_company_name(domain)
