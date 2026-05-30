from __future__ import annotations

import json
import urllib.parse
import urllib.request
from typing import Any

from collector.queries import TYPE_EXTENSIONS


class InternetArchiveSource:
    name = "internet_archive"

    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config

    def discover(self, query: str, kind: str, rows: int) -> list[dict[str, Any]]:
        docs = self._search(query, kind, rows)
        links: list[dict[str, Any]] = []
        for doc in docs:
            identifier = doc.get("identifier", "")
            if not identifier:
                continue
            title = doc.get("title") or identifier
            page_url = f"https://archive.org/details/{identifier}"
            chosen = self._choose_file(identifier, kind)
            item = {
                "source": self.name,
                "source_id": identifier,
                "title": title,
                "page_url": page_url,
                "download_url": "",
                "kind": kind,
                "query": query,
                "status": "link_found",
                "reason": "",
                "metadata": doc,
            }
            if chosen:
                file_name = chosen["name"]
                item["download_url"] = f"https://archive.org/download/{urllib.parse.quote(identifier)}/{urllib.parse.quote(file_name)}"
                item["metadata"] = {**doc, "archive_file": file_name, "archive_size": chosen.get("size", 0)}
            else:
                item["reason"] = "No direct file within configured type/size limits"
            links.append(item)
        return links

    def _search(self, query: str, kind: str, rows: int) -> list[dict[str, Any]]:
        mediatype = {
            "pdf": "texts",
            "text": "texts",
            "video": "movies",
            "lecture": "movies",
            "audio": "audio",
            "image": "image",
            "other": "",
        }.get(kind, "")
        archive_query = query
        if mediatype:
            archive_query = f"({query}) AND mediatype:{mediatype}"
        params = urllib.parse.urlencode(
            {
                "q": archive_query,
                "fl[]": ["identifier", "title", "creator", "mediatype", "description"],
                "rows": str(rows),
                "page": "1",
                "output": "json",
                "sort[]": "downloads desc",
            },
            doseq=True,
        )
        payload = self._fetch_json(f"https://archive.org/advancedsearch.php?{params}")
        return payload.get("response", {}).get("docs", [])

    def _choose_file(self, identifier: str, kind: str) -> dict[str, Any] | None:
        metadata = self._fetch_json(f"https://archive.org/metadata/{urllib.parse.quote(identifier)}")
        files = metadata.get("files", [])
        wanted = TYPE_EXTENSIONS.get(kind, TYPE_EXTENSIONS["other"])
        max_mb = float(self.config.get("max_file_mb", {}).get(kind, 40))
        max_bytes = int(max_mb * 1024 * 1024)
        candidates: list[dict[str, Any]] = []
        for item in files:
            name = item.get("name", "")
            lowered = name.lower()
            if not any(lowered.endswith(ext) for ext in wanted):
                continue
            try:
                size = int(item.get("size", "0") or 0)
            except ValueError:
                size = 0
            candidates.append({"name": name, "size": size})
        candidates.sort(key=lambda item: (item["size"] == 0, item["size"]))
        for candidate in candidates:
            if candidate["size"] <= max_bytes or candidate["size"] == 0:
                return candidate
        return None

    def _fetch_json(self, url: str) -> dict[str, Any]:
        request = urllib.request.Request(url, headers={"User-Agent": "PashtoPoetryCollector/2.0"})
        with urllib.request.urlopen(request, timeout=45) as response:
            return json.loads(response.read().decode("utf-8", errors="replace"))
