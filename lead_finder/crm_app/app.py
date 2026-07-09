import csv
import json
import os
import smtplib
import sqlite3
from email.message import EmailMessage
from pathlib import Path

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "leads.db"
SETTINGS_PATH = BASE_DIR / "settings.json"

templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
app = FastAPI(title="Salvation Territory", version="0.1.0")
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

DEFAULT_USERNAME = os.getenv("CRM_USERNAME", "admin")
DEFAULT_PASSWORD = os.getenv("CRM_PASSWORD", "admin123")
SESSION_COOKIE = "crm_user"
DEFAULT_EMAIL_TEMPLATE = """Hi {First Name},

I came across {Business Name} while researching local businesses in {City}, and wanted to reach out directly rather than send a generic pitch.

A lot of small business owners I talk to are handling their own bookkeeping on top of everything else — which works, until tax season sneaks up or a reconciliation gets missed.

I help small businesses like yours keep clean, accurate books for a flat monthly fee, usually well below what a local bookkeeper or in-house hire would cost. No long-term contract, no setup fees, and I'm happy to do a free 20-minute review of your current books (QuickBooks/Xero) just so you can see where things stand — no obligation either way.

Would you be open to a quick call sometime this week or next?

Best,
{Your Name}
{Your Business Name}
{Phone/Email}
"""


def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS leads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                company TEXT,
                email TEXT,
                phone TEXT,
                location TEXT,
                status TEXT DEFAULT 'New',
                notes TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.commit()


init_db()


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def fetch_leads():
    with get_db() as conn:
        rows = conn.execute(
            "SELECT id, name, company, email, phone, location, status, notes, created_at FROM leads ORDER BY id DESC"
        ).fetchall()
    return [dict(row) for row in rows]


def insert_lead(name, company, email, phone, location, status, notes):
    with get_db() as conn:
        conn.execute(
            "INSERT INTO leads (name, company, email, phone, location, status, notes) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (name, company, email, phone, location, status, notes),
        )
        conn.commit()


def update_lead_status(lead_id, status, notes):
    with get_db() as conn:
        conn.execute(
            "UPDATE leads SET status = ?, notes = ? WHERE id = ?",
            (status, notes, lead_id),
        )
        conn.commit()


def get_current_user(request: Request):
    return request.cookies.get(SESSION_COOKIE)


def set_session_cookie(response, username: str):
    response.set_cookie(SESSION_COOKIE, username, httponly=True, samesite="lax")


def clear_session_cookie(response):
    response.delete_cookie(SESSION_COOKIE)


def authenticate(username: str, password: str) -> bool:
    return username == DEFAULT_USERNAME and password == DEFAULT_PASSWORD


def load_settings():
    if SETTINGS_PATH.exists():
        try:
            with open(SETTINGS_PATH, "r", encoding="utf-8") as handle:
                return json.load(handle)
        except json.JSONDecodeError:
            return {}
    return {}


def save_settings(settings):
    with open(SETTINGS_PATH, "w", encoding="utf-8") as handle:
        json.dump(settings, handle, indent=2)


def get_settings():
    settings = load_settings()
    defaults = {
        "smtp_host": os.getenv("SMTP_HOST", ""),
        "smtp_port": os.getenv("SMTP_PORT", "587"),
        "smtp_username": os.getenv("SMTP_USERNAME", ""),
        "smtp_password": os.getenv("SMTP_PASSWORD", ""),
        "smtp_from": os.getenv("SMTP_FROM", ""),
        "sender_name": os.getenv("SENDER_NAME", "Your Name"),
        "business_name": os.getenv("BUSINESS_NAME", "Your Business Name"),
        "sender_contact": os.getenv("SENDER_CONTACT", "yourphone@example.com"),
        "email_subject": "Quick question about your bookkeeping",
        "email_template": DEFAULT_EMAIL_TEMPLATE,
    }
    defaults.update(settings)
    return defaults


def render_email_template(template, lead, settings):
    first_name = lead.get("name", "there").split()[0].strip() or "there"
    business_name = lead.get("company", "your business").strip() or "your business"
    city = lead.get("location", "your city").split(",")[0].strip() or "your city"
    replacements = {
        "{First Name}": first_name,
        "{Business Name}": business_name,
        "{City}": city,
        "{Your Name}": settings.get("sender_name", "Your Name"),
        "{Your Business Name}": settings.get("business_name", "Your Business Name"),
        "{Phone/Email}": settings.get("sender_contact", "yourphone@example.com"),
    }
    rendered = template
    for key, value in replacements.items():
        rendered = rendered.replace(key, value)
    return rendered


def send_email(to_email, subject, body, settings):
    smtp_host = settings.get("smtp_host") or os.getenv("SMTP_HOST")
    smtp_port = int(settings.get("smtp_port") or os.getenv("SMTP_PORT", "587"))
    smtp_user = settings.get("smtp_username") or os.getenv("SMTP_USERNAME")
    smtp_password = settings.get("smtp_password") or os.getenv("SMTP_PASSWORD")
    smtp_from = settings.get("smtp_from") or os.getenv("SMTP_FROM") or smtp_user or "outreach@example.com"

    if not all([smtp_host, smtp_user, smtp_password]):
        raise RuntimeError("SMTP is not configured. Set SMTP_HOST, SMTP_USERNAME, SMTP_PASSWORD, or use the settings form.")

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = smtp_from
    msg["To"] = to_email
    msg.set_content(body)

    with smtplib.SMTP(smtp_host, smtp_port, timeout=20) as server:
        server.starttls()
        server.login(smtp_user, smtp_password)
        server.send_message(msg)


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    if get_current_user(request):
        return RedirectResponse(url="/", status_code=303)
    return templates.TemplateResponse(request, "login.html", {"request": request, "error": None})


