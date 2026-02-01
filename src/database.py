"""Database models and operations using SQLAlchemy."""

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    create_engine,
    Column,
    Integer,
    String,
    Text,
    Float,
    DateTime,
    ForeignKey,
    Table,
    UniqueConstraint,
)
from sqlalchemy.orm import (
    declarative_base,
    relationship,
    sessionmaker,
    Session,
)

from .config import DATABASE_URL

Base = declarative_base()


# Association table for contact-category many-to-many relationship
contact_categories = Table(
    "contact_categories",
    Base.metadata,
    Column("contact_id", Integer, ForeignKey("contacts.id"), primary_key=True),
    Column("category_id", Integer, ForeignKey("categories.id"), primary_key=True),
    Column("confidence", Float, default=1.0),
)

# Association table for contact-brand many-to-many relationship
contact_brands = Table(
    "contact_brands",
    Base.metadata,
    Column("contact_id", Integer, ForeignKey("contacts.id"), primary_key=True),
    Column("brand_id", Integer, ForeignKey("brands.id"), primary_key=True),
    Column("mention_count", Integer, default=1),
)


class Contact(Base):
    """Main contacts table."""

    __tablename__ = "contacts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(Text)
    primary_email = Column(Text, unique=True, nullable=False)
    company = Column(Text)
    title = Column(Text)
    phone = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # New fields for enhanced extraction
    country = Column(Text)              # e.g., "United Arab Emirates"
    country_code = Column(Text)         # e.g., "AE"
    country_source = Column(Text)       # How detected: phone_code, tld, signature
    email_domain = Column(Text, index=True)  # For grouping: "edelman.com"
    company_source = Column(Text)       # How found: signature, website, ai
    website = Column(Text)              # Company website URL

    # Relationships
    additional_emails = relationship("ContactEmail", back_populates="contact", cascade="all, delete-orphan")
    categories = relationship("Category", secondary=contact_categories, back_populates="contacts")
    brands = relationship("Brand", secondary=contact_brands, back_populates="contacts")
    emails_received = relationship("EmailProcessed", back_populates="contact")

    def __repr__(self):
        return f"<Contact(id={self.id}, name='{self.name}', email='{self.primary_email}')>"


class ContactEmail(Base):
    """Additional email addresses for contacts."""

    __tablename__ = "contact_emails"

    id = Column(Integer, primary_key=True, autoincrement=True)
    contact_id = Column(Integer, ForeignKey("contacts.id"), nullable=False)
    email = Column(Text, nullable=False)
    notes = Column(Text)

    contact = relationship("Contact", back_populates="additional_emails")

    __table_args__ = (UniqueConstraint("contact_id", "email", name="uix_contact_email"),)


class Category(Base):
    """PR categories (e.g., Technology, Travel, Sports)."""

    __tablename__ = "categories"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(Text, unique=True, nullable=False)
    description = Column(Text)

    contacts = relationship("Contact", secondary=contact_categories, back_populates="categories")

    def __repr__(self):
        return f"<Category(id={self.id}, name='{self.name}')>"


class Brand(Base):
    """Brands/companies mentioned in PR emails."""

    __tablename__ = "brands"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(Text, unique=True, nullable=False)

    contacts = relationship("Contact", secondary=contact_brands, back_populates="brands")

    def __repr__(self):
        return f"<Brand(id={self.id}, name='{self.name}')>"


class EmailProcessed(Base):
    """Track which emails have been processed."""

    __tablename__ = "emails_processed"

    id = Column(Integer, primary_key=True, autoincrement=True)
    gmail_id = Column(Text, unique=True, nullable=False)
    subject = Column(Text)
    from_email = Column(Text)
    received_at = Column(DateTime)
    contact_id = Column(Integer, ForeignKey("contacts.id"))
    processed_at = Column(DateTime, default=datetime.utcnow)

    contact = relationship("Contact", back_populates="emails_received")

    def __repr__(self):
        return f"<EmailProcessed(id={self.id}, gmail_id='{self.gmail_id}')>"


