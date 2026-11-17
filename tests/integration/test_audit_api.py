"""Optional endpoints, queue sharing, privacy, restart and cancellation."""

import tempfile
import unittest
from pathlib import Path
from threading import Event
from unittest.mock import patch

from fastapi.testclient import TestClient
from app.config import Settings
from app.main import create_app


class AuditAPITests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.settings = Settings(data_dir=Path(self.directory.name))
        self.app = create_app(self.settings)
        self.client = TestClient(self.app)
        self.client.__enter__()
        self.addCleanup(self.client.__exit__, None, None, None)
        self.doc = self.client.post(
            "/api/v1/documents/text",
            json={"text": "训练集共3条，测试集共2条，训练100轮。提出方法B。"},
        ).json()["id"]

    def payload(self, ids=()):
        return dict(
            document_id=self.doc,
            model_mode="mock",
            experiments=[
                dict(
                    id="E01",
                    name="主实验",
                    paper_quote="训练集共3条，测试集共2条，训练100轮。",
                    material_ids=list(ids),
                )
            ],
        )

    def upload(self, name, data, **fields):
        response = self.client.post(
            "/api/v1/audit-materials", files={"file": (name, data)}, data=fields
        )
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()["id"]

    def test_complete_mock_local_artifacts_and_old_contract(self):
        self.assertIs(
            self.app.state.audit_service.worker, self.app.state.service.worker
        )
        train = self.upload(
            "train.csv", b"id,y\na,0\nb,1\n", role="data", split="train", id_column="id"
        )
        test = self.upload(
            "test.csv", b"id,y\nb,1\nc,0\n", role="data", split="test", id_column="id"
        )
        cfg = self.upload("run.yaml", b"epochs: 50", role="config")
        self.assertEqual(
            self.client.get(f"/api/v1/audit-materials/{cfg}/content").content,
            b"epochs: 50",
        )
        response = self.client.post(
            "/api/v1/audits", json=self.payload([train, test, cfg])
        )
        self.assertEqual(response.status_code, 202)
        identifier = response.json()["id"]
        self.app.state.service.worker.shutdown(wait=True)
        self.assertEqual(
            self.client.get(f"/api/v1/audits/{identifier}").json()["status"], "partial"
        )
        report = self.client.get(f"/api/v1/audits/{identifier}/report").json()
        findings = report["experiments"][0]["findings"]
        self.assertEqual(len(findings), 3)
        self.assertTrue(all(e["filename"] for f in findings for e in f["evidence"]))
        self.assertEqual(report["novelty"]["status"], "未启用")
        self.assertNotIn("rule_matrix", report)
        self.assertEqual(self.client.get("/api/v1/jobs").json(), [])
        self.assertEqual(
            self.client.get(f"/api/v1/audits/{identifier}/download").status_code, 200
        )
        folder = Path(self.directory.name) / "audits" / identifier
        self.assertEqual(
            {p.name for p in folder.iterdir()},
            {"request.json", "state.json", "report.json", "report.md"},
        )
        self.assertEqual(self.client.get("/audit").status_code, 200)

    def test_approval_validation_and_only_explicit_query_leaves(self):
        payload = dict(
            document_id=self.doc, model_mode="mock", public_queries=["public topic"]
        )
        with patch("app.audit.novelty.search_items") as search:
            self.assertEqual(
                self.client.post("/api/v1/audits", json=payload).status_code, 403
            )
            search.assert_not_called()
        with patch("app.audit.novelty.search_items", return_value=[]) as search:
            response = self.client.post(
                "/api/v1/audits", json=dict(payload, search_approved=True)
            )
            self.assertEqual(response.status_code, 202)
            self.app.state.service.worker.shutdown(wait=True)
            search.assert_called_once_with("public topic")
            report = self.client.get(
                f"/api/v1/audits/{response.json()['id']}/report"
            ).json()
            self.assertEqual(report["novelty"]["status"], "信息不足")
        self.assertEqual(
            self.client.post(
                "/api/v1/audits", json=dict(payload, literature_cutoff="2024-99-01")
            ).status_code,
            422,
        )

    def test_cancel_in_flight_does_not_publish(self):
        material = self.upload("code.py", b"epochs = 50", role="code")
        entered, release = Event(), Event()

        def delayed(*args):
            entered.set()
            if not release.wait(5):
                raise TimeoutError("test release missing")
            return [], []

        with patch("app.audit.service.semantic_review", delayed):
            identifier = self.client.post(
                "/api/v1/audits", json=self.payload([material])
            ).json()["id"]
            try:
                self.assertTrue(entered.wait(5))
                self.assertEqual(
                    self.client.post(f"/api/v1/audits/{identifier}/cancel").json()[
                        "status"
                    ],
                    "cancelled",
                )
            finally:
                release.set()
                self.app.state.service.worker.shutdown(wait=True)
        self.assertEqual(
            self.client.get(f"/api/v1/audits/{identifier}/report").status_code, 409
        )
        self.assertFalse(
            (Path(self.directory.name) / "audits" / identifier / "report.json").exists()
        )

    def test_bad_binding_fails_no_invented_report_and_restart(self):
        payload = self.payload()
        payload["experiments"][0]["paper_quote"] = "不存在的原文"
        identifier = self.client.post("/api/v1/audits", json=payload).json()["id"]
        self.app.state.service.worker.shutdown(wait=True)
        self.assertEqual(
            self.client.get(f"/api/v1/audits/{identifier}").json()["status"], "failed"
        )
        self.assertEqual(
            self.client.get(f"/api/v1/audits/{identifier}/report").status_code, 409
        )
        state = self.app.state.audit_service.state(identifier)
        state["status"] = "running"
        self.app.state.store.write(
            Path(self.directory.name) / "audits" / identifier, "state.json", state
        )
        other = create_app(self.settings)
        try:
            self.assertEqual(
                other.state.audit_service.state(identifier)["status"], "interrupted"
            )
        finally:
            other.state.service.worker.shutdown()

    def test_search_and_model_failure_are_not_clean_bill(self):
        payload = dict(
            document_id=self.doc,
            model_mode="mock",
            public_queries=["public topic"],
            search_approved=True,
        )
        with patch(
            "app.audit.novelty.search_items", side_effect=TimeoutError("fixture")
        ):
            identifier = self.client.post("/api/v1/audits", json=payload).json()["id"]
            self.app.state.service.worker.shutdown(wait=True)
        self.assertEqual(
            self.client.get(f"/api/v1/audits/{identifier}").json()["status"], "partial"
        )
        report = self.client.get(f"/api/v1/audits/{identifier}/report").json()
        self.assertEqual(report["novelty"]["sources"], [])
        self.assertTrue(any("失败" in n for n in report["novelty"]["notes"]))

    def test_local_transport_traces_and_grounded_novelty(self):
        import io
        import json
        from langsmith.utils import tracing_is_enabled

        self.settings = Settings(
            data_dir=Path(self.directory.name),
            model_url="http://internal-model/v1",
            model_name="internal",
        )
        self.app.state.audit_service.settings = self.settings
        material = self.upload("metrics.json", b'{"accuracy": 0.9}', role="result")
        payload = self.payload([material])
        payload.update(public_queries=["approved keyword"], search_approved=True)
        # API settings were configured before startup, so use the service for transport testing.
        from app.audit.schemas import AuditRequest

        sent, tracing = [], []

        def reply(request, timeout):
            sent.append(json.loads(request.data))
            tracing.append(tracing_is_enabled())
            records = (
                []
                if len(sent) == 1
                else [
                    dict(
                        source_id="lit_1",
                        paper_quote="提出方法B。",
                        source_quote="Uses method A.",
                        judgment="创新差异尚不清楚",
                        difference="需要解释方法区别。",
                    )
                ]
            )
            return io.BytesIO(
                json.dumps(
                    {
                        "choices": [
                            {"message": {"content": json.dumps({"findings": records})}}
                        ]
                    }
                ).encode()
            )

        items = [dict(DOI="10.1/example", title=["Example"], abstract="Uses method A.")]
        with patch("app.audit.novelty.search_items", return_value=items), patch(
            "app.model_client.urlopen", side_effect=reply
        ):
            identifier = self.app.state.audit_service.submit(
                AuditRequest(**dict(payload, model_mode="local"))
            )["id"]
            self.app.state.service.worker.shutdown(wait=True)
        report = self.client.get(f"/api/v1/audits/{identifier}/report").json()
        self.assertEqual(report["novelty"]["status"], "创新差异尚不清楚")
        self.assertEqual(len(sent), 2)
        self.assertEqual(tracing, [False, False])
        traces = sorted(
            (Path(self.directory.name) / "audits" / identifier / "traces").glob(
                "*.json"
            )
        )
        self.assertEqual([p.name for p in traces], ["0001.json", "0002.json"])
        self.assertTrue(all(json.loads(p.read_text())["error"] is None for p in traces))


if __name__ == "__main__":
    unittest.main()
