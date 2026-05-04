from __future__ import annotations

import logging
import traceback
from typing import Any

from tracker.analysis import analyse_video
from tracker.catalog import load_channels
from tracker.config import get_settings
from tracker.db import (
    create_job_run,
    fetch_channels,
    fetch_dashboard_rows,
    fetch_pending_analysis_videos,
    fetch_pending_transcript_videos,
    fetch_stats,
    finish_job_run,
    get_connection,
    initialise_database,
    update_video_status,
    upsert_analysis,
    upsert_channel,
    upsert_transcript,
    upsert_video,
)
from tracker.exporter import write_dashboard_snapshot
from tracker.transcripts import fetch_transcript
from tracker.youtube import fetch_channel_and_videos, normalise_videos


def run_ingestion() -> dict[str, Any]:
    initialise_database()
    logger = logging.getLogger(__name__)
    logger.info("Starting ingestion")
    settings = get_settings()
    result = {"channels_processed": 0, "videos_seen": 0, "source_breakdown": {}, "errors": []}

    with get_connection() as connection:
        job_id = create_job_run(connection, "ingestion")
        try:
            for channel_config in load_channels():
                try:
                    logger.info("Processing channel: %s", channel_config.get("name") or channel_config.get("url"))
                    channel_payload, raw_videos, source = fetch_channel_and_videos(
                        channel_config,
                        settings.max_videos_per_channel,
                    )
                    channel_db_id = upsert_channel(connection, channel_payload)
                    videos = normalise_videos(source, channel_db_id, raw_videos)
                    for video in videos:
                        upsert_video(connection, video)
                    result["channels_processed"] += 1
                    result["videos_seen"] += len(videos)
                    result["source_breakdown"][source] = result["source_breakdown"].get(source, 0) + 1
                    logger.info("Channel processed: %s (%d videos)", channel_config.get("name"), len(videos))
                except Exception as exc:
                    logger.exception("Error processing channel: %s", channel_config.get("name"))
                    result["errors"].append(
                        {
                            "channel": channel_config.get("name"),
                            "message": str(exc),
                            "traceback": traceback.format_exc(limit=3),
                        }
                    )
            status = "success" if not result["errors"] else "partial_success"
            logger.info("Ingestion finished: %s", status)
            finish_job_run(connection, job_id, status=status, details=result)
        except Exception:
            finish_job_run(connection, job_id, status="failed", details=result)
            raise
    return result


def run_transcripts(limit: int = 25) -> dict[str, Any]:
    initialise_database()
    logger = logging.getLogger(__name__)
    logger.info("Starting transcript processing (limit=%d)", limit)
    result = {"processed": 0, "completed": 0, "failed": 0, "errors": []}

    with get_connection() as connection:
        job_id = create_job_run(connection, "transcripts")
        try:
            rows = fetch_pending_transcript_videos(connection, limit=limit)
            for row in rows:
                result["processed"] += 1
                logger.info("Fetching transcript for video %s (db id=%s)", row["youtube_video_id"], row["id"])
                try:
                    transcript = fetch_transcript(row["youtube_video_id"], row["url"])
                    transcript["video_id"] = int(row["id"])
                    upsert_transcript(connection, transcript)
                    if transcript.get("source") == "unavailable":
                        update_video_status(connection, int(row["id"]), transcript_status="failed")
                        result["failed"] += 1
                        result["errors"].append(
                            {
                                "video_id": row["youtube_video_id"],
                                "title": row["title"],
                                "message": transcript.get("retrieval_error", "Transcript unavailable."),
                            }
                        )
                        logger.warning(
                            "Transcript unavailable for video %s; saved placeholder and marked failed",
                            row["youtube_video_id"],
                        )
                    else:
                        update_video_status(connection, int(row["id"]), transcript_status="complete")
                        result["completed"] += 1
                        logger.info("Transcript complete for video %s", row["youtube_video_id"])
                except Exception as exc:
                    update_video_status(connection, int(row["id"]), transcript_status="failed")
                    result["failed"] += 1
                    logger.exception("Transcript failed for video %s", row["youtube_video_id"])
                    result["errors"].append(
                        {
                            "video_id": row["youtube_video_id"],
                            "title": row["title"],
                            "message": str(exc),
                        }
                    )
            logger.info("Transcripts finished: processed=%d completed=%d failed=%d", result["processed"], result["completed"], result["failed"])
            finish_job_run(connection, job_id, status="success", details=result)
        except Exception:
            finish_job_run(connection, job_id, status="failed", details=result)
            raise
    return result


def run_analyses(limit: int = 25) -> dict[str, Any]:
    initialise_database()
    logger = logging.getLogger(__name__)
    logger.info("Starting analysis processing (limit=%d)", limit)
    result = {"processed": 0, "completed": 0, "failed": 0, "errors": []}

    with get_connection() as connection:
        job_id = create_job_run(connection, "analysis")
        try:
            rows = fetch_pending_analysis_videos(connection, limit=limit)
            for row in rows:
                result["processed"] += 1
                logger.info("Analysing video %s (db id=%s)", row["youtube_video_id"], row["id"])
                try:
                    analysis = analyse_video(
                        row["title"],
                        row["cleaned_text"] or "",
                        row["channel_name"],
                    )
                    analysis["video_id"] = int(row["id"])
                    upsert_analysis(connection, analysis)
                    update_video_status(connection, int(row["id"]), analysis_status="complete")
                    result["completed"] += 1
                    logger.info("Analysis complete for video %s", row["youtube_video_id"])
                except Exception as exc:
                    update_video_status(connection, int(row["id"]), analysis_status="failed")
                    result["failed"] += 1
                    logger.exception("Analysis failed for video %s", row["youtube_video_id"])
                    result["errors"].append(
                        {
                            "video_id": row["youtube_video_id"],
                            "title": row["title"],
                            "message": str(exc),
                        }
                    )
            logger.info("Analysis finished: processed=%d completed=%d failed=%d", result["processed"], result["completed"], result["failed"])
            finish_job_run(connection, job_id, status="success", details=result)
        except Exception:
            finish_job_run(connection, job_id, status="failed", details=result)
            raise
    return result


def export_dashboard_snapshot() -> str:
    initialise_database()
    settings = get_settings()
    with get_connection() as connection:
        snapshot = {
            "generated_at": None,
            "stats": fetch_stats(connection),
            "channels": fetch_channels(connection),
            "videos": fetch_dashboard_rows(connection),
        }
    write_dashboard_snapshot(snapshot)
    return str(settings.dashboard_export_path)


def run_all() -> dict[str, Any]:
    initialise_database()
    ingestion = run_ingestion()
    transcripts = run_transcripts()
    analysis = run_analyses()
    dashboard_path = export_dashboard_snapshot()
    return {
        "ingestion": ingestion,
        "transcripts": transcripts,
        "analysis": analysis,
        "dashboard_snapshot": dashboard_path,
    }
