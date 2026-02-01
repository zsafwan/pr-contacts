"""Country detection from phone codes, email TLDs, and signature patterns."""

import re
from dataclasses import dataclass
from typing import Optional


@dataclass
class CountryResult:
    """Container for country detection result."""
    country: str
    country_code: str
    source: str  # phone_code, tld, signature


class CountryDetector:
    """Detect country from various signals in contact information."""

    # Phone country code mappings (code -> (country_name, ISO code))
    PHONE_CODES = {
        # Middle East (primary focus for PR)
        "+971": ("United Arab Emirates", "AE"),
        "+966": ("Saudi Arabia", "SA"),
        "+974": ("Qatar", "QA"),
        "+965": ("Kuwait", "KW"),
        "+973": ("Bahrain", "BH"),
        "+968": ("Oman", "OM"),
        "+962": ("Jordan", "JO"),
        "+961": ("Lebanon", "LB"),
        "+20": ("Egypt", "EG"),
        "+212": ("Morocco", "MA"),
        "+216": ("Tunisia", "TN"),
        "+213": ("Algeria", "DZ"),
        "+964": ("Iraq", "IQ"),
        "+963": ("Syria", "SY"),
        "+970": ("Palestine", "PS"),
        "+972": ("Israel", "IL"),
        "+98": ("Iran", "IR"),

        # Major global markets
        "+1": ("United States", "US"),
        "+44": ("United Kingdom", "GB"),
        "+33": ("France", "FR"),
        "+49": ("Germany", "DE"),
        "+39": ("Italy", "IT"),
        "+34": ("Spain", "ES"),
        "+31": ("Netherlands", "NL"),
        "+32": ("Belgium", "BE"),
        "+41": ("Switzerland", "CH"),
        "+43": ("Austria", "AT"),
        "+46": ("Sweden", "SE"),
        "+47": ("Norway", "NO"),
        "+45": ("Denmark", "DK"),
        "+358": ("Finland", "FI"),
        "+48": ("Poland", "PL"),
        "+351": ("Portugal", "PT"),
        "+353": ("Ireland", "IE"),
        "+30": ("Greece", "GR"),
        "+7": ("Russia", "RU"),
        "+380": ("Ukraine", "UA"),
        "+90": ("Turkey", "TR"),

        # Asia Pacific
        "+91": ("India", "IN"),
        "+86": ("China", "CN"),
        "+852": ("Hong Kong", "HK"),
        "+853": ("Macau", "MO"),
        "+886": ("Taiwan", "TW"),
        "+81": ("Japan", "JP"),
        "+82": ("South Korea", "KR"),
        "+65": ("Singapore", "SG"),
        "+60": ("Malaysia", "MY"),
        "+66": ("Thailand", "TH"),
        "+62": ("Indonesia", "ID"),
        "+63": ("Philippines", "PH"),
        "+84": ("Vietnam", "VN"),
        "+61": ("Australia", "AU"),
        "+64": ("New Zealand", "NZ"),

        # Americas
        "+52": ("Mexico", "MX"),
        "+55": ("Brazil", "BR"),
        "+54": ("Argentina", "AR"),
        "+56": ("Chile", "CL"),
        "+57": ("Colombia", "CO"),
        "+51": ("Peru", "PE"),

        # Africa
        "+27": ("South Africa", "ZA"),
        "+234": ("Nigeria", "NG"),
        "+254": ("Kenya", "KE"),
        "+233": ("Ghana", "GH"),
    }

    # TLD to country mappings
    TLD_COUNTRIES = {
        # Middle East
        ".ae": ("United Arab Emirates", "AE"),
        ".sa": ("Saudi Arabia", "SA"),
        ".qa": ("Qatar", "QA"),
        ".kw": ("Kuwait", "KW"),
        ".bh": ("Bahrain", "BH"),
        ".om": ("Oman", "OM"),
        ".jo": ("Jordan", "JO"),
        ".lb": ("Lebanon", "LB"),
        ".eg": ("Egypt", "EG"),
        ".ma": ("Morocco", "MA"),
        ".tn": ("Tunisia", "TN"),
        ".dz": ("Algeria", "DZ"),
        ".iq": ("Iraq", "IQ"),
        ".sy": ("Syria", "SY"),
        ".ps": ("Palestine", "PS"),
        ".il": ("Israel", "IL"),
        ".ir": ("Iran", "IR"),

        # Europe
        ".uk": ("United Kingdom", "GB"),
        ".co.uk": ("United Kingdom", "GB"),
        ".fr": ("France", "FR"),
        ".de": ("Germany", "DE"),
        ".it": ("Italy", "IT"),
        ".es": ("Spain", "ES"),
        ".nl": ("Netherlands", "NL"),
        ".be": ("Belgium", "BE"),
        ".ch": ("Switzerland", "CH"),
        ".at": ("Austria", "AT"),
        ".se": ("Sweden", "SE"),
        ".no": ("Norway", "NO"),
        ".dk": ("Denmark", "DK"),
        ".fi": ("Finland", "FI"),
        ".pl": ("Poland", "PL"),
        ".pt": ("Portugal", "PT"),
        ".ie": ("Ireland", "IE"),
        ".gr": ("Greece", "GR"),
        ".ru": ("Russia", "RU"),
        ".ua": ("Ukraine", "UA"),
        ".tr": ("Turkey", "TR"),

        # Asia Pacific
        ".in": ("India", "IN"),
        ".cn": ("China", "CN"),
        ".hk": ("Hong Kong", "HK"),
        ".mo": ("Macau", "MO"),
        ".tw": ("Taiwan", "TW"),
        ".jp": ("Japan", "JP"),
        ".kr": ("South Korea", "KR"),
        ".sg": ("Singapore", "SG"),
        ".my": ("Malaysia", "MY"),
        ".th": ("Thailand", "TH"),
        ".id": ("Indonesia", "ID"),
        ".ph": ("Philippines", "PH"),
        ".vn": ("Vietnam", "VN"),
        ".au": ("Australia", "AU"),
        ".nz": ("New Zealand", "NZ"),

        # Americas
        ".us": ("United States", "US"),
        ".ca": ("Canada", "CA"),
        ".mx": ("Mexico", "MX"),
        ".br": ("Brazil", "BR"),
        ".ar": ("Argentina", "AR"),
        ".cl": ("Chile", "CL"),
        ".co": ("Colombia", "CO"),
        ".pe": ("Peru", "PE"),

        # Africa
        ".za": ("South Africa", "ZA"),
        ".ng": ("Nigeria", "NG"),
        ".ke": ("Kenya", "KE"),
        ".gh": ("Ghana", "GH"),
    }

    # City/location patterns for signature detection
    LOCATION_PATTERNS = {
        # UAE
        r"\bdubai\b": ("United Arab Emirates", "AE"),
        r"\babu\s*dhabi\b": ("United Arab Emirates", "AE"),
        r"\bsharjah\b": ("United Arab Emirates", "AE"),
        r"\bajman\b": ("United Arab Emirates", "AE"),
        r"\bu\.?a\.?e\.?\b": ("United Arab Emirates", "AE"),

        # Saudi Arabia
        r"\briyadh\b": ("Saudi Arabia", "SA"),
        r"\bjeddah\b": ("Saudi Arabia", "SA"),
        r"\bdammam\b": ("Saudi Arabia", "SA"),
        r"\bksa\b": ("Saudi Arabia", "SA"),

        # Other Gulf
        r"\bdoha\b": ("Qatar", "QA"),
        r"\bkuwait\s*city\b": ("Kuwait", "KW"),
        r"\bmanama\b": ("Bahrain", "BH"),
        r"\bmuscat\b": ("Oman", "OM"),

        # Levant
        r"\bamman\b": ("Jordan", "JO"),
        r"\bbeirut\b": ("Lebanon", "LB"),
        r"\bcairo\b": ("Egypt", "EG"),

        # Major global cities
        r"\blondon\b": ("United Kingdom", "GB"),
        r"\bnew\s*york\b": ("United States", "US"),
        r"\blos\s*angeles\b": ("United States", "US"),
        r"\bparis\b": ("France", "FR"),
        r"\bberlin\b": ("Germany", "DE"),
        r"\bmilan\b": ("Italy", "IT"),
        r"\bmadrid\b": ("Spain", "ES"),
        r"\bamsterdam\b": ("Netherlands", "NL"),
        r"\bsingapore\b": ("Singapore", "SG"),
        r"\bhong\s*kong\b": ("Hong Kong", "HK"),
        r"\btokyo\b": ("Japan", "JP"),
        r"\bseoul\b": ("South Korea", "KR"),
        r"\bsydney\b": ("Australia", "AU"),
        r"\bmelbourne\b": ("Australia", "AU"),
        r"\bmumbai\b": ("India", "IN"),
        r"\bnew\s*delhi\b": ("India", "IN"),
    }

    def detect(
        self,
        phone: str = None,
        email: str = None,
        signature: str = None,
    ) -> Optional[CountryResult]:
        """
        Detect country from available information.

        Detection priority (highest to lowest confidence):
        1. Phone country code
        2. Signature location patterns
        3. Email TLD

        Args:
            phone: Phone number (may include country code)
            email: Email address
            signature: Email signature text

        Returns:
            CountryResult if detected, None otherwise
        """
        # Try phone code first (highest confidence)
        if phone:
            result = self.detect_from_phone(phone)
            if result:
                return result

        # Try signature patterns
        if signature:
            result = self.detect_from_signature(signature)
            if result:
                return result

        # Try email TLD last (lowest confidence)
        if email:
            result = self.detect_from_email_tld(email)
            if result:
                return result

        return None

    def detect_from_phone(self, phone: str) -> Optional[CountryResult]:
        """Detect country from phone number country code."""
        if not phone:
            return None

        # Normalize phone number - remove spaces, dashes, parentheses
        normalized = re.sub(r"[\s\-().]+", "", phone)

        # Must start with + for country code detection
        if not normalized.startswith("+"):
            # Try adding + if it looks like an international number
            if normalized.startswith("00"):
                normalized = "+" + normalized[2:]
            else:
                return None

        # Try matching country codes (longest match first)
        for code in sorted(self.PHONE_CODES.keys(), key=len, reverse=True):
            if normalized.startswith(code):
                country, iso = self.PHONE_CODES[code]
                return CountryResult(
                    country=country,
                    country_code=iso,
                    source="phone_code"
                )

        return None

    def detect_from_email_tld(self, email: str) -> Optional[CountryResult]:
        """Detect country from email domain TLD."""
        if not email or "@" not in email:
            return None

        domain = email.split("@")[1].lower()

        # Check for compound TLDs first (e.g., .co.uk)
        for tld in sorted(self.TLD_COUNTRIES.keys(), key=len, reverse=True):
            if domain.endswith(tld):
                country, iso = self.TLD_COUNTRIES[tld]
                return CountryResult(
                    country=country,
                    country_code=iso,
                    source="tld"
                )

        return None

    def detect_from_signature(self, signature: str) -> Optional[CountryResult]:
        """Detect country from signature location patterns."""
        if not signature:
            return None

        text_lower = signature.lower()

        # Check location patterns
        for pattern, (country, iso) in self.LOCATION_PATTERNS.items():
            if re.search(pattern, text_lower, re.IGNORECASE):
                return CountryResult(
                    country=country,
                    country_code=iso,
                    source="signature"
                )

        return None
