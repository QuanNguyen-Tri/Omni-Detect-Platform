from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI

from omni_detect.api.errors import install_error_handlers
from omni_detect.api.routes import router
from omni_detect.config import Settings
from omni_detect.jobs import JobStore
from omni_detect.runpod import RunPodClient, build_runpod_client
from omni_detect.scheduler import DetectionScheduler


def create_app(
    *,
    settings: Optional[Settings] = None,
    runpod_client: Optional[RunPodClient] = None,
) -> FastAPI:
    resolved_settings = settings or Settings.from_env()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        jobs = JobStore()
        runpod = runpod_client or build_runpod_client(resolved_settings)
        scheduler = DetectionScheduler(
            settings=resolved_settings,
            jobs=jobs,
            runpod=runpod,
        )
        app.state.settings = resolved_settings
        app.state.jobs = jobs
        app.state.runpod = runpod
        app.state.scheduler = scheduler
        await scheduler.start()
        try:
            yield
        finally:
            await scheduler.stop()

    app = FastAPI(
        title="Omni-Detect API",
        version="0.1.0",
        lifespan=lifespan,
    )
    install_error_handlers(app)
    app.include_router(router)
    return app


app = create_app()

