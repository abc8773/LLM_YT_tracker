from __future__ import annotations

import json
import re
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from collections import Counter
from typing import Any

from tracker.config import get_settings
from tracker.utils import build_excerpt, clean_whitespace


PROMPT_VERSION = "video-analysis-v1"
THEME_KEYWORDS = {
    "agents": ["agent", "workflow", "tool use", "browser use", "assistant"],
    "benchmarks": ["benchmark", "evaluation", "leaderboard", "accuracy"],
    "inference": ["inference", "latency", "serving", "vllm", "quantization"],
    "multimodality": ["image", "video", "audio", "multimodal", "vision"],
    "safety": ["safety", "alignment", "policy", "guardrail", "risk"],
    "scaling_laws": ["scaling", "emergent", "compute", "pretraining"],
    "training": ["training", "finetuning", "rlhf", "dataset", "distillation"],
    "tools": ["tool", "copilot", "app", "automation", "productivity"],
}
STOPWORDS = {
    "about",
    "after",
    "also",
    "been",
    "being",
    "could",
    "from",
    "have",
    "into",
    "just",
    "more",
    "most",
    "that",
    "their",
    "there",
    "they",
    "this",
    "what",
    "when",
    "with",
    "would",
    "your",
}


def _load_prompt_template() -> str:
    settings = get_settings()
    prompt_path = settings.prompts_dir / "video_analysis.md"
    return prompt_path.read_text(encoding="utf-8")


def _extract_keywords(text: str, limit: int = 8) -> list[str]:
    words = re.findall(r"[A-Za-z][A-Za-z0-9\-]{3,}", text.lower())
    filtered = [word for word in words if word not in STOPWORDS]
    ranked = Counter(filtered).most_common(limit * 3)
    keywords: list[str] = []
    for word, _count in ranked:
        if word not in keywords:
            keywords.append(word)
        if len(keywords) >= limit:
            break
    return keywords


def _extract_themes(text: str) -> list[str]:
    lowered = text.lower()
    themes = []
    for theme, keywords in THEME_KEYWORDS.items():
        if any(keyword in lowered for keyword in keywords):
            themes.append(theme)
    return themes or ["general_llm_news"]


def _extract_topics(title: str, text: str) -> list[str]:
    combined = f"{title}\n{text}".lower()
    topics = []
    topic_map = {
        "agents": ["agent", "agentic", "assistant"],
        "open-source models": ["open source", "llama", "mistral", "qwen"],
        "product releases": ["launch", "release", "announced", "update"],
        "research papers": ["paper", "research", "study", "arxiv"],
        "tools and apps": ["app", "tool", "workflow", "plugin"],
        "enterprise adoption": ["company", "enterprise", "business", "team"],
        "safety and alignment": ["safety", "alignment", "risk", "policy"],
    }
    for topic, keywords in topic_map.items():
        if any(keyword in combined for keyword in keywords):
            topics.append(topic)
    return topics or ["llm_overview"]


def _extract_speakers(title: str, channel_name: str) -> list[str]:
    speakers = [channel_name]
    patterns = [
        r"\bwith ([A-Z][A-Za-z]+(?: [A-Z][A-Za-z]+)?)",
        r"\bfeaturing ([A-Z][A-Za-z]+(?: [A-Z][A-Za-z]+)?)",
        r"\binterview with ([A-Z][A-Za-z]+(?: [A-Z][A-Za-z]+)?)",
    ]
    for pattern in patterns:
        match = re.search(pattern, title)
        if match:
            candidate = match.group(1).strip()
            if candidate not in speakers:
                speakers.append(candidate)
    return speakers


def _heuristic_summary(title: str, transcript: str) -> str:
    sentences = re.split(r"(?<=[.!?])\s+", clean_whitespace(transcript))
    summary_sentences = [sentence for sentence in sentences if sentence][:3]
    if not summary_sentences:
        return f"{title}: transcript available but too short for a strong automatic summary."
    summary = " ".join(summary_sentences)
    return clean_whitespace(summary[:500])


def _heuristic_analysis(title: str, transcript: str, channel_name: str) -> dict[str, Any]:
    combined = f"{title}\n{transcript}"
    return {
        "model": "heuristic-fallback",
        "prompt_version": PROMPT_VERSION,
        "summary": _heuristic_summary(title, transcript),
        "speakers": _extract_speakers(title, channel_name),
        "topics": _extract_topics(title, transcript),
        "keywords": _extract_keywords(combined),
        "themes": _extract_themes(combined),
        "confidence": 0.45,
        "raw_response": None,
    }


