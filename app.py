"""Streamlit web application for PR Contacts Extractor."""

import pandas as pd
import streamlit as st
from datetime import datetime, timedelta

from src import __version__
from src.config import validate_config, DAYS_TO_FETCH
from src.database import db, Contact, Category, Brand, EmailProcessed
from src.mbox_client import MboxClient
from src.contact_extractor import ContactExtractor
from src.categorizer import Categorizer
from src.utils import clean_email, format_phone, format_date

# Page configuration
st.set_page_config(
    page_title="PR Contacts Extractor",
    page_icon="📧",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Initialize database
db.init_db()


def get_session():
    """Get database session."""
    if "db_session" not in st.session_state:
        st.session_state.db_session = db.get_session()
    return st.session_state.db_session


def refresh_session():
    """Refresh database session."""
    if "db_session" in st.session_state:
        st.session_state.db_session.close()
    st.session_state.db_session = db.get_session()
    return st.session_state.db_session


# Sidebar navigation
st.sidebar.title("PR Contacts")
st.sidebar.caption(f"v{__version__}")
page = st.sidebar.radio(
    "Navigation",
    ["Dashboard", "Contacts", "Categories", "Brands", "Run Extraction"],
)


# Dashboard page
def show_dashboard():
    st.title("Dashboard")

    session = get_session()

    # Key metrics
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        contact_count = db.get_contact_count(session)
        st.metric("Total Contacts", contact_count)

    with col2:
        email_count = db.get_email_count(session)
        st.metric("Emails Processed", email_count)

    with col3:
        category_count = len(db.get_all_categories(session))
        st.metric("Categories", category_count)

    with col4:
        brand_count = len(db.get_all_brands(session))
        st.metric("Brands Tracked", brand_count)

    st.divider()

    # Charts
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Contacts by Category")
        category_stats = db.get_category_stats(session)
        if category_stats:
            df = pd.DataFrame(category_stats, columns=["Category", "Count"])
            st.bar_chart(df.set_index("Category"))
        else:
            st.info("No categories yet. Run extraction to populate.")

    with col2:
        st.subheader("Top Brands Mentioned")
        brand_stats = db.get_brand_stats(session, limit=10)
        if brand_stats:
            df = pd.DataFrame(brand_stats, columns=["Brand", "Mentions"])
            st.bar_chart(df.set_index("Brand"))
        else:
            st.info("No brands yet. Run extraction to populate.")

    # Recent contacts
    st.subheader("Recently Added Contacts")
    contacts = (
        session.query(Contact)
        .order_by(Contact.created_at.desc())
        .limit(10)
        .all()
    )

    if contacts:
        data = [
            {
                "Name": c.name or "Unknown",
                "Email": c.primary_email,
                "Company": c.company or "",
                "Added": format_date(c.created_at),
            }
            for c in contacts
        ]
        st.dataframe(pd.DataFrame(data), use_container_width=True, hide_index=True)
    else:
        st.info("No contacts yet. Run extraction to get started.")


# Contacts page
def show_contacts():
    st.title("Contacts Browser")

    session = get_session()

    # Filters
    col1, col2, col3 = st.columns(3)

    with col1:
        search_query = st.text_input("Search", placeholder="Name, email, or company...")

    with col2:
        categories = db.get_all_categories(session)
        category_options = ["All Categories"] + [c.name for c in categories]
        selected_category = st.selectbox("Category", category_options)

    with col3:
        brands = db.get_all_brands(session)
        brand_options = ["All Brands"] + [b.name for b in brands]
        selected_brand = st.selectbox("Brand", brand_options)

    # Apply filters
    category_filter = None if selected_category == "All Categories" else selected_category
    brand_filter = None if selected_brand == "All Brands" else selected_brand

    contacts = db.search_contacts(
        session,
        query=search_query if search_query else None,
        category=category_filter,
        brand=brand_filter,
    )

    st.write(f"Found {len(contacts)} contacts")

    # Export button
    if contacts:
        df = pd.DataFrame([
            {
                "Name": c.name or "",
                "Email": c.primary_email,
                "Company": c.company or "",
                "Title": c.title or "",
                "Phone": c.phone or "",
                "Categories": ", ".join([cat.name for cat in c.categories]),
                "Brands": ", ".join([b.name for b in c.brands]),
            }
            for c in contacts
        ])

        csv = df.to_csv(index=False)
        st.download_button(
            "Export to CSV",
            csv,
            "pr_contacts.csv",
            "text/csv",
            key="download-csv",
        )

    # Contacts table
    if contacts:
        for contact in contacts:
            with st.expander(f"{contact.name or 'Unknown'} - {contact.primary_email}"):
                col1, col2 = st.columns(2)

                with col1:
                    st.write("**Email:**", contact.primary_email)
                    if contact.company:
                        st.write("**Company:**", contact.company)
                    if contact.title:
                        st.write("**Title:**", contact.title)
                    if contact.phone:
                        st.write("**Phone:**", format_phone(contact.phone))

                with col2:
                    if contact.categories:
                        st.write("**Categories:**")
                        for cat in contact.categories:
                            st.write(f"  - {cat.name}")

                    if contact.brands:
                        st.write("**Associated Brands:**")
                        for brand in contact.brands:
                            st.write(f"  - {brand.name}")

                # Additional emails
                if contact.additional_emails:
                    st.write("**Additional Emails:**")
                    for ae in contact.additional_emails:
                        st.write(f"  - {ae.email}")

                # Emails received
                if contact.emails_received:
                    st.write(f"**Emails received:** {len(contact.emails_received)}")
                    with st.expander("View emails"):
                        for email in contact.emails_received[:10]:
                            st.write(f"- {email.subject} ({format_date(email.received_at)})")
    else:
        st.info("No contacts match your filters.")


# Categories page
def show_categories():
    st.title("Categories Manager")

    session = get_session()
    categories = db.get_all_categories(session)

    if not categories:
        st.info("No categories yet. Run extraction with AI categorization to discover categories.")
        return

    # Category stats table
    category_stats = db.get_category_stats(session)
    stats_dict = {name: count for name, count in category_stats}

    st.subheader(f"All Categories ({len(categories)})")

    for category in categories:
        contact_count = stats_dict.get(category.name, 0)
        with st.expander(f"{category.name} ({contact_count} contacts)"):
            if category.description:
                st.write(category.description)

            # Show contacts in this category
            contacts = db.get_contacts_by_category(session, category.name)
            if contacts:
                data = [
                    {
                        "Name": c.name or "Unknown",
                        "Email": c.primary_email,
                        "Company": c.company or "",
                    }
                    for c in contacts[:20]
                ]
                st.dataframe(pd.DataFrame(data), use_container_width=True, hide_index=True)

                if len(contacts) > 20:
                    st.write(f"... and {len(contacts) - 20} more")


# Brands page
def show_brands():
    st.title("Brands")

    session = get_session()
    brand_stats = db.get_brand_stats(session, limit=100)

    if not brand_stats:
        st.info("No brands yet. Run extraction with AI categorization to extract brands.")
        return

    st.subheader(f"Top Brands ({len(brand_stats)} total)")

    # Display as table
    df = pd.DataFrame(brand_stats, columns=["Brand", "Mentions"])
    st.dataframe(df, use_container_width=True, hide_index=True)

    # Search contacts by brand
    st.divider()
    st.subheader("Search by Brand")

    brands = db.get_all_brands(session)
    brand_names = [b.name for b in brands]
    selected_brand = st.selectbox("Select a brand", brand_names)

    if selected_brand:
        contacts = db.search_contacts(session, brand=selected_brand)
        st.write(f"**{len(contacts)} contacts** associated with {selected_brand}")

        if contacts:
            data = [
                {
                    "Name": c.name or "Unknown",
                    "Email": c.primary_email,
                    "Company": c.company or "",
                }
                for c in contacts
            ]
            st.dataframe(pd.DataFrame(data), use_container_width=True, hide_index=True)


# Run Extraction page
def show_extraction():
    st.title("Run Extraction")

    # Check for MBOX file
    mbox_client = MboxClient()
    mbox_file = mbox_client.find_mbox_file()

    if mbox_file:
        st.success(f"Found MBOX file: {mbox_file.name}")
    else:
        st.warning("No MBOX file found. Please extract your Google Takeout to the 'Takeout' folder.")
        st.info("Download your emails from https://takeout.google.com/ and extract the archive to the project folder.")

    # Check configuration for AI features
    errors = validate_config()
    if errors:
        # Filter out Gmail-related errors since we're using MBOX
        errors = [e for e in errors if "credentials" not in e.lower()]
        if errors:
            st.warning("Configuration issues detected:")
            for error in errors:
                st.write(f"- {error}")
            st.info("AI categorization requires ANTHROPIC_API_KEY in .env file.")

    # Options
    col1, col2 = st.columns(2)

    with col1:
        use_date_filter = st.checkbox("Filter by date", value=False)
        days_back = None
        if use_date_filter:
            days_back = st.number_input(
                "Days to look back",
                min_value=1,
                max_value=365,
                value=DAYS_TO_FETCH,
            )

    with col2:
        max_emails = st.number_input(
            "Maximum emails (0 for all)",
            min_value=0,
            max_value=10000,
            value=0,
        )

    skip_categorization = st.checkbox(
        "Skip AI categorization (faster, basic extraction only)",
        value=True,
    )

    # Run button
    if st.button("Start Extraction", type="primary", disabled=not mbox_file):
        run_extraction_process(
            days_back=days_back,
            max_emails=max_emails if max_emails > 0 else None,
            skip_categorization=skip_categorization,
        )

    # Stats
    st.divider()
    st.subheader("Current Database Stats")

    session = get_session()
    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric("Contacts", db.get_contact_count(session))

    with col2:
        st.metric("Emails Processed", db.get_email_count(session))

    with col3:
        st.metric("Categories", len(db.get_all_categories(session)))


def run_extraction_process(days_back, max_emails, skip_categorization):
    """Run the extraction process with Streamlit progress display."""

    progress_bar = st.progress(0)
    status_text = st.empty()

    try:
        # Open MBOX file
        status_text.text("Opening MBOX file...")
        mbox = MboxClient()
        if not mbox.authenticate():
            st.error("Failed to open MBOX file. Please check the Takeout folder.")
            return

        progress_bar.progress(10)

        # Fetch emails
        if days_back:
            status_text.text(f"Fetching emails from the last {days_back} days...")
        else:
            status_text.text("Fetching all emails...")
        emails = list(mbox.fetch_emails(days_back=days_back, max_results=max_emails))
        st.write(f"Found {len(emails)} emails")

        if not emails:
            st.warning("No emails found.")
            return

        progress_bar.progress(30)

        # Initialize components
        extractor = ContactExtractor()
        categorizer = None

        if not skip_categorization:
            try:
                categorizer = Categorizer()
            except ValueError as e:
                st.warning(f"AI categorization unavailable: {e}")

        # Process emails
        session = refresh_session()
        processed = 0
        skipped = 0

        emails_to_categorize = []
        email_contact_map = []

        status_text.text("Processing emails...")

        for i, email_data in enumerate(emails):
            gmail_id = email_data.get("id")

            # Skip if already processed
            if db.is_email_processed(session, gmail_id):
                skipped += 1
                continue

            # Extract contact
            try:
                contact_info = extractor.extract_from_email(email_data)
            except Exception:
                continue

            sender_email = clean_email(contact_info.email)
            if not sender_email:
                continue

            # Create/update contact
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
            if categorizer:
                emails_to_categorize.append(email_data)
                email_contact_map.append((email_data, contact))

            # Mark processed
            db.mark_email_processed(
                session,
                gmail_id=gmail_id,
                subject=email_data.get("subject", ""),
                from_email=sender_email,
                received_at=email_data.get("received_at"),
                contact=contact,
            )

            processed += 1

            # Update progress
            progress = 30 + int(40 * (i + 1) / len(emails))
            progress_bar.progress(progress)
            status_text.text(f"Processing emails... {i + 1}/{len(emails)}")

        progress_bar.progress(70)

        # Categorization
        if categorizer and emails_to_categorize:
            status_text.text(f"Categorizing {len(emails_to_categorize)} emails with AI...")

            results = categorizer.categorize_emails_with_rate_limit(
                emails_to_categorize,
                batch_size=10,
            )

            for (email_data, contact), result in zip(email_contact_map, results):
                for category_name, confidence in result.categories:
                    db.add_category_to_contact(session, contact, category_name, confidence)

                for brand_name in result.brands:
                    db.add_brand_to_contact(session, contact, brand_name)

            progress_bar.progress(90)

        # Commit
        session.commit()
        progress_bar.progress(100)

        # Summary
        status_text.text("Complete!")
        st.success(f"""
        Extraction complete!
        - Emails processed: {processed}
        - Emails skipped (already processed): {skipped}
        - Total contacts: {db.get_contact_count(session)}
        """)

    except Exception as e:
        st.error(f"Error during extraction: {e}")
        raise


# Main routing
if page == "Dashboard":
    show_dashboard()
elif page == "Contacts":
    show_contacts()
elif page == "Categories":
    show_categories()
elif page == "Brands":
    show_brands()
elif page == "Run Extraction":
    show_extraction()
