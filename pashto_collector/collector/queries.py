from __future__ import annotations

import re
from pathlib import Path
from typing import Any


TYPE_EXTENSIONS = {
    "text": [".txt", ".djvu.txt", ".epub", ".html"],
    "pdf": [".pdf"],
    "video": [".mp4", ".m4v", ".ogv", ".webm"],
    "lecture": [".mp4", ".m4v", ".mp3", ".ogg", ".pdf"],
    "audio": [".mp3", ".ogg", ".flac", ".wav", ".m4a"],
    "image": [".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff"],
    "other": [".pdf", ".txt", ".epub", ".mp3", ".mp4", ".jpg", ".png", ".html"],
}

EXTENSION_TYPES = {
    ".txt": "text",
    ".md": "text",
    ".json": "text",
    ".csv": "text",
    ".epub": "text",
    ".html": "text",
    ".htm": "text",
    ".pdf": "pdf",
    ".mp4": "video",
    ".m4v": "video",
    ".webm": "video",
    ".ogv": "video",
    ".mp3": "audio",
    ".ogg": "audio",
    ".flac": "audio",
    ".wav": "audio",
    ".m4a": "audio",
    ".jpg": "image",
    ".jpeg": "image",
    ".png": "image",
    ".webp": "image",
    ".tif": "image",
    ".tiff": "image",
}

TYPE_HINTS = {
    "video": {"video", "videos", "documentaries", "short_clips", "film", "films"},
    "lecture": {"lecture", "lectures", "video_lectures", "teaching_materials", "syllabi", "curriculum"},
    "audio": {"audio", "recitations", "audio_recitations", "podcasts", "radio", "songs", "sung_poetry", "recordings"},
    "image": {"image", "images", "calligraphy", "maps", "facsimiles", "manuscripts", "digitized_manuscripts"},
    "pdf": {
        "books",
        "book_chapters",
        "articles",
        "journal_articles",
        "research_papers",
        "papers",
        "theses",
        "dissertations",
        "reviews",
        "bibliographies",
        "manuscripts",
        "editions",
        "conference_papers",
    },
    "text": {"primary_texts", "texts", "transcriptions", "translations", "glossary", "index", "indexes", "notes", "claims"},
}

GENERIC_WORDS = {
    "books",
    "videos",
    "primary",
    "texts",
    "primary_texts",
    "audio",
    "images",
    "and",
    "the",
    "of",
    "by",
    "source",
    "types",
    "collection",
    "inbox",
    "by_date",
    "by_language",
    "by_status",
}

TYPE_QUERY_WORDS = {
    "pdf": "pdf book article",
    "text": "poem text",
    "video": "video",
    "lecture": "lecture",
    "audio": "audio recitation",
    "image": "image manuscript",
    "other": "archive",
}


def clean_token(value: str) -> str:
    value = re.sub(r"^\d+_", "", value)
    value = value.replace("_", " ").replace("-", " ")
    value = re.sub(r"\s+", " ", value).strip()
    return value


def safe_filename(value: str, fallback: str = "item") -> str:
    value = re.sub(r"[<>:\"/\\|?*\x00-\x1f]+", "_", value)
    value = re.sub(r"\s+", " ", value).strip().strip(".")
    return value[:150] or fallback


def infer_kind(path: Path, root_dir: Path) -> str:
    parts = [part.lower() for part in path.relative_to(root_dir).parts]
    for part in reversed(parts):
        for kind, hints in TYPE_HINTS.items():
            if part in hints:
                return kind
    return "other"


def topic_terms(path: Path, root_dir: Path) -> list[str]:
    pieces: list[str] = []
    kind = infer_kind(path, root_dir)
    for index, part in enumerate(path.relative_to(root_dir).parts):
        if index == 0 and re.match(r"^\d+_", part):
            continue
        lowered = part.lower()
        if lowered in GENERIC_WORDS or lowered in TYPE_HINTS.get(kind, set()):
            continue
        cleaned = clean_token(part)
        tokens = cleaned.lower().split()
        if cleaned and cleaned.lower() not in GENERIC_WORDS and not all(token in GENERIC_WORDS for token in tokens):
            pieces.append(cleaned)
    return pieces[-4:]


def build_queries(path: Path, root_dir: Path, kind: str, config: dict[str, Any]) -> list[str]:
    terms = topic_terms(path, root_dir)
    type_word = TYPE_QUERY_WORDS.get(kind, "archive")
    prefixes = config.get("query_prefixes") or ["Pashto poetry"]
    max_queries = int(config.get("max_queries_per_folder", 4))

    queries: list[str] = []
    compact_terms = terms[-2:] if terms else []
    broad_terms = terms[-3:] if terms else []
    for prefix in prefixes:
        queries.append(" ".join([prefix, *compact_terms, type_word]).strip())
        if broad_terms != compact_terms:
            queries.append(" ".join([prefix, *broad_terms, type_word]).strip())

    if terms:
        subject = " ".join(compact_terms)
        queries.extend(
            [
                f"{subject} Pashto poetry {type_word}",
                f"{subject} Pakhto poetry {type_word}",
                f"{subject} Pukhto poetry {type_word}",
            ]
        )

    seen: set[str] = set()
    unique: list[str] = []
    for query in queries:
        normalized = re.sub(r"\s+", " ", query).strip()
        key = normalized.lower()
        if normalized and key not in seen:
            seen.add(key)
            unique.append(normalized)
        if len(unique) >= max_queries:
            break
    return unique
