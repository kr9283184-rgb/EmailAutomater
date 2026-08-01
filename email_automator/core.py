import csv
import hashlib
import json
import logging
import os
import re
import smtplib
import threading
import time
from datetime import datetime
from email.message import EmailMessage
from email.utils import formataddr
from io import StringIO
from zoneinfo import ZoneInfo

log = logging.getLogger("email_automator.core")

DATA_DIR = os.environ.get("DATA_DIR", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data"))
DAILY_LIMIT = int(os.environ.get("DAILY_LIMIT", 100))
GAP_MINUTES = int(os.environ.get("GAP_MINUTES", 5))
LOCK_MINUTES = int(os.environ.get("LOCK_MINUTES", 5))
LOG_LIMIT = int(os.environ.get("LOG_LIMIT", 50))
DOMAIN_DAILY_LIMIT = int(os.environ.get("DOMAIN_DAILY_LIMIT", 100))
SEND_START_HOUR = int(os.environ.get("SEND_START_HOUR", 8))
SEND_END_HOUR = int(os.environ.get("SEND_END_HOUR", 21))
SPAM_WARN = int(os.environ.get("SPAM_WARN", 30))
SPAM_BLOCK = int(os.environ.get("SPAM_BLOCK", 50))
TIMEZONE = os.environ.get("TIMEZONE", "Europe/Brussels")
PERSIST_CREDS = os.environ.get("PERSIST_CREDS", "").lower() in ("1", "true", "yes", "on")
CREDS_KEY = os.environ.get("CREDS_KEY", "")

os.makedirs(DATA_DIR, exist_ok=True)

_LOCK = threading.RLock()

# SMTP credentials normally live only in memory (populated by the browser at
# login) and are never written to disk. With PERSIST_CREDS=1 they are stored
# encrypted on disk instead, so the scheduler survives restarts without a
# browser login (headless 24/7 deployments).
_SMTP_CREDS = {"user": "", "pass": ""}

_CREDS_FILE = os.path.join(DATA_DIR, "creds.enc")
_KEY_FILE = os.path.join(DATA_DIR, ".creds.key")


def set_smtp_creds(user, password):
    if not user or not password:
        _SMTP_CREDS["user"] = ""
        _SMTP_CREDS["pass"] = ""
        _delete_persisted()
        return False
    _SMTP_CREDS["user"] = user
    _SMTP_CREDS["pass"] = password
    _persist_creds()
    return True


def get_smtp_creds():
    return dict(_SMTP_CREDS)


def _creds_key():
    if CREDS_KEY:
        return CREDS_KEY.encode()
    try:
        with open(_KEY_FILE, "rb") as f:
            return f.read()
    except OSError:
        from cryptography.fernet import Fernet
        key = Fernet.generate_key()
        fd = os.open(_KEY_FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "wb") as f:
            f.write(key)
        return key


def _persist_creds():
    if not PERSIST_CREDS:
        return
    from cryptography.fernet import Fernet
    token = Fernet(_creds_key()).encrypt(json.dumps(_SMTP_CREDS).encode())
    tmp = _CREDS_FILE + ".tmp"
    with open(tmp, "wb") as f:
        f.write(token)
    os.replace(tmp, _CREDS_FILE)


def _delete_persisted():
    if not PERSIST_CREDS:
        return
    try:
        os.remove(_CREDS_FILE)
    except OSError:
        pass


def _load_persisted_creds():
    if not PERSIST_CREDS:
        return
    if _SMTP_CREDS["user"] and _SMTP_CREDS["pass"]:
        return
    if not os.path.exists(_CREDS_FILE):
        return
    try:
        from cryptography.fernet import Fernet
        with open(_CREDS_FILE, "rb") as f:
            token = f.read()
        data = json.loads(Fernet(_creds_key()).decrypt(token))
        _SMTP_CREDS.update(data)
        log.info("Loaded persisted SMTP credentials from disk")
    except Exception as err:
        log.warning("Could not decrypt persisted SMTP credentials: %s", err)

EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
HTML_RE = re.compile(r"<[a-z][\s\S]*>", re.IGNORECASE)


def _path(key):
    return os.path.join(DATA_DIR, key + ".json")


def get_json(key, fallback=None):
    with _LOCK:
        try:
            with open(_path(key), "r", encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            return fallback


def set_json(key, value):
    with _LOCK:
        tmp = _path(key) + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(value, f, ensure_ascii=False)
        os.replace(tmp, _path(key))


def migrate_old_creds():
    """One-time cleanup: pull plaintext user/pass out of settings.json
    into memory, then scrub them from disk."""
    settings = get_json("settings") or {}
    if settings.get("user") or settings.get("pass"):
        if settings.get("user") and settings.get("pass"):
            set_smtp_creds(settings["user"], settings["pass"])
        settings.pop("user", None)
        settings.pop("pass", None)
        set_json("settings", settings)


migrate_old_creds()
_load_persisted_creds()


# ================= PIN =================

def hash_pin(pin, salt):
    return hashlib.pbkdf2_hmac("sha256", pin.encode(), salt.encode(), 100_000).hex()


def create_pin_meta(pin):
    salt = os.urandom(16).hex()
    return {"salt": salt, "hash": hash_pin(pin, salt)}


def check_pin(pin):
    meta = get_json("meta")
    if not meta or not meta.get("hash"):
        return False
    return hash_pin(str(pin), meta["salt"]) == meta["hash"]


# ================= CSV =================

def parse_csv(text):
    lines = [l for l in str(text or "").replace("\r", "").splitlines() if l.strip()]
    if not lines:
        return [], "CSV is empty"
    header = next(csv.reader([lines[0]]))
    header = [h.strip().lower() for h in header]
    name_idx = header.index("name") if "name" in header else 0
    email_idx = header.index("email") if "email" in header else min(1, len(header) - 1)

    items = []
    seen = set()
    for line in lines[1:]:
        cells = next(csv.reader([line]))
        cells = [c.strip() for c in cells]
        email = (cells[email_idx] if email_idx < len(cells) else "").lower()
        if not EMAIL_RE.match(email) or email in seen:
            continue
        seen.add(email)
        name = (cells[name_idx] if name_idx < len(cells) and cells[name_idx] else "") or email.split("@")[0]
        items.append({"name": name, "email": email, "status": "pending", "error": "", "sentAt": ""})
    if not items:
        return [], "No valid emails found in CSV (check name,email headers)"
    return items, ""


# ================= Email =================

def replace_name(text, name):
    return str(text or "").replace("{name}", name or "")


def is_html(text):
    return bool(HTML_RE.search(str(text or "")))


SPAM_WORDS = [
    "free", "win", "winner", "prize", "cash", "guarantee", "guaranteed",
    "urgent", "act now", "limited offer", "limited time", "buy now",
    "click here", "discount", "cheap", "credit", "lottery", "millions",
    "invest", "make money", "earn", "no obligation", "100%", "risk free",
    "dear friend", "viagra", "$$$", "double your", "instant",
]


def strip_html(text):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", str(text or ""))).strip()


def spam_check(subject, body):
    """Score 0-100. Warn at SPAM_WARN, block at SPAM_BLOCK."""
    plain = strip_html(f"{subject or ''} {body or ''}")
    text = plain.lower()
    score = 0
    issues = []
    for word in SPAM_WORDS:
        if word in text:
            score += 10
            issues.append(f'Trigger word: "{word}"')
    letters = sum(1 for c in plain if c.isalpha())
    caps = sum(1 for c in plain if c.isupper())
    if letters and caps / letters > 0.4:
        score += 15
        issues.append("Excessive ALL CAPS")
    if text.count("!") > 2:
        score += 10
        issues.append("Too many exclamation marks")
    if text.count("$") > 2:
        score += 10
        issues.append("Money symbols in message")
    links = len(re.findall(r"https?://", text))
    if links:
        score += min(15, links * 5)
        issues.append(f"{links} link(s) in message")
    if len(text) < 80:
        score += 8
        issues.append("Very short message")
    return {"score": min(100, score), "issues": issues[:8]}


def domain_of(email):
    return email.rsplit("@", 1)[-1].lower() if "@" in email else ""


def _now_tz():
    return datetime.now(ZoneInfo(TIMEZONE))


def outside_window(now=None):
    t = now or _now_tz()
    hour = t.hour if hasattr(t, "hour") else t.tm_hour
    return hour < SEND_START_HOUR or hour >= SEND_END_HOUR


def send_mail(settings, to, subject, body):
    msg = EmailMessage()
    msg["From"] = formataddr((settings.get("fromName") or settings["user"], settings["user"]))
    msg["To"] = to
    msg["Subject"] = subject
    msg["List-Unsubscribe"] = f"<mailto:{settings['user']}?subject=unsubscribe>"
    if is_html(body):
        msg.set_content(strip_html(body))
        msg.add_alternative(body, subtype="html")
    else:
        msg.set_content(body)

    host = settings.get("host") or "smtp.gmail.com"
    port = int(settings.get("port") or 465)
    secure = bool(settings.get("secure", port == 465))
    user = settings["user"]
    password = settings["pass"]

    if secure:
        with smtplib.SMTP_SSL(host, port, timeout=30) as server:
            server.login(user, password)
            server.send_message(msg)
    else:
        with smtplib.SMTP(host, port, timeout=30) as server:
            server.starttls()
            server.login(user, password)
            server.send_message(msg)


# ================= Activity log =================

def log_event(kind, detail="", ok=True):
    logs = get_json("logs", [])
    logs.insert(0, {"t": time.strftime("%Y-%m-%d %H:%M:%S"), "kind": kind, "detail": detail, "ok": ok})
    set_json("logs", logs[:LOG_LIMIT])


# ================= Core send rules =================

def today_key():
    """Calendar day in the configured TIMEZONE (daily limit resets here)."""
    return _now_tz().strftime("%Y-%m-%d")


def run_send_once():
    settings = get_json("settings")
    if not settings:
        return {"status": "no-settings"}
    creds = _SMTP_CREDS
    if not creds["user"] or not creds["pass"]:
        return {"status": "creds-needed"}
    settings = dict(settings)
    settings["user"] = creds["user"]
    settings["pass"] = creds["pass"]

    queue = get_json("queue", {"items": []})
    if not queue.get("items"):
        return {"status": "empty"}
    if queue.get("paused"):
        return {"status": "paused"}
    if outside_window():
        return {"status": "outside-window"}

    lock = get_json("lock")
    if lock and time.time() - lock["t"] < LOCK_MINUTES * 60:
        return {"status": "locked"}
    set_json("lock", {"t": time.time()})

    today = today_key()
    daily = get_json("daily", {"date": today, "count": 0, "lastSentAt": ""})
    if daily.get("date") != today:
        daily = {"date": today, "count": 0, "lastSentAt": "", "domains": {}}

    if daily["count"] >= DAILY_LIMIT:
        return {"status": "daily-limit", "count": daily["count"]}

    if daily.get("lastSentAt"):
        elapsed = time.time() - daily["lastSentAt"]
        wait_sec = GAP_MINUTES * 60 - elapsed
        if wait_sec > 0:
            return {"status": "gap", "waitMin": int(wait_sec // 60) + 1}

    pending_idx = [i for i, item in enumerate(queue["items"]) if item["status"] == "pending"]
    if not pending_idx:
        return {"status": "done"}

    domains_used = daily.get("domains") or {}
    idx = next(
        (i for i in pending_idx if domains_used.get(domain_of(queue["items"][i]["email"]), 0) < DOMAIN_DAILY_LIMIT),
        None,
    )
    if idx is None:
        return {"status": "domain-limit", "limit": DOMAIN_DAILY_LIMIT}

    item = queue["items"][idx]
    try:
        send_mail(
            settings,
            item["email"],
            replace_name(settings.get("subject"), item["name"]),
            replace_name(settings.get("body"), item["name"]),
        )
        item["status"] = "sent"
        item["error"] = ""
        item["sentAt"] = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime())
        daily["count"] += 1
        daily["lastSentAt"] = time.time()
        domains_used[domain_of(item["email"])] = domains_used.get(domain_of(item["email"]), 0) + 1
        daily["domains"] = domains_used
        set_json("queue", queue)
        set_json("daily", daily)
        log_event("sent", item["email"], True)
        return {"status": "sent", "to": item["email"], "count": daily["count"]}
    except Exception as err:
        item["status"] = "failed"
        item["error"] = str(err)[:500]
        set_json("queue", queue)
        log_event("failed", f"{item['email']}: {item['error']}", False)
        return {"status": "failed", "to": item["email"], "error": item["error"]}
