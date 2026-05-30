from __future__ import annotations

import json
import mimetypes
import os
import threading
import time
import urllib.parse
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from collector.queries import EXTENSION_TYPES
from collector.scanner import scan_folders
from downloader.downloader import download_link
from sources.crossref import CrossrefSource
from sources.internet_archive import InternetArchiveSource
from sources.library_of_congress import LibraryOfCongressSource
from sources.open_library import OpenLibrarySource
from sources.semantic_scholar import SemanticScholarSource
from sources.targeted_sites import TargetedSitesSource
from sources.web_search import WebSearchSource
from sources.wikimedia import WikimediaSource
from storage.database import CollectorDatabase, utc_now


APP_DIR = Path(__file__).resolve().parent
ROOT_DIR = APP_DIR.parent
DATA_DIR = APP_DIR / "data"
STATIC_DIR = APP_DIR / "static"
CONFIG_PATH = APP_DIR / "config.json"
DB_PATH = DATA_DIR / "archive.db"

DATA_DIR.mkdir(exist_ok=True)
DB = CollectorDatabase(DB_PATH)
DB.reset_interrupted_downloads()


class WorkerState:
    def __init__(self) -> None:
        self.lock = threading.RLock()
        self.link_running = False
        self.download_running = False
        self.link_current = "Idle"
        self.download_current = "Idle"
        self.last_error = ""
        self.link_stop = threading.Event()
        self.download_stop = threading.Event()

    def snapshot(self) -> dict[str, Any]:
        with self.lock:
            return {
                "linkRunning": self.link_running,
                "downloadRunning": self.download_running,
                "linkCurrent": self.link_current,
                "downloadCurrent": self.download_current,
                "lastError": self.last_error,
            }

    def set_link(self, running: bool | None = None, current: str | None = None, error: str | None = None) -> None:
        with self.lock:
            if running is not None:
                self.link_running = running
            if current is not None:
                self.link_current = current
            if error is not None:
                self.last_error = error

    def set_download(self, running: bool | None = None, current: str | None = None, error: str | None = None) -> None:
        with self.lock:
            if running is not None:
                self.download_running = running
            if current is not None:
                self.download_current = current
            if error is not None:
                self.last_error = error


WORKERS = WorkerState()
LINK_THREAD: threading.Thread | None = None
DOWNLOAD_THREAD: threading.Thread | None = None


def load_config() -> dict[str, Any]:
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def scan_and_store() -> list[dict[str, Any]]:
    folders = scan_folders(ROOT_DIR, load_config())
    DB.upsert_folders(folders)
    DB.set_setting("last_scan_count", len(folders))
    DB.set_setting("last_scan_at", utc_now())
    return folders


def ensure_initial_index() -> None:
    if DB.folder_count() == 0:
        scan_and_store()
    if not DB.get_setting("existing_sources_indexed", False):
        index_existing_source_files()
        DB.set_setting("existing_sources_indexed", True)


