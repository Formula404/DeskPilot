from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from backend.app.api.routes_browser import router as browser_router
from backend.app.api.routes_artifacts import router as artifacts_router
from backend.app.api.routes_chat import router as chat_router
from backend.app.api.routes_context import router as context_router
from backend.app.api.routes_events import router as events_router
from backend.app.api.routes_knowledge import router as knowledge_router
from backend.app.api.routes_settings import router as settings_router
from backend.app.api.routes_sessions import router as sessions_router
from backend.app.api.routes_memory import router as memory_router
from backend.app.api.routes_personal_info import router as personal_info_router
from backend.app.api.routes_tools import router as tools_router
from backend.app.agent.graph import run_agent
from backend.app.api.events import event_bus
from backend.app.core.config import get_settings
from backend.app.core.logging import configure_logging
from backend.app.core.paths import ensure_data_dirs
from backend.app.core.task_lifecycle import cancel_background_tasks
from backend.app.db.connection import init_db
from backend.app.db.repository import cleanup_expired_context, list_recoverable_tasks
from backend.app.knowledge.paths import ensure_knowledge_dirs
from backend.app.knowledge.web_monitor import scheduler_loop
from backend.app.knowledge.jobs import knowledge_job_manager


def create_app() -> FastAPI:
    configure_logging()
    ensure_data_dirs()
    init_db()
    ensure_knowledge_dirs()

    settings = get_settings()
    scheduler_stop = asyncio.Event()

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        scheduler_stop.clear()
        scheduler_task = asyncio.create_task(scheduler_loop(scheduler_stop))
        knowledge_job_manager.recover()
        cleanup_expired_context()
        recovered_tasks = [
            asyncio.create_task(
                run_agent(
                    task["id"],
                    task["user_message"],
                    task.get("context_snapshot_id"),
                    event_bus,
                )
            )
            for task in list_recoverable_tasks()
        ]
        try:
            yield
        finally:
            scheduler_stop.set()
            await cancel_background_tasks(recovered_tasks)
            await knowledge_job_manager.shutdown()
            await asyncio.gather(scheduler_task, return_exceptions=True)

    app = FastAPI(title="DeskPilot API", version="0.1.0", lifespan=lifespan)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "testserver"])
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(chat_router)
    app.include_router(artifacts_router)
    app.include_router(browser_router)
    app.include_router(context_router)
    app.include_router(events_router)
    app.include_router(knowledge_router)
    app.include_router(settings_router)
    app.include_router(sessions_router)
    app.include_router(memory_router)
    app.include_router(personal_info_router)
    app.include_router(tools_router)
    return app


app = create_app()


def run() -> None:
    settings = get_settings()
    uvicorn.run(
        "backend.app.main:app",
        host=settings.host,
        port=settings.port,
        reload=False,
    )


if __name__ == "__main__":
    run()
