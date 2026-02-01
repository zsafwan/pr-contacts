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
from src.utils import clean_email, format_phone, format_date, get_second_level_domain
from src.company_resolver import CompanyResolver

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
    ["Dashboard", "Contacts", "PR Agencies", "Categories", "Brands", "Data Management", "Run Extraction"],
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
                "Website": c.website or "",
                "Title": c.title or "",
                "Phone": c.phone or "",
                "Country": c.country or "",
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
                # Check if we're in edit mode for this contact
                edit_key = f"edit_mode_{contact.id}"
                if edit_key not in st.session_state:
                    st.session_state[edit_key] = False

                # Edit/View toggle buttons
                col_btn1, col_btn2, col_btn3 = st.columns([1, 1, 4])
                with col_btn1:
                    if st.button("Edit", key=f"edit_btn_{contact.id}"):
                        st.session_state[edit_key] = True
                        st.rerun()
                with col_btn2:
                    if st.button("Delete", key=f"delete_btn_{contact.id}"):
                        st.session_state[f"confirm_delete_{contact.id}"] = True
                        st.rerun()

                # Confirm delete dialog
                if st.session_state.get(f"confirm_delete_{contact.id}"):
                    st.warning(f"Are you sure you want to delete {contact.name or contact.primary_email}?")
                    col_yes, col_no, _ = st.columns([1, 1, 4])
                    with col_yes:
                        if st.button("Yes, Delete", key=f"confirm_yes_{contact.id}"):
                            session.delete(contact)
                            session.commit()
                            st.session_state[f"confirm_delete_{contact.id}"] = False
                            st.success("Contact deleted!")
                            st.rerun()
                    with col_no:
                        if st.button("Cancel", key=f"confirm_no_{contact.id}"):
                            st.session_state[f"confirm_delete_{contact.id}"] = False
                            st.rerun()

                # Edit mode
                elif st.session_state[edit_key]:
                    with st.form(key=f"edit_form_{contact.id}"):
                        col_form1, col_form2 = st.columns(2)

                        with col_form1:
                            new_name = st.text_input("Name", value=contact.name or "")
                            new_company = st.text_input("Company", value=contact.company or "")
                            new_website = st.text_input("Website", value=contact.website or "")
                            new_title = st.text_input("Title", value=contact.title or "")
                            new_phone = st.text_input("Phone", value=contact.phone or "")
                            new_country = st.text_input("Country", value=contact.country or "")

                        with col_form2:
                            # Categories multiselect
                            all_categories = [c.name for c in db.get_all_categories(session)]
                            current_categories = [c.name for c in contact.categories]
                            new_categories = st.multiselect(
                                "Categories",
                                options=all_categories,
                                default=current_categories,
                                key=f"cat_select_{contact.id}"
                            )
                            new_category_input = st.text_input(
                                "Add new category",
                                key=f"new_cat_{contact.id}",
                                placeholder="Type to add new category"
                            )

                            # Brands multiselect
                            all_brands = [b.name for b in db.get_all_brands(session)]
                            current_brands = [b.name for b in contact.brands]
                            new_brands = st.multiselect(
                                "Brands",
                                options=all_brands,
                                default=current_brands,
                                key=f"brand_select_{contact.id}"
                            )
                            new_brand_input = st.text_input(
                                "Add new brand",
                                key=f"new_brand_{contact.id}",
                                placeholder="Type to add new brand"
                            )

                        col_save, col_cancel, _ = st.columns([1, 1, 4])
                        with col_save:
                            submitted = st.form_submit_button("Save")
                        with col_cancel:
                            cancelled = st.form_submit_button("Cancel")

                        if submitted:
                            # Update basic fields
                            contact.name = new_name if new_name else None
                            contact.company = new_company if new_company else None
                            contact.website = new_website if new_website else None
                            contact.title = new_title if new_title else None
                            contact.phone = new_phone if new_phone else None
                            contact.country = new_country if new_country else None

                            # Update categories
                            contact.categories.clear()
                            for cat_name in new_categories:
                                category = db.get_or_create_category(session, cat_name)
                                contact.categories.append(category)
                            if new_category_input:
                                category = db.get_or_create_category(session, new_category_input.strip())
                                if category not in contact.categories:
                                    contact.categories.append(category)

                            # Update brands
                            contact.brands.clear()
                            for brand_name in new_brands:
                                brand = db.get_or_create_brand(session, brand_name)
                                contact.brands.append(brand)
                            if new_brand_input:
                                brand = db.get_or_create_brand(session, new_brand_input.strip())
                                if brand not in contact.brands:
                                    contact.brands.append(brand)

                            session.commit()
                            st.session_state[edit_key] = False
                            st.success("Contact updated!")
                            st.rerun()

                        if cancelled:
                            st.session_state[edit_key] = False
                            st.rerun()

                # View mode
                else:
                    col1, col2 = st.columns(2)

                    with col1:
                        st.write("**Email:**", contact.primary_email)
                        if contact.company:
                            st.write("**Company:**", contact.company)
                        if contact.website:
                            st.write("**Website:**", contact.website)
                        if contact.title:
                            st.write("**Title:**", contact.title)
                        if contact.phone:
                            st.write("**Phone:**", format_phone(contact.phone))
                        if contact.country:
                            st.write("**Country:**", contact.country)

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


