from __future__ import annotations

import html.parser
import re
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any

from collector.queries import EXTENSION_TYPES, TYPE_EXTENSIONS


PASHTO_KEYWORDS = {
    "pashto",
    "pushto",
    "pakhto",
    "pukhto",
    "pashtun",
    "poetry",
    "poem",
    "poems",
    "shayari",
    "shairi",
    "dewan",
    "diwan",
    "rahman",
    "khushal",
    "ghani",
    "hamza",
    "landay",
    "tapa",
    "پښتو",
    "شاعري",
    "شعر",
    "لنډۍ",
    "ټپه",
}


@dataclass
class FoundLink:
    title: str
    url: str
    site_name: str
    seed_url: str


class _AnchorParser(html.parser.HTMLParser):
    def __init__(self, base_url: str) -> None:
        super().__init__()
        self.base_url = base_url
        self.links: list[FoundLink] = []
        self._href = ""
        self._title_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "a":
            return
        attrs_dict = {key.lower(): value or "" for key, value in attrs}
        href = attrs_dict.get("href", "")
        if not href or href.startswith("#") or href.startswith("mailto:") or href.startswith("javascript:"):
            return
        self._href = urllib.parse.urljoin(self.base_url, href)
        self._title_parts = []

    def handle_data(self, data: str) -> None:
        if self._href:
            self._title_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._href:
            title = re.sub(r"\s+", " ", " ".join(self._title_parts)).strip()
            self.links.append(FoundLink(title=title, url=self._href, site_name="", seed_url=self.base_url))
            self._href = ""
            self._title_parts = []


class TargetedSitesSource:
    name = "targeted_sites"

    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        self._cache: list[FoundLink] | None = None

    def discover(self, query: str, kind: str, rows: int) -> list[dict[str, Any]]:
        if not self.config.get("public_sources", {}).get("targeted_sites", True):
            return []
        links = self._load_links()
        query_terms = self._query_terms(query)
        scored: list[tuple[int, FoundLink]] = []
        for link in links:
            haystack = f"{link.title} {link.url}".lower()
            if not self._is_relevant(haystack, query_terms, kind):
                continue
            score = self._score(haystack, query_terms, kind)
            scored.append((score, link))
        scored.sort(key=lambda item: item[0], reverse=True)

        results: list[dict[str, Any]] = []
        for _score, link in scored[:rows]:
            inferred_kind = self._kind_from_url(link.url) or kind
            direct = link.url if self._is_direct_file(link.url, inferred_kind) else ""
            results.append(
                {
                    "source": self.name,
                    "source_id": link.url,
                    "title": link.title or link.url,
                    "page_url": link.url,
                    "download_url": direct,
                    "kind": inferred_kind,
                    "query": query,
                    "status": "link_found",
                    "reason": "" if direct else "Targeted site page saved for later review/download",
                    "metadata": {"site_name": link.site_name, "seed_url": link.seed_url},
                }
            )
        return results

    def _load_links(self) -> list[FoundLink]:
        if self._cache is not None:
            return self._cache
        found: list[FoundLink] = []
        seen: set[str] = set()
        for site in self.config.get("targeted_sites", []):
            name = site.get("name", "targeted_site")
            seed_url = site.get("url", "")
            if not seed_url:
                continue
            for link in self._fetch_seed_links(seed_url, name):
                normalized = self._normalize_url(link.url)
                if normalized in seen:
                    continue
                seen.add(normalized)
                link.url = normalized
                found.append(link)
        self._cache = found
        return found

    def _fetch_seed_links(self, seed_url: str, site_name: str) -> list[FoundLink]:
        request = urllib.request.Request(seed_url, headers={"User-Agent": "Mozilla/5.0 PashtoPoetryCollector/2.0"})
        with urllib.request.urlopen(request, timeout=45) as response:
            html_text = response.read().decode("utf-8", errors="replace")
        parser = _AnchorParser(seed_url)
        parser.feed(html_text)
        links: list[FoundLink] = []
        seed_domain = urllib.parse.urlparse(seed_url).netloc.lower()
        for link in parser.links:
            domain = urllib.parse.urlparse(link.url).netloc.lower()
            if domain != seed_domain and not domain.endswith("." + seed_domain):
                continue
            link.site_name = site_name
            link.seed_url = seed_url
            links.append(link)
        links.append(FoundLink(title=site_name, url=seed_url, site_name=site_name, seed_url=seed_url))
        return links

    def _query_terms(self, query: str) -> set[str]:
        terms = {term for term in re.split(r"[^A-Za-z0-9\u0600-\u06ff]+", query.lower()) if len(term) >= 3}
        return terms | PASHTO_KEYWORDS

    def _is_relevant(self, haystack: str, query_terms: set[str], kind: str) -> bool:
        if self._is_direct_file(haystack, kind):
            return True
        return any(term in haystack for term in query_terms)

    def _score(self, haystack: str, query_terms: set[str], kind: str) -> int:
        score = sum(3 for term in query_terms if term in haystack)
        if self._is_direct_file(haystack, kind):
            score += 20
        if any(keyword in haystack for keyword in PASHTO_KEYWORDS):
            score += 10
        return score

    def _normalize_url(self, url: str) -> str:
        parsed = urllib.parse.urlparse(url)
        clean = parsed._replace(fragment="")
        return urllib.parse.urlunparse(clean)

    def _kind_from_url(self, url: str) -> str | None:
        path = urllib.parse.urlparse(url).path.lower()
        for ext, kind in EXTENSION_TYPES.items():
            if path.endswith(ext):
                return kind
        return None

    def _is_direct_file(self, url: str, kind: str) -> bool:
        path = urllib.parse.urlparse(url).path.lower()
        return any(path.endswith(ext) for ext in TYPE_EXTENSIONS.get(kind, TYPE_EXTENSIONS["other"]))
