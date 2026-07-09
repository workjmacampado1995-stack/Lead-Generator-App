# Lead Generator App

A Python-based lead generation and outreach tool designed to help identify small businesses that may benefit from bookkeeping or outsourced business services.

## Overview
This project combines two simple workflows:
- a lead finder that searches public OpenStreetMap data for businesses in targeted cities
- a lightweight CRM-style outreach app for managing leads and sending cold outreach emails

It is a practical portfolio project that shows data collection, automation, and basic business workflow design.

## Features
- Search for businesses in selected cities
- Filter by business categories such as restaurants, salons, repair shops, and more
- Generate a CSV file of leads with business name, address, phone, website, and email when available
- Import leads into a simple web app
- Track lead status and notes
- Send personalized outreach emails using SMTP settings

## Project Structure
- lead_finder_osm.py — main lead generation script
- crm_app/ — simple web app for lead management and outreach
- requirements.txt — Python dependencies
- sample_leads.csv — example lead input data

## Tech Stack
- Python
- FastAPI
- Jinja2
- SQLite
- OpenStreetMap / Overpass API
- HTML, CSS, JavaScript

## Getting Started

### 1. Create and activate a virtual environment
```bash
python -m venv .venv
.venv\Scripts\activate
```

### 2. Install dependencies
```bash
pip install -r requirements.txt
```

### 3. Run the lead finder
```bash
python lead_finder_osm.py --cities "Los Angeles, California, USA" --business-types amenity:restaurant shop:hairdresser --output leads.csv
```

### 4. Run the outreach app
```bash
cd crm_app
python -m uvicorn app:app --host 127.0.0.1 --port 8001
```

Then open:
```text
http://127.0.0.1:8001/
```

## Notes
- This project uses public map data and may not include complete contact details.
- For real email sending, configure SMTP settings inside the CRM app.
- Use the sample CSV file as a test input if needed.

## Why This Project Is Valuable
This project demonstrates:
- data gathering from public sources
- automation for lead discovery
- business-focused workflow design
- practical web app development for outreach operations

## Future Improvements
- add more advanced lead scoring
- add SMS or calling support
- integrate with a real CRM
- add a dashboard with analytics and reporting
