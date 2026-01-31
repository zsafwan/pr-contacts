# PR Contacts Extractor

![Version](https://img.shields.io/badge/version-0.0.2-blue.svg)
![Python](https://img.shields.io/badge/python-3.11+-green.svg)

A web application that reads Google Workspace emails, extracts PR agency contact information, dynamically categorizes contacts by PR type using AI, and provides a searchable database with web interface.

## Features

- **Gmail Integration**: OAuth2 authentication to securely read your emails
- **Smart Contact Extraction**: Parses email headers and signatures to extract names, titles, companies, and phone numbers
- **AI Categorization**: Uses Claude API to automatically categorize contacts (Technology, Travel, Healthcare, etc.)
- **Brand Tracking**: Identifies and tracks brand/company mentions in PR emails
- **Web Dashboard**: Streamlit-based interface for browsing, searching, and exporting contacts
- **CSV Export**: Export filtered contact lists for use in other tools

## Tech Stack

- **Backend**: Python 3.11+
- **Gmail Integration**: Google Gmail API with OAuth2
- **AI/NLP**: Claude API (Anthropic) for categorization & entity extraction
- **Database**: SQLite with SQLAlchemy ORM
- **Web Interface**: Streamlit
- **Environment**: python-dotenv for configuration

## Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/yourusername/pr-contacts.git
   cd pr-contacts
   ```

2. Create a virtual environment and install dependencies:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```

3. Set up Google Cloud credentials:
   - Go to [Google Cloud Console](https://console.cloud.google.com/)
   - Create a new project
   - Enable the Gmail API
   - Create OAuth 2.0 credentials (Desktop application)
   - Download the credentials and save as `credentials.json` in the project root

4. Configure environment variables:
   ```bash
   cp .env.example .env
   ```
   Edit `.env` and add your Anthropic API key:
   ```
   ANTHROPIC_API_KEY=sk-ant-xxxxx
   ```

## Usage

### Run Extraction (CLI)

```bash
# Test with 5 emails
python run_extraction.py --test

# Extract from last 90 days (default)
python run_extraction.py

# Extract from last 30 days
python run_extraction.py --days 30

# Skip AI categorization (faster, basic extraction only)
python run_extraction.py --skip-categorization

# Discover categories from sample emails
python run_extraction.py --discover-categories
```

### Web Interface

```bash
streamlit run app.py
```

The web interface includes:
- **Dashboard**: Overview stats, category distribution, top brands
- **Contacts**: Browse, search, filter, and export contacts
- **Categories**: View contacts by category
- **Brands**: See brand mention statistics
- **Run Extraction**: Trigger extraction from the web UI

## Project Structure

```
pr-contacts/
├── .env.example              # Template for environment variables
├── requirements.txt          # Python dependencies
├── credentials.json          # Google OAuth credentials (gitignored)
├── token.json               # OAuth token (gitignored, auto-generated)
├── database.db              # SQLite database (gitignored)
├── src/
│   ├── __init__.py
│   ├── config.py            # Configuration management
│   ├── gmail_client.py      # Gmail API integration
│   ├── contact_extractor.py # Extract contacts from emails
│   ├── categorizer.py       # Claude API categorization
│   ├── database.py          # SQLAlchemy models & operations
│   └── utils.py             # Helper functions
├── app.py                   # Streamlit web application
└── run_extraction.py        # CLI script for extraction
```

## Database Schema

- **contacts**: Main contact information (name, email, company, title, phone)
- **contact_emails**: Additional email addresses for contacts
- **categories**: PR categories (Technology, Travel, etc.)
- **contact_categories**: Many-to-many relationship with confidence scores
- **brands**: Tracked brands/companies
- **contact_brands**: Many-to-many relationship with mention counts
- **emails_processed**: Track which emails have been processed

## License

MIT
