from __future__ import annotations

import html.parser
import re
import urllib.parse
import urllib.request
from typing import Any

from collector.queries import EXTENSION_TYPES, TYPE_EXTENSIONS


class _DuckDuckGoParser(html.parser.HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[tuple[str, str]] = []
        self._href = ""
        self._in_result = False
        self._title_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = {key: value or "" for key, value in attrs}
        if tag == "a" and "result__a" in attrs_dict.get("class", ""):
            self._href = attrs_dict.get("href", "")
            self._in_result = True
            self._title_parts = []

    def handle_data(self, data: str) -> None:
        if self._in_result:
            self._title_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._in_result:
            title = re.sub(r"\s+", " ", " ".join(self._title_parts)).strip()
            if self._href:
                self.links.append((title, self._href))
            self._href = ""
            self._in_result = False
            self._title_parts = []


class WebSearchSource:
    name = "web_search"

    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config

    def discover(self, query: str, kind: str, rows: int) -> list[dict[str, Any]]:
        if not self.config.get("public_sources", {}).get("web_search", False):
            return []
        search_query = query
        if kind in {"pdf", "text"}:
            search_query = f"{query} filetype:pdf OR filetype:txt"
        url = "https://duckduckgo.com/html/?" + urllib.parse.urlencode({"q": search_query})
        request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 PashtoPoetryCollector/2.0"})
        with urllib.request.urlopen(request, timeout=45) as response:
            html_text = response.read().decode("utf-8", errors="replace")

        parser = _DuckDuckGoParser()
        parser.feed(html_text)
        links: list[dict[str, Any]] = []
        for title, href in parser.links[:rows]:
            resolved = self._resolve_ddg_url(href)
            inferred_kind = self._kind_from_url(resolved) or kind
            direct = resolved if self._is_direct_file(resolved, inferred_kind) else ""
            links.append(
                {
                    "source": self.name,
                    "source_id": resolved,
                    "title": title or resolved,
                    "page_url": resolved,
                    "download_url": direct,
                    "kind": inferred_kind,
                    "query": query,
                    "status": "link_found",
                    "reason": "" if direct else "Search result saved as source link; no direct file detected",
                    "metadata": {"search_url": url},
                }
            )
        return links

    def _resolve_ddg_url(self, href: str) -> str:
        parsed = urllib.parse.urlparse(href)
        qs = urllib.parse.parse_qs(parsed.query)
        if "uddg" in qs:
            return qs["uddg"][0]
        if parsed.scheme:
            return href
        return urllib.parse.urljoin("https://duckduckgo.com", href)

    def _kind_from_url(self, url: str) -> str | None:
        path = urllib.parse.urlparse(url).path.lower()
        for ext, kind in EXTENSION_TYPES.items():
            if path.endswith(ext):
                return kind
        return None

    def _is_direct_file(self, url: str, kind: str) -> bool:
        path = urllib.parse.urlparse(url).path.lower()
        return any(path.endswith(ext) for ext in TYPE_EXTENSIONS.get(kind, TYPE_EXTENSIONS["other"]))
