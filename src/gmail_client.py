"""Gmail API client for fetching emails."""

import base64
import time
from datetime import datetime, timedelta
from email.utils import parseaddr
from pathlib import Path
from typing import Iterator

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from .config import (
    GMAIL_CREDENTIALS_PATH,
    GMAIL_TOKEN_PATH,
    GMAIL_SCOPES,
    GMAIL_RATE_LIMIT_DELAY,
    get_absolute_path,
)


class GmailClient:
    """Client for interacting with Gmail API."""

    def __init__(self):
        self.service = None
        self.credentials = None

    def authenticate(self) -> bool:
        """
        Handle OAuth flow and authenticate with Gmail API.

        Returns True if authentication successful, False otherwise.
        """
        token_path = get_absolute_path(GMAIL_TOKEN_PATH)
        credentials_path = get_absolute_path(GMAIL_CREDENTIALS_PATH)

        # Check for existing token
        if token_path.exists():
            self.credentials = Credentials.from_authorized_user_file(
                str(token_path), GMAIL_SCOPES
            )

        # If no valid credentials, get new ones
        if not self.credentials or not self.credentials.valid:
            if self.credentials and self.credentials.expired and self.credentials.refresh_token:
                try:
                    self.credentials.refresh(Request())
                except Exception as e:
                    print(f"Error refreshing token: {e}")
                    self.credentials = None

            if not self.credentials:
                if not credentials_path.exists():
                    print(f"Error: credentials.json not found at {credentials_path}")
                    print("Please download OAuth credentials from Google Cloud Console.")
                    return False

                flow = InstalledAppFlow.from_client_secrets_file(
                    str(credentials_path), GMAIL_SCOPES
                )
                self.credentials = flow.run_local_server(port=0)

            # Save credentials for future use
            with open(token_path, "w") as token_file:
                token_file.write(self.credentials.to_json())

        # Build the Gmail service
        self.service = build("gmail", "v1", credentials=self.credentials)
        return True

    def fetch_emails(
        self,
        days_back: int = 90,
        max_results: int = None,
        query: str = None,
    ) -> Iterator[dict]:
        """
        Fetch emails from the last N days.

        Args:
            days_back: Number of days to look back
            max_results: Maximum number of emails to fetch (None for all)
            query: Additional Gmail search query

        Yields:
            Email message dictionaries with id, subject, from, date, body
        """
        if not self.service:
            raise RuntimeError("Not authenticated. Call authenticate() first.")

        # Build the query
        after_date = datetime.now() - timedelta(days=days_back)
        date_query = f"after:{after_date.strftime('%Y/%m/%d')}"

        full_query = date_query
        if query:
            full_query = f"{date_query} {query}"

        # Fetch message IDs
        messages = []
        page_token = None

        while True:
            try:
                results = self.service.users().messages().list(
                    userId="me",
                    q=full_query,
                    pageToken=page_token,
                    maxResults=min(500, max_results) if max_results else 500,
                ).execute()

                if "messages" in results:
                    messages.extend(results["messages"])

                    if max_results and len(messages) >= max_results:
                        messages = messages[:max_results]
                        break

                page_token = results.get("nextPageToken")
                if not page_token:
                    break

                time.sleep(GMAIL_RATE_LIMIT_DELAY)

            except HttpError as e:
                print(f"Error fetching message list: {e}")
                break

        # Fetch full message content
        for msg_info in messages:
            try:
                email_data = self.get_email_content(msg_info["id"])
                if email_data:
                    yield email_data
                time.sleep(GMAIL_RATE_LIMIT_DELAY)
            except HttpError as e:
                print(f"Error fetching message {msg_info['id']}: {e}")
                continue

    def get_email_content(self, message_id: str) -> dict | None:
        """
        Get full email content including body.

        Args:
            message_id: Gmail message ID

        Returns:
            Dictionary with email data or None if error
        """
        if not self.service:
            raise RuntimeError("Not authenticated. Call authenticate() first.")

        try:
            message = self.service.users().messages().get(
                userId="me",
                id=message_id,
                format="full",
            ).execute()

            # Extract headers
            headers = {h["name"].lower(): h["value"] for h in message["payload"]["headers"]}

            # Parse sender
            from_header = headers.get("from", "")
            sender_name, sender_email = parseaddr(from_header)

            # Get date
            date_str = headers.get("date", "")
            received_at = self._parse_date(date_str)

            # Extract body
            body = self._extract_body(message["payload"])

            return {
                "id": message_id,
                "subject": headers.get("subject", "(No Subject)"),
                "from_name": sender_name,
                "from_email": sender_email,
                "to": headers.get("to", ""),
                "date": date_str,
                "received_at": received_at,
                "body": body,
                "snippet": message.get("snippet", ""),
            }

        except HttpError as e:
            print(f"Error fetching message {message_id}: {e}")
            return None

    def _extract_body(self, payload: dict) -> str:
        """Extract email body from message payload."""
        body = ""

        if "body" in payload and payload["body"].get("data"):
            body = base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8", errors="ignore")

        elif "parts" in payload:
            for part in payload["parts"]:
                mime_type = part.get("mimeType", "")

                if mime_type == "text/plain" and part.get("body", {}).get("data"):
                    body = base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8", errors="ignore")
                    break

                elif mime_type == "text/html" and not body and part.get("body", {}).get("data"):
                    # Fall back to HTML if no plain text
                    body = base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8", errors="ignore")

                elif "parts" in part:
                    # Handle nested multipart
                    nested_body = self._extract_body(part)
                    if nested_body:
                        body = nested_body
                        break

        return body

    def _parse_date(self, date_str: str) -> datetime | None:
        """Parse email date string to datetime."""
        from email.utils import parsedate_to_datetime

        try:
            return parsedate_to_datetime(date_str)
        except (TypeError, ValueError):
            return None

    def test_connection(self) -> bool:
        """Test the Gmail connection by fetching user profile."""
        if not self.service:
            return False

        try:
            profile = self.service.users().getProfile(userId="me").execute()
            print(f"Connected as: {profile.get('emailAddress')}")
            return True
        except HttpError as e:
            print(f"Connection test failed: {e}")
            return False
