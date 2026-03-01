from contextlib import asynccontextmanager

from fastapi import FastAPI
from apscheduler.schedulers.background import BackgroundScheduler

from app.db import Base, engine, SessionLocal
from app.api.routes import router
from app.config import settings
from app.jobs.pipeline import run_pipeline_once


scheduler: BackgroundScheduler | None = None


def _scheduled_pipeline_wrapper():
    db = SessionLocal()
    try:
        result = run_pipeline_once(db)
        print("[scheduler] pipeline run complete:", result)
    except Exception as e:
        print("[scheduler] pipeline run failed:", str(e))
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    global scheduler

    Base.metadata.create_all(bind=engine)

    if settings.enable_scheduler:
        scheduler = BackgroundScheduler()
        scheduler.add_job(
            _scheduled_pipeline_wrapper,
            "interval",
            minutes=settings.scheduler_interval_minutes,
            id="pipeline_run_once",
            replace_existing=True,
        )
        scheduler.start()
        print(f"[startup] Scheduler enabled. Interval: {settings.scheduler_interval_minutes} min")
    else:
        print("[startup] Scheduler disabled (ENABLE_SCHEDULER=false)")

    yield

    if scheduler:
        scheduler.shutdown(wait=False)
        print("[shutdown] Scheduler stopped")


app = FastAPI(
    title="Habeas 1225/1226 Judge Pattern Tracker",
    version="0.2.0",
    lifespan=lifespan,
)

app.include_router(router, prefix="/api")