@app.post("/login")
async def login(request: Request, username: str = Form(...), password: str = Form(...)):
    if authenticate(username, password):
        response = RedirectResponse(url="/", status_code=303)
        set_session_cookie(response, username)
        return response

    return templates.TemplateResponse(
        request,
        "login.html",
        {"request": request, "error": "Invalid username or password. Try admin / admin123"},
    )


@app.post("/logout")
async def logout():
    response = RedirectResponse(url="/login", status_code=303)
    clear_session_cookie(response)
    return response


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse(request, "landing.html", {"request": request})


@app.get("/crm", response_class=HTMLResponse)
async def crm_home(request: Request):
    if not get_current_user(request):
        return RedirectResponse(url="/login", status_code=303)

    leads = fetch_leads()
    settings = get_settings()
    return templates.TemplateResponse(
        request,
        "index.html",
        {"request": request, "leads": leads, "username": get_current_user(request), "settings": settings},
    )


@app.post("/leads")
async def create_lead(
    request: Request,
    name: str = Form(...),
    company: str = Form(""),
    email: str = Form(""),
    phone: str = Form(""),
    location: str = Form(""),
    status: str = Form("New"),
    notes: str = Form(""),
):
    if not get_current_user(request):
        return RedirectResponse(url="/login", status_code=303)

    insert_lead(name, company, email, phone, location, status, notes)
    return RedirectResponse(url="/", status_code=303)


@app.post("/import")
async def import_leads(request: Request, file: UploadFile = File(...)):
    if not get_current_user(request):
        return RedirectResponse(url="/login", status_code=303)

    if not file.filename or not file.filename.endswith(".csv"):
        return RedirectResponse(url="/", status_code=303)

    contents = await file.read()
    text = contents.decode("utf-8-sig")
    reader = csv.DictReader(text.splitlines())

    for row in reader:
        insert_lead(
            name=row.get("name", "").strip() or "Unknown",
            company=row.get("company", "").strip(),
            email=row.get("email", "").strip(),
            phone=row.get("phone", "").strip(),
            location=row.get("location", "").strip(),
            status=row.get("status", "New").strip() or "New",
            notes=row.get("notes", "").strip(),
        )

    return RedirectResponse(url="/", status_code=303)


@app.post("/settings")
async def save_outreach_settings(
    request: Request,
    smtp_host: str = Form(""),
    smtp_port: str = Form("587"),
    smtp_username: str = Form(""),
    smtp_password: str = Form(""),
    smtp_from: str = Form(""),
    sender_name: str = Form("Your Name"),
    business_name: str = Form("Your Business Name"),
    sender_contact: str = Form("yourphone@example.com"),
    email_subject: str = Form("Quick question about your bookkeeping"),
    email_template: str = Form(DEFAULT_EMAIL_TEMPLATE),
):
    if not get_current_user(request):
        return RedirectResponse(url="/login", status_code=303)

    save_settings(
        {
            "smtp_host": smtp_host,
            "smtp_port": smtp_port,
            "smtp_username": smtp_username,
            "smtp_password": smtp_password,
            "smtp_from": smtp_from,
            "sender_name": sender_name,
            "business_name": business_name,
            "sender_contact": sender_contact,
            "email_subject": email_subject,
            "email_template": email_template,
        }
    )
    return RedirectResponse(url="/", status_code=303)


@app.post("/leads/{lead_id}/status")
async def update_status(request: Request, lead_id: int, status: str = Form("New"), notes: str = Form("")):
    if not get_current_user(request):
        return RedirectResponse(url="/login", status_code=303)

    update_lead_status(lead_id, status, notes)
    return RedirectResponse(url="/", status_code=303)


@app.post("/leads/{lead_id}/send")
async def send_outreach(request: Request, lead_id: int, subject: str = Form(""), body: str = Form("")):
    if not get_current_user(request):
        return RedirectResponse(url="/login", status_code=303)

    lead = next((lead for lead in fetch_leads() if lead["id"] == lead_id), None)
    if not lead:
        return RedirectResponse(url="/", status_code=303)

    settings = get_settings()
    rendered_subject = render_email_template(subject or settings.get("email_subject", ""), lead, settings)
    rendered_body = render_email_template(body or settings.get("email_template", DEFAULT_EMAIL_TEMPLATE), lead, settings)

    try:
        send_email(lead["email"], rendered_subject, rendered_body, settings)
        update_lead_status(lead_id, "Email Sent", (lead.get("notes") or "") + "\nSent: " + rendered_subject)
    except Exception as exc:
        update_lead_status(lead_id, "Pending SMTP", (lead.get("notes") or "") + f"\nSMTP error: {exc}")

    return RedirectResponse(url="/", status_code=303)


@app.post("/cold-outreach/send")
async def send_bulk_outreach(request: Request):
    if not get_current_user(request):
        return RedirectResponse(url="/login", status_code=303)

    settings = get_settings()
    leads = fetch_leads()
    leads_to_send = [lead for lead in leads if lead.get("email") and lead.get("status") != "Email Sent"]

    for lead in leads_to_send:
        rendered_subject = render_email_template(settings.get("email_subject", ""), lead, settings)
        rendered_body = render_email_template(settings.get("email_template", DEFAULT_EMAIL_TEMPLATE), lead, settings)
        try:
            send_email(lead["email"], rendered_subject, rendered_body, settings)
            update_lead_status(lead["id"], "Email Sent", (lead.get("notes") or "") + "\nSent: " + rendered_subject)
        except Exception as exc:
            update_lead_status(lead["id"], "Pending SMTP", (lead.get("notes") or "") + f"\nSMTP error: {exc}")

    return RedirectResponse(url="/", status_code=303)
