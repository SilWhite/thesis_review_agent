"""Read-only workbench history includes both legacy and supplemental tasks."""

import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient
from app.config import Settings
from app.main import create_app
from app.storage import new_id


class WorkspaceTests(unittest.TestCase):
    def test_group_all_tasks_without_rewriting_originals(self):
        with tempfile.TemporaryDirectory() as directory:
            settings = Settings(data_dir=Path(directory))
            app = create_app(settings)
            with TestClient(app) as client:
                self.assertEqual(client.get("/api/v1/workspace/tasks").json(), [])
                store = app.state.store
                papers = [
                    store.save_document(name, b"paper")
                    for name in ["one.txt", "two.txt"]
                ]
                entries = [
                    (
                        "jobs",
                        "job",
                        {"document_ids": [p["id"] for p in papers]},
                        "completed",
                        "2026-11-14",
                        ["review"],
                    ),
                    (
                        "audits",
                        "audit",
                        {
                            "document_id": papers[0]["id"],
                            "public_queries": ["public"],
                            "experiments": [],
                        },
                        "partial",
                        "2026-11-15",
                        ["novelty"],
                    ),
                    (
                        "audits",
                        "audit",
                        {
                            "document_id": papers[0]["id"],
                            "public_queries": [],
                            "experiments": [{"id": "E01"}],
                        },
                        "failed",
                        "2026-11-16",
                        ["experiments"],
                    ),
                    (
                        "audits",
                        "audit",
                        {
                            "document_id": papers[1]["id"],
                            "public_queries": ["public"],
                            "experiments": [{"id": "E01"}],
                        },
                        "cancelled",
                        "2026-11-17",
                        ["novelty", "experiments"],
                    ),
                ]
                originals, expected = {}, {}
                for folder, prefix, request, status, timestamp, checks in entries:
                    identifier = new_id(prefix)
                    path = store.folder(folder, identifier)
                    state = dict(
                        id=identifier,
                        status=status,
                        created_at=timestamp,
                        updated_at=timestamp,
                        stage="reporting",
                        error=None,
                    )
                    store.write(path, "request.json", request)
                    store.write(path, "state.json", state)
                    for file in path.iterdir():
                        originals[file] = file.read_bytes()
                    expected[identifier] = checks
                result = client.get("/api/v1/workspace/tasks")
                self.assertEqual(result.status_code, 200, result.text)
                groups = result.json()
                self.assertEqual([g["title"] for g in groups], ["two.txt", "one.txt"])
                tasks = [task for group in groups for task in group["tasks"]]
                self.assertEqual(len(tasks), 4)
                self.assertEqual({t["id"]: t["checks"] for t in tasks}, expected)
                self.assertEqual(groups[1]["tasks"][0]["checks"], ["experiments"])
                self.assertEqual(len(groups[1]["tasks"][-1]["document_ids"]), 2)
                for file, content in originals.items():
                    self.assertEqual(file.read_bytes(), content)
                self.assertEqual(client.get("/").content, client.get("/audit").content)
                self.assertFalse((Path(directory) / "workspace").exists())
            # A new process can reconstruct the same view without browser-local state.
            other = create_app(settings)
            with TestClient(other) as client:
                self.assertEqual(client.get("/api/v1/workspace/tasks").json(), groups)


if __name__ == "__main__":
    unittest.main()
