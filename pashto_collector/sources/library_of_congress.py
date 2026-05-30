from __future__ import annotations

import json
import urllib.parse
import urllib.request
from typing import Any


class LibraryOfCongressSource:
    name = "library_of_congress"

    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config

    def discover(self, query: str, kind: str, rows: int) -> list[dict[str, Any]]:
        if not self.config.get("public_sources", {}).get("library_of_congress", True):
            return []
        params = urllib.parse.urlencode({"q": query, "fo": "json", "c": str(rows)})
        payload = self._fetch_json(f"https://www.loc.gov/search/?{params}")
        output: list[dict[str, Any]] = []
        for item in payload.get("results", [])[:rows]:
            title = item.get("title") or "Library of Congress item"
            page_url = item.get("url") or item.get("id") or ""
            download_url = self._best_resource_url(item)
            output.append(
                {
                    "source": self.name,
                    "source_id": item.get("id") or page_url,
                    "title": title,
                    "page_url": page_url,
                    "download_url": download_url,
                    "kind": self._kind_for_item(kind, item, download_url),
                    "query": query,
                    "status": "link_found",
                    "reason": "" if download_url else "Library of Congress metadata/page link",
                    "metadata": item,
                }
            )
        return output

    def _best_resource_url(self, item: dict[str, Any]) -> str:
        resources = item.get("resources") or []
        if not isinstance(resources, list):
            resources = []
        for resource in resources:
            if not isinstance(resource, dict):
                continue
            files = resource.get("files") or []
            if not isinstance(files, list):
                files = []
            for file_item in files:
                if isinstance(file_item, dict):
                    url = file_item.get("url") or file_item.get("download")
                    if url:
                        return url
        image = item.get("image_url") or []
        if isinstance(image, list) and image:
            return image[-1]
        return ""

    def _kind_for_item(self, fallback: str, item: dict[str, Any], download_url: str) -> str:
        subject = self._join_field(item.get("subject")).lower()
        original_format = self._join_field(item.get("original_format")).lower()
        haystack = f"{subject} {original_format} {download_url}".lower()
        if any(token in haystack for token in ["photo", "image", ".jpg", ".jpeg", ".png"]):
            return "image"
        if any(token in haystack for token in ["audio", ".mp3", ".wav"]):
            return "audio"
        if any(token in haystack for token in ["video", "film", ".mp4"]):
            return "video"
        if ".pdf" in haystack or "book" in haystack:
            return "pdf"
        return fallback

    def _join_field(self, value: Any) -> str:
        if isinstance(value, list):
            return " ".join(str(item) for item in value)
        if value is None:
            return ""
        return str(value)

    def _fetch_json(self, url: str) -> dict[str, Any]:
        request = urllib.request.Request(url, headers={"User-Agent": "PashtoPoetryCollector/2.0"})
        with urllib.request.urlopen(request, timeout=45) as response:
            return json.loads(response.read().decode("utf-8", errors="replace"))