class Database:
    """Database operations manager."""

    def __init__(self, db_url: str = None):
        self.db_url = db_url or DATABASE_URL
        self.engine = create_engine(self.db_url)
        self.SessionLocal = sessionmaker(bind=self.engine)

    def init_db(self):
        """Create all tables."""
        Base.metadata.create_all(self.engine)

    def get_session(self) -> Session:
        """Get a new database session."""
        return self.SessionLocal()

    # Contact operations
    def create_or_update_contact(
        self,
        session: Session,
        email: str,
        name: str = None,
        company: str = None,
        title: str = None,
        phone: str = None,
        country: str = None,
        country_code: str = None,
        country_source: str = None,
        email_domain: str = None,
        company_source: str = None,
        website: str = None,
    ) -> Contact:
        """Create a new contact or update existing one."""
        contact = session.query(Contact).filter(Contact.primary_email == email).first()

        # Extract email domain if not provided
        if not email_domain and "@" in email:
            email_domain = email.split("@")[1].lower()

        if contact:
            # Update with new info if provided
            if name and not contact.name:
                contact.name = name
            if company and not contact.company:
                contact.company = company
                if company_source:
                    contact.company_source = company_source
            if title and not contact.title:
                contact.title = title
            if phone and not contact.phone:
                contact.phone = phone
            if country and not contact.country:
                contact.country = country
                contact.country_code = country_code
                contact.country_source = country_source
            if email_domain and not contact.email_domain:
                contact.email_domain = email_domain
            if website and not contact.website:
                contact.website = website
            contact.updated_at = datetime.utcnow()
        else:
            contact = Contact(
                primary_email=email,
                name=name,
                company=company,
                title=title,
                phone=phone,
                country=country,
                country_code=country_code,
                country_source=country_source,
                email_domain=email_domain,
                company_source=company_source,
                website=website,
            )
            session.add(contact)

        session.flush()
        return contact

    def add_email_to_contact(
        self,
        session: Session,
        contact: Contact,
        email: str,
        notes: str = None,
    ):
        """Add an additional email address to a contact."""
        # Check if email already exists
        existing = (
            session.query(ContactEmail)
            .filter(ContactEmail.contact_id == contact.id, ContactEmail.email == email)
            .first()
        )

        if not existing and email != contact.primary_email:
            contact_email = ContactEmail(
                contact_id=contact.id,
                email=email,
                notes=notes,
            )
            session.add(contact_email)

    def get_or_create_category(
        self,
        session: Session,
        name: str,
        description: str = None,
    ) -> Category:
        """Get existing category or create new one."""
        category = session.query(Category).filter(Category.name == name).first()

        if not category:
            category = Category(name=name, description=description)
            session.add(category)
            session.flush()

        return category

    def add_category_to_contact(
        self,
        session: Session,
        contact: Contact,
        category_name: str,
        confidence: float = 1.0,
    ):
        """Add a category to a contact."""
        category = self.get_or_create_category(session, category_name)

        if category not in contact.categories:
            contact.categories.append(category)
            # Update confidence in association table
            session.execute(
                contact_categories.update()
                .where(contact_categories.c.contact_id == contact.id)
                .where(contact_categories.c.category_id == category.id)
                .values(confidence=confidence)
            )

    def get_or_create_brand(self, session: Session, name: str) -> Brand:
        """Get existing brand or create new one."""
        brand = session.query(Brand).filter(Brand.name == name).first()

        if not brand:
            brand = Brand(name=name)
            session.add(brand)
            session.flush()

        return brand

    def add_brand_to_contact(
        self,
        session: Session,
        contact: Contact,
        brand_name: str,
        increment_count: bool = True,
    ):
        """Add a brand association to a contact."""
        brand = self.get_or_create_brand(session, brand_name)

        if brand not in contact.brands:
            contact.brands.append(brand)
        elif increment_count:
            # Increment mention count
            session.execute(
                contact_brands.update()
                .where(contact_brands.c.contact_id == contact.id)
                .where(contact_brands.c.brand_id == brand.id)
                .values(mention_count=contact_brands.c.mention_count + 1)
            )

    def mark_email_processed(
        self,
        session: Session,
        gmail_id: str,
        subject: str,
        from_email: str,
        received_at: datetime,
        contact: Contact = None,
    ) -> EmailProcessed:
        """Mark an email as processed."""
        email_record = EmailProcessed(
            gmail_id=gmail_id,
            subject=subject,
            from_email=from_email,
            received_at=received_at,
            contact_id=contact.id if contact else None,
        )
        session.add(email_record)
        return email_record

    def is_email_processed(self, session: Session, gmail_id: str) -> bool:
        """Check if an email has already been processed."""
        return session.query(EmailProcessed).filter(EmailProcessed.gmail_id == gmail_id).first() is not None

    def get_all_contacts(self, session: Session) -> list[Contact]:
        """Get all contacts."""
        return session.query(Contact).order_by(Contact.name).all()

    def search_contacts(
        self,
        session: Session,
        query: str = None,
        category: str = None,
        brand: str = None,
    ) -> list[Contact]:
        """Search contacts with optional filters."""
        q = session.query(Contact)

        if query:
            search = f"%{query}%"
            q = q.filter(
                (Contact.name.ilike(search))
                | (Contact.primary_email.ilike(search))
                | (Contact.company.ilike(search))
            )

        if category:
            q = q.join(Contact.categories).filter(Category.name == category)

        if brand:
            q = q.join(Contact.brands).filter(Brand.name == brand)

        return q.order_by(Contact.name).all()

    def get_contacts_by_category(self, session: Session, category_name: str) -> list[Contact]:
        """Get all contacts in a specific category."""
        return (
            session.query(Contact)
            .join(Contact.categories)
            .filter(Category.name == category_name)
            .order_by(Contact.name)
            .all()
        )

    def get_all_categories(self, session: Session) -> list[Category]:
        """Get all categories."""
        return session.query(Category).order_by(Category.name).all()

    def get_all_brands(self, session: Session) -> list[Brand]:
        """Get all brands."""
        return session.query(Brand).order_by(Brand.name).all()

    def get_contact_count(self, session: Session) -> int:
        """Get total number of contacts."""
        return session.query(Contact).count()

    def get_email_count(self, session: Session) -> int:
        """Get total number of processed emails."""
        return session.query(EmailProcessed).count()

    def get_category_stats(self, session: Session) -> list[tuple[str, int]]:
        """Get contact counts per category."""
        from sqlalchemy import func

        return (
            session.query(Category.name, func.count(contact_categories.c.contact_id))
            .join(contact_categories, Category.id == contact_categories.c.category_id)
            .group_by(Category.name)
            .order_by(func.count(contact_categories.c.contact_id).desc())
            .all()
        )

    def get_brand_stats(self, session: Session, limit: int = 20) -> list[tuple[str, int]]:
        """Get top brands by mention count."""
        from sqlalchemy import func

        return (
            session.query(Brand.name, func.sum(contact_brands.c.mention_count))
            .join(contact_brands, Brand.id == contact_brands.c.brand_id)
            .group_by(Brand.name)
            .order_by(func.sum(contact_brands.c.mention_count).desc())
            .limit(limit)
            .all()
        )

    def get_domain_stats(self, session: Session, exclude_personal: bool = True) -> list[tuple[str, int]]:
        """Get contact counts per email domain for PR agency grouping."""
        from sqlalchemy import func

        personal_domains = [
            "gmail.com", "yahoo.com", "hotmail.com", "outlook.com",
            "aol.com", "icloud.com", "me.com", "mac.com", "live.com", "msn.com",
        ]

        query = (
            session.query(Contact.email_domain, func.count(Contact.id))
            .filter(Contact.email_domain.isnot(None))
        )

        if exclude_personal:
            query = query.filter(~Contact.email_domain.in_(personal_domains))

        return (
            query.group_by(Contact.email_domain)
            .order_by(func.count(Contact.id).desc())
            .all()
        )

    def get_contacts_by_domain(self, session: Session, domain: str) -> list[Contact]:
        """Get all contacts from a specific email domain."""
        return (
            session.query(Contact)
            .filter(Contact.email_domain == domain)
            .order_by(Contact.name)
            .all()
        )


# Global database instance
db = Database()
