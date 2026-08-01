import logging

from apscheduler.schedulers.background import BackgroundScheduler

from . import core

log = logging.getLogger("email_automator.scheduler")


def start_scheduler():
    scheduler = BackgroundScheduler(daemon=True)
    scheduler.add_job(
        core.run_send_once,
        "interval",
        minutes=1,
        id="sender",
        replace_existing=True,
        misfire_grace_time=60,
    )
    scheduler.start()
    log.info("Background sender started (checks every minute)")
    return scheduler
