# DentClinic - Dental Clinic Management System

## Overview
A comprehensive dental clinic management system built with Flask. Features patient record management, clinical sessions with an SVG-based odontogram, appointment scheduling, stock management, and reporting with multi-language support (Portuguese, English, Spanish).

## Tech Stack
- **Backend:** Python 3.12 + Flask 3
- **Database:** SQLite (via SQLAlchemy), stored at `instance/dental.db`
- **Frontend:** Bootstrap 5 + Jinja2 templating + FullCalendar.js
- **Auth:** Flask-Login + Flask-WTF (CSRF)
- **i18n:** Flask-Babel (PT default, EN, ES)
- **PDF generation:** ReportLab
- **Package manager:** pip

## Project Structure
- `run.py` — App entry point
- `app/` — Main application package (Application Factory pattern)
  - `__init__.py` — Factory, DB init, migrations, seeding
  - `models.py` — Database models
  - `extensions.py` — Flask extension instances
  - Blueprints: `auth/`, `admin/`, `main/`, `patients/`, `scheduling/`, `sessions/`, `superadmin/`, `stock/`, `pdfs/`
- `instance/` — SQLite database and config
- `translations/` — i18n files (pt, en, es)
- `uploads/` — Uploaded files

## Running the App
- **Dev:** `python run.py` on port 5000 (0.0.0.0)
- **Production:** `gunicorn --bind=0.0.0.0:5000 --reuse-port run:app`

## Default Credentials
- Username: `admin` / Password: `admin`
- To seed demo users, set env var `SEED_DEMO_USERS=1`

## Database
- SQLite at `instance/dental.db`
- Auto-migrated on startup (idempotent column additions)
- Auto-seeded with admin user and 2 rooms on first run

## Recent Changes
- **Medical Order Number (`license_number`)**: Added support for storing and displaying the medical order number for dentists/clinical directors
  - Added database column with auto-migration
  - Dentists can edit their own number in the profile page
  - Admin can manage via user admin panel
  - Number appears in PDFs below the dentist's name in signature blocks
- **PDF Signature Label Toggle**: Added new setting "Mostrar rótulo de assinatura" in PDF template editor to control visibility of signature/stamp labels in all three PDF types

## Notes
- SECRET_KEY env var should be set in production
- Flask-Babel translations compiled automatically on startup
- Max upload size: 512 MB
