from __future__ import annotations

import json
import urllib.parse
import urllib.request
from typing import Any


class OpenLibrarySource:
    name = "open_library"

    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config

    def discover(self, query: str, kind: str, rows: int) -> list[dict[str, Any]]:
        if not self.config.get("public_sources", {}).get("open_library", True):
            return []
        params = urllib.parse.urlencode({"q": query, "limit": str(rows), "language": "pus"})
        payload = self._fetch_json(f"https://openlibrary.org/search.json?{params}")
        results: list[dict[str, Any]] = []
        for doc in payload.get("docs", [])[:rows]:
            key = doc.get("key", "")
            title = doc.get("title") or doc.get("title_suggest") or key or "Open Library item"
            page_url = f"https://openlibrary.org{key}" if key else "https://openlibrary.org/search?" + params
            ia_ids = doc.get("ia") or []
            download_url = ""
            source_url = page_url
            if ia_ids:
                source_url = f"https://archive.org/details/{ia_ids[0]}"
            results.append(
                {
                    "source": self.name,
                    "source_id": key or source_url,
                    "title": title,
                    "page_url": source_url,
                    "download_url": download_url,
                    "kind": "pdf" if kind in {"pdf", "text", "other"} else kind,
                    "query": query,
                    "status": "link_found",
                    "reason": "Open Library metadata link; may point to Internet Archive item",
                    "metadata": doc,
                }
            )
        return results

    def _fetch_json(self, url: str) -> dict[str, Any]:
        request = urllib.request.Request(url, headers={"User-Agent": "PashtoPoetryCollector/2.0"})
        with urllib.request.urlopen(request, timeout=45) as response:
            return json.loads(response.read().decode("utf-8", errors="replace"))
