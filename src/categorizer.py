"""AI-powered categorization using Claude API."""

import json
import time
from dataclasses import dataclass

import anthropic

from .config import ANTHROPIC_API_KEY, CLAUDE_RATE_LIMIT_DELAY


@dataclass
class CategorizationResult:
    """Result of email categorization."""

    categories: list[tuple[str, float]]  # (category_name, confidence)
    brands: list[str]
    raw_response: dict


class Categorizer:
    """Categorize emails and extract brands using Claude API."""

    def __init__(self, api_key: str = None):
        self.api_key = api_key or ANTHROPIC_API_KEY
        if not self.api_key:
            raise ValueError("Anthropic API key is required")

        self.client = anthropic.Anthropic(api_key=self.api_key)
        self.model = "claude-sonnet-4-20250514"

    def discover_categories(self, email_samples: list[dict]) -> list[str]:
        """
        Analyze sample emails to discover PR categories.

        Args:
            email_samples: List of email dicts with subject and snippet

        Returns:
            List of discovered category names
        """
        # Build sample text
        samples_text = "\n\n".join(
            f"Subject: {e.get('subject', '')}\nSnippet: {e.get('snippet', '')[:200]}"
            for e in email_samples[:50]  # Limit samples
        )

        prompt = f"""Analyze these PR email samples and identify distinct PR/marketing categories.

Email Samples:
{samples_text}

Based on these emails, identify 10-20 distinct PR categories that would be useful for organizing contacts.
Categories should be industry/topic focused (e.g., "Technology", "Travel & Hospitality", "Consumer Electronics", "Healthcare", "Automotive", etc.)

Return ONLY a JSON array of category names, nothing else. Example:
["Technology", "Travel & Hospitality", "Consumer Electronics"]"""

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=1000,
                messages=[{"role": "user", "content": prompt}],
            )

            # Parse response
            text = response.content[0].text.strip()

            # Extract JSON array
            if text.startswith("["):
                categories = json.loads(text)
                return categories
            else:
                # Try to find JSON in response
                import re

                match = re.search(r"\[.*\]", text, re.DOTALL)
                if match:
                    return json.loads(match.group())

            return []

        except Exception as e:
            print(f"Error discovering categories: {e}")
            return []

    def categorize_email(
        self,
        subject: str,
        body_snippet: str,
        sender_name: str = "",
        sender_company: str = "",
    ) -> CategorizationResult:
        """
        Categorize a single email.

        Args:
            subject: Email subject
            body_snippet: First ~500 chars of email body
            sender_name: Name of sender (optional)
            sender_company: Company of sender (optional)

        Returns:
            CategorizationResult with categories and brands
        """
        prompt = f"""Analyze this PR/marketing email and extract:
1. PR Categories (e.g., Technology, Travel, Sports, Consumer Electronics, Healthcare, etc.)
2. Specific brands/companies mentioned (not PR agencies)
3. Confidence score (0-1) for each category

Email Subject: {subject}
Sender: {sender_name} {f'at {sender_company}' if sender_company else ''}
Email Body Preview:
{body_snippet[:500]}

Return ONLY valid JSON in this exact format:
{{
  "categories": [
    {{"name": "Category Name", "confidence": 0.9}},
  ],
  "brands": ["Brand1", "Brand2"]
}}

Rules:
- Include 1-3 most relevant categories
- Only include brands/companies being promoted, not the PR agency
- Confidence should reflect how clearly the email fits the category"""

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=500,
                messages=[{"role": "user", "content": prompt}],
            )

            text = response.content[0].text.strip()

            # Parse JSON response
            # Find JSON object in response
            import re

            match = re.search(r"\{.*\}", text, re.DOTALL)
            if match:
                data = json.loads(match.group())

                categories = [
                    (c["name"], c.get("confidence", 0.8)) for c in data.get("categories", [])
                ]
                brands = data.get("brands", [])

                return CategorizationResult(
                    categories=categories,
                    brands=brands,
                    raw_response=data,
                )

            return CategorizationResult(categories=[], brands=[], raw_response={})

        except json.JSONDecodeError as e:
            print(f"Error parsing categorization response: {e}")
            return CategorizationResult(categories=[], brands=[], raw_response={})
        except Exception as e:
            print(f"Error categorizing email: {e}")
            return CategorizationResult(categories=[], brands=[], raw_response={})

    def categorize_batch(
        self,
        emails: list[dict],
    ) -> list[CategorizationResult]:
        """
        Categorize a batch of emails (more efficient API usage).

        Args:
            emails: List of email dicts with subject, body/snippet

        Returns:
            List of CategorizationResults
        """
        if not emails:
            return []

        # Build batch prompt
        email_texts = []
        for i, email in enumerate(emails):
            subject = email.get("subject", "")
            snippet = email.get("snippet", "") or email.get("body", "")[:300]
            email_texts.append(f"[Email {i + 1}]\nSubject: {subject}\nPreview: {snippet}")

        batch_text = "\n\n".join(email_texts)

        prompt = f"""Analyze these {len(emails)} PR/marketing emails. For each, extract:
1. PR Categories (e.g., Technology, Travel, Sports, Consumer Electronics, Healthcare, etc.)
2. Specific brands/companies mentioned (not PR agencies)
3. Confidence score (0-1) for each category

{batch_text}

Return ONLY valid JSON array with one object per email, in order:
[
  {{
    "email_index": 1,
    "categories": [{{"name": "Category", "confidence": 0.9}}],
    "brands": ["Brand1"]
  }},
  ...
]

Rules:
- Include 1-3 most relevant categories per email
- Only include brands being promoted, not PR agencies
- Return exactly {len(emails)} results in order"""

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=2000,
                messages=[{"role": "user", "content": prompt}],
            )

            text = response.content[0].text.strip()

            # Parse JSON array
            import re

            match = re.search(r"\[.*\]", text, re.DOTALL)
            if match:
                data = json.loads(match.group())

                results = []
                for item in data:
                    categories = [
                        (c["name"], c.get("confidence", 0.8))
                        for c in item.get("categories", [])
                    ]
                    brands = item.get("brands", [])
                    results.append(
                        CategorizationResult(
                            categories=categories,
                            brands=brands,
                            raw_response=item,
                        )
                    )

                # Pad with empty results if needed
                while len(results) < len(emails):
                    results.append(
                        CategorizationResult(categories=[], brands=[], raw_response={})
                    )

                return results

            return [
                CategorizationResult(categories=[], brands=[], raw_response={})
                for _ in emails
            ]

        except Exception as e:
            print(f"Error in batch categorization: {e}")
            return [
                CategorizationResult(categories=[], brands=[], raw_response={})
                for _ in emails
            ]

    def categorize_emails_with_rate_limit(
        self,
        emails: list[dict],
        batch_size: int = 10,
        progress_callback=None,
    ) -> list[CategorizationResult]:
        """
        Categorize emails with rate limiting and batching.

        Args:
            emails: List of email dicts
            batch_size: Number of emails per API call
            progress_callback: Optional callback(processed, total)

        Returns:
            List of CategorizationResults
        """
        results = []
        total = len(emails)

        for i in range(0, total, batch_size):
            batch = emails[i : i + batch_size]
            batch_results = self.categorize_batch(batch)
            results.extend(batch_results)

            if progress_callback:
                progress_callback(min(i + batch_size, total), total)

            # Rate limiting
            if i + batch_size < total:
                time.sleep(CLAUDE_RATE_LIMIT_DELAY)

        return results
