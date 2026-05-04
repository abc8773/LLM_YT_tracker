from __future__ import annotations

from pathlib import Path
from typing import Any

from tracker.config import get_settings
from tracker.utils import clean_transcript_text, clean_whitespace


class _YtDlpLogger:
    def debug(self, _message: str) -> None:
        return None

    def warning(self, _message: str) -> None:
        return None

    def error(self, _message: str) -> None:
        return None


def fetch_transcript(video_id: str, video_url: str) -> dict[str, Any]:
    retrieval_errors: list[str] = []

    for fetcher in (_fetch_from_ytdlp_subtitles, _fetch_from_youtube):
        try:
            transcript = fetcher(video_id, video_url)
            if transcript:
                return transcript
        except Exception as exc:
            retrieval_errors.append(_format_error(exc))

    try:
        return _transcribe_with_openai(video_id, video_url)
    except Exception as exc:
        retrieval_errors.append(_format_error(exc))
        return {
            "source": "unavailable",
            "language": None,
            "raw_text": "",
            "cleaned_text": "",
            "generated_with": None,
            "retrieval_error": "Transcript retrieval failed. " + " | ".join(retrieval_errors),
        }


def _format_error(exc: Exception) -> str:
    message = clean_whitespace(str(exc))
    if len(message) > 320:
        message = message[:317].rstrip() + "..."
    return f"{type(exc).__name__}: {message}"


def _build_ytdlp_options() -> dict[str, Any]:
    settings = get_settings()
    options: dict[str, Any] = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "logger": _YtDlpLogger(),
    }
    if settings.ytdlp_cookies_from_browser:
        options["cookiesfrombrowser"] = (settings.ytdlp_cookies_from_browser,)
    if settings.ytdlp_cookie_file:
        options["cookiefile"] = str(settings.ytdlp_cookie_file)
    return options


def _parse_vtt_text(vtt_text: str) -> str:
    lines = []
    for raw_line in vtt_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line == "WEBVTT":
            continue
        if "-->" in line:
            continue
        if line.isdigit():
            continue
        lines.append(line)
    return "\n".join(lines)


def _fetch_from_ytdlp_subtitles(video_id: str, video_url: str) -> dict[str, Any] | None:
    try:
        from yt_dlp import YoutubeDL
    except ImportError as exc:
        raise RuntimeError("yt-dlp is required for subtitle extraction.") from exc

    settings = get_settings()
    subtitles_dir = settings.temp_dir / "subtitles"
    subtitles_dir.mkdir(parents=True, exist_ok=True)
    output_template = str(subtitles_dir / f"{video_id}.%(ext)s")

    options = _build_ytdlp_options()
    options.update(
        {
            "skip_download": True,
            "writesubtitles": True,
            "writeautomaticsub": True,
            "subtitleslangs": settings.transcript_languages,
            "subtitlesformat": "vtt",
            "outtmpl": output_template,
        }
    )

    with YoutubeDL(options) as ydl:
        info = ydl.extract_info(video_url, download=True)

    subtitle_files = sorted(subtitles_dir.glob(f"{video_id}*.vtt"))
    if not subtitle_files:
        return None

    subtitle_path = subtitle_files[0]
    raw_text = _parse_vtt_text(subtitle_path.read_text(encoding="utf-8", errors="ignore"))
    subtitle_path.unlink(missing_ok=True)
    if not raw_text.strip():
        return None

    requested_subtitles = info.get("requested_subtitles") or {}
    language = next(iter(requested_subtitles.keys()), None)
    source = "youtube_caption"
    if info.get("automatic_captions"):
        source = "youtube_generated"

    return {
        "source": source,
        "language": language or (settings.transcript_languages[0] if settings.transcript_languages else "en"),
        "raw_text": raw_text,
        "cleaned_text": clean_transcript_text(raw_text),
        "generated_with": "yt_dlp_subtitles",
    }


def _fetch_from_youtube(video_id: str, _video_url: str) -> dict[str, Any] | None:
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
    except ImportError as exc:
        raise RuntimeError("youtube-transcript-api is required for transcript extraction.") from exc

    settings = get_settings()
    languages = settings.transcript_languages
    api = YouTubeTranscriptApi()
    transcript_chunks: Any = api.fetch(video_id, languages=languages)

    segments: list[str] = []
    language = None
    is_generated = False

    for chunk in transcript_chunks:
        if hasattr(chunk, "text"):
            text = getattr(chunk, "text")
            language = language or getattr(chunk, "language", None)
            is_generated = is_generated or bool(getattr(chunk, "is_generated", False))
        else:
            text = chunk.get("text", "")
            language = language or chunk.get("language")
        if text:
            segments.append(text.strip())

    raw_text = "\n".join(segment for segment in segments if segment)
    if not raw_text.strip():
        return None

    return {
        "source": "youtube_generated" if is_generated else "youtube_caption",
        "language": language or (languages[0] if languages else "en"),
        "raw_text": raw_text,
        "cleaned_text": clean_transcript_text(raw_text),
        "generated_with": None,
    }


def _download_audio(video_id: str, video_url: str, destination_dir: Path) -> Path:
    try:
        from yt_dlp import YoutubeDL
    except ImportError as exc:
        raise RuntimeError("yt-dlp is required to download audio for OpenAI transcription.") from exc

    destination_dir.mkdir(parents=True, exist_ok=True)
    output_template = str(destination_dir / f"{video_id}.%(ext)s")
    options = _build_ytdlp_options()
    options.update(
        {
            "format": "bestaudio/best",
            "outtmpl": output_template,
        }
    )
    with YoutubeDL(options) as ydl:
        info = ydl.extract_info(video_url, download=True)
        downloaded_path = Path(ydl.prepare_filename(info))
    return downloaded_path


def _transcribe_with_openai(video_id: str, video_url: str) -> dict[str, Any]:
    settings = get_settings()
    if not settings.openai_api_key:
        raise RuntimeError(
            "OPENAI_API_KEY is not configured for Whisper fallback transcription."
        )

    try:
        from openai import OpenAI
    except ImportError as exc:
        raise RuntimeError("openai is required for fallback transcription.") from exc

    audio_path = _download_audio(video_id, video_url, settings.temp_dir / "audio")
    client = OpenAI(api_key=settings.openai_api_key)

    try:
        with audio_path.open("rb") as audio_file:
            response = client.audio.transcriptions.create(
                model=settings.whisper_model,
                file=audio_file,
            )
    finally:
        audio_path.unlink(missing_ok=True)

    raw_text = getattr(response, "text", None) or str(response)
    return {
        "source": "openai_whisper",
        "language": "en",
        "raw_text": raw_text,
        "cleaned_text": clean_transcript_text(raw_text),
        "generated_with": settings.whisper_model,
    }
