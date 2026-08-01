# Email Automator

A self-hosted email campaign automation tool built with Python (Flask + APScheduler). Upload a CSV of recipients, compose your message once, and the app sends personalized emails on a throttled schedule using your own SMTP credentials — no email service provider or API keys required.

## Features

- **PIN-protected dashboard** — set a PIN on first launch, login to manage everything, change PIN anytime
- **Status dashboard** — live stat cards (recipients / sent / pending / failed), daily-limit and queue progress bars, status breakdown, worker state pill, and a recent-activity log
- **Campaign management** — start, pause, resume campaigns with live progress tracking
- **CSV recipient upload** — `name,email` format with `{name}` personalization tokens in subject/body
- **Batching & throttling** — one email per `GAP_MINUTES` (default 30), max `DAILY_LIMIT` (default 15) per day — both configurable via env vars
- **Background scheduler** — APScheduler checks the queue every minute and sends when the gap/limit rules allow; runs 24/7 while the process is up
- **Per-recipient status tracking** — pending / sent / failed states with error messages
- **JSON file storage** — no database needed; everything lives in `data/`
- **Test send** — verify SMTP settings before launching a campaign

## Tech Stack

- Backend: Flask (Python 3.10+)
- Scheduler: APScheduler (background thread)
- Email: `smtplib` + `email` from the standard library
- Storage: JSON files in `data/`
- Frontend: Vanilla HTML/CSS/JS (no build step)
- Tests: `unittest` (no extra dependencies)

## Project Structure

```
├── app.py                        # Entry point: creates app, starts scheduler
├── email_automator/
│   ├── __init__.py               # Flask app factory
│   ├── core.py                   # Storage, PIN auth, CSV parsing, SMTP, send rules
│   ├── routes.py                 # /api endpoints
│   └── scheduler.py              # APScheduler background job
├── templates/index.html          # Dashboard UI
├── static/
│   ├── style.css                 # Styles
│   └── app.js                    # Frontend logic
├── tests/test_core.py            # Unit tests
├── data/                         # Runtime JSON storage (gitignored)
├── sample.csv                    # Example recipient list
└── requirements.txt
```

## Getting Started

### Prerequisites

- Python 3.10+
- SMTP credentials (e.g. Gmail app password, Zoho, or any SMTP provider)

### Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py          # http://localhost:8000
```

### Configuration (optional env vars)

| Variable | Default | Description |
|---|---|---|
| `PORT` | `8000` | HTTP port |
| `DATA_DIR` | `./data` | Where JSON storage lives |
| `DAILY_LIMIT` | `15` | Max emails per day |
| `GAP_MINUTES` | `30` | Min minutes between sends |
| `LOCK_MINUTES` | `5` | Send lock expiry (prevents double-sends) |
| `LOG_LIMIT` | `50` | Entries kept in the activity log |

Run with a WSGI server for production (the scheduler only works in the process that starts it, so keep a single worker):

```bash
pip install gunicorn
gunicorn -w 1 -b 0.0.0.0:8000 app:app
```

### First-Time Setup

1. Open the app — you'll be asked to set a PIN.
2. Go to **Settings** and enter your SMTP host, port, user, and password. Use **Send test email** to verify.
3. Write your subject and body in **Campaign**, using `{name}` for personalization.
4. Upload your recipients via a CSV (`name,email` — see `sample.csv`).
5. Press **Start** — emails are sent automatically by the background scheduler at one per `GAP_MINUTES`, up to `DAILY_LIMIT` per day.
6. Watch progress on the **Dashboard**.

## Running Tests

```bash
python -m unittest discover -s tests
```

## Sample CSV

```csv
name,email
Rahul Sharma,rahul@example.com
Priya Verma,priya@example.com
```

## License

MIT — see [LICENSE](LICENSE).
