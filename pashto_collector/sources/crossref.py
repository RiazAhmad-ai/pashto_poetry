from __future__ import annotations

import json
import urllib.parse
import urllib.request
from typing import Any


class CrossrefSource:
    name = "crossref"

    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config

    def discover(self, query: str, kind: str, rows: int) -> list[dict[str, Any]]:
        if not self.config.get("public_sources", {}).get("crossref", True):
            return []
        params = {"query.bibliographic": query, "rows": str(rows)}
        mailto = self.config.get("api_contact_email", "")
        if mailto:
            params["mailto"] = mailto
        url = "https://api.crossref.org/works?" + urllib.parse.urlencode(params)
        payload = self._fetch_json(url)
        output: list[dict[str, Any]] = []
        for item in payload.get("message", {}).get("items", [])[:rows]:
            title = " ".join(item.get("title") or []) or item.get("DOI") or "Crossref work"
            doi = item.get("DOI", "")
            page_url = item.get("URL") or (f"https://doi.org/{doi}" if doi else "")
            output.append(
                {
                    "source": self.name,
                    "source_id": doi or page_url,
                    "title": title,
                    "page_url": page_url,
                    "download_url": "",
                    "kind": "pdf" if kind in {"pdf", "text", "other"} else kind,
                    "query": query,
                    "status": "link_found",
                    "reason": "Crossref scholarly metadata; source page may contain article/PDF access",
                    "metadata": item,
                }
            )
        return output

    def _fetch_json(self, url: str) -> dict[str, Any]:
        request = urllib.request.Request(url, headers={"User-Agent": "PashtoPoetryCollector/2.0"})
        with urllib.request.urlopen(request, timeout=45) as response:
            return json.loads(response.read().decode("utf-8", errors="replace"))