def _llm_analysis(title: str, transcript: str, channel_name: str) -> dict[str, Any]:
    settings = get_settings()
    provider = (settings.analysis_provider or "auto").lower()
    excerpt = build_excerpt(transcript, settings.analysis_max_chars)

    if provider == "gemini":
        return _gemini_analysis(title, excerpt, channel_name, transcript)
    if provider == "openai":
        return _openai_analysis(title, excerpt, channel_name, transcript)

    if settings.openai_api_key:
        return _openai_analysis(title, excerpt, channel_name, transcript)
    if settings.gemini_api_key:
        return _gemini_analysis(title, excerpt, channel_name, transcript)
    return _heuristic_analysis(title, transcript, channel_name)


def _openai_analysis(title: str, excerpt: str, channel_name: str, transcript: str) -> dict[str, Any]:
    settings = get_settings()
    if not settings.openai_api_key:
        return _heuristic_analysis(title, transcript, channel_name)

    try:
        from openai import OpenAI
    except ImportError:
        return _heuristic_analysis(title, transcript, channel_name)

    client = OpenAI(api_key=settings.openai_api_key)
    prompt = _load_prompt_template().replace("{{THEMES}}", ", ".join(THEME_KEYWORDS.keys()))
    response = client.chat.completions.create(
        model=settings.openai_model,
        temperature=0.2,
        response_format={"type": "json_object"},
        messages=[
            {
                "role": "system",
                "content": prompt,
            },
            {
                "role": "user",
                "content": (
                    f"Channel: {channel_name}\n"
                    f"Video title: {title}\n\n"
                    f"Transcript excerpt:\n{excerpt}"
                ),
            },
        ],
    )

    content = response.choices[0].message.content or "{}"
    parsed = json.loads(content)
    return {
        "model": settings.openai_model,
        "prompt_version": PROMPT_VERSION,
        "summary": clean_whitespace(parsed.get("summary", "")) or _heuristic_summary(title, transcript),
        "speakers": parsed.get("speakers") or _extract_speakers(title, channel_name),
        "topics": parsed.get("topics") or _extract_topics(title, transcript),
        "keywords": parsed.get("keywords") or _extract_keywords(transcript),
        "themes": parsed.get("themes") or _extract_themes(transcript),
        "confidence": float(parsed.get("confidence", 0.75)),
        "raw_response": content,
    }


def _gemini_analysis(title: str, excerpt: str, channel_name: str, transcript: str) -> dict[str, Any]:
    settings = get_settings()
    if not settings.gemini_api_key:
        return _heuristic_analysis(title, transcript, channel_name)

    prompt = _load_prompt_template().replace("{{THEMES}}", ", ".join(THEME_KEYWORDS.keys()))
    payload = {
        "contents": [
            {
                "parts": [
                    {
                        "text": (
                            f"{prompt}\n\n"
                            f"Channel: {channel_name}\n"
                            f"Video title: {title}\n\n"
                            f"Transcript excerpt:\n{excerpt}"
                        )
                    }
                ]
            }
        ],
        "generationConfig": {
            "temperature": 0.2,
            "responseMimeType": "application/json",
        },
    }
    request = Request(
        url=f"https://generativelanguage.googleapis.com/v1beta/models/{settings.gemini_model}:generateContent",
        headers={
            "Content-Type": "application/json",
            "x-goog-api-key": settings.gemini_api_key,
        },
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
    )

    try:
        with urlopen(request, timeout=60) as response:
            response_payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"Gemini API error {exc.code}: {body}") from exc
    except URLError as exc:
        raise RuntimeError(f"Gemini API request failed: {exc.reason}") from exc

    content = (
        response_payload.get("candidates", [{}])[0]
        .get("content", {})
        .get("parts", [{}])[0]
        .get("text", "{}")
    )
    parsed = json.loads(content)
    return {
        "model": settings.gemini_model,
        "prompt_version": PROMPT_VERSION,
        "summary": clean_whitespace(parsed.get("summary", "")) or _heuristic_summary(title, transcript),
        "speakers": parsed.get("speakers") or _extract_speakers(title, channel_name),
        "topics": parsed.get("topics") or _extract_topics(title, transcript),
        "keywords": parsed.get("keywords") or _extract_keywords(transcript),
        "themes": parsed.get("themes") or _extract_themes(transcript),
        "confidence": float(parsed.get("confidence", 0.75)),
        "raw_response": content,
    }


def analyse_video(title: str, transcript: str, channel_name: str) -> dict[str, Any]:
    if not transcript.strip():
        return _heuristic_analysis(title, transcript, channel_name)
    return _llm_analysis(title, transcript, channel_name)
