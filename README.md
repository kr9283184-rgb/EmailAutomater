# Email Automator

A self-hosted email campaign automation tool built with Python (Flask + APScheduler). Upload a CSV of recipients, compose your message once, and the app sends personalized emails on a throttled schedule using your own SMTP credentials — no email service provider or API keys required.

## Features

- **PIN-protected dashboard** — set a PIN on first launch, login to manage everything, change PIN anytime
- **Status dashboard** — live stat cards (recipients / sent / pending / failed), daily-limit and queue progress bars, status breakdown, worker state pill, and a recent-activity log
- **Campaign management** — start, pause, resume campaigns with live progress tracking
- **CSV recipient upload** — `name,email` format with `{name}` personalization tokens in subject/body
- **Batching & throttling** — one email per `GAP_MINUTES` (default 5), max `DAILY_LIMIT` (default 100) per day — both configurable via env vars
- **Credential security** — SMTP email/password live only in your browser (localStorage); the server keeps them in memory while you're logged in and never writes them to disk. Set `PERSIST_CREDS=1` for headless 24/7 deployments (encrypted at rest instead)
- **Timezone-aware sending** — the sending window is evaluated in a configurable timezone (default `Europe/Brussels`), so EU recipients get mail during their business hours regardless of where the server runs
- **Completion notification** — when all recipients are processed the dashboard shows a toast, plays a beep, and (if allowed) sends a browser notification
- **Anti-spam safeguards** — content scoring (blocks high-risk templates, warns on medium), both plain-text + HTML parts in every email, a per-domain daily cap, and a daytime sending window
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
| `DAILY_LIMIT` | `100` | Max emails per day |
| `GAP_MINUTES` | `5` | Min minutes between sends |
| `LOCK_MINUTES` | `5` | Send lock expiry (prevents double-sends) |
| `LOG_LIMIT` | `50` | Entries kept in the activity log |
| `DOMAIN_DAILY_LIMIT` | `100` | Max emails per recipient domain per day |
| `SEND_START_HOUR` / `SEND_END_HOUR` | `8` / `21` | Only send between these local hours |
| `SPAM_WARN` / `SPAM_BLOCK` | `30` / `50` | Spam score thresholds for warning / blocking campaign start |
| `TIMEZONE` | `Europe/Brussels` | IANA tz for the sending window and daily-limit reset |
| `PERSIST_CREDS` | `0` | `1` stores SMTP creds encrypted on disk (auto-reload after restarts) |
| `CREDS_KEY` | *(empty)* | Optional encryption key for `PERSIST_CREDS` (else a 0600 key file in `DATA_DIR`) |

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

## Deploying on Railway

Railway's filesystem is **ephemeral** (wiped on every restart), so persistent storage must live on a Volume.

1. Push this repo to GitHub.
2. In Railway: **New Project → Deploy from GitHub repo** → select `EmailAutomater`.
3. Add a **Volume** to the service:
   - Mount path: `/data`
   - (any size ≥ 1 GB is fine)
4. Set the environment variables in the service settings:
   - `DATA_DIR=/data`
   - `PERSIST_CREDS=1`
   - `CREDS_KEY=<generate with: python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())">`
   - `TIMEZONE=Europe/Brussels` (or your recipients' tz)
   - `DAILY_LIMIT=100`, `GAP_MINUTES=5`, `SEND_START_HOUR=8`, `SEND_END_HOUR=21` (defaults, optional)
5. The `Procfile` starts `gunicorn -w 1` (single worker — required, the scheduler runs inside it) on the `PORT` Railway provides.
6. Deploy, open the app URL, set your PIN, save SMTP settings once — credentials get encrypted to the volume (`/data/creds.enc`) and survive restarts automatically.

Note: `starttls` is required for port 587 — verify with **Send test email** on the deployed site.

## Running Tests

```bash
python -m unittest discover -s tests
```

## Credential Security

Your SMTP email and password are **never stored on the server's disk**:

- The browser keeps them in `localStorage`, keyed to your machine.
- On login (or whenever you save settings) they're pushed to the server's **memory only** — the background sender uses them from there.
- A server restart clears them; you just log in again from the dashboard to reload them.
- The dashboard shows an amber "SMTP credentials not loaded" pill whenever the server has no credentials (e.g. right after a restart).
- Old plaintext credentials are automatically scrubbed from `settings.json` on first run of this version.

This means even a fully compromised platform or a dumped `data/` folder yields no credentials — the password exists only in your browser until you log in.

### Headless 24/7 deployments (`PERSIST_CREDS=1`)

If you run the app on an always-on box where nobody logs into the dashboard (so the browser can't re-supply credentials after a restart), enable persistent mode:

```bash
export PERSIST_CREDS=1
# recommended: set your own key so creds can't be decrypted without it
export CREDS_KEY="$(python3 -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')"
python app.py
```

Credentials are then encrypted (Fernet/AES) to `data/creds.enc` and auto-loaded into memory on every startup — the scheduler keeps working across restarts with no browser involved. The key is your `CREDS_KEY`; without it a key file is auto-generated with `0600` permissions inside `DATA_DIR` (protects against casual access, but a full server compromise also gets the key — set `CREDS_KEY` for real security).

## Reducing Spam Rate

The app applies several layers to keep emails out of the spam folder:

- **Content scoring** — subject + body are scored 0–100 against common spam triggers (money words, ALL CAPS, exclamation overload, links, "click here"/"buy now" phrasing). Score ≥ `SPAM_WARN` shows a warning when you save; score ≥ `SPAM_BLOCK` refuses to start the campaign and lists the trigger words. The score is visible in Settings and Campaign.
- **Text + HTML parts** — every HTML message also carries a plain-text version, which filters treat more favorably than HTML-only mail.
- **Per-domain cap** — max `DOMAIN_DAILY_LIMIT` emails per recipient domain per day, so one provider (e.g. Gmail) doesn't see a flood from your queue.
- **Sending window** — emails only go out between `SEND_START_HOUR` and `SEND_END_HOUR` in the `TIMEZONE` (default `Europe/Brussels` — set it to your recipients' timezone), avoiding overnight bursts that look automated.
- **List-Unsubscribe header** — already added to every message.

### Delivering even better

- Keep the message personal, 1–2 paragraphs, 1 link maximum, and avoid ALL CAPS.
- Use your own domain + SPF/DKIM records if your provider supports custom domains — the single biggest trust signal.
- Warm up: start small (e.g. 20–30/day) and increase over a week before pushing high volumes.
- Note: with a 5-min gap, the theoretical max is ~288/day (24h) — the daily cap above that can't be reached unless you lower `GAP_MINUTES`.

## Sample CSV

```csv
name,email
Rahul Sharma,rahul@example.com
Priya Verma,priya@example.com
```

## License

MIT — see [LICENSE](LICENSE).
