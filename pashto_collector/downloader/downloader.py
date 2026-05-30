from __future__ import annotations

import json
import mimetypes
import shutil
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Callable

from collector.queries import TYPE_EXTENSIONS, safe_filename
from storage.database import utc_now


ProgressCallback = Callable[[int, int], None]


class LimitedReader:
    def __init__(self, stream: Any, max_bytes: int, total_bytes: int = 0, progress: ProgressCallback | None = None) -> None:
        self.stream = stream
        self.max_bytes = max_bytes
        self.total_bytes = total_bytes
        self.progress = progress
        self.total = 0

    def read(self, size: int = -1) -> bytes:
        chunk_size = 1024 * 128 if size is None or size < 0 else min(size, 1024 * 128)
        chunk = self.stream.read(chunk_size)
        self.total += len(chunk)
        if self.total > self.max_bytes:
            raise ValueError("Download exceeded configured size limit")
        if chunk and self.progress:
            self.progress(self.total, self.total_bytes)
        return chunk


def save_source_link(root_dir: Path, link: dict[str, Any], reason: str) -> Path:
    target_folder = root_dir / link["folder"]
    target_folder.mkdir(parents=True, exist_ok=True)
    filename = safe_filename(link.get("title") or link.get("source_id") or "source") + ".source.json"
    target = _unique_path(target_folder / filename)
    payload = {
        "title": link.get("title", ""),
        "source_url": link.get("page_url", ""),
        "download_url": link.get("download_url", ""),
        "source": link.get("source", ""),
        "source_id": link.get("source_id", ""),
        "kind": link.get("kind", ""),
        "folder": link.get("folder", ""),
        "reason": reason,
        "metadata": link.get("metadata", {}),
        "saved_at": utc_now(),
    }
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def download_link(
    root_dir: Path,
    config: dict[str, Any],
    link: dict[str, Any],
    progress: ProgressCallback | None = None,
) -> dict[str, Any]:
    if not link.get("download_url"):
        if config.get("download_web_pages", True) and link.get("page_url", "").startswith(("http://", "https://")):
            return download_web_page(root_dir, config, link, progress)
        path = save_source_link(root_dir, link, link.get("reason") or "No direct download URL")
        return {
            "status": "metadata_saved",
            "saved_path": str(path.relative_to(root_dir)),
            "bytes": 0,
            "message": link.get("reason") or "No direct download URL; source metadata saved",
        }

    kind = link.get("kind", "other")
    max_mb = float(config.get("max_file_mb", {}).get(kind, 40))
    max_bytes = int(max_mb * 1024 * 1024)
    target_folder = root_dir / link["folder"]
    target_folder.mkdir(parents=True, exist_ok=True)
    suffix = _suffix_for_url(link["download_url"], kind)
    target_name = safe_filename(link.get("title") or link.get("source_id") or "item") + suffix
    target_path = _unique_path(target_folder / target_name)

    request = urllib.request.Request(link["download_url"], headers={"User-Agent": "PashtoPoetryCollector/2.0"})
    with urllib.request.urlopen(request, timeout=120) as response, target_path.open("wb") as handle:
        total_bytes = _content_length(response)
        if progress:
            progress(0, total_bytes)
        shutil.copyfileobj(LimitedReader(response, max_bytes, total_bytes, progress), handle)
        bytes_written = handle.tell()

    metadata_path = target_path.with_suffix(target_path.suffix + ".source.json")
    metadata_path.write_text(
        json.dumps(
            {
                "title": link.get("title", ""),
                "source_url": link.get("page_url", ""),
                "download_url": link.get("download_url", ""),
                "source": link.get("source", ""),
                "source_id": link.get("source_id", ""),
                "kind": kind,
                "folder": link.get("folder", ""),
                "saved_at": utc_now(),
                "metadata": link.get("metadata", {}),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return {
        "status": "downloaded",
        "saved_path": str(target_path.relative_to(root_dir)),
        "bytes": bytes_written,
        "message": "Direct file downloaded",
    }


def download_web_page(
    root_dir: Path,
    config: dict[str, Any],
    link: dict[str, Any],
    progress: ProgressCallback | None = None,
) -> dict[str, Any]:
    max_mb = float(config.get("max_file_mb", {}).get("text", 25))
    max_bytes = int(max_mb * 1024 * 1024)
    target_folder = root_dir / link["folder"]
    target_folder.mkdir(parents=True, exist_ok=True)
    target_name = safe_filename(link.get("title") or link.get("source_id") or "webpage") + ".html"
    target_path = _unique_path(target_folder / target_name)

    request = urllib.request.Request(link["page_url"], headers={"User-Agent": "Mozilla/5.0 PashtoPoetryCollector/2.0"})
    with urllib.request.urlopen(request, timeout=90) as response, target_path.open("wb") as handle:
        total_bytes = _content_length(response)
        if progress:
            progress(0, total_bytes)
        shutil.copyfileobj(LimitedReader(response, max_bytes, total_bytes, progress), handle)
        bytes_written = handle.tell()

    metadata_path = target_path.with_suffix(target_path.suffix + ".source.json")
    metadata_path.write_text(
        json.dumps(
            {
                "title": link.get("title", ""),
                "source_url": link.get("page_url", ""),
                "download_url": link.get("download_url", ""),
                "source": link.get("source", ""),
                "source_id": link.get("source_id", ""),
                "kind": "text",
                "folder": link.get("folder", ""),
                "saved_as": "web_page_snapshot",
                "saved_at": utc_now(),
                "metadata": link.get("metadata", {}),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return {
        "status": "downloaded",
        "saved_path": str(target_path.relative_to(root_dir)),
        "bytes": bytes_written,
        "message": "Web page snapshot downloaded",
    }


def _suffix_for_url(url: str, kind: str) -> str:
    path = urllib.parse.unquote(urllib.parse.urlparse(url).path)
    suffix = Path(path).suffix.lower()
    if suffix:
        return suffix
    guessed = mimetypes.guess_extension(mimetypes.guess_type(url)[0] or "") or ""
    if guessed:
        return guessed
    return TYPE_EXTENSIONS.get(kind, [".bin"])[0]


def _content_length(response: Any) -> int:
    value = response.headers.get("Content-Length", "0")
    try:
        return int(value or 0)
    except ValueError:
        return 0


def _unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    stem = path.stem
    suffix = path.suffix
    parent = path.parent
    counter = 2
    while True:
        candidate = parent / f"{stem} ({counter}){suffix}"
        if not candidate.exists():
            return candidate
        counter += 1
