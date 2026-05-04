from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent.parent


def _load_env_file(env_path: Path) -> None:
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


@dataclass(slots=True)
class Settings:
    root_dir: Path
    data_dir: Path
    temp_dir: Path
    docs_dir: Path
    prompts_dir: Path
    channels_config_path: Path
    database_path: Path
    dashboard_export_path: Path
    youtube_api_key: str | None
    openai_api_key: str | None
    gemini_api_key: str | None
    analysis_provider: str
    openai_model: str
    gemini_model: str
    whisper_model: str
    api_host: str
    api_port: int
    poll_hours: int
    max_videos_per_channel: int
    transcript_languages: list[str]
    analysis_max_chars: int
    ytdlp_cookies_from_browser: str | None
    ytdlp_cookie_file: Path | None

    def ensure_directories(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        self.docs_dir.mkdir(parents=True, exist_ok=True)
        self.dashboard_export_path.parent.mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    _load_env_file(ROOT_DIR / ".env")

    transcript_languages = [
        item.strip()
        for item in os.getenv("TRANSCRIPT_LANGUAGES", "en,en-US").split(",")
        if item.strip()
    ]

    settings = Settings(
        root_dir=ROOT_DIR,
        data_dir=ROOT_DIR / "data",
        temp_dir=ROOT_DIR / "data" / "tmp",
        docs_dir=ROOT_DIR / "docs",
        prompts_dir=ROOT_DIR / "prompts",
        channels_config_path=ROOT_DIR / "config" / "channels.json",
        database_path=ROOT_DIR / os.getenv("DATABASE_PATH", "data/tracker.db"),
        dashboard_export_path=ROOT_DIR / os.getenv(
            "DASHBOARD_EXPORT_PATH",
            "docs/data/latest.json",
        ),
        youtube_api_key=os.getenv("YOUTUBE_API_KEY"),
        openai_api_key=os.getenv("OPENAI_API_KEY"),
        gemini_api_key=os.getenv("GEMINI_API_KEY"),
        analysis_provider=os.getenv("ANALYSIS_PROVIDER", "auto"),
        openai_model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        gemini_model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
        whisper_model=os.getenv("WHISPER_MODEL", "whisper-1"),
        api_host=os.getenv("API_HOST", "127.0.0.1"),
        api_port=int(os.getenv("API_PORT", "8000")),
        poll_hours=int(os.getenv("POLL_HOURS", "6")),
        max_videos_per_channel=int(os.getenv("MAX_VIDEOS_PER_CHANNEL", "8")),
        transcript_languages=transcript_languages or ["en"],
        analysis_max_chars=int(os.getenv("ANALYSIS_MAX_CHARS", "12000")),
        ytdlp_cookies_from_browser=os.getenv("YTDLP_COOKIES_FROM_BROWSER"),
        ytdlp_cookie_file=(
            ROOT_DIR / os.getenv("YTDLP_COOKIE_FILE")
            if os.getenv("YTDLP_COOKIE_FILE")
            else None
        ),
    )
    settings.ensure_directories()
    return settings