# PR Agencies page
def show_pr_agencies():
    st.title("PR Agencies")
    st.write("Contacts grouped by email domain (corporate PR agencies)")

    session = get_session()

    # Get domain stats
    domain_stats = db.get_domain_stats(session, exclude_personal=True)

    if not domain_stats:
        st.info("No corporate email domains found yet. Run extraction to populate contacts.")
        return

    st.subheader(f"Corporate Domains ({len(domain_stats)} total)")

    # Filter/search
    search_domain = st.text_input("Search domains", placeholder="e.g., edelman")

    # Filter stats by search
    if search_domain:
        domain_stats = [
            (domain, count)
            for domain, count in domain_stats
            if search_domain.lower() in domain.lower()
        ]

    # Display as table with clickable domains
    col1, col2 = st.columns([3, 1])
    with col1:
        st.write("**Domain**")
    with col2:
        st.write("**Contacts**")

    # Show domain list
    for domain, count in domain_stats[:50]:  # Limit to top 50
        col1, col2 = st.columns([3, 1])
        with col1:
            if st.button(domain, key=f"domain_{domain}"):
                st.session_state.selected_domain = domain
        with col2:
            st.write(count)

    if len(domain_stats) > 50:
        st.write(f"... and {len(domain_stats) - 50} more domains")

    # Show contacts for selected domain
    st.divider()

    selected_domain = st.session_state.get("selected_domain")

    if selected_domain:
        st.subheader(f"Contacts from {selected_domain}")

        contacts = db.get_contacts_by_domain(session, selected_domain)

        if contacts:
            # Export button for this agency
            df = pd.DataFrame([
                {
                    "Name": c.name or "",
                    "Email": c.primary_email,
                    "Company": c.company or "",
                    "Website": c.website or "",
                    "Title": c.title or "",
                    "Phone": c.phone or "",
                    "Country": c.country or "",
                }
                for c in contacts
            ])

            st.download_button(
                f"Export {selected_domain} contacts",
                df.to_csv(index=False),
                f"{selected_domain.replace('.', '_')}_contacts.csv",
                "text/csv",
                key="download-agency-csv",
            )

            # Display contacts
            st.dataframe(df, use_container_width=True, hide_index=True)

            # Detailed view
            with st.expander("View contact details"):
                for contact in contacts:
                    st.write(f"**{contact.name or 'Unknown'}** - {contact.primary_email}")
                    details = []
                    if contact.title:
                        details.append(f"Title: {contact.title}")
                    if contact.phone:
                        details.append(f"Phone: {format_phone(contact.phone)}")
                    if contact.country:
                        details.append(f"Country: {contact.country}")
                    if details:
                        st.write("  " + " | ".join(details))
                    st.write("---")
    else:
        st.info("Click a domain above to view its contacts")


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
        company_resolver = CompanyResolver()  # For resolving company from domain
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

            # Resolve company name using multiple strategies
            company = contact_info.company
            company_source = contact_info.company_source

            # If no company from signature, use company resolver
            if not company:
                resolved_company, resolved_source = company_resolver.resolve(
                    sender_email,
                    try_website=False  # Don't fetch websites in Streamlit (too slow)
                )
                if resolved_company:
                    company = resolved_company
                    company_source = resolved_source

            # Generate website URL from email domain
            website = company_resolver.get_website_url(sender_email)

            # Create/update contact
            contact = db.create_or_update_contact(
                session,
                email=sender_email,
                name=contact_info.name,
                company=company,
                title=contact_info.title,
                phone=contact_info.phone,
                country=contact_info.country,
                country_code=contact_info.country_code,
                country_source=contact_info.country_source,
                company_source=company_source,
                website=website,
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


# Data Management page
def show_data_management():
    st.title("Data Management")

    session = get_session()

    tab1, tab2, tab3, tab4 = st.tabs(["Bulk Edit", "Merge Duplicates", "Import Data", "Export Data"])

    # Tab 1: Bulk Edit
    with tab1:
        st.subheader("Bulk Edit Contacts")
        st.write("Select contacts and apply changes to all of them at once.")

        contacts = session.query(Contact).order_by(Contact.name).all()

        if not contacts:
            st.info("No contacts in database.")
        else:
            # Filter options
            col_filter1, col_filter2 = st.columns(2)
            with col_filter1:
                filter_domain = st.text_input("Filter by email domain", placeholder="e.g., bursonglobal.com")
            with col_filter2:
                filter_company = st.text_input("Filter by company", placeholder="e.g., Edelman")

            # Apply filters
            filtered_contacts = contacts
            if filter_domain:
                filtered_contacts = [c for c in filtered_contacts if filter_domain.lower() in (c.email_domain or "").lower()]
            if filter_company:
                filtered_contacts = [c for c in filtered_contacts if filter_company.lower() in (c.company or "").lower()]

            st.write(f"Showing {len(filtered_contacts)} contacts")

            # Contact selection
            contact_options = {f"{c.name or 'Unknown'} ({c.primary_email})": c.id for c in filtered_contacts}

            if contact_options:
                selected_names = st.multiselect(
                    "Select contacts to edit",
                    options=list(contact_options.keys()),
                    key="bulk_select"
                )

                # Select all button
                if st.button("Select All Filtered"):
                    st.session_state.bulk_select = list(contact_options.keys())
                    st.rerun()

                if selected_names:
                    selected_ids = [contact_options[name] for name in selected_names]
                    st.write(f"**{len(selected_ids)} contacts selected**")

                    st.divider()
                    st.write("**Apply changes to selected contacts:**")

                    with st.form("bulk_edit_form"):
                        col1, col2 = st.columns(2)

                        with col1:
                            bulk_company = st.text_input("Set Company (leave empty to skip)")
                            bulk_website = st.text_input("Set Website (leave empty to skip)")
                            bulk_country = st.text_input("Set Country (leave empty to skip)")

                        with col2:
                            all_categories = [c.name for c in db.get_all_categories(session)]
                            bulk_add_categories = st.multiselect("Add Categories", options=all_categories)
                            bulk_remove_categories = st.multiselect("Remove Categories", options=all_categories)

                        submitted = st.form_submit_button("Apply Changes")

                        if submitted:
                            updated = 0
                            for contact_id in selected_ids:
                                contact = session.query(Contact).get(contact_id)
                                if contact:
                                    if bulk_company:
                                        contact.company = bulk_company
                                        contact.company_source = "manual"
                                    if bulk_website:
                                        contact.website = bulk_website
                                    if bulk_country:
                                        contact.country = bulk_country
                                        contact.country_source = "manual"

                                    # Add categories
                                    for cat_name in bulk_add_categories:
                                        category = db.get_or_create_category(session, cat_name)
                                        if category not in contact.categories:
                                            contact.categories.append(category)

                                    # Remove categories
                                    for cat_name in bulk_remove_categories:
                                        contact.categories = [c for c in contact.categories if c.name != cat_name]

                                    updated += 1

                            session.commit()
                            st.success(f"Updated {updated} contacts!")
                            st.rerun()

    # Tab 2: Merge Duplicates
    with tab2:
        st.subheader("Merge Duplicate Contacts")
        st.write("Find and merge contacts that may be duplicates.")

        # Find potential duplicates
        contacts = session.query(Contact).all()

        # Group by email domain
        domain_groups = {}
        for c in contacts:
            if c.email_domain and c.email_domain not in ["gmail.com", "yahoo.com", "hotmail.com", "outlook.com"]:
                if c.email_domain not in domain_groups:
                    domain_groups[c.email_domain] = []
                domain_groups[c.email_domain].append(c)

        # Find domains with multiple contacts (potential duplicates)
        duplicate_domains = {k: v for k, v in domain_groups.items() if len(v) > 1}

        if not duplicate_domains:
            st.info("No potential duplicates found.")
        else:
            st.write(f"Found {len(duplicate_domains)} domains with multiple contacts")

            for domain, domain_contacts in sorted(duplicate_domains.items(), key=lambda x: -len(x[1])):
                with st.expander(f"{domain} ({len(domain_contacts)} contacts)"):
                    # Show contacts in this domain
                    for c in domain_contacts:
                        st.write(f"- **{c.name or 'Unknown'}** - {c.primary_email}")
                        if c.title:
                            st.write(f"  Title: {c.title}")

                    st.divider()

                    # Merge form
                    st.write("**Merge contacts:**")
                    contact_opts = {f"{c.name or 'Unknown'} ({c.primary_email})": c.id for c in domain_contacts}

                    primary_contact = st.selectbox(
                        "Keep as primary (others will be merged into this)",
                        options=list(contact_opts.keys()),
                        key=f"primary_{domain}"
                    )

                    contacts_to_merge = st.multiselect(
                        "Select contacts to merge into primary",
                        options=[k for k in contact_opts.keys() if k != primary_contact],
                        key=f"merge_{domain}"
                    )

                    if st.button(f"Merge Selected", key=f"merge_btn_{domain}"):
                        if contacts_to_merge:
                            primary_id = contact_opts[primary_contact]
                            primary = session.query(Contact).get(primary_id)

                            for merge_name in contacts_to_merge:
                                merge_id = contact_opts[merge_name]
                                merge_contact = session.query(Contact).get(merge_id)

                                if merge_contact:
                                    # Transfer data if primary doesn't have it
                                    if not primary.name and merge_contact.name:
                                        primary.name = merge_contact.name
                                    if not primary.company and merge_contact.company:
                                        primary.company = merge_contact.company
                                    if not primary.title and merge_contact.title:
                                        primary.title = merge_contact.title
                                    if not primary.phone and merge_contact.phone:
                                        primary.phone = merge_contact.phone
                                    if not primary.country and merge_contact.country:
                                        primary.country = merge_contact.country

                                    # Transfer categories
                                    for cat in merge_contact.categories:
                                        if cat not in primary.categories:
                                            primary.categories.append(cat)

                                    # Transfer brands
                                    for brand in merge_contact.brands:
                                        if brand not in primary.brands:
                                            primary.brands.append(brand)

                                    # Add merged email as additional email
                                    db.add_email_to_contact(session, primary, merge_contact.primary_email, notes="Merged contact")

                                    # Delete merged contact
                                    session.delete(merge_contact)

                            session.commit()
                            st.success(f"Merged {len(contacts_to_merge)} contacts into {primary_contact}")
                            st.rerun()

    # Tab 3: Import Data
    with tab3:
        st.subheader("Import Contacts from CSV")
        st.write("Upload a CSV file to import or update contacts.")

        st.info("""
        **CSV Format:**
        - Required column: `Email`
        - Optional columns: `Name`, `Company`, `Website`, `Title`, `Phone`, `Country`, `Categories`, `Brands`
        - Categories and Brands should be comma-separated within the cell
        """)

        uploaded_file = st.file_uploader("Choose a CSV file", type="csv")

        if uploaded_file:
            try:
                df = pd.read_csv(uploaded_file)
                st.write(f"Found {len(df)} rows")
                st.dataframe(df.head(10))

                # Validate required columns
                if "Email" not in df.columns:
                    st.error("CSV must have an 'Email' column")
                else:
                    col1, col2 = st.columns(2)
                    with col1:
                        update_existing = st.checkbox("Update existing contacts", value=True)
                    with col2:
                        skip_empty = st.checkbox("Skip empty values (don't overwrite)", value=True)

                    if st.button("Import Contacts"):
                        imported = 0
                        updated = 0
                        skipped = 0

                        for _, row in df.iterrows():
                            email = clean_email(str(row.get("Email", "")))
                            if not email:
                                skipped += 1
                                continue

                            # Check if contact exists
                            existing = session.query(Contact).filter(Contact.primary_email == email).first()

                            if existing and not update_existing:
                                skipped += 1
                                continue

                            # Prepare data
                            name = str(row.get("Name", "")) if pd.notna(row.get("Name")) else None
                            company = str(row.get("Company", "")) if pd.notna(row.get("Company")) else None
                            website = str(row.get("Website", "")) if pd.notna(row.get("Website")) else None
                            title = str(row.get("Title", "")) if pd.notna(row.get("Title")) else None
                            phone = str(row.get("Phone", "")) if pd.notna(row.get("Phone")) else None
                            country = str(row.get("Country", "")) if pd.notna(row.get("Country")) else None

                            if existing:
                                # Update existing
                                if name and (not skip_empty or name.strip()):
                                    existing.name = name
                                if company and (not skip_empty or company.strip()):
                                    existing.company = company
                                    existing.company_source = "import"
                                if website and (not skip_empty or website.strip()):
                                    existing.website = website
                                if title and (not skip_empty or title.strip()):
                                    existing.title = title
                                if phone and (not skip_empty or phone.strip()):
                                    existing.phone = phone
                                if country and (not skip_empty or country.strip()):
                                    existing.country = country
                                    existing.country_source = "import"

                                # Handle categories
                                if "Categories" in row and pd.notna(row.get("Categories")):
                                    cats = [c.strip() for c in str(row["Categories"]).split(",") if c.strip()]
                                    for cat_name in cats:
                                        category = db.get_or_create_category(session, cat_name)
                                        if category not in existing.categories:
                                            existing.categories.append(category)

                                # Handle brands
                                if "Brands" in row and pd.notna(row.get("Brands")):
                                    brands = [b.strip() for b in str(row["Brands"]).split(",") if b.strip()]
                                    for brand_name in brands:
                                        brand = db.get_or_create_brand(session, brand_name)
                                        if brand not in existing.brands:
                                            existing.brands.append(brand)

                                updated += 1
                            else:
                                # Create new contact
                                email_domain = email.split("@")[1] if "@" in email else None

                                contact = Contact(
                                    primary_email=email,
                                    name=name,
                                    company=company,
                                    website=website,
                                    title=title,
                                    phone=phone,
                                    country=country,
                                    email_domain=email_domain,
                                    company_source="import" if company else None,
                                    country_source="import" if country else None,
                                )
                                session.add(contact)
                                session.flush()

                                # Handle categories
                                if "Categories" in row and pd.notna(row.get("Categories")):
                                    cats = [c.strip() for c in str(row["Categories"]).split(",") if c.strip()]
                                    for cat_name in cats:
                                        category = db.get_or_create_category(session, cat_name)
                                        contact.categories.append(category)

                                # Handle brands
                                if "Brands" in row and pd.notna(row.get("Brands")):
                                    brands = [b.strip() for b in str(row["Brands"]).split(",") if b.strip()]
                                    for brand_name in brands:
                                        brand = db.get_or_create_brand(session, brand_name)
                                        contact.brands.append(brand)

                                imported += 1

                        session.commit()
                        st.success(f"Import complete! Created: {imported}, Updated: {updated}, Skipped: {skipped}")
                        st.rerun()

            except Exception as e:
                st.error(f"Error reading CSV: {e}")

    # Tab 4: Export Data
    with tab4:
        st.subheader("Export Contacts to CSV")
        st.write("Export all contacts for editing in Excel or Google Sheets.")

        contacts = session.query(Contact).order_by(Contact.name).all()

        if not contacts:
            st.info("No contacts to export.")
        else:
            # Export options
            col1, col2 = st.columns(2)
            with col1:
                include_categories = st.checkbox("Include Categories", value=True)
                include_brands = st.checkbox("Include Brands", value=True)
            with col2:
                include_metadata = st.checkbox("Include Metadata (sources)", value=False)

            # Build export dataframe
            export_data = []
            for c in contacts:
                row = {
                    "Email": c.primary_email,
                    "Name": c.name or "",
                    "Company": c.company or "",
                    "Website": c.website or "",
                    "Title": c.title or "",
                    "Phone": c.phone or "",
                    "Country": c.country or "",
                }

                if include_categories:
                    row["Categories"] = ", ".join([cat.name for cat in c.categories])

                if include_brands:
                    row["Brands"] = ", ".join([b.name for b in c.brands])

                if include_metadata:
                    row["Email Domain"] = c.email_domain or ""
                    row["Company Source"] = c.company_source or ""
                    row["Country Source"] = c.country_source or ""
                    row["Created At"] = format_date(c.created_at) if c.created_at else ""
                    row["Updated At"] = format_date(c.updated_at) if c.updated_at else ""

                export_data.append(row)

            df = pd.DataFrame(export_data)

            st.write(f"**{len(df)} contacts ready to export**")
            st.dataframe(df.head(20))

            # Download buttons
            col1, col2 = st.columns(2)
            with col1:
                csv_data = df.to_csv(index=False)
                st.download_button(
                    "Download CSV",
                    csv_data,
                    "pr_contacts_export.csv",
                    "text/csv",
                    key="export_csv"
                )
            with col2:
                # Excel export
                try:
                    from io import BytesIO
                    buffer = BytesIO()
                    with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                        df.to_excel(writer, index=False, sheet_name='Contacts')
                    excel_data = buffer.getvalue()
                    st.download_button(
                        "Download Excel",
                        excel_data,
                        "pr_contacts_export.xlsx",
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        key="export_excel"
                    )
                except ImportError:
                    st.info("Install openpyxl for Excel export: pip install openpyxl")


# Main routing
if page == "Dashboard":
    show_dashboard()
elif page == "Contacts":
    show_contacts()
elif page == "PR Agencies":
    show_pr_agencies()
elif page == "Categories":
    show_categories()
elif page == "Brands":
    show_brands()
elif page == "Data Management":
    show_data_management()
elif page == "Run Extraction":
    show_extraction()
