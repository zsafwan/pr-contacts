"""MBOX file reader for Google Takeout email exports."""

import mailbox
import base64
import hashlib
from datetime import datetime
from email.utils import parseaddr, parsedate_to_datetime
from pathlib import Path
from typing import Iterator

from .config import get_absolute_path


class MboxClient:
    """Client for reading emails from MBOX files (Google Takeout format)."""

    def __init__(self, mbox_path: str = None):
        """
        Initialize the MBOX client.

        Args:
            mbox_path: Path to the MBOX file. If None, will look in default Takeout location.
        """
        self.mbox_path = mbox_path
        self.mbox = None

    def find_mbox_file(self) -> Path | None:
        """Find MBOX file in common Takeout locations."""
        project_root = get_absolute_path(".")

        # Common locations to check
        search_paths = [
            project_root / "Takeout" / "Mail",
            project_root / "takeout" / "Mail",
            project_root / "takout" / "Mail",
            project_root / "Takeout",
            project_root / "takeout",
        ]

        for search_path in search_paths:
            if search_path.exists():
                # Look for .mbox files
                mbox_files = list(search_path.glob("*.mbox"))
                if mbox_files:
                    # Return the largest one (likely "All mail")
                    return max(mbox_files, key=lambda f: f.stat().st_size)

        return None

    def authenticate(self) -> bool:
        """
        Open the MBOX file for reading.

        Returns True if successful, False otherwise.
        """
        if self.mbox_path:
            mbox_file = Path(self.mbox_path)
        else:
            mbox_file = self.find_mbox_file()

        if not mbox_file or not mbox_file.exists():
            print(f"Error: MBOX file not found.")
            print("Please ensure your Google Takeout is extracted to the 'Takeout' folder.")
            return False

        print(f"Opening MBOX file: {mbox_file}")
        self.mbox = mailbox.mbox(str(mbox_file))
        return True

    def test_connection(self) -> bool:
        """Test that the MBOX file is readable."""
        if not self.mbox:
            return False

        try:
            # Try to read the first message
            count = len(self.mbox)
            print(f"MBOX file contains {count} messages")
            return True
        except Exception as e:
            print(f"Error reading MBOX file: {e}")
            return False

    def fetch_emails(
        self,
        days_back: int = None,
        max_results: int = None,
        query: str = None,
    ) -> Iterator[dict]:
        """
        Fetch emails from the MBOX file.

        Args:
            days_back: Only return emails from the last N days (optional)
            max_results: Maximum number of emails to return (optional)
            query: Not implemented for MBOX (ignored)

        Yields:
            Email message dictionaries with id, subject, from, date, body
        """
        if not self.mbox:
            raise RuntimeError("MBOX not opened. Call authenticate() first.")

        # Calculate cutoff date if days_back specified
        cutoff_date = None
        if days_back:
            cutoff_date = datetime.now().astimezone() - __import__('datetime').timedelta(days=days_back)

        count = 0
        total = len(self.mbox)

        for i, message in enumerate(self.mbox):
            if max_results and count >= max_results:
                break

            try:
                email_data = self._parse_message(message, i)
                if not email_data:
                    continue

                # Filter by date if specified
                if cutoff_date and email_data.get("received_at"):
                    if email_data["received_at"] < cutoff_date:
                        continue

                count += 1
                yield email_data

            except Exception as e:
                print(f"Error parsing message {i}: {e}")
                continue

    def _parse_message(self, message, index: int) -> dict | None:
        """Parse a mailbox message into our standard format."""
        try:
            # Generate a unique ID based on message headers
            msg_id = message.get("Message-ID", "")
            if not msg_id:
                # Create ID from date + subject + from
                msg_id = f"{message.get('Date', '')}-{message.get('Subject', '')}-{message.get('From', '')}"

            # Create a hash-based ID
            unique_id = hashlib.md5(msg_id.encode()).hexdigest()

            # Parse sender
            from_header = message.get("From", "")
            sender_name, sender_email = parseaddr(from_header)

            # Get date
            date_str = message.get("Date", "")
            received_at = self._parse_date(date_str)

            # Extract body
            body = self._extract_body(message)

            # Create snippet from body
            snippet = ""
            if body:
                snippet = body[:200].replace("\n", " ").strip()

            return {
                "id": unique_id,
                "subject": message.get("Subject", "(No Subject)"),
                "from_name": sender_name,
                "from_email": sender_email,
                "to": message.get("To", ""),
                "date": date_str,
                "received_at": received_at,
                "body": body,
                "snippet": snippet,
            }

        except Exception as e:
            print(f"Error parsing message: {e}")
            return None

    def _extract_body(self, message) -> str:
        """Extract email body from message."""
        body = ""

        if message.is_multipart():
            for part in message.walk():
                content_type = part.get_content_type()
                content_disposition = str(part.get("Content-Disposition", ""))

                # Skip attachments
                if "attachment" in content_disposition:
                    continue

                if content_type == "text/plain":
                    try:
                        payload = part.get_payload(decode=True)
                        if payload:
                            charset = part.get_content_charset() or "utf-8"
                            body = payload.decode(charset, errors="ignore")
                            break  # Prefer plain text
                    except Exception:
                        pass

                elif content_type == "text/html" and not body:
                    try:
                        payload = part.get_payload(decode=True)
                        if payload:
                            charset = part.get_content_charset() or "utf-8"
                            body = payload.decode(charset, errors="ignore")
                    except Exception:
                        pass
        else:
            try:
                payload = message.get_payload(decode=True)
                if payload:
                    charset = message.get_content_charset() or "utf-8"
                    body = payload.decode(charset, errors="ignore")
            except Exception:
                # Fall back to non-decoded payload
                body = str(message.get_payload())

        return body

    def _parse_date(self, date_str: str) -> datetime | None:
        """Parse email date string to datetime."""
        if not date_str:
            return None

        try:
            return parsedate_to_datetime(date_str)
        except (TypeError, ValueError):
            return None

    def get_email_content(self, message_id: str) -> dict | None:
        """
        Get email content by ID.

        Note: For MBOX, this requires scanning the file which is slow.
        Prefer using fetch_emails() iterator instead.
        """
        if not self.mbox:
            raise RuntimeError("MBOX not opened. Call authenticate() first.")

        for i, message in enumerate(self.mbox):
            email_data = self._parse_message(message, i)
            if email_data and email_data["id"] == message_id:
                return email_data

        return None
