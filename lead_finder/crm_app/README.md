# US Outreach CRM

A simple starter app for managing leads and sending outreach emails to U.S. clients from the Philippines.

## Features
- Add leads manually
- Import leads from CSV
- Track follow-up status
- Send outreach emails (requires SMTP configuration)

## Run locally

```bash
cd crm_app
pip install -r requirements.txt
uvicorn app:app --reload
```

Then open http://127.0.0.1:8000/

## Email setup
Set these environment variables before sending mail:

```bash
export SMTP_HOST=your-smtp-host
export SMTP_PORT=587
export SMTP_USERNAME=your-username
export SMTP_PASSWORD=your-password
export SMTP_FROM=you@example.com
```
