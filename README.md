# Email Automator

A self-hosted email campaign automation tool built with plain HTML/CSS/JS frontend and Netlify Functions. Upload a CSV of recipients, compose your message once, and the app sends personalized emails in batches on a schedule — no email service provider (ESP) or API keys required, just your own SMTP credentials.

## Features

- **PIN-protected dashboard** — set a PIN on first launch, login to manage everything, change PIN anytime
- **Campaign management** — start, pause, resume campaigns with a live progress tracker
- **CSV recipient upload** — `name,email` format with `{{name}}` personalization tokens in subject/body
- **Batching & throttling** — emails are sent in controlled batches to stay within SMTP rate limits
- **Scheduled sending** — Netlify scheduled functions (`sendScheduled`) process the queue every 30 minutes; a `cron-ping` keep-alive wakes the process between runs
- **Per-recipient status tracking** — pending / sent / failed states with retry for failures
- **SMTP settings stored in Netlify Blobs** — no database needed
- **Test send** — verify SMTP settings before launching a campaign

## Tech Stack

- Frontend: Vanilla HTML/CSS/JS (no build step)
- Backend: Netlify Functions (Node.js, ES modules)
- Email: [nodemailer](https://nodemailer.com/)
- Storage: [Netlify Blobs](https://docs.netlify.com/blobs/overview/)
- Tests: Node's built-in test runner (`node --test`)

## Project Structure

```
├── public/                      # Static frontend
│   └── index.html               # Single-page app (UI)
├── netlify/
│   └── functions/
│       ├── api.mjs              # Main API: PIN auth, settings, campaign control
│       ├── _core.mjs            # Shared logic: storage, SMTP, CSV parsing, batching
│       ├── sendScheduled.mjs    # Scheduled runner (every 30 min)
│       └── cron-ping.mjs        # Keep-alive ping endpoint
├── test/
│   └── core.test.mjs            # Unit tests
├── sample.csv                   # Example recipient list
├── netlify.toml                 # Build + function config
└── package.json
```

## Getting Started

### Prerequisites

- [Node.js](https://nodejs.org/) 18+
- A Netlify account (free tier works)
- SMTP credentials (e.g. Gmail app password, Zoho, or any SMTP provider)

### Local Development

```bash
npm install
npm run dev      # starts Netlify Dev on http://localhost:8888
```

### Deploy to Netlify

1. Push this repo to GitHub and import it in the Netlify dashboard (or run `netlify deploy --prod` from the CLI).
2. The `netlify.toml` handles everything:
   - `public/` is published as the site
   - `/api` handles all API actions
   - `sendScheduled` runs every 30 minutes (min allowed cron frequency) to process queued emails

### First-Time Setup

1. Open your deployed site — you'll be asked to set a PIN.
2. Go to **Settings** and enter your SMTP host, port, user, and password. Use **Test Send** to verify.
3. Upload your recipients via a CSV (`name,email` — see `sample.csv`).
4. Write your subject and body, using `{{name}}` for personalization.
5. Hit **Start** — emails are queued and sent by the scheduled function in batches.

### Keep-Alive Note

Free Netlify functions can spin down between cron runs. The built-in `cron-ping` endpoint can be hit by an external uptime monitor (e.g. UptimeRobot) to keep the site warm.

## Running Tests

```bash
npm test
```

## Sample CSV

```csv
name,email
Rahul Sharma,rahul@example.com
Priya Verma,priya@example.com
```

## License

MIT — see [LICENSE](LICENSE).
