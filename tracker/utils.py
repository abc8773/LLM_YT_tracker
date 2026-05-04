from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any


EMOJI_RE = re.compile(
    "["
    "\U0001F1E6-\U0001F1FF"
    "\U0001F300-\U0001F5FF"
    "\U0001F600-\U0001F64F"
    "\U0001F680-\U0001F6FF"
    "\U0001F700-\U0001F77F"
    "\U0001F780-\U0001F7FF"
    "\U0001F800-\U0001F8FF"
    "\U0001F900-\U0001F9FF"
    "\U0001FA70-\U0001FAFF"
    "\u2600-\u26FF"
    "\u2700-\u27BF"
    "]+",
    flags=re.UNICODE,
)
VARIATION_SELECTOR_RE = re.compile("[\uFE0E\uFE0F]")


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def normalise_datetime(value: Any) -> str | None:
    if value is None or value == "":
        return None

    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, timezone.utc).replace(microsecond=0).isoformat()

    text = str(value).strip()
    if not text:
        return None

    if text.endswith("Z"):
        return text.replace("Z", "+00:00")

    if len(text) == 8 and text.isdigit():
        parsed = datetime.strptime(text, "%Y%m%d")
        return parsed.replace(tzinfo=timezone.utc).isoformat()

    try:
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.replace(microsecond=0).isoformat()
    except ValueError:
        return text


def clean_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def strip_emojis(text: str) -> str:
    cleaned = EMOJI_RE.sub("", text)
    cleaned = VARIATION_SELECTOR_RE.sub("", cleaned)
    cleaned = re.sub(r"\s{2,}", " ", cleaned)
    return cleaned.strip()


def clean_transcript_text(text: str) -> str:
    cleaned = re.sub(r"\[(music|applause|laughter)\]", " ", text, flags=re.IGNORECASE)
    cleaned = re.sub(r"\([^)]*\bsubscribe\b[^)]*\)", " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\buh+\b|\bum+\b", " ", cleaned, flags=re.IGNORECASE)
    return clean_whitespace(cleaned)


def safe_json_loads(value: str | None, default: Any) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default


def to_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True)


def parse_iso8601_duration(duration: str | None) -> int | None:
    if not duration:
        return None

    match = re.fullmatch(
        r"P(?:\d+Y)?(?:\d+M)?(?:\d+D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?",
        duration,
    )
    if not match:
        return None

    hours = int(match.group(1) or 0)
    minutes = int(match.group(2) or 0)
    seconds = int(match.group(3) or 0)
    return hours * 3600 + minutes * 60 + seconds


def build_excerpt(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text

    head = max_chars // 2
    tail = max_chars - head
    return f"{text[:head].rstrip()}\n\n[...]\n\n{text[-tail:].lstrip()}"
