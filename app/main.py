import os
import logging
from fastapi import FastAPI
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime

from app.routes.digest import router as digest_router
from app.routes.preview import router as preview_router

logger = logging.getLogger("gary")
logging.basicConfig(level=logging.INFO)

app = FastAPI(title="Gary-Asst (MVP Loop)")

# Scheduler (runs in-process)
scheduler = BackgroundScheduler(timezone="US/Eastern")
SCHEDULER_JOB_ID = "morning_digest"
RUN_SCHEDULER = os.getenv("RUN_SCHEDULER", "0") == "1"
DIGEST_HOUR = int(os.getenv("DIGEST_HOUR", "7"))
DIGEST_MINUTE = int(os.getenv("DIGEST_MINUTE", "30"))


def morning_job():
    try:
        from app.rendering.context_builder import build_digest_context_with_provider
        from app.rendering.digest_renderer import render_digest_html
        from app.services.emailer import select_emailer_from_env

        context = build_digest_context_with_provider(source="live", date=None, exec_name=None)
        html = render_digest_html({**context, "request": None})

        subject = f"RPCK – Morning Briefing: {context.get('date_human', datetime.now().strftime('%a, %b %d, %Y'))}"
        recipients_env = os.getenv("DEFAULT_RECIPIENTS", "")
        recipients = [r.strip() for r in recipients_env.split(",") if r.strip()]
        sender = os.getenv("DEFAULT_SENDER", "gary@rpck.com")

        emailer = select_emailer_from_env()
        message_id = emailer.send(subject=subject, html=html, recipients=recipients, sender=sender)
        logger.info({
            "action": "sent",
            "driver": getattr(emailer, "driver", "unknown"),
            "source": context.get("source", "unknown"),
            "subject": subject,
            "recipients_count": len(recipients),
            "message_id": message_id,
        })
    except Exception as e:
        logger.exception(f"morning_job failed: {e}")


@app.on_event("startup")
def _startup():
    if RUN_SCHEDULER:
        scheduler.add_job(
            morning_job,
            "cron",
            id=SCHEDULER_JOB_ID,
            hour=DIGEST_HOUR,
            minute=DIGEST_MINUTE,
            replace_existing=True,
        )
        scheduler.start()
        logger.info(f"Scheduler started (RUN_SCHEDULER=1) — {DIGEST_HOUR:02d}:{DIGEST_MINUTE:02d} ET")
    else:
        logger.info("Scheduler disabled (RUN_SCHEDULER=0)")


@app.on_event("shutdown")
def _shutdown():
    try:
        if RUN_SCHEDULER:
            scheduler.shutdown(wait=False)
            logger.info("Scheduler stopped")
    except Exception:
        pass


# Routes
app.include_router(digest_router, prefix="/digest", tags=["digest"])
app.include_router(preview_router, prefix="/digest", tags=["preview"])


@app.get("/")
def health():
    return {"status": "ok"}
