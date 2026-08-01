from flask import Blueprint, jsonify, request

from . import core

api = Blueprint("api", __name__, url_prefix="/api")


def out(data, status=200):
    return jsonify(data), status


@api.get("")
def root():
    meta = core.get_json("meta")
    return out({"hasPin": bool(meta and meta.get("hash"))})


@api.post("")
def action():
    body = request.get_json(silent=True) or {}
    action_name = body.get("action")

    try:
        if action_name == "setPin":
            meta = core.get_json("meta")
            if meta and meta.get("hash"):
                return out({"error": "PIN already set - login and use changePin"})
            if not body.get("pin") or len(str(body["pin"])) < 4:
                return out({"error": "PIN must be at least 4 characters"})
            core.set_json("meta", core.create_pin_meta(str(body["pin"])))
            return out({"ok": True})

        if action_name == "login":
            if not core.check_pin(body.get("pin")):
                return out({"error": "Wrong PIN"}, 401)
            return out({"ok": True})

        if action_name == "changePin":
            if not core.check_pin(body.get("pin")):
                return out({"error": "Wrong PIN"}, 401)
            if not body.get("newPin") or len(str(body["newPin"])) < 4:
                return out({"error": "New PIN must be at least 4 characters"})
            core.set_json("meta", core.create_pin_meta(str(body["newPin"])))
            return out({"ok": True})

        if action_name == "setCreds":
            if not core.check_pin(body.get("pin")):
                return out({"error": "Wrong PIN"}, 401)
            user = str(body.get("smtpUser") or "").strip()
            password = str(body.get("smtpPass") or "")
            if not core.set_smtp_creds(user, password):
                return out({"error": "Email and password are both required"})
            return out({"ok": True})

        if action_name == "saveSettings":
            if not core.check_pin(body.get("pin")):
                return out({"error": "Wrong PIN"}, 401)
            port = int(body.get("port") or 465)
            s = {
                "host": str(body.get("host") or "").strip() or "smtp.gmail.com",
                "port": port,
                "secure": bool(body.get("secure", port == 465)),
                "fromName": str(body.get("fromName") or "").strip(),
                "subject": str(body.get("subject") or ""),
                "body": str(body.get("body") or ""),
            }
            user = str(body.get("user") or "").strip()
            password = str(body.get("pass") or "")
            if user and password:
                core.set_smtp_creds(user, password)
            elif not core.get_smtp_creds()["user"] or not core.get_smtp_creds()["pass"]:
                return out({"error": "Email and password are both required"})
            core.set_json("settings", s)
            core.log_event("settings", "SMTP settings saved (credentials stay in your browser)")
            return out({"ok": True, "spam": core.spam_check(s["subject"], s["body"])})

        if action_name == "getSettings":
            if not core.check_pin(body.get("pin")):
                return out({"error": "Wrong PIN"}, 401)
            settings = core.get_json("settings") or {}
            creds = core.get_smtp_creds()
            resp = {
                "settings": settings,
                "user": creds["user"],
                "credsLoaded": bool(creds["user"] and creds["pass"]),
            }
            if settings:
                resp["spam"] = core.spam_check(settings.get("subject"), settings.get("body"))
            return out(resp)

        if action_name == "uploadCsv":
            if not core.check_pin(body.get("pin")):
                return out({"error": "Wrong PIN"}, 401)
            items, error = core.parse_csv(body.get("csv"))
            if error:
                return out({"error": error})
            core.set_json("draft", {"items": items})
            return out({"ok": True, "count": len(items), "preview": items[:5]})

        if action_name == "start":
            if not core.check_pin(body.get("pin")):
                return out({"error": "Wrong PIN"}, 401)
            draft = core.get_json("draft") or {"items": []}
            if not draft.get("items"):
                return out({"error": "Upload a CSV first"})
            settings = core.get_json("settings") or {}
            spam = core.spam_check(settings.get("subject"), settings.get("body"))
            if spam["score"] >= core.SPAM_BLOCK:
                return out({"error": f"Blocked: spam score {spam['score']}. " + "; ".join(spam["issues"])})
            core.set_json("queue", {"items": draft["items"], "paused": False})
            core.set_json("draft", {"items": []})
            core.log_event("campaign", f"Campaign started with {len(draft['items'])} recipients")
            resp = {"ok": True, "count": len(draft["items"])}
            if spam["score"] >= core.SPAM_WARN:
                resp["spamWarning"] = spam
            return out(resp)

        if action_name in ("pause", "resume"):
            if not core.check_pin(body.get("pin")):
                return out({"error": "Wrong PIN"}, 401)
            queue = core.get_json("queue") or {"items": []}
            queue["paused"] = action_name == "pause"
            core.set_json("queue", queue)
            core.log_event("campaign", "Campaign paused" if queue["paused"] else "Campaign resumed")
            return out({"ok": True, "paused": queue["paused"]})

        if action_name == "status":
            if not core.check_pin(body.get("pin")):
                return out({"error": "Wrong PIN"}, 401)
            settings = core.get_json("settings") or {}
            queue = core.get_json("queue") or {"items": []}
            draft = core.get_json("draft") or {"items": []}
            daily = core.get_json("daily") or {"date": core.today_key(), "count": 0, "lastSentAt": ""}
            creds = core.get_smtp_creds()
            return out({
                "settings": {"exists": bool(settings) and bool(creds["user"] and creds["pass"])},
                "credsLoaded": bool(creds["user"] and creds["pass"]),
                "queue": queue,
                "draftCount": len(draft.get("items", [])),
                "daily": daily,
                "logs": core.get_json("logs") or [],
                "limits": {
                    "daily": core.DAILY_LIMIT,
                    "gapMinutes": core.GAP_MINUTES,
                    "domainLimit": core.DOMAIN_DAILY_LIMIT,
                    "windowStart": core.SEND_START_HOUR,
                    "windowEnd": core.SEND_END_HOUR,
                    "tz": core.TIMEZONE,
                },
            })

        if action_name == "testSend":
            if not core.check_pin(body.get("pin")):
                return out({"error": "Wrong PIN"}, 401)
            settings = core.get_json("settings")
            creds = core.get_smtp_creds()
            if not settings or not creds["user"] or not creds["pass"]:
                return out({"error": "Save settings with your email and password first"})
            settings = dict(settings, user=creds["user"], password=creds["pass"])
            try:
                core.send_mail(
                    settings,
                    settings["user"],
                    core.replace_name(settings.get("subject"), "Test"),
                    core.replace_name(settings.get("body"), "Test"),
                )
                core.log_event("test", "Test email sent successfully")
                return out({"ok": True, "message": "Test email sent to your own address"})
            except Exception as err:
                core.log_event("test", f"Test send failed: {err}", False)
                return out({"error": f"Send failed: {err}"})

        return out({"error": "Unknown action"})
    except Exception as err:
        return out({"error": str(err) or "Server error"})
