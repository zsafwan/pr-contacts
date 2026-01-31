"""Configuration management for PR Contacts Extractor."""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Project root directory
PROJECT_ROOT = Path(__file__).parent.parent

# API Keys
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

# Gmail Configuration
GMAIL_CREDENTIALS_PATH = os.getenv("GMAIL_CREDENTIALS_PATH", "./credentials.json")
GMAIL_TOKEN_PATH = os.getenv("GMAIL_TOKEN_PATH", "./token.json")
GMAIL_SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

# Database Configuration
DATABASE_PATH = os.getenv("DATABASE_PATH", "./database.db")
DATABASE_URL = f"sqlite:///{DATABASE_PATH}"

# Extraction Settings
DAYS_TO_FETCH = int(os.getenv("DAYS_TO_FETCH", "90"))
CATEGORIZATION_BATCH_SIZE = int(os.getenv("CATEGORIZATION_BATCH_SIZE", "10"))

# Rate Limiting
GMAIL_RATE_LIMIT_DELAY = 0.1  # seconds between API calls
CLAUDE_RATE_LIMIT_DELAY = 0.5  # seconds between API calls


def validate_config():
    """Validate that required configuration is present."""
    errors = []

    if not ANTHROPIC_API_KEY:
        errors.append("ANTHROPIC_API_KEY is not set")

    credentials_path = Path(GMAIL_CREDENTIALS_PATH)
    if not credentials_path.exists():
        errors.append(f"Gmail credentials file not found at {GMAIL_CREDENTIALS_PATH}")

    return errors


def get_absolute_path(relative_path: str) -> Path:
    """Convert a relative path to absolute, relative to project root."""
    path = Path(relative_path)
    if path.is_absolute():
        return path
    return PROJECT_ROOT / path
