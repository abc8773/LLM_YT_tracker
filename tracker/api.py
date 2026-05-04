from __future__ import annotations

from typing import Any

from tracker.db import (
    fetch_channels,
    fetch_dashboard_rows,
    fetch_stats,
    get_connection,
    initialise_database,
)
from tracker.pipeline import export_dashboard_snapshot, run_all


def _filter_rows(
    rows: list[dict[str, Any]],
    *,
    channel: str | None,
    topic: str | None,
    theme: str | None,
) -> list[dict[str, Any]]:
    filtered = rows
    if channel:
        filtered = [row for row in filtered if row["channel"].lower() == channel.lower()]
    if topic:
        filtered = [row for row in filtered if topic.lower() in {item.lower() for item in row["topics"]}]
    if theme:
        filtered = [row for row in filtered if theme.lower() in {item.lower() for item in row["themes"]}]
    return filtered


def create_app():
    try:
        from fastapi import BackgroundTasks, FastAPI
        from fastapi.middleware.cors import CORSMiddleware
        from fastapi.staticfiles import StaticFiles
    except ImportError as exc:
        raise RuntimeError("fastapi and uvicorn are required to serve the API.") from exc

    from tracker.config import get_settings

    settings = get_settings()
    initialise_database()
    app = FastAPI(title="LLM YouTube Tracker", version="1.0.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/channels")
    def channels() -> list[dict[str, Any]]:
        with get_connection() as connection:
            return fetch_channels(connection)

    @app.get("/stats")
    def stats() -> dict[str, Any]:
        with get_connection() as connection:
            return fetch_stats(connection)

    @app.get("/videos")
    def videos(
        limit: int = 250,
        channel: str | None = None,
        topic: str | None = None,
        theme: str | None = None,
    ) -> list[dict[str, Any]]:
        with get_connection() as connection:
            rows = fetch_dashboard_rows(connection, limit=limit)
        return _filter_rows(rows, channel=channel, topic=topic, theme=theme)

    @app.get("/dashboard-data")
    def dashboard_data(limit: int = 250) -> dict[str, Any]:
        with get_connection() as connection:
            return {
                "stats": fetch_stats(connection),
                "channels": fetch_channels(connection),
                "videos": fetch_dashboard_rows(connection, limit=limit),
            }

    @app.post("/refresh")
    def refresh(background_tasks: BackgroundTasks) -> dict[str, str]:
        def _refresh() -> None:
            run_all()
            export_dashboard_snapshot()

        background_tasks.add_task(_refresh)
        return {"status": "queued"}

    if settings.docs_dir.exists():
        app.mount("/dashboard", StaticFiles(directory=str(settings.docs_dir), html=True), name="dashboard")

    return app


app = create_app()
