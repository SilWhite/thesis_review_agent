"""Small file repository. One server process; JSON updates use atomic replace."""

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from uuid import uuid4


def now():
    return datetime.now(timezone.utc).isoformat()


def new_id(prefix):
    return f"{prefix}_{uuid4().hex}"


class Store:
    def __init__(self, root: Path):
        self.root = root
        self.lock = RLock()
        for folder in ("documents", "jobs", "searches"):
            (root / folder).mkdir(parents=True, exist_ok=True)

    def folder(self, kind, identifier):
        if not re.fullmatch(r"[a-z]+_[0-9a-f]{32}", identifier):
            raise ValueError("无效的资源 ID")
        return self.root / kind / identifier

    def write(self, folder, name, value):
        with self.lock:
            folder.mkdir(parents=True, exist_ok=True)
            target = folder / name
            temp = folder / (name + ".tmp")
            temp.write_text(
                json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            temp.replace(target)

    def read(self, folder, name):
        return json.loads((folder / name).read_text(encoding="utf-8"))

    def documents(self):
        return sorted(
            (
                self.read(p.parent, p.name)
                for p in (self.root / "documents").glob("*/document.json")
            ),
            key=lambda d: d["created_at"],
            reverse=True,
        )

    def save_document(self, filename, content, role="primary"):
        identifier = new_id("doc")
        folder = self.folder("documents", identifier)
        folder.mkdir()
        suffix = Path(filename).suffix.lower()
        (folder / ("source" + suffix)).write_bytes(content)
        document = dict(
            id=identifier,
            filename=Path(filename).name,
            suffix=suffix,
            role=role,
            size_bytes=len(content),
            sha256=hashlib.sha256(content).hexdigest(),
            created_at=now(),
        )
        self.write(folder, "document.json", document)
        return document

    def jobs(self):
        return sorted(
            (
                self.read(p.parent, p.name)
                for p in (self.root / "jobs").glob("*/state.json")
            ),
            key=lambda j: j["created_at"],
            reverse=True,
        )

    def update_job(self, identifier, **changes):
        with self.lock:
            folder = self.folder("jobs", identifier)
            state = self.read(folder, "state.json")
            state.update(changes, updated_at=now())
            self.write(folder, "state.json", state)
            return state
