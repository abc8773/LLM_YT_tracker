from __future__ import annotations

import json

from tracker.config import get_settings
from tracker.utils import strip_emojis, utcnow_iso


def _sanitize_snapshot(value):
    if isinstance(value, str):
        return strip_emojis(value)
    if isinstance(value, list):
        return [_sanitize_snapshot(item) for item in value]
    if isinstance(value, dict):
        return {key: _sanitize_snapshot(item) for key, item in value.items()}
    return value


def write_dashboard_snapshot(snapshot: dict) -> None:
    settings = get_settings()
    settings.dashboard_export_path.parent.mkdir(parents=True, exist_ok=True)
    payload = _sanitize_snapshot(dict(snapshot))
    payload["generated_at"] = utcnow_iso()
    settings.dashboard_export_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=True),
        encoding="utf-8",
    )
