import csv
import hashlib
import json
import os
import re
import smtplib
import threading
import time
from email.message import EmailMessage
from email.utils import formataddr
from io import StringIO

DATA_DIR = os.environ.get("DATA_DIR", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data"))
DAILY_LIMIT = int(os.environ.get("DAILY_LIMIT", 15))
GAP_MINUTES = int(os.environ.get("GAP_MINUTES", 30))
LOCK_MINUTES = int(os.environ.get("LOCK_MINUTES", 5))
LOG_LIMIT = int(os.environ.get("LOG_LIMIT", 50))

os.makedirs(DATA_DIR, exist_ok=True)

_LOCK = threading.RLock()

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


def send_mail(settings, to, subject, body):
    msg = EmailMessage()
    msg["From"] = formataddr((settings.get("fromName") or settings["user"], settings["user"]))
    msg["To"] = to
    msg["Subject"] = subject
    msg["List-Unsubscribe"] = f"<mailto:{settings['user']}?subject=unsubscribe>"
    if is_html(body):
        msg.set_content(body, subtype="html")
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

def today_utc():
    return time.strftime("%Y-%m-%d", time.gmtime())


def run_send_once():
    settings = get_json("settings")
    if not settings or not settings.get("user") or not settings.get("pass"):
        return {"status": "no-settings"}

    queue = get_json("queue", {"items": []})
    if not queue.get("items"):
        return {"status": "empty"}
    if queue.get("paused"):
        return {"status": "paused"}

    lock = get_json("lock")
    if lock and time.time() - lock["t"] < LOCK_MINUTES * 60:
        return {"status": "locked"}
    set_json("lock", {"t": time.time()})

    today = today_utc()
    daily = get_json("daily", {"date": today, "count": 0, "lastSentAt": ""})
    if daily.get("date") != today:
        daily = {"date": today, "count": 0, "lastSentAt": ""}

    if daily["count"] >= DAILY_LIMIT:
        return {"status": "daily-limit", "count": daily["count"]}

    if daily.get("lastSentAt"):
        elapsed = time.time() - daily["lastSentAt"]
        wait_sec = GAP_MINUTES * 60 - elapsed
        if wait_sec > 0:
            return {"status": "gap", "waitMin": int(wait_sec // 60) + 1}

    idx = next((i for i, item in enumerate(queue["items"]) if item["status"] == "pending"), None)
    if idx is None:
        return {"status": "done"}

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
