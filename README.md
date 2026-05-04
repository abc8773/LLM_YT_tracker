# LLM YouTube Landscape Tracker

An end-to-end recruitment-ready system that monitors selected AI/LLM YouTube channels, fetches new videos, retrieves transcripts, summarises content with an LLM, classifies themes, stores everything in SQLite, and publishes a live dashboard.

## What this ships

- Modular ingestion pipeline with `YouTube Data API v3` as the primary path when `channel_id` values are supplied, and `yt-dlp` as the metadata fallback.
- Transcript pipeline that first tries YouTube captions or auto-generated transcripts, then falls back to OpenAI Whisper when captions are missing.
- Analysis pipeline that produces summaries, speakers, topics, keywords, and LLM themes using OpenAI, Gemini, or a heuristic fallback.
- SQLite schema covering `channels`, `videos`, `transcripts`, `analysis`, and `job_runs`.
- FastAPI backend for local/API-first usage.
- Static public dashboard in [`docs/`](docs/index.html) for GitHub Pages.
- Scheduled GitHub Actions workflow for continuous refresh.
- Markdown report in [`REPORT.md`](REPORT.md).

## Recommended stack in this repo

- Backend: FastAPI
- Storage: SQLite
- Scheduling: GitHub Actions every 6 hours
- Public dashboard: GitHub Pages served from `docs/`
- Transcript fallback: OpenAI Whisper
- Analysis model: OpenAI `gpt-4o-mini` or Gemini `gemini-2.5-flash`

## Project layout

```text
.
|-- config/
|   `-- channels.json
|-- data/
|-- docs/
|   |-- app.js
|   |-- data/latest.json
|   |-- index.html
|   `-- styles.css
|-- prompts/
|   `-- video_analysis.md
|-- tracker/
|   |-- analysis.py
|   |-- api.py
|   |-- catalog.py
|   |-- config.py
|   |-- db.py
|   |-- exporter.py
|   |-- pipeline.py
|   |-- schema.sql
|   |-- transcripts.py
|   `-- youtube.py
`-- main.py
```

## Quick start

1. Create and activate a virtual environment.
2. Install dependencies with `pip install -r requirements.txt`.
3. Copy `.env.example` to `.env` and set either `OPENAI_API_KEY` or `GEMINI_API_KEY` for analysis. Add `YOUTUBE_API_KEY` if you want the API-first ingestion path.
   If YouTube starts blocking per-video transcript or audio requests, also set either `YTDLP_COOKIES_FROM_BROWSER=chrome` or `YTDLP_COOKIE_FILE=path/to/cookies.txt`.
4. Edit [`config/channels.json`](config/channels.json) to track your preferred channels.
5. Run the full pipeline once:

```powershell
C:/Users/carrk/AppData/Local/Programs/Python/Python313/python.exe main.py run
```

6. Start the local API and dashboard:

```powershell
C:/Users/carrk/AppData/Local/Programs/Python/Python313/python.exe main.py serve-api --reload
```

Then open `http://127.0.0.1:8000/dashboard`.

## CLI commands

- `python main.py init-db`
- `python main.py ingest`
- `python main.py transcript`
- `python main.py analyse`
- `python main.py export-dashboard`
- `python main.py run`
- `python main.py serve-api`

## Data model

- `channels`: tracked channels and metadata
- `videos`: per-video metadata and processing status
- `transcripts`: raw and cleaned transcript text
- `analysis`: summary, speakers, topics, keywords, themes, model metadata
- `job_runs`: audit trail for scheduled runs

## Automation strategy

The included GitHub Actions workflow runs the full pipeline every 6 hours, then commits the updated SQLite database and static snapshot back into the repository. That makes GitHub Pages automatically reflect the latest state without a separate frontend deployment step.

For a production deployment, move the database to a persistent service such as PostgreSQL or a mounted volume on Railway/Render/Fly.io. The current SQLite-in-repo strategy is deliberate because it keeps the exercise simple and reproducible.

## Notes on API-first ingestion

This repo supports both:

- API-first channel polling when `YOUTUBE_API_KEY` is configured and your channel entries include `channel_id`
- `yt-dlp` fallback using channel `/videos` URLs

The starter [`config/channels.json`](config/channels.json) uses channel URLs so the project can work even before you fill in channel IDs.

## Notes on transcript reliability

Recent YouTube anti-bot checks can block transcript and per-video subtitle extraction from some environments. This repo now supports optional `yt-dlp` cookie configuration through:

- `YTDLP_COOKIES_FROM_BROWSER`
- `YTDLP_COOKIE_FILE`

If those are not configured and YouTube blocks transcript access, the pipeline will fall back to OpenAI Whisper only when `OPENAI_API_KEY` is present. A `GEMINI_API_KEY` helps with analysis after transcripts exist, but it does not replace the Whisper fallback in the current implementation.
