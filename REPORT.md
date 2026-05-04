# LLM YouTube Landscape Tracker Report

## 1. Problem Statement

This exercise asks for a fully automated system that tracks the fast-moving LLM YouTube landscape. The value is twofold: it creates a structured dataset from otherwise noisy video content, and it makes recurring themes across creators, companies, and research channels visible through a public dashboard.

LLM video coverage matters because product launches, benchmark claims, research interpretations, and workflow trends often appear on YouTube before they are captured cleanly in traditional written datasets.

## 2. Methodology

### Architecture

- Ingestion: `YouTube Data API v3` when available, `yt-dlp` fallback otherwise
- Transcript extraction: YouTube captions or auto-generated transcripts first, OpenAI Whisper fallback second
- Analysis: OpenAI `gpt-4o-mini` with a versioned prompt template
- Storage: SQLite for portability and easy review
- API: FastAPI
- Public dashboard: static `docs/` site powered by a JSON snapshot
- Automation: GitHub Actions every 6 hours

### Data pipeline

The pipeline runs in four stages:

1. Ingest channels and recent uploads into SQLite
2. Retrieve or generate transcripts
3. Run LLM analysis for summaries, speakers, topics, keywords, and themes
4. Export the latest dashboard snapshot to `docs/data/latest.json`

### Prompting strategy

Prompt templates are stored in [`prompts/video_analysis.md`](prompts/video_analysis.md). The system records a `prompt_version` in the `analysis` table so outputs remain attributable to the exact prompt contract used during evaluation.

### Automation strategy

GitHub Actions is used as the default scheduler because it is easy to review, cheap to operate for a recruitment exercise, and works well with a GitHub Pages dashboard. The workflow both refreshes data and persists the updated SQLite file back to the repo.

## 3. Evaluation Dataset

Starter channels included in this repo:

- OpenAI
- Anthropic
- Google DeepMind
- DeepLearningAI
- Hugging Face
- Two Minute Papers
- Yannic Kilcher
- Matthew Berman

The exact number of processed videos depends on the latest scheduled run and the `MAX_VIDEOS_PER_CHANNEL` setting in `.env`.

Transcript sources are logged per video as:

- `youtube_caption`
- `youtube_generated`
- `openai_whisper`

## 4. Evaluation Methods

Summary quality can be validated by manually reviewing a sample of generated summaries against the original transcripts and checking whether key claims, model names, and conclusions are preserved.

Topic accuracy can be validated by:

- comparing extracted topics to the transcript and title
- sampling edge cases where multiple themes overlap
- checking whether the theme taxonomy is too broad or too sparse

Pipeline reliability is evaluated by:

- idempotent reruns against the same videos
- status tracking in `videos.transcript_status` and `videos.analysis_status`
- `job_runs` logs for scheduled executions

## 5. Experimental Results

The dashboard exposes:

- channel
- date
- video title
- speakers
- topics
- themes
- summary

Example insights this system is designed to surface:

- official company channels emphasize launches and demos
- research-focused channels emphasize papers, benchmarks, and training details
- creator channels often emphasize tools, workflows, and agent use cases

Once the tracker has run against live data, this section should be expanded with:

- screenshots of the dashboard
- example summaries
- theme frequency observations
- channel-by-channel qualitative differences
