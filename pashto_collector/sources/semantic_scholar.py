from __future__ import annotations

import json
import urllib.parse
import urllib.request
from typing import Any


class SemanticScholarSource:
    name = "semantic_scholar"

    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config

    def discover(self, query: str, kind: str, rows: int) -> list[dict[str, Any]]:
        if not self.config.get("public_sources", {}).get("semantic_scholar", True):
            return []
        params = urllib.parse.urlencode(
            {
                "query": query,
                "limit": str(min(rows, 10)),
                "fields": "title,url,year,authors,abstract,openAccessPdf,externalIds",
            }
        )
        payload = self._fetch_json(f"https://api.semanticscholar.org/graph/v1/paper/search?{params}")
        output: list[dict[str, Any]] = []
        for paper in payload.get("data", [])[:rows]:
            title = paper.get("title") or paper.get("paperId") or "Semantic Scholar paper"
            page_url = paper.get("url") or ""
            open_pdf = paper.get("openAccessPdf") or {}
            download_url = open_pdf.get("url") or ""
            output.append(
                {
                    "source": self.name,
                    "source_id": paper.get("paperId") or page_url,
                    "title": title,
                    "page_url": page_url or download_url,
                    "download_url": download_url,
                    "kind": "pdf" if kind in {"pdf", "text", "other"} else kind,
                    "query": query,
                    "status": "link_found",
                    "reason": "" if download_url else "Semantic Scholar metadata; no open PDF URL in result",
                    "metadata": paper,
                }
            )
        return output

    def _fetch_json(self, url: str) -> dict[str, Any]:
        request = urllib.request.Request(url, headers={"User-Agent": "PashtoPoetryCollector/2.0"})
        with urllib.request.urlopen(request, timeout=45) as response:
            return json.loads(response.read().decode("utf-8", errors="replace"))
