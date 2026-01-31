#!/usr/bin/env python3
"""CLI script for running the email extraction pipeline."""

import argparse
import sys
from datetime import datetime

from src.config import validate_config, DAYS_TO_FETCH, CATEGORIZATION_BATCH_SIZE
from src.gmail_client import GmailClient
from src.contact_extractor import ContactExtractor
from src.categorizer import Categorizer
from src.database import db
from src.utils import progress_bar, clean_email


def main():
    parser = argparse.ArgumentParser(
        description="Extract PR contacts from Gmail"
    )
    parser.add_argument(
        "--days",
        type=int,
        default=DAYS_TO_FETCH,
        help=f"Number of days to look back (default: {DAYS_TO_FETCH})",
    )
    parser.add_argument(
        "--max-emails",
        type=int,
        default=None,
        help="Maximum number of emails to process (default: all)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=CATEGORIZATION_BATCH_SIZE,
        help=f"Batch size for categorization (default: {CATEGORIZATION_BATCH_SIZE})",
    )
    parser.add_argument(
        "--skip-categorization",
        action="store_true",
        help="Skip AI categorization (faster, basic extraction only)",
    )
    parser.add_argument(
        "--discover-categories",
        action="store_true",
        help="Run category discovery on sample emails",
    )
    parser.add_argument(
        "--test",
        action="store_true",
        help="Test mode: process only 5 emails",
    )

    args = parser.parse_args()

    # Validate configuration
    print("Checking configuration...")
    errors = validate_config()
    if errors and not args.skip_categorization:
        print("Configuration errors:")
        for error in errors:
            print(f"  - {error}")
        if "ANTHROPIC_API_KEY" in str(errors):
            print("\nYou can use --skip-categorization to run without AI features.")
        sys.exit(1)

    # Initialize database
    print("Initializing database...")
    db.init_db()

    # Authenticate with Gmail
    print("Authenticating with Gmail...")
    gmail = GmailClient()
    if not gmail.authenticate():
        print("Failed to authenticate with Gmail.")
        sys.exit(1)

    if not gmail.test_connection():
        print("Gmail connection test failed.")
        sys.exit(1)

    # Initialize other components
    extractor = ContactExtractor()
    categorizer = None
    if not args.skip_categorization:
        try:
            categorizer = Categorizer()
        except ValueError as e:
            print(f"Warning: {e}")
            print("Continuing without categorization.")

    # Set limits
    max_emails = 5 if args.test else args.max_emails

    # Fetch emails
    print(f"\nFetching emails from the last {args.days} days...")
    emails = list(gmail.fetch_emails(days_back=args.days, max_results=max_emails))
    print(f"Found {len(emails)} emails")

    if not emails:
        print("No emails found.")
        return

    # Category discovery mode
    if args.discover_categories and categorizer:
        print("\nDiscovering categories from email samples...")
        categories = categorizer.discover_categories(emails[:50])
        print(f"Discovered {len(categories)} categories:")
        for cat in categories:
            print(f"  - {cat}")
        print()

    # Process emails
    print("\nProcessing emails...")
    session = db.get_session()

    stats = {
        "total": len(emails),
        "processed": 0,
        "skipped": 0,
        "new_contacts": 0,
        "updated_contacts": 0,
        "errors": 0,
    }

    # Batch emails for categorization
    emails_to_categorize = []
    email_contact_map = []  # Track (email_data, contact) pairs

    try:
        for i, email_data in enumerate(emails):
            # Progress update
            if (i + 1) % 10 == 0 or i == len(emails) - 1:
                print(f"\r{progress_bar(i + 1, len(emails))}", end="", flush=True)

            gmail_id = email_data.get("id")

            # Skip if already processed
            if db.is_email_processed(session, gmail_id):
                stats["skipped"] += 1
                continue

            # Extract contact info
            try:
                contact_info = extractor.extract_from_email(email_data)
            except Exception as e:
                print(f"\nError extracting contact from email {gmail_id}: {e}")
                stats["errors"] += 1
                continue

            # Skip if no valid email
            sender_email = clean_email(contact_info.email)
            if not sender_email:
                stats["skipped"] += 1
                continue

            # Create or update contact
            contact = db.create_or_update_contact(
                session,
                email=sender_email,
                name=contact_info.name,
                company=contact_info.company,
                title=contact_info.title,
                phone=contact_info.phone,
            )

            # Add additional emails
            for add_email in contact_info.additional_emails:
                db.add_email_to_contact(session, contact, add_email)

            # Track for categorization
            if categorizer and not args.skip_categorization:
                emails_to_categorize.append(email_data)
                email_contact_map.append((email_data, contact))

            # Mark email as processed
            db.mark_email_processed(
                session,
                gmail_id=gmail_id,
                subject=email_data.get("subject", ""),
                from_email=sender_email,
                received_at=email_data.get("received_at"),
                contact=contact,
            )

            stats["processed"] += 1

        print()  # New line after progress bar

        # Run batch categorization
        if categorizer and emails_to_categorize:
            print(f"\nCategorizing {len(emails_to_categorize)} emails...")

            def progress_callback(current, total):
                print(f"\r{progress_bar(current, total)}", end="", flush=True)

            results = categorizer.categorize_emails_with_rate_limit(
                emails_to_categorize,
                batch_size=args.batch_size,
                progress_callback=progress_callback,
            )
            print()

            # Apply categorization results
            for (email_data, contact), result in zip(email_contact_map, results):
                for category_name, confidence in result.categories:
                    db.add_category_to_contact(
                        session, contact, category_name, confidence
                    )

                for brand_name in result.brands:
                    db.add_brand_to_contact(session, contact, brand_name)

        # Commit all changes
        session.commit()

    except KeyboardInterrupt:
        print("\n\nInterrupted! Saving progress...")
        session.commit()
    except Exception as e:
        print(f"\nError during processing: {e}")
        session.rollback()
        raise
    finally:
        session.close()

    # Print summary
    print("\n" + "=" * 50)
    print("Extraction Summary")
    print("=" * 50)
    print(f"Total emails found: {stats['total']}")
    print(f"Emails processed: {stats['processed']}")
    print(f"Emails skipped (already processed): {stats['skipped']}")
    print(f"Errors: {stats['errors']}")
    print()

    # Database stats
    session = db.get_session()
    try:
        print(f"Total contacts in database: {db.get_contact_count(session)}")
        print(f"Total emails processed: {db.get_email_count(session)}")

        categories = db.get_all_categories(session)
        if categories:
            print(f"Categories: {len(categories)}")

        brands = db.get_all_brands(session)
        if brands:
            print(f"Brands tracked: {len(brands)}")
    finally:
        session.close()

    print("\nDone! Run 'streamlit run app.py' to view the web interface.")


if __name__ == "__main__":
    main()
