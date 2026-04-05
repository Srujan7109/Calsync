import asyncio
import logging
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI

from ingestion.app.config import get_settings
from ingestion.app.routers.agent import router as agent_router
from ingestion.app.routers.imap import router as imap_router
from ingestion.app.routers.webhook import router as webhook_router
from ingestion.app.services.imap_poller import run_imap_poller


APP_DESCRIPTION = """
Calsync backend for ingesting scheduling emails and triggering asynchronous meeting coordination.

Core capabilities:
- Receive inbound scheduling emails via webhook
- Poll IMAP inbox every 10 seconds (configurable)
- Deduplicate events using Redis, Supabase, or in-memory backend
- Queue accepted emails for async agent processing
"""

OPENAPI_TAGS = [
    {
        "name": "agent",
        "description": "Internal orchestration endpoints used by async background processing and integrators.",
    },
    {
        "name": "webhook",
        "description": "Inbound email webhook endpoints (SendGrid-style multipart payloads).",
    },
    {
        "name": "imap",
        "description": "Manual IMAP polling endpoints for retrieving and queuing new inbox messages.",
    },
]


logger = logging.getLogger("uvicorn.error")


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings = get_settings()
    poller_task: asyncio.Task[None] | None = None

    logger.info("Lifespan startup: imap_auto_poll_enabled=%s", settings.imap_auto_poll_enabled)

    if settings.imap_auto_poll_enabled:
        poller_task = asyncio.create_task(run_imap_poller())
        logger.info("IMAP auto-poller task created")

    yield

    if poller_task is not None:
        poller_task.cancel()
        with suppress(asyncio.CancelledError):
            await poller_task


def create_app() -> FastAPI:
    settings = get_settings()
    api_prefix = settings.api_v1_prefix.rstrip("/")

    app = FastAPI(
        title="Calsync API",
        version="0.1.0",
        summary="Email coordination backend",
        description=APP_DESCRIPTION,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_tags=OPENAPI_TAGS,
        lifespan=lifespan,
    )
    app.include_router(agent_router, prefix=f"{api_prefix}/agent")
    app.include_router(webhook_router, prefix=f"{api_prefix}/webhook")
    app.include_router(imap_router, prefix=f"{api_prefix}/imap")
    return app


app = create_app()
