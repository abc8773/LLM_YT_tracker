from __future__ import annotations

import json
from typing import Any

from tracker.config import get_settings


def load_channels() -> list[dict[str, Any]]:
    settings = get_settings()
    payload = json.loads(settings.channels_config_path.read_text(encoding="utf-8"))
    return payload.get("channels", [])
