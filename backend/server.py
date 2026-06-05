"""Bud — FastAPI backend entrypoint."""
from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import List

from dotenv import load_dotenv
from fastapi import APIRouter, FastAPI, Request
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, ConfigDict, Field
from starlette.middleware.cors import CORSMiddleware

from agent_mail import router as agent_mail_router
from outlook import router as outlook_router
from bud_assets import router as bud_assets_router
from briefing import router as briefing_router, scheduled_briefing_job
from voice import router as voice_router
from voice_rt import router as voice_rt_router

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from pytz import timezone as tz_timezone

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

mongo_url = os.environ["MONGO_URL"]
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ["DB_NAME"]]

app = FastAPI(title="Bud — Doc's personal AI foreman")
app.state.db = db

api_router = APIRouter(prefix="/api")


class StatusCheck(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    client_name: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class StatusCheckCreate(BaseModel):
    client_name: str


@api_router.get("/")
async def root():
    return {"agent": "bud", "status": "online", "for": "Doc Holmes"}


@api_router.get("/health")
async def health(request: Request):
    """Quick sanity check — mongo + memory dir reachable."""
    try:
        await request.app.state.db.command("ping")
        mongo_ok = True
    except Exception:
        mongo_ok = False
    memory_dir = Path("/app/memory")
    return {
        "mongo": mongo_ok,
        "memory_dir": memory_dir.exists(),
        "memory_files": sorted(p.name for p in memory_dir.glob("*.md")) if memory_dir.exists() else [],
        "time": datetime.now(timezone.utc).isoformat(),
    }


@api_router.post("/status", response_model=StatusCheck)
async def create_status_check(input: StatusCheckCreate):
    status_obj = StatusCheck(**input.model_dump())
    doc = status_obj.model_dump()
    doc["timestamp"] = doc["timestamp"].isoformat()
    await db.status_checks.insert_one(doc)
    return status_obj


@api_router.get("/status", response_model=List[StatusCheck])
async def get_status_checks():
    status_checks = await db.status_checks.find({}, {"_id": 0}).to_list(1000)
    for check in status_checks:
        if isinstance(check["timestamp"], str):
            check["timestamp"] = datetime.fromisoformat(check["timestamp"])
    return status_checks


app.include_router(api_router)
app.include_router(agent_mail_router)
app.include_router(outlook_router)
app.include_router(bud_assets_router)
app.include_router(briefing_router)
app.include_router(voice_router)
app.include_router(voice_rt_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@app.on_event("shutdown")
async def shutdown_db_client():
    sched = getattr(app.state, "scheduler", None)
    if sched and sched.running:
        sched.shutdown(wait=False)
    client.close()


@app.on_event("startup")
async def startup_scheduler():
    """Schedule the daily foreman briefing at the configured hour (CT)."""
    tz_name = os.environ.get("BRIEFING_TIMEZONE", "America/Chicago")
    hour = int(os.environ.get("BRIEFING_HOUR", "7"))
    minute = int(os.environ.get("BRIEFING_MINUTE", "0"))
    scheduler = AsyncIOScheduler(timezone=tz_timezone(tz_name))
    scheduler.add_job(
        scheduled_briefing_job,
        CronTrigger(hour=hour, minute=minute, timezone=tz_timezone(tz_name)),
        kwargs={"db": db},
        id="daily_briefing",
        replace_existing=True,
        misfire_grace_time=600,
    )

    # Nightly brain mirror sync at 3 AM CT
    async def brain_resync(db_ref):
        import os, httpx
        token = os.environ.get("BUD_BRAIN_BEARER")
        base = os.environ.get("BRAIN_BASE")
        if not token or not base:
            return
        shop = "drunderhood-fortsmith"
        h = {"Authorization": f"Bearer {token}"}
        try:
            async with httpx.AsyncClient(timeout=30.0) as c:
                s = await c.get(f"{base}/api/brain/stats?shop_id={shop}", headers=h)
                ro = await c.get(f"{base}/api/brain/recent-outcomes?shop_id={shop}&limit=200", headers=h)
            if ro.status_code == 200:
                events = ro.json().get("events", [])
                if events:
                    await db_ref["brain_mirror_outcomes"].delete_many({})
                    await db_ref["brain_mirror_outcomes"].insert_many(events)
            if s.status_code == 200:
                from datetime import datetime, timezone as _tz
                stats_doc = s.json()
                stats_doc["mirrored_at"] = datetime.now(_tz.utc).isoformat()
                await db_ref["brain_mirror_stats"].update_one(
                    {"shop_id": shop}, {"$set": stats_doc}, upsert=True
                )
            logger.info("brain resync complete")
        except Exception as e:
            logger.exception("brain resync failed: %s", e)

    scheduler.add_job(
        brain_resync,
        CronTrigger(hour=3, minute=0, timezone=tz_timezone(tz_name)),
        kwargs={"db_ref": db},
        id="brain_resync",
        replace_existing=True,
        misfire_grace_time=600,
    )
    scheduler.start()
    app.state.scheduler = scheduler
    logger.info("daily briefing scheduled @ %02d:%02d %s", hour, minute, tz_name)
