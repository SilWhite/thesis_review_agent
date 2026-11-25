"""Repository snapshots, no submitted-code execution and no literature network."""

import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient
from app.main import create_app
from app.config import Settings
from app.audit.schemas import RepositoryInput
from app.audit.repository import prepare
from app.audit.code_review import compare_claim
from app.audit.statistics import review


class RepositoryTests(unittest.TestCase):
    def test_local_pipeline_snapshot_no_network_and_no_execution(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "repo"
            root.mkdir()
            subprocess.run(["git", "init", str(root)], check=True, capture_output=True)
            (root / "train.py").write_text(
                "epochs = 50\nraise RuntimeError('DO NOT RUN')\n"
            )
            (root / "README.md").write_text("Run python train.py with config.yaml")
            (root / "config.yaml").write_text("epochs: 50")
            subprocess.run(["git", "-C", str(root), "add", "."], check=True)
            subprocess.run(
                [
                    "git",
                    "-C",
                    str(root),
                    "-c",
                    "user.name=test",
                    "-c",
                    "user.email=test@example.com",
                    "commit",
                    "-m",
                    "fixture",
                ],
                check=True,
                capture_output=True,
            )
            (root / "secret.txt").symlink_to(Path(tmp) / "missing")
            app = create_app(
                Settings(
                    data_dir=Path(tmp) / "data",
                    model_url="http://internal/v1",
                    model_name="test",
                )
            )

            def call(client, prompt, mode):
                if "从论文材料提取" in prompt:
                    batch = json.loads(prompt[prompt.index('[{"id"') :])
                    return {
                        "findings": [
                            dict(
                                kind="implementation",
                                source_id=batch[0]["id"],
                                quote="训练100轮",
                                claim="训练100轮",
                                experiment="E1",
                            )
                        ]
                    }, None
                payload = json.loads(prompt[prompt.index('{"claim"') :])
                source = next(
                    (s for s in payload["code"] if "epochs = 50" in s["text"]), None
                )
                if payload["claim"]["kind"] != "implementation":
                    return {"findings": []}, None
                return {
                    "findings": [
                        dict(
                            issue="训练轮数与配置存在差异。",
                            suggestion="核对实际入口和覆盖关系。",
                            evidence=[
                                dict(source_id=source["id"], quote="epochs = 50")
                            ],
                        )
                    ]
                }, None

            with TestClient(app) as client, patch(
                "app.model_client.ModelClient.call", call
            ), patch("app.audit.novelty.retrieve") as network, patch(
                "app.audit.service.audit_citations"
            ) as citations:
                doc = client.post(
                    "/api/v1/documents/text",
                    json={
                        "text": "训练100轮。准确率为120%。最小值为0，最大值为1，均值为2。"
                    },
                ).json()["id"]
                body = dict(
                    document_id=doc,
                    check_experiments=True,
                    repository=dict(kind="local", location=str(root)),
                )
                result = client.post("/api/v1/audits", json=body)
                self.assertEqual(result.status_code, 202, result.text)
                identifier = result.json()["id"]
                app.state.service.worker.shutdown(wait=True)
                report = client.get(f"/api/v1/audits/{identifier}/report")
                self.assertEqual(report.status_code, 200, report.text)
                experiment = report.json()["experiments"][0]
                self.assertTrue(
                    any(f["check"] == "implementation" for f in experiment["findings"])
                )
                self.assertEqual(
                    sum(
                        f["check"] == "statistical_bounds"
                        for f in experiment["findings"]
                    ),
                    2,
                )
                self.assertTrue(
                    any(
                        e.get("location") == "行 1"
                        for f in experiment["findings"]
                        for e in f["evidence"]
                    )
                )
                folder = Path(tmp) / "data" / "audits" / identifier / "repository"
                self.assertTrue((folder / "manifest.json").exists())
                self.assertFalse((folder / "files" / "secret.txt").exists())
                saved = (folder / "files" / "train.py").read_text()
                (root / "train.py").write_text("changed")
                self.assertEqual((folder / "files" / "train.py").read_text(), saved)
                network.assert_not_called()
                citations.assert_not_called()
                self.assertIn(
                    "experiments",
                    client.get("/api/v1/workspace/tasks").json()[0]["tasks"][0][
                        "checks"
                    ],
                )

    def test_evidence_gate_and_statistical_controls(self):
        from unittest.mock import Mock

        client = Mock()
        client.call.return_value = (
            {
                "findings": [
                    dict(
                        issue="问题",
                        suggestion="核查",
                        evidence=[dict(source_id="bad", quote="fake")],
                    )
                ]
            },
            None,
        )
        claim = dict(
            id="c1",
            kind="implementation",
            claim="test",
            evidence=dict(quote="训练100轮"),
        )
        findings, notes = compare_claim(client, "local", claim, [])
        self.assertEqual(findings, [])
        self.assertTrue(notes)
        self.assertEqual(
            review(
                [
                    dict(
                        id="b",
                        filename="p",
                        location="1",
                        text="准确率为95%。最小值为0，最大值为1，均值为0.5。",
                    )
                ]
            ),
            [],
        )

    def test_github_validation(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                prepare(
                    RepositoryInput(
                        kind="github", location="https://other.example/repo"
                    ),
                    Path(tmp),
                    lambda: None,
                )


if __name__ == "__main__":
    unittest.main()
