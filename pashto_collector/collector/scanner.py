from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from collector.queries import build_queries, infer_kind, topic_terms


def scan_folders(root_dir: Path, config: dict[str, Any]) -> list[dict[str, Any]]:
    skip = {name.lower() for name in config.get("skip_directory_names", [])}
    folders: list[dict[str, Any]] = []
    for dirpath, dirnames, _filenames in os.walk(root_dir):
        dirnames[:] = [name for name in dirnames if name.lower() not in skip and not name.startswith(".")]
        path = Path(dirpath)
        if path == root_dir:
            continue
        kind = infer_kind(path, root_dir)
        rel = path.relative_to(root_dir).as_posix()
        terms = topic_terms(path, root_dir)
        folders.append(
            {
                "path": rel,
                "kind": kind,
                "terms": terms,
                "query": build_queries(path, root_dir, kind, config)[0],
                "queries": build_queries(path, root_dir, kind, config),
            }
        )
    folders.sort(key=lambda item: (item["kind"] == "other", item["path"]))
    return folders
