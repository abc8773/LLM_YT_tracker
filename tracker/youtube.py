from __future__ import annotations

import json
from typing import Any
from urllib.parse import urlencode
from urllib.request import urlopen

from tracker.config import get_settings
from tracker.utils import normalise_datetime, parse_iso8601_duration, utcnow_iso


class _YtDlpLogger:
    def debug(self, _message: str) -> None:
        return None

    def warning(self, _message: str) -> None:
        return None

    def error(self, _message: str) -> None:
        return None


def _read_json(url: str) -> dict[str, Any]:
    with urlopen(url) as response:
        return json.loads(response.read().decode("utf-8"))


def _api_fetch_channel_bundle(channel_id: str, limit: int) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    settings = get_settings()
    if not settings.youtube_api_key:
        raise RuntimeError("Missing YOUTUBE_API_KEY.")

    base = "https://www.googleapis.com/youtube/v3"
    channel_params = urlencode(
        {
            "part": "snippet,contentDetails",
            "id": channel_id,
            "key": settings.youtube_api_key,
        }
    )
    channel_payload = _read_json(f"{base}/channels?{channel_params}")
    items = channel_payload.get("items", [])
    if not items:
        raise RuntimeError(f"Channel {channel_id} was not found.")

    channel_item = items[0]
    uploads_playlist_id = channel_item["contentDetails"]["relatedPlaylists"]["uploads"]

    playlist_params = urlencode(
        {
            "part": "snippet,contentDetails",
            "playlistId": uploads_playlist_id,
            "maxResults": limit,
            "key": settings.youtube_api_key,
        }
    )
    playlist_payload = _read_json(f"{base}/playlistItems?{playlist_params}")
    video_ids = [
        entry["contentDetails"]["videoId"]
        for entry in playlist_payload.get("items", [])
        if entry.get("contentDetails", {}).get("videoId")
    ]
    if not video_ids:
        return channel_item, []

    videos_params = urlencode(
        {
            "part": "snippet,contentDetails",
            "id": ",".join(video_ids),
            "key": settings.youtube_api_key,
        }
    )
    videos_payload = _read_json(f"{base}/videos?{videos_params}")
    return channel_item, videos_payload.get("items", [])


def _fetch_bundle_via_ytdlp(channel_url: str, limit: int) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    try:
        from yt_dlp import YoutubeDL
    except ImportError as exc:
        raise RuntimeError("yt-dlp is required for fallback ingestion.") from exc

    settings = get_settings()
    options = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "extract_flat": True,
        "logger": _YtDlpLogger(),
        "playlistend": limit,
    }
    if settings.ytdlp_cookies_from_browser:
        options["cookiesfrombrowser"] = (settings.ytdlp_cookies_from_browser,)
    if settings.ytdlp_cookie_file:
        options["cookiefile"] = str(settings.ytdlp_cookie_file)
    with YoutubeDL(options) as ydl:
        payload = ydl.extract_info(channel_url, download=False)

    entries = payload.get("entries", []) or []
    videos = [entry for entry in entries if entry]
    return payload, videos[:limit]


def _normalise_channel_from_api(channel_config: dict[str, Any], channel_item: dict[str, Any]) -> dict[str, Any]:
    snippet = channel_item.get("snippet", {})
    custom_url = snippet.get("customUrl", "")
    handle = custom_url.lstrip("@") if custom_url.startswith("@") else channel_config.get("handle")
    return {
        "source_channel_id": channel_item.get("id"),
        "name": snippet.get("title") or channel_config["name"],
        "handle": handle,
        "url": channel_config["url"],
        "description": snippet.get("description") or channel_config.get("description"),
        "last_checked_at": utcnow_iso(),
    }


def _normalise_video_from_api(channel_id: int, video_item: dict[str, Any]) -> dict[str, Any]:
    snippet = video_item.get("snippet", {})
    thumbnails = snippet.get("thumbnails", {})
    thumbnail_url = (
        thumbnails.get("high", {}).get("url")
        or thumbnails.get("medium", {}).get("url")
        or thumbnails.get("default", {}).get("url")
    )
    return {
        "channel_id": channel_id,
        "youtube_video_id": video_item["id"],
        "title": snippet.get("title") or "Untitled video",
        "description": snippet.get("description"),
        "published_at": normalise_datetime(snippet.get("publishedAt")),
        "url": f"https://www.youtube.com/watch?v={video_item['id']}",
        "duration_seconds": parse_iso8601_duration(video_item.get("contentDetails", {}).get("duration")),
        "thumbnail_url": thumbnail_url,
        "metadata": video_item,
    }


def _normalise_channel_from_ytdlp(channel_config: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "source_channel_id": payload.get("channel_id"),
        "name": payload.get("channel") or payload.get("uploader") or channel_config["name"],
        "handle": payload.get("uploader_id") or channel_config.get("handle"),
        "url": channel_config["url"],
        "description": payload.get("description") or channel_config.get("description"),
        "last_checked_at": utcnow_iso(),
    }


def _normalise_video_from_ytdlp(channel_id: int, entry: dict[str, Any]) -> dict[str, Any]:
    video_id = entry.get("id")
    if not video_id:
        raise RuntimeError("Encountered a video entry without an id.")

    url = entry.get("url")
    if not url or not str(url).startswith("http"):
        url = f"https://www.youtube.com/watch?v={video_id}"

    return {
        "channel_id": channel_id,
        "youtube_video_id": video_id,
        "title": entry.get("title") or "Untitled video",
        "description": entry.get("description"),
        "published_at": normalise_datetime(entry.get("timestamp") or entry.get("upload_date")),
        "url": url,
        "duration_seconds": entry.get("duration"),
        "thumbnail_url": entry.get("thumbnail"),
        "metadata": entry,
    }


def fetch_channel_and_videos(channel_config: dict[str, Any], limit: int) -> tuple[dict[str, Any], list[dict[str, Any]], str]:
    settings = get_settings()
    channel_id = channel_config.get("channel_id")

    if settings.youtube_api_key and channel_id:
        channel_item, videos = _api_fetch_channel_bundle(channel_id, limit)
        channel_payload = _normalise_channel_from_api(channel_config, channel_item)
        return channel_payload, videos, "youtube_api"

    channel_payload, videos = _fetch_bundle_via_ytdlp(channel_config["url"], limit)
    normalised_channel = _normalise_channel_from_ytdlp(channel_config, channel_payload)
    return normalised_channel, videos, "yt_dlp"


def normalise_videos(source: str, channel_id: int, raw_videos: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if source == "youtube_api":
        return [_normalise_video_from_api(channel_id, item) for item in raw_videos]
    return [_normalise_video_from_ytdlp(channel_id, item) for item in raw_videos]
