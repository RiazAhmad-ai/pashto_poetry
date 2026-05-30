from __future__ import annotations

import json
import urllib.parse
import urllib.request
from typing import Any


class WikimediaSource:
    name = "wikimedia"

    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        self.projects = config.get("wikimedia_projects", ["ps.wikipedia.org", "en.wikipedia.org"])

    def discover(self, query: str, kind: str, rows: int) -> list[dict[str, Any]]:
        if not self.config.get("public_sources", {}).get("wikimedia", True):
            return []
        output: list[dict[str, Any]] = []
        per_project = max(1, rows)
        for project in self.projects:
            url = f"https://{project}/w/rest.php/v1/search/page?" + urllib.parse.urlencode({"q": query, "limit": str(per_project)})
            try:
                payload = self._fetch_json(url)
            except Exception:
                continue
            for page in payload.get("pages", [])[:per_project]:
                title = page.get("title") or page.get("key") or "Wikimedia page"
                page_url = page.get("url")
                if page_url and page_url.startswith("/"):
                    page_url = f"https://{project}{page_url}"
                if not page_url:
                    key = urllib.parse.quote(page.get("key") or title.replace(" ", "_"))
                    page_url = f"https://{project}/wiki/{key}"
                output.append(
                    {
                        "source": self.name,
                        "source_id": f"{project}:{page.get('id', title)}",
                        "title": title,
                        "page_url": page_url,
                        "download_url": "",
                        "kind": "text" if kind in {"text", "other", "pdf"} else kind,
                        "query": query,
                        "status": "link_found",
                        "reason": "Wikimedia page saved as source link or HTML snapshot",
                        "metadata": {"project": project, **page},
                    }
                )
                if len(output) >= rows:
                    return output
        return output

    def _fetch_json(self, url: str) -> dict[str, Any]:
        request = urllib.request.Request(url, headers={"User-Agent": "PashtoPoetryCollector/2.0"})
        with urllib.request.urlopen(request, timeout=45) as response:
            return json.loads(response.read().decode("utf-8", errors="replace"))
