"""Public contract, full mock assessment and task cancellation regressions."""

import json
import sys
import tempfile
import time
from pathlib import Path
from threading import Event
from unittest.mock import patch
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fastapi.testclient import TestClient
from app.config import Settings
from app.main import create_app
from app.documents import build_document_tree_from_pdf
from app.review.engine import NegativeChecklistReviewer, MockReviewer
from app.schemas import ReviewRequest
from app.model_client import ModelClient

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


class CompatibilityTest(unittest.TestCase):
    def test_openapi_contract(self):
        with tempfile.TemporaryDirectory() as directory:
            app = create_app(Settings(data_dir=Path(directory)))
            self.assertEqual(
                app.openapi(),
                json.loads((FIXTURES / "expected_openapi.json").read_text()),
            )
            app.state.service.worker.shutdown()

    def test_assessment_contract(self):
        p = FIXTURES / "cross_page.pdf"
        tree = build_document_tree_from_pdf(p, p.name)
        result = NegativeChecklistReviewer().assess(
            ReviewRequest(document_ids=["sample"], model_mode="mock"), [], [], tree=tree
        )
        self.assertEqual(
            result.model_dump(),
            json.loads((FIXTURES / "expected_assessment.json").read_text()),
        )

    def test_cancel_after_reviewer_started(self):
        entered, release = Event(), Event()
        original = MockReviewer.assess

        def delayed(*args, **kwargs):
            entered.set()
            if not release.wait(5):
                raise TimeoutError("test reviewer release missing")
            return original(*args, **kwargs)

        with tempfile.TemporaryDirectory() as directory:
            app = create_app(Settings(data_dir=Path(directory)))
            with TestClient(app) as client, patch.object(
                MockReviewer, "assess", delayed
            ):
                doc = client.post(
                    "/api/v1/documents/text", json={"text": "第一章 绪论\n正文说明。"}
                ).json()
                job = client.post(
                    "/api/v1/jobs",
                    json={"document_ids": [doc["id"]], "model_mode": "mock"},
                ).json()["id"]
                try:
                    self.assertTrue(entered.wait(5))
                    self.assertEqual(
                        client.post(f"/api/v1/jobs/{job}/cancel").json()["status"],
                        "cancelled",
                    )
                finally:
                    release.set()
                    app.state.service.worker.shutdown(wait=True)
                self.assertEqual(
                    client.get(f"/api/v1/jobs/{job}").json()["status"], "cancelled"
                )
                self.assertEqual(
                    client.get(f"/api/v1/jobs/{job}/report").status_code, 409
                )
                self.assertFalse(
                    (Path(directory) / "jobs" / job / "report.json").exists()
                )

    def test_trace_and_no_cloud_fallback_on_model_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            client = ModelClient(
                Settings(
                    data_dir=Path(directory),
                    model_url="http://127.0.0.1:9/v1",
                    model_name="fixture",
                )
            )
            client.trace_dir = Path(directory) / "calls"
            with patch(
                "app.model_client.urlopen", side_effect=TimeoutError("fixture timeout")
            ) as call:
                result, error = client.call("原文测试", "local")
            self.assertIsNone(result)
            self.assertIn("fixture timeout", error)
            self.assertEqual(call.call_count, 1)
            record = json.loads(next(client.trace_dir.glob("*.json")).read_text())
            self.assertEqual(record["prompt"], "原文测试")
            self.assertEqual(record["error"], error)

    def test_resource_errors_search_approval_and_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            settings = Settings(data_dir=Path(directory))
            app = create_app(settings)
            with TestClient(app) as client:
                self.assertEqual(client.get("/api/v1/jobs/not-an-id").status_code, 400)
                self.assertEqual(
                    client.get("/api/v1/jobs/job_" + "a" * 32).status_code, 404
                )
                with patch("app.api.search.search_public") as search:
                    self.assertEqual(
                        client.post(
                            "/api/v1/search",
                            json={"query": "Public title", "approved": False},
                        ).status_code,
                        403,
                    )
                    search.assert_not_called()
                with patch("app.api.search.search_public", return_value=[]):
                    self.assertEqual(
                        client.post(
                            "/api/v1/search",
                            json={"query": "Public title", "approved": True},
                        ).status_code,
                        200,
                    )
                self.assertEqual(
                    len(list((Path(directory) / "searches").glob("*.json"))), 1
                )
                job = "job_" + "b" * 32
                app.state.store.write(
                    app.state.store.folder("jobs", job),
                    "state.json",
                    {"id": job, "status": "running", "created_at": "2026-11-16"},
                )
            other = create_app(settings)
            self.assertEqual(other.state.store.jobs()[0]["status"], "interrupted")
            other.state.service.worker.shutdown()

    def test_image_is_not_claimed_as_reviewed(self):
        with tempfile.TemporaryDirectory() as directory:
            app = create_app(Settings(data_dir=Path(directory)))
            with TestClient(app) as client:
                doc = client.post(
                    "/api/v1/documents", files={"file": ("scan.png", b"fixture")}
                ).json()
                job = client.post(
                    "/api/v1/jobs",
                    json={"document_ids": [doc["id"]], "model_mode": "mock"},
                ).json()["id"]
                app.state.service.worker.shutdown(wait=True)
                self.assertEqual(
                    client.get(f"/api/v1/jobs/{job}").json()["status"], "failed"
                )
                self.assertEqual(
                    client.get(f"/api/v1/jobs/{job}/report").status_code, 409
                )

    def test_graph_cloud_tracing_disabled(self):
        import os
        from langsmith.utils import tracing_is_enabled

        observed = []
        original = MockReviewer.assess

        def assess(*args, **kwargs):
            observed.append(tracing_is_enabled())
            return original(*args, **kwargs)

        with tempfile.TemporaryDirectory() as directory:
            app = create_app(Settings(data_dir=Path(directory)))
            with TestClient(app) as client, patch.dict(
                os.environ, {"LANGSMITH_TRACING": "true"}
            ), patch.object(MockReviewer, "assess", assess):
                doc = client.post(
                    "/api/v1/documents/text",
                    json={"text": "第一章 绪论\n本章研究测试方法。"},
                ).json()
                client.post(
                    "/api/v1/jobs",
                    json={"document_ids": [doc["id"]], "model_mode": "mock"},
                )
                app.state.service.worker.shutdown(wait=True)
        self.assertEqual(observed, [False])


if __name__ == "__main__":
    unittest.main()
