from __future__ import annotations

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.api.routes_chat import router as chat_router
from backend.app.api.routes_context import router as context_router
from backend.app.api.routes_events import router as events_router
from backend.app.api.routes_settings import router as settings_router
from backend.app.api.routes_tools import router as tools_router
from backend.app.core.config import get_settings
from backend.app.core.logging import configure_logging
from backend.app.core.paths import ensure_data_dirs
from backend.app.db.connection import init_db


def create_app() -> FastAPI:
    configure_logging()
    ensure_data_dirs()
    init_db()

    settings = get_settings()
    app = FastAPI(title="DeskPilot API", version="0.1.0")
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
    app.include_router(context_router)
    app.include_router(events_router)
    app.include_router(settings_router)
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