def index_existing_source_files() -> None:
    for source_file in ROOT_DIR.rglob("*.source.json"):
        if APP_DIR in source_file.parents:
            continue
        try:
            payload = json.loads(source_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        actual_path = Path(str(source_file)[: -len(".source.json")])
        folder = source_file.parent.relative_to(ROOT_DIR).as_posix()
        suffix = actual_path.suffix.lower()
        kind = payload.get("kind") or EXTENSION_TYPES.get(suffix, "other")
        status = "downloaded" if actual_path.exists() else "metadata_saved"
        DB.add_link(
            {
                "source": payload.get("source", "existing_source"),
                "source_id": payload.get("identifier") or payload.get("source_id") or str(source_file.relative_to(ROOT_DIR)),
                "title": payload.get("title") or actual_path.stem,
                "page_url": payload.get("source_url") or "",
                "download_url": payload.get("download_url") or "",
                "kind": kind,
                "folder": folder,
                "query": "existing file index",
                "status": status,
                "reason": payload.get("reason", ""),
                "metadata": payload,
            }
        )


def folder_stats() -> list[dict[str, Any]]:
    stats: dict[str, dict[str, Any]] = {}
    for file_path in ROOT_DIR.rglob("*"):
        if not file_path.is_file() or APP_DIR in file_path.parents:
            continue
        if file_path.name.endswith(".source.json"):
            continue
        rel_dir = file_path.parent.relative_to(ROOT_DIR).as_posix()
        ext = file_path.suffix.lower()
        kind = EXTENSION_TYPES.get(ext, "other")
        bucket = stats.setdefault(
            rel_dir,
            {"folder": rel_dir, "total": 0, "bytes": 0, "text": 0, "pdf": 0, "video": 0, "lecture": 0, "audio": 0, "image": 0, "other": 0},
        )
        bucket["total"] += 1
        bucket["bytes"] += file_path.stat().st_size
        bucket[kind] = bucket.get(kind, 0) + 1
    return sorted(stats.values(), key=lambda item: (-item["total"], item["folder"]))[:250]


def dashboard_state() -> dict[str, Any]:
    file_counts = {"text": 0, "pdf": 0, "video": 0, "lecture": 0, "audio": 0, "image": 0, "other": 0}
    total_bytes = 0
    total_files = 0
    folders = folder_stats()
    for item in folders:
        total_files += item["total"]
        total_bytes += item["bytes"]
        for kind in file_counts:
            file_counts[kind] += item.get(kind, 0)

    link_statuses = DB.link_counts_by_status()
    link_kinds = DB.link_counts_by_kind()
    source_counts = DB.link_counts_by_source()
    worker_state = WORKERS.snapshot()
    return {
        "projectRoot": str(ROOT_DIR),
        "updatedAt": utc_now(),
        "lastScanCount": DB.folder_count(),
        "lastScanAt": DB.get_setting("last_scan_at", ""),
        "totalFiles": total_files,
        "totalBytes": total_bytes,
        "filesByType": file_counts,
        "linksByStatus": link_statuses,
        "linksByType": link_kinds,
        "linksBySource": source_counts,
        "linksByDomain": DB.link_counts_by_domain(25),
        "candidateDomains": DB.list_candidate_domains(5000),
        "enabledSources": [source.name for source in source_connectors(load_config())],
        "totalLinks": sum(link_statuses.values()),
        "pendingDownloads": link_statuses.get("link_found", 0) + link_statuses.get("download_failed", 0),
        "folderStats": folders,
        "recentLinks": DB.recent_links(100),
        "collectedLinks": DB.links_by_status(["link_found"], 200),
        "activeDownloads": DB.links_by_status(["downloading"], 50),
        "completedDownloads": DB.links_by_status(["downloaded", "metadata_saved"], 200),
        "failedDownloads": DB.links_by_status(["download_failed"], 100),
        "recentEvents": DB.recent_events(80),
        **worker_state,
    }


def source_connectors(config: dict[str, Any]) -> list[Any]:
    sources: list[Any] = []
    config = {**config, "targeted_sites": [*config.get("targeted_sites", []), *DB.approved_candidate_sites()]}
    if config.get("public_sources", {}).get("targeted_sites", True):
        sources.append(TargetedSitesSource(config))
    if config.get("public_sources", {}).get("internet_archive", True):
        sources.append(InternetArchiveSource(config))
    if config.get("public_sources", {}).get("open_library", True):
        sources.append(OpenLibrarySource(config))
    if config.get("public_sources", {}).get("wikimedia", True):
        sources.append(WikimediaSource(config))
    if config.get("public_sources", {}).get("crossref", True):
        sources.append(CrossrefSource(config))
    if config.get("public_sources", {}).get("semantic_scholar", True):
        sources.append(SemanticScholarSource(config))
    if config.get("public_sources", {}).get("library_of_congress", True):
        sources.append(LibraryOfCongressSource(config))
    if config.get("public_sources", {}).get("web_search", False):
        sources.append(WebSearchSource(config))
    return sources


def known_domains(config: dict[str, Any]) -> set[str]:
    domains: set[str] = {"archive.org", "duckduckgo.com"}
    for site in config.get("targeted_sites", []):
        domain = normalize_domain(site.get("url", ""))
        if domain:
            domains.add(domain)
    for site in DB.approved_candidate_sites():
        domain = normalize_domain(site.get("url", ""))
        if domain:
            domains.add(domain)
    return domains


def normalize_domain(url: str) -> str:
    domain = urllib.parse.urlparse(url).netloc.lower()
    if domain.startswith("www."):
        domain = domain[4:]
    return domain


def record_candidate_domain(item: dict[str, Any], known: set[str]) -> None:
    domain = normalize_domain(item.get("page_url", ""))
    if not domain or domain in known:
        return
    DB.upsert_candidate_domain(domain, item.get("source", ""), item.get("page_url", ""), item.get("title", ""))


def should_keep_link(item: dict[str, Any], query: str) -> bool:
    haystack = " ".join(
        [
            str(item.get("title", "")),
            str(item.get("page_url", "")),
            str(item.get("download_url", "")),
            json.dumps(item.get("metadata", {}), ensure_ascii=False)[:2000],
        ]
    ).lower()
    strong_terms = {
        "pashto",
        "pushto",
        "pakhto",
        "pukhto",
        "poetry",
        "poem",
        "poems",
        "dewan",
        "diwan",
        "shayari",
        "rahman",
        "khushal",
        "ghani",
        "hamza",
        "landay",
        "پښتو",
        "شاعري",
        "شعر",
        "لنډۍ",
        "ټپه",
    }
    if any(term in haystack for term in strong_terms):
        return True
    query_terms = [term for term in query.lower().replace("_", " ").split() if len(term) >= 5]
    useful_matches = sum(1 for term in query_terms if term in haystack)
    return useful_matches >= 2


def run_link_collection(folder_limit: int, results_per_folder: int, selected_paths: list[str] | None = None) -> None:
    config = load_config()
    delay = float(config.get("request_delay_seconds", 1.0))
    folders = scan_and_store()
    if selected_paths:
        selected = set(selected_paths)
        folders = [folder for folder in folders if folder["path"] in selected]
    folders = folders[:folder_limit]
    sources = source_connectors(config)
    known = known_domains(config)

    WORKERS.link_stop.clear()
    WORKERS.set_link(running=True, current="Starting link collection", error="")
    DB.add_event("links", "info", f"Started link collection for {len(folders)} folders")
    try:
        for folder in folders:
            if WORKERS.link_stop.is_set():
                break
            rel_folder = folder["path"]
            kind = folder["kind"]
            for query in folder.get("queries", [folder.get("query", "")]):
                if WORKERS.link_stop.is_set():
                    break
                WORKERS.set_link(current=f"{rel_folder} - {query}")
                for source in sources:
                    if WORKERS.link_stop.is_set():
                        break
                    try:
                        discovered = source.discover(query, kind, results_per_folder)
                    except Exception as exc:
                        message = f"{source.name} search failed: {exc}"
                        WORKERS.set_link(error=message)
                        DB.add_event("links", "error", message, rel_folder, query)
                        continue
                    inserted = 0
                    duplicates = 0
                    for item in discovered:
                        item["folder"] = rel_folder
                        item.setdefault("kind", kind)
                        item.setdefault("query", query)
                        if not should_keep_link(item, query):
                            continue
                        record_candidate_domain(item, known)
                        _link_id, created = DB.add_link(item)
                        inserted += 1 if created else 0
                        duplicates += 0 if created else 1
                    DB.add_event("links", "info", f"{source.name}: {inserted} links, {duplicates} duplicates", rel_folder, query)
                    time.sleep(delay)
    finally:
        stopped = WORKERS.link_stop.is_set()
        WORKERS.set_link(running=False, current="Stopped" if stopped else "Idle")
        DB.add_event("links", "info", "Link collection stopped" if stopped else "Link collection finished")


def run_download_queue(batch_size: int, continuous: bool = True) -> None:
    config = load_config()
    delay = float(config.get("request_delay_seconds", 1.0))
    WORKERS.download_stop.clear()
    WORKERS.set_download(running=True, current="Starting data downloads", error="")
    DB.add_event("downloads", "info", "Started data download worker")
    try:
        while not WORKERS.download_stop.is_set():
            links = DB.next_download_links(batch_size)
            if not links:
                if continuous:
                    WORKERS.set_download(current="Waiting for saved links")
                    time.sleep(max(delay, 2.0))
                    continue
                break
            for link in links:
                if WORKERS.download_stop.is_set():
                    break
                WORKERS.set_download(current=f"{link['folder']} - {link['title']}")
                DB.update_link(link["id"], status="downloading", downloaded_bytes=0, total_bytes=0, error="")
                try:
                    last_progress_update = 0.0

                    def progress(downloaded_bytes: int, total_bytes: int) -> None:
                        nonlocal last_progress_update
                        now = time.monotonic()
                        if now - last_progress_update < 0.5 and downloaded_bytes != total_bytes:
                            return
                        last_progress_update = now
                        DB.update_link(link["id"], downloaded_bytes=downloaded_bytes, total_bytes=total_bytes)

                    result = download_link(ROOT_DIR, config, link, progress)
                    DB.update_link(
                        link["id"],
                        status=result["status"],
                        reason=result.get("message", ""),
                        saved_path=result.get("saved_path", ""),
                        bytes=int(result.get("bytes", 0) or 0),
                        downloaded_bytes=int(result.get("bytes", 0) or 0),
                        total_bytes=int(result.get("bytes", 0) or 0),
                        error="",
                    )
                    DB.add_event("downloads", "info", f"{result['status']}: {link['title']}", link["folder"], link["query"])
                except Exception as exc:
                    message = str(exc)
                    DB.update_link(link["id"], status="download_failed", reason=message, error=message)
                    WORKERS.set_download(error=message)
                    DB.add_event("downloads", "error", message, link["folder"], link["query"])
                time.sleep(delay)
            if not continuous:
                break
    finally:
        stopped = WORKERS.download_stop.is_set()
        WORKERS.set_download(running=False, current="Stopped" if stopped else "Idle")
        DB.add_event("downloads", "info", "Data download worker stopped" if stopped else "Data download worker finished")


class Handler(SimpleHTTPRequestHandler):
    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/api/state":
            self.send_json(dashboard_state())
            return
        if parsed.path == "/api/folders":
            query = urllib.parse.parse_qs(parsed.query)
            limit = int(query.get("limit", ["500"])[0])
            self.send_json({"folders": DB.list_folders(limit)})
            return
        if parsed.path == "/":
            self.path = "/index.html"
        return super().do_GET()

    def do_POST(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        length = int(self.headers.get("Content-Length", "0") or 0)
        body = self.rfile.read(length).decode("utf-8") if length else "{}"
        try:
            payload = json.loads(body or "{}")
        except json.JSONDecodeError:
            self.send_json({"error": "Invalid JSON"}, status=400)
            return
        routes = {
            "/api/start": self.start_links,
            "/api/start-links": self.start_links,
            "/api/stop": self.stop_links,
            "/api/stop-links": self.stop_links,
            "/api/start-downloads": self.start_downloads,
            "/api/stop-downloads": self.stop_downloads,
            "/api/rescan": self.rescan,
            "/api/domain/approve": self.approve_domain,
            "/api/domain/reject": self.reject_domain,
        }
        handler = routes.get(parsed.path)
        if handler:
            handler(payload)
            return
        self.send_json({"error": "Not found"}, status=404)

    def start_links(self, payload: dict[str, Any]) -> None:
        global LINK_THREAD
        if WORKERS.snapshot()["linkRunning"]:
            self.send_json({"ok": False, "error": "Link collector already running"}, status=409)
            return
        config = load_config()
        folder_limit = int(payload.get("folderLimit", config.get("default_folder_limit", 25)))
        results_per_folder = int(payload.get("resultsPerFolder", config.get("default_results_per_folder", 1)))
        selected_paths = payload.get("selectedPaths") or None
        LINK_THREAD = threading.Thread(target=run_link_collection, args=(folder_limit, results_per_folder, selected_paths), daemon=True)
        LINK_THREAD.start()
        self.send_json({"ok": True})

    def stop_links(self, _payload: dict[str, Any]) -> None:
        WORKERS.link_stop.set()
        WORKERS.set_link(current="Stopping after current request")
        self.send_json({"ok": True})

    def start_downloads(self, payload: dict[str, Any]) -> None:
        global DOWNLOAD_THREAD
        if WORKERS.snapshot()["downloadRunning"]:
            self.send_json({"ok": False, "error": "Data downloader already running"}, status=409)
            return
        config = load_config()
        batch_size = int(payload.get("batchSize", config.get("default_download_batch_size", 5)))
        continuous = bool(payload.get("continuous", True))
        DOWNLOAD_THREAD = threading.Thread(target=run_download_queue, args=(batch_size, continuous), daemon=True)
        DOWNLOAD_THREAD.start()
        self.send_json({"ok": True})

    def stop_downloads(self, _payload: dict[str, Any]) -> None:
        WORKERS.download_stop.set()
        WORKERS.set_download(current="Stopping after current download")
        self.send_json({"ok": True})

    def rescan(self, payload: dict[str, Any]) -> None:
        folders = scan_and_store()
        self.send_json({"folders": folders[: int(payload.get("limit", 500))]})

    def approve_domain(self, payload: dict[str, Any]) -> None:
        domain = str(payload.get("domain", "")).strip().lower()
        if not domain:
            self.send_json({"error": "Missing domain"}, status=400)
            return
        DB.update_candidate_domain(domain, "approved")
        DB.add_event("domains", "info", f"Approved domain: {domain}")
        self.send_json({"ok": True})

    def reject_domain(self, payload: dict[str, Any]) -> None:
        domain = str(payload.get("domain", "")).strip().lower()
        if not domain:
            self.send_json({"error": "Missing domain"}, status=400)
            return
        DB.update_candidate_domain(domain, "rejected")
        DB.add_event("domains", "info", f"Rejected domain: {domain}")
        self.send_json({"ok": True})

    def translate_path(self, path: str) -> str:
        parsed = urllib.parse.urlparse(path)
        rel = urllib.parse.unquote(parsed.path).lstrip("/")
        if not rel:
            rel = "index.html"
        target = (STATIC_DIR / rel).resolve()
        if STATIC_DIR.resolve() not in target.parents and target != STATIC_DIR.resolve():
            return str((STATIC_DIR / "index.html").resolve())
        return str(target)

    def send_json(self, data: Any, status: int = 200) -> None:
        raw = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        try:
            self.wfile.write(raw)
        except (BrokenPipeError, ConnectionAbortedError):
            return

    def end_headers(self) -> None:
        if self.path.endswith(".css"):
            self.send_header("Content-Type", "text/css")
        elif self.path.endswith(".js"):
            self.send_header("Content-Type", "application/javascript")
        super().end_headers()


def main() -> None:
    ensure_initial_index()
    port = int(os.environ.get("PASHTO_COLLECTOR_PORT", "8765"))
    mimetypes.add_type("text/css", ".css")
    mimetypes.add_type("application/javascript", ".js")
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"Pashto Poetry Collector running at http://127.0.0.1:{port}")
    print(f"Project root: {ROOT_DIR}")
    server.serve_forever()


if __name__ == "__main__":
    main()
