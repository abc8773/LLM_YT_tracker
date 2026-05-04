from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from tracker.config import get_settings
from tracker.utils import safe_json_loads, to_json, utcnow_iso


def _schema_sql() -> str:
    schema_path = Path(__file__).with_name("schema.sql")
    return schema_path.read_text(encoding="utf-8")


@contextmanager
def get_connection() -> Iterator[sqlite3.Connection]:
    settings = get_settings()
    settings.ensure_directories()
    connection = sqlite3.connect(settings.database_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        yield connection
        connection.commit()
    finally:
        connection.close()


def initialise_database() -> None:
    with get_connection() as connection:
        connection.executescript(_schema_sql())


def _find_channel_id(connection: sqlite3.Connection, source_channel_id: str | None, url: str) -> int | None:
    if source_channel_id:
        row = connection.execute(
            "SELECT id FROM channels WHERE source_channel_id = ?",
            (source_channel_id,),
        ).fetchone()
        if row:
            return int(row["id"])
    row = connection.execute(
        "SELECT id FROM channels WHERE url = ?",
        (url,),
    ).fetchone()
    return int(row["id"]) if row else None


def upsert_channel(connection: sqlite3.Connection, payload: dict[str, Any]) -> int:
    now = utcnow_iso()
    channel_id = _find_channel_id(
        connection,
        payload.get("source_channel_id"),
        payload["url"],
    )
    values = (
        payload.get("source_channel_id"),
        payload["name"],
        payload.get("handle"),
        payload["url"],
        payload.get("description"),
        payload.get("last_checked_at", now),
        now,
        now,
    )
    if channel_id is None:
        cursor = connection.execute(
            """
            INSERT INTO channels (
                source_channel_id, name, handle, url, description,
                last_checked_at, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            values,
        )
        return int(cursor.lastrowid)

    connection.execute(
        """
        UPDATE channels
        SET source_channel_id = ?, name = ?, handle = ?, url = ?, description = ?,
            last_checked_at = ?, updated_at = ?
        WHERE id = ?
        """,
        (
            payload.get("source_channel_id"),
            payload["name"],
            payload.get("handle"),
            payload["url"],
            payload.get("description"),
            payload.get("last_checked_at", now),
            now,
            channel_id,
        ),
    )
    return channel_id


def upsert_video(connection: sqlite3.Connection, payload: dict[str, Any]) -> int:
    now = utcnow_iso()
    row = connection.execute(
        "SELECT id, transcript_status, analysis_status FROM videos WHERE youtube_video_id = ?",
        (payload["youtube_video_id"],),
    ).fetchone()

    metadata_json = to_json(payload.get("metadata", {}))

    if row is None:
        cursor = connection.execute(
            """
            INSERT INTO videos (
                youtube_video_id, channel_id, title, description, published_at, url,
                duration_seconds, thumbnail_url, transcript_status, analysis_status,
                metadata_json, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload["youtube_video_id"],
                payload["channel_id"],
                payload["title"],
                payload.get("description"),
                payload.get("published_at"),
                payload["url"],
                payload.get("duration_seconds"),
                payload.get("thumbnail_url"),
                payload.get("transcript_status", "pending"),
                payload.get("analysis_status", "pending"),
                metadata_json,
                now,
                now,
            ),
        )
        return int(cursor.lastrowid)

    connection.execute(
        """
        UPDATE videos
        SET channel_id = ?, title = ?, description = ?, published_at = ?, url = ?,
            duration_seconds = ?, thumbnail_url = ?, metadata_json = ?, updated_at = ?
        WHERE id = ?
        """,
        (
            payload["channel_id"],
            payload["title"],
            payload.get("description"),
            payload.get("published_at"),
            payload["url"],
            payload.get("duration_seconds"),
            payload.get("thumbnail_url"),
            metadata_json,
            now,
            int(row["id"]),
        ),
    )
    return int(row["id"])


def update_video_status(
    connection: sqlite3.Connection,
    video_id: int,
    *,
    transcript_status: str | None = None,
    analysis_status: str | None = None,
) -> None:
    assignments = []
    params: list[Any] = []
    if transcript_status is not None:
        assignments.append("transcript_status = ?")
        params.append(transcript_status)
    if analysis_status is not None:
        assignments.append("analysis_status = ?")
        params.append(analysis_status)
    assignments.append("updated_at = ?")
    params.append(utcnow_iso())
    params.append(video_id)
    connection.execute(
        f"UPDATE videos SET {', '.join(assignments)} WHERE id = ?",
        tuple(params),
    )


def upsert_transcript(connection: sqlite3.Connection, payload: dict[str, Any]) -> None:
    now = utcnow_iso()
    row = connection.execute(
        "SELECT id FROM transcripts WHERE video_id = ?",
        (payload["video_id"],),
    ).fetchone()
    params = (
        payload["source"],
        payload.get("language"),
        payload["raw_text"],
        payload["cleaned_text"],
        payload.get("generated_with"),
    )
    if row is None:
        connection.execute(
            """
            INSERT INTO transcripts (
                video_id, source, language, raw_text, cleaned_text,
                generated_with, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (payload["video_id"], *params, now, now),
        )
    else:
        connection.execute(
            """
            UPDATE transcripts
            SET source = ?, language = ?, raw_text = ?, cleaned_text = ?,
                generated_with = ?, updated_at = ?
            WHERE video_id = ?
            """,
            (*params, now, payload["video_id"]),
        )


def upsert_analysis(connection: sqlite3.Connection, payload: dict[str, Any]) -> None:
    now = utcnow_iso()
    row = connection.execute(
        "SELECT id FROM analysis WHERE video_id = ?",
        (payload["video_id"],),
    ).fetchone()
    params = (
        payload["model"],
        payload["prompt_version"],
        payload["summary"],
        to_json(payload["speakers"]),
        to_json(payload["topics"]),
        to_json(payload["keywords"]),
        to_json(payload["themes"]),
        payload.get("confidence"),
        payload.get("raw_response"),
    )
    if row is None:
        connection.execute(
            """
            INSERT INTO analysis (
                video_id, model, prompt_version, summary, speakers_json,
                topics_json, keywords_json, themes_json, confidence,
                raw_response, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (payload["video_id"], *params, now, now),
        )
    else:
        connection.execute(
            """
            UPDATE analysis
            SET model = ?, prompt_version = ?, summary = ?, speakers_json = ?,
                topics_json = ?, keywords_json = ?, themes_json = ?, confidence = ?,
                raw_response = ?, updated_at = ?
            WHERE video_id = ?
            """,
            (*params, now, payload["video_id"]),
        )


def create_job_run(connection: sqlite3.Connection, job_name: str, details: dict[str, Any] | None = None) -> int:
    cursor = connection.execute(
        """
        INSERT INTO job_runs (job_name, status, started_at, details_json)
        VALUES (?, ?, ?, ?)
        """,
        (job_name, "running", utcnow_iso(), json.dumps(details or {}, ensure_ascii=True)),
    )
    return int(cursor.lastrowid)


def finish_job_run(
    connection: sqlite3.Connection,
    job_run_id: int,
    *,
    status: str,
    details: dict[str, Any] | None = None,
) -> None:
    connection.execute(
        """
        UPDATE job_runs
        SET status = ?, finished_at = ?, details_json = ?
        WHERE id = ?
        """,
        (
            status,
            utcnow_iso(),
            json.dumps(details or {}, ensure_ascii=True),
            job_run_id,
        ),
    )


def fetch_pending_transcript_videos(connection: sqlite3.Connection, limit: int = 25) -> list[sqlite3.Row]:
    rows = connection.execute(
        """
        SELECT v.*, c.name AS channel_name
        FROM videos v
        JOIN channels c ON c.id = v.channel_id
        LEFT JOIN transcripts t ON t.video_id = v.id
        WHERE t.id IS NULL OR v.transcript_status IN ('pending', 'failed')
        ORDER BY v.published_at DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return list(rows)


def fetch_pending_analysis_videos(connection: sqlite3.Connection, limit: int = 25) -> list[sqlite3.Row]:
    rows = connection.execute(
        """
        SELECT v.*, c.name AS channel_name, t.cleaned_text, t.source AS transcript_source
        FROM videos v
        JOIN channels c ON c.id = v.channel_id
        JOIN transcripts t ON t.video_id = v.id
        LEFT JOIN analysis a ON a.video_id = v.id
        WHERE a.id IS NULL OR v.analysis_status IN ('pending', 'failed')
        ORDER BY v.published_at DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return list(rows)


def fetch_dashboard_rows(connection: sqlite3.Connection, limit: int = 250) -> list[dict[str, Any]]:
    rows = connection.execute(
        """
        SELECT
            v.id,
            v.youtube_video_id,
            v.title,
            v.description,
            v.published_at,
            v.url,
            v.thumbnail_url,
            v.duration_seconds,
            v.transcript_status,
            v.analysis_status,
            c.name AS channel_name,
            c.handle AS channel_handle,
            t.source AS transcript_source,
            t.language AS transcript_language,
            a.summary,
            a.model AS analysis_model,
            a.prompt_version,
            a.speakers_json,
            a.topics_json,
            a.keywords_json,
            a.themes_json,
            a.confidence
        FROM videos v
        JOIN channels c ON c.id = v.channel_id
        LEFT JOIN transcripts t ON t.video_id = v.id
        LEFT JOIN analysis a ON a.video_id = v.id
        ORDER BY v.published_at DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()

    result: list[dict[str, Any]] = []
    for row in rows:
        result.append(
            {
                "id": int(row["id"]),
                "youtube_video_id": row["youtube_video_id"],
                "title": row["title"],
                "description": row["description"],
                "published_at": row["published_at"],
                "url": row["url"],
                "thumbnail_url": row["thumbnail_url"],
                "duration_seconds": row["duration_seconds"],
                "transcript_status": row["transcript_status"],
                "analysis_status": row["analysis_status"],
                "channel": row["channel_name"],
                "channel_handle": row["channel_handle"],
                "transcript_source": row["transcript_source"],
                "transcript_language": row["transcript_language"],
                "summary": row["summary"],
                "analysis_model": row["analysis_model"],
                "prompt_version": row["prompt_version"],
                "speakers": safe_json_loads(row["speakers_json"], []),
                "topics": safe_json_loads(row["topics_json"], []),
                "keywords": safe_json_loads(row["keywords_json"], []),
                "themes": safe_json_loads(row["themes_json"], []),
                "confidence": row["confidence"],
            }
        )
    return result


def fetch_channels(connection: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = connection.execute(
        """
        SELECT id, source_channel_id, name, handle, url, description, last_checked_at
        FROM channels
        ORDER BY name
        """
    ).fetchall()
    return [dict(row) for row in rows]


def fetch_stats(connection: sqlite3.Connection) -> dict[str, Any]:
    row = connection.execute(
        """
        SELECT
            (SELECT COUNT(*) FROM channels) AS channels,
            (SELECT COUNT(*) FROM videos) AS videos,
            (SELECT COUNT(*) FROM transcripts) AS transcripts,
            (SELECT COUNT(*) FROM analysis) AS analysis,
            (SELECT MAX(updated_at) FROM videos) AS last_video_update
        """
    ).fetchone()
    return dict(row)
