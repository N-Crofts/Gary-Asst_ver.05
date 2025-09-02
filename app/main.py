from fastapi import FastAPI
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime

from app.routes.digest import router as digest_router

app = FastAPI(title="Gary-Asst (MVP Skeleton)")

# Scheduler (runs in-process)
scheduler = BackgroundScheduler(timezone="US/Eastern")


def morning_job():
    # TODO: replace with: calendar → enrichment → LLM → render → send
    print(f"[{datetime.now().isoformat()}] Morning job ran")


@app.on_event("startup")
def _startup():
    # 7:30am ET daily
    scheduler.add_job(morning_job, "cron", hour=7, minute=30)
    scheduler.start()


@app.on_event("shutdown")
def _shutdown():
    scheduler.shutdown(wait=False)


# Routes
app.include_router(digest_router, prefix="/digest", tags=["digest"])


@app.get("/")
def health():
    return {"status": "ok"}
