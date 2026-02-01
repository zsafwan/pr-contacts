"""Resolve company names from email domains using multiple strategies."""

import re
from typing import Optional, Tuple
from functools import lru_cache


class CompanyResolver:
    """
    Resolve company names from email addresses using multiple strategies:
    1. Known PR agency domain mapping (fast, accurate)
    2. Website fetching (accurate, slower)
    3. Domain name formatting (fallback, always works)
    """

    # Known PR agency and company domain mappings
    # Format: domain -> Company Name
    KNOWN_DOMAINS = {
        # Global PR Agencies
        "edelman.com": "Edelman",
        "bursonglobal.com": "Burson Global",
        "mena.bursonglobal.com": "Burson Global MENA",
        "ae.bursonglobal.com": "Burson Global UAE",
        "webershandwick.com": "Weber Shandwick",
        "golin.com": "Golin",
        "golin-mena.com": "Golin MENA",
        "fleishman.com": "FleishmanHillard",
        "fleishmanhillard.com": "FleishmanHillard",
        "hillandknowlton.com": "Hill & Knowlton",
        "hkstrategies.com": "H+K Strategies",
        "ketchum.com": "Ketchum",
        "mslgroup.com": "MSL Group",
        "ogilvy.com": "Ogilvy",
        "ogilvypr.com": "Ogilvy PR",
        "bcw-global.com": "BCW Global",
        "cohnwolfe.com": "Cohn & Wolfe",
        "prweek.com": "PRWeek",
        "teamlewis.com": "TEAM LEWIS",
        "media.teamlewis.com": "TEAM LEWIS",
        "currentglobal.com": "Current Global",
        "redhavas.com": "Red Havas",
        "havas.com": "Havas",
        "havaspr.com": "Havas PR",
        "ruderfinninc.com": "Ruder Finn",
        "ruderfinn.com": "Ruder Finn",
        "icrinc.com": "ICR",
        "sardverb.com": "Sard Verbinnen",
        "fticonsulting.com": "FTI Consulting",
        "brunswickgroup.com": "Brunswick Group",
        "finsbury.com": "Finsbury",
        "prosek.com": "Prosek Partners",
        "sloanecompany.com": "Sloane & Company",
        "joelefrank.com": "Joele Frank",
        "teneo.com": "Teneo",
        "publicisgroupe.com": "Publicis Groupe",
        "mccann.com": "McCann",
        "wpp.com": "WPP",
        "omnicomgroup.com": "Omnicom Group",
        "ipghealth.com": "IPG Health",
        "interpublic.com": "Interpublic Group",
        "dentsu.com": "Dentsu",

        # Middle East PR Agencies
        "brazenmena.com": "Brazen MENA",
        "gambit.ae": "Gambit Communications",
        "jspr.ae": "JS PR",
        "activedmc.com": "Active DMC",
        "matrixdubai.com": "Matrix PR",
        "matrixpr.ae": "Matrix PR",
        "actionprgroup.com": "Action PR Group",
        "actionglobalcomms.com": "Action Global Communications",
        "fourpr.com": "Four Communications",
        "fourcommunications.com": "Four Communications",
        "aaborchid.com": "Orchid Communications",
        "sevenme.com": "Seven Media",
        "sevenmedia.ae": "Seven Media",
        "asaborini.com": "Asda'a BCW",
        "asdaa-bcw.com": "Asda'a BCW",
        "prochoicecomms.com": "ProChoice Communications",
        "therocketscience.com": "Rocket Science",
        "tishcomms.com": "TISH Communications",
        "traccs.net": "TRACCS",
        "w7worldwide.com": "W7Worldwide",
        "watermelon.ae": "Watermelon Communications",
        "crestadv.com": "Crest Communications",
        "houseofcomms.com": "House of Comms",
        "theqode.com": "The Qode",
        "sherwoodcomms.com": "Sherwood Communications",
        "epressrelease.me": "ePressPR",
        "katchthis.com": "Katch Communications",
        "cisionone.cision.com": "Cision",
        "cision.com": "Cision",

        # Tech Companies
        "google.com": "Google",
        "microsoft.com": "Microsoft",
        "apple.com": "Apple",
        "amazon.com": "Amazon",
        "meta.com": "Meta",
        "facebook.com": "Meta",
        "netflix.com": "Netflix",
        "salesforce.com": "Salesforce",
        "oracle.com": "Oracle",
        "ibm.com": "IBM",
        "intel.com": "Intel",
        "nvidia.com": "NVIDIA",
        "adobe.com": "Adobe",
        "cisco.com": "Cisco",
        "samsung.com": "Samsung",
        "huawei.com": "Huawei",
        "dell.com": "Dell",
        "hp.com": "HP",
        "lenovo.com": "Lenovo",

        # Hospitality & Travel
        "marriott.com": "Marriott International",
        "hilton.com": "Hilton",
        "ihg.com": "IHG Hotels & Resorts",
        "accor.com": "Accor",
        "hyatt.com": "Hyatt",
        "fourseasons.com": "Four Seasons",
        "fairmont.com": "Fairmont Hotels",
        "raffles.com": "Raffles Hotels",
        "ritzcarlton.com": "The Ritz-Carlton",
        "starwoodhotels.com": "Starwood Hotels",
        "emirates.com": "Emirates",
        "etihad.ae": "Etihad Airways",
        "qatarairways.com": "Qatar Airways",
        "saudia.com": "Saudia",
        "flydubai.com": "flydubai",

        # Automotive
        "bmw.com": "BMW",
        "mercedes-benz.com": "Mercedes-Benz",
        "audi.com": "Audi",
        "volkswagen.com": "Volkswagen",
        "toyota.com": "Toyota",
        "honda.com": "Honda",
        "nissan.com": "Nissan",
        "ford.com": "Ford",
        "gm.com": "General Motors",
        "tesla.com": "Tesla",
        "porsche.com": "Porsche",
        "ferrari.com": "Ferrari",
        "lamborghini.com": "Lamborghini",
        "bentley.com": "Bentley",
        "rollsroyce.com": "Rolls-Royce",
        "landrover.com": "Land Rover",
        "jaguar.com": "Jaguar",

        # Finance
        "jpmorgan.com": "JP Morgan",
        "goldmansachs.com": "Goldman Sachs",
        "morganstanley.com": "Morgan Stanley",
        "bankofamerica.com": "Bank of America",
        "citi.com": "Citi",
        "citibank.com": "Citibank",
        "hsbc.com": "HSBC",
        "barclays.com": "Barclays",
        "deutschebank.com": "Deutsche Bank",
        "ubs.com": "UBS",
        "creditsuisse.com": "Credit Suisse",
        "visa.com": "Visa",
        "mastercard.com": "Mastercard",
        "americanexpress.com": "American Express",
        "paypal.com": "PayPal",
    }

    # Domains to skip (personal email providers)
    PERSONAL_DOMAINS = {
        "gmail.com", "yahoo.com", "hotmail.com", "outlook.com",
        "aol.com", "icloud.com", "me.com", "mac.com", "live.com",
        "msn.com", "protonmail.com", "zoho.com", "yandex.com",
        "mail.com", "gmx.com", "inbox.com",
    }

    def __init__(self, website_fetcher=None):
        """
        Initialize the company resolver.

        Args:
            website_fetcher: Optional WebsiteFetcher instance for fetching from websites
        """
        self.website_fetcher = website_fetcher

    def resolve(self, email: str, try_website: bool = True) -> Tuple[Optional[str], str]:
        """
        Resolve company name from email address.

        Args:
            email: Email address (e.g., "john@bursonglobal.com")
            try_website: Whether to attempt website fetching if domain not in mapping

        Returns:
            Tuple of (company_name, source) where source is one of:
            - "known_domain": From KNOWN_DOMAINS mapping
            - "website": Fetched from company website
            - "domain_formatted": Formatted from domain name
            - None if company couldn't be resolved (e.g., personal email)
        """
        if not email or "@" not in email:
            return None, ""

        domain = email.split("@")[1].lower()

        # Skip personal email domains
        if domain in self.PERSONAL_DOMAINS:
            return None, ""

        # Strategy 1: Check known domains mapping
        company = self._lookup_known_domain(domain)
        if company:
            return company, "known_domain"

        # Strategy 2: Try website fetching
        if try_website and self.website_fetcher:
            company = self._fetch_from_website(domain)
            if company:
                return company, "website"

        # Strategy 3: Format domain name as company name
        company = self._format_domain_as_company(domain)
        if company:
            return company, "domain_formatted"

        return None, ""

    def _lookup_known_domain(self, domain: str) -> Optional[str]:
        """Look up domain in known mappings, trying subdomains too."""
        # Try exact match first
        if domain in self.KNOWN_DOMAINS:
            return self.KNOWN_DOMAINS[domain]

        # Try parent domains (e.g., mena.bursonglobal.com -> bursonglobal.com)
        parts = domain.split(".")
        for i in range(1, len(parts) - 1):
            parent_domain = ".".join(parts[i:])
            if parent_domain in self.KNOWN_DOMAINS:
                return self.KNOWN_DOMAINS[parent_domain]

        return None

    @lru_cache(maxsize=500)
    def _fetch_from_website(self, domain: str) -> Optional[str]:
        """Fetch company name from website (cached)."""
        if not self.website_fetcher:
            return None

        try:
            return self.website_fetcher.fetch_company_name(domain)
        except Exception:
            return None

    def _format_domain_as_company(self, domain: str) -> Optional[str]:
        """
        Format domain name as a readable company name.

        Examples:
            bursonglobal.com -> Bursonglobal
            weber-shandwick.com -> Weber Shandwick
            my_company.co.uk -> My Company
        """
        # Extract the main domain part (before TLD)
        parts = domain.split(".")

        # Handle compound TLDs
        if len(parts) >= 3 and parts[-2] in ("co", "com", "org", "net"):
            company_part = parts[-3]
        elif len(parts) >= 2:
            company_part = parts[-2]
        else:
            return None

        # Skip if it's a subdomain indicator
        if company_part in ("www", "mail", "email", "smtp", "imap", "pop"):
            return None

        # Clean up and format
        # Replace hyphens and underscores with spaces
        company_part = company_part.replace("-", " ").replace("_", " ")

        # Title case
        formatted = company_part.title()

        # Skip if too short
        if len(formatted) < 2:
            return None

        return formatted

    def get_second_level_domain(self, email: str) -> str:
        """
        Extract second-level domain from email for grouping.

        Examples:
            john@pr.edelman.com -> edelman.com
            jane@company.co.uk -> company.co.uk
        """
        if not email or "@" not in email:
            return ""

        domain = email.split("@")[1].lower()
        parts = domain.split(".")

        if len(parts) < 2:
            return domain

        # Handle compound TLDs
        if len(parts) >= 3 and parts[-2] in ("co", "com", "org", "net", "gov", "edu", "ac"):
            return ".".join(parts[-3:])

        return ".".join(parts[-2:])

    def get_website_url(self, email: str) -> Optional[str]:
        """
        Generate company website URL from email address.

        Uses the second-level domain to construct the URL.
        Skips personal email providers.

        Examples:
            john@pr.edelman.com -> https://edelman.com
            jane@company.co.uk -> https://company.co.uk
            user@gmail.com -> None (personal email)
        """
        if not email or "@" not in email:
            return None

        domain = email.split("@")[1].lower()

        # Skip personal email domains
        if domain in self.PERSONAL_DOMAINS:
            return None

        # Get the second-level domain for the website
        sld = self.get_second_level_domain(email)
        if not sld:
            return None

        return f"https://{sld}"
