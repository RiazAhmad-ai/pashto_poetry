from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class CollectorDatabase:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.init_schema()

    def init_schema(self) -> None:
        with self.lock, self.conn:
            self.conn.executescript(
                """
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS folders (
                    path TEXT PRIMARY KEY,
                    kind TEXT NOT NULL,
                    terms_json TEXT NOT NULL,
                    query TEXT NOT NULL,
                    queries_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS links (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    link_key TEXT NOT NULL UNIQUE,
                    source TEXT NOT NULL,
                    source_id TEXT,
                    title TEXT NOT NULL,
                    page_url TEXT NOT NULL,
                    download_url TEXT,
                    kind TEXT NOT NULL,
                    folder TEXT NOT NULL,
                    query TEXT NOT NULL,
                    status TEXT NOT NULL,
                    reason TEXT,
                    saved_path TEXT,
                    bytes INTEGER NOT NULL DEFAULT 0,
                    downloaded_bytes INTEGER NOT NULL DEFAULT 0,
                    total_bytes INTEGER NOT NULL DEFAULT 0,
                    error TEXT,
                    metadata_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_links_status ON links(status);
                CREATE INDEX IF NOT EXISTS idx_links_folder ON links(folder);
                CREATE INDEX IF NOT EXISTS idx_links_kind ON links(kind);
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    phase TEXT NOT NULL,
                    level TEXT NOT NULL,
                    message TEXT NOT NULL,
                    folder TEXT,
                    query TEXT,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS candidate_domains (
                    domain TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    first_source TEXT NOT NULL,
                    sample_url TEXT NOT NULL,
                    sample_title TEXT NOT NULL,
                    link_count INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                """
            )
            self._ensure_column("links", "saved_path", "TEXT")
            self._ensure_column("links", "bytes", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_column("links", "downloaded_bytes", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_column("links", "total_bytes", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_column("links", "error", "TEXT")

    def _ensure_column(self, table: str, column: str, definition: str) -> None:
        columns = {row["name"] for row in self.conn.execute(f"PRAGMA table_info({table})").fetchall()}
        if column not in columns:
            self.conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    def set_setting(self, key: str, value: Any) -> None:
        raw = json.dumps(value, ensure_ascii=False)
        with self.lock, self.conn:
            self.conn.execute(
                """
                INSERT INTO settings (key, value, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
                """,
                (key, raw, utc_now()),
            )

    def get_setting(self, key: str, default: Any = None) -> Any:
        with self.lock:
            row = self.conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        if not row:
            return default
        try:
            return json.loads(row["value"])
        except json.JSONDecodeError:
            return default

    def add_event(self, phase: str, level: str, message: str, folder: str = "", query: str = "") -> None:
        with self.lock, self.conn:
            self.conn.execute(
                "INSERT INTO events (phase, level, message, folder, query, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (phase, level, message, folder, query, utc_now()),
            )

    def upsert_folders(self, folders: list[dict[str, Any]]) -> None:
        now = utc_now()
        rows = [
            (
                item["path"],
                item["kind"],
                json.dumps(item.get("terms", []), ensure_ascii=False),
                item.get("query", ""),
                json.dumps(item.get("queries", []), ensure_ascii=False),
                now,
            )
            for item in folders
        ]
        with self.lock, self.conn:
            self.conn.executemany(
                """
                INSERT INTO folders (path, kind, terms_json, query, queries_json, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(path) DO UPDATE SET
                    kind = excluded.kind,
                    terms_json = excluded.terms_json,
                    query = excluded.query,
                    queries_json = excluded.queries_json,
                    updated_at = excluded.updated_at
                """,
                rows,
            )

    def list_folders(self, limit: int = 500) -> list[dict[str, Any]]:
        with self.lock:
            rows = self.conn.execute(
                "SELECT path, kind, terms_json, query, queries_json FROM folders ORDER BY kind = 'other', path LIMIT ?",
                (limit,),
            ).fetchall()
        return [self._folder_row(row) for row in rows]

    def folder_count(self) -> int:
        with self.lock:
            row = self.conn.execute("SELECT COUNT(*) AS count FROM folders").fetchone()
        return int(row["count"] if row else 0)

    def add_link(self, item: dict[str, Any]) -> tuple[int, bool]:
        now = utc_now()
        key = self._link_key(item)
        metadata = json.dumps(item.get("metadata", {}), ensure_ascii=False)
        values = (
            key,
            item["source"],
            item.get("source_id", ""),
            item.get("title") or item.get("source_id") or "Untitled",
            item["page_url"],
            item.get("download_url") or "",
            item["kind"],
            item["folder"],
            item.get("query", ""),
            item.get("status", "link_found"),
            item.get("reason", ""),
            item.get("saved_path", ""),
            int(item.get("bytes", 0) or 0),
            int(item.get("downloaded_bytes", 0) or 0),
            int(item.get("total_bytes", 0) or 0),
            item.get("error", ""),
            metadata,
            now,
            now,
        )
        with self.lock, self.conn:
            try:
                cursor = self.conn.execute(
                    """
                    INSERT INTO links (
                        link_key, source, source_id, title, page_url, download_url, kind, folder,
                        query, status, reason, saved_path, bytes, downloaded_bytes, total_bytes, error, metadata_json, created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    values,
                )
                return int(cursor.lastrowid), True
            except sqlite3.IntegrityError:
                row = self.conn.execute("SELECT id FROM links WHERE link_key = ?", (key,)).fetchone()
                return int(row["id"]), False

    def upsert_candidate_domain(self, domain: str, source: str, sample_url: str, sample_title: str) -> None:
        if not domain:
            return
        now = utc_now()
        with self.lock, self.conn:
            self.conn.execute(
                """
                INSERT INTO candidate_domains (
                    domain, status, first_source, sample_url, sample_title, link_count, created_at, updated_at
                )
                VALUES (?, 'candidate', ?, ?, ?, 1, ?, ?)
                ON CONFLICT(domain) DO UPDATE SET
                    link_count = candidate_domains.link_count + 1,
                    sample_url = excluded.sample_url,
                    sample_title = excluded.sample_title,
                    updated_at = excluded.updated_at
                """,
                (domain, source, sample_url, sample_title, now, now),
            )

    def update_candidate_domain(self, domain: str, status: str) -> None:
        with self.lock, self.conn:
            self.conn.execute(
                "UPDATE candidate_domains SET status = ?, updated_at = ? WHERE domain = ?",
                (status, utc_now(), domain),
            )

    def list_candidate_domains(self, limit: int = 100, status: str | None = None) -> list[dict[str, Any]]:
        if status:
            sql = "SELECT * FROM candidate_domains WHERE status = ? ORDER BY link_count DESC, updated_at DESC LIMIT ?"
            params: tuple[Any, ...] = (status, limit)
        else:
            sql = "SELECT * FROM candidate_domains ORDER BY status = 'approved' DESC, link_count DESC, updated_at DESC LIMIT ?"
            params = (limit,)
        with self.lock:
            rows = self.conn.execute(sql, params).fetchall()
        return [dict(row) for row in rows]

    def approved_candidate_sites(self) -> list[dict[str, str]]:
        with self.lock:
            rows = self.conn.execute(
                "SELECT domain, sample_url FROM candidate_domains WHERE status = 'approved' ORDER BY domain"
            ).fetchall()
        return [{"name": f"Approved {row['domain']}", "url": row["sample_url"]} for row in rows]

    def next_download_links(self, limit: int) -> list[dict[str, Any]]:
        with self.lock:
            rows = self.conn.execute(
                """
                SELECT * FROM links
                WHERE status IN ('link_found', 'download_failed')
                ORDER BY updated_at ASC, id ASC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [self._link_row(row) for row in rows]

    def update_link(self, link_id: int, **updates: Any) -> None:
        if not updates:
            return
        updates["updated_at"] = utc_now()
        parts = [f"{key} = ?" for key in updates]
        values = list(updates.values())
        values.append(link_id)
        with self.lock, self.conn:
            self.conn.execute(f"UPDATE links SET {', '.join(parts)} WHERE id = ?", values)

    def reset_interrupted_downloads(self) -> None:
        with self.lock, self.conn:
            self.conn.execute(
                """
                UPDATE links
                SET status = 'link_found',
                    reason = 'Recovered from interrupted download state',
                    downloaded_bytes = 0,
                    total_bytes = 0,
                    error = '',
                    updated_at = ?
                WHERE status = 'downloading'
                """,
                (utc_now(),),
            )

    def link_counts_by_status(self) -> dict[str, int]:
        with self.lock:
            rows = self.conn.execute("SELECT status, COUNT(*) AS count FROM links GROUP BY status").fetchall()
        return {row["status"]: int(row["count"]) for row in rows}

    def link_counts_by_source(self) -> dict[str, int]:
        with self.lock:
            rows = self.conn.execute("SELECT source, COUNT(*) AS count FROM links GROUP BY source").fetchall()
        return {row["source"]: int(row["count"]) for row in rows}

    def link_counts_by_kind(self) -> dict[str, int]:
        with self.lock:
            rows = self.conn.execute("SELECT kind, COUNT(*) AS count FROM links GROUP BY kind").fetchall()
        return {row["kind"]: int(row["count"]) for row in rows}

    def link_counts_by_domain(self, limit: int = 25) -> list[dict[str, Any]]:
        with self.lock:
            rows = self.conn.execute(
                "SELECT page_url FROM links WHERE page_url LIKE 'http%'"
            ).fetchall()
        counts: dict[str, int] = {}
        for row in rows:
            domain = urllib.parse.urlparse(row["page_url"]).netloc.lower()
            if domain.startswith("www."):
                domain = domain[4:]
            if domain:
                counts[domain] = counts.get(domain, 0) + 1
        return [
            {"domain": domain, "count": count}
            for domain, count in sorted(counts.items(), key=lambda item: item[1], reverse=True)[:limit]
        ]

    def recent_links(self, limit: int = 100) -> list[dict[str, Any]]:
        with self.lock:
            rows = self.conn.execute("SELECT * FROM links ORDER BY updated_at DESC, id DESC LIMIT ?", (limit,)).fetchall()
        return [self._link_row(row) for row in rows]

    def links_by_status(self, statuses: list[str], limit: int = 100) -> list[dict[str, Any]]:
        if not statuses:
            return []
        placeholders = ", ".join("?" for _status in statuses)
        with self.lock:
            rows = self.conn.execute(
                f"SELECT * FROM links WHERE status IN ({placeholders}) ORDER BY updated_at DESC, id DESC LIMIT ?",
                (*statuses, limit),
            ).fetchall()
        return [self._link_row(row) for row in rows]

    def recent_events(self, limit: int = 100) -> list[dict[str, Any]]:
        with self.lock:
            rows = self.conn.execute("SELECT * FROM events ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(row) for row in rows]

    def _folder_row(self, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "path": row["path"],
            "kind": row["kind"],
            "terms": json.loads(row["terms_json"]),
            "query": row["query"],
            "queries": json.loads(row["queries_json"]),
        }

    def _link_row(self, row: sqlite3.Row) -> dict[str, Any]:
        item = dict(row)
        item["metadata"] = json.loads(item.pop("metadata_json") or "{}")
        return item

    def _link_key(self, item: dict[str, Any]) -> str:
        raw = "|".join(
            [
                item.get("source", ""),
                item.get("folder", ""),
                item.get("kind", ""),
                item.get("source_id", ""),
                item.get("page_url", ""),
                item.get("download_url") or "",
            ]
        )
        return hashlib.sha256(raw.encode("utf-8", errors="replace")).hexdigest()
