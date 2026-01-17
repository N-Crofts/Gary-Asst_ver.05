import os
import logging
from fastapi import FastAPI
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

from app.routes.digest import router as digest_router
from app.routes.preview import router as preview_router
from app.routes.scheduler import router as scheduler_router
from app.routes.health import router as health_router
from app.routes.actions import router as actions_router
from app.routes.search import router as search_router
from app.routes.debug import router as debug_router
from app.scheduler.service import start_scheduler, stop_scheduler

logger = logging.getLogger("gary")
logging.basicConfig(level=logging.INFO)

app = FastAPI(title="Gary-Asst (MVP Loop)")

@app.on_event("startup")
async def _startup():
    await start_scheduler()


@app.on_event("shutdown")
async def _shutdown():
    await stop_scheduler()


# Routes
app.include_router(digest_router, prefix="/digest", tags=["digest"])
app.include_router(preview_router, prefix="/digest", tags=["preview"])
app.include_router(search_router, prefix="/digest", tags=["search"])
app.include_router(debug_router, tags=["debug"])
app.include_router(scheduler_router, tags=["scheduler"])
app.include_router(health_router, tags=["health"])
app.include_router(actions_router, prefix="/actions", tags=["actions"])


@app.get("/")
def health():
    return {"status": "ok"}
