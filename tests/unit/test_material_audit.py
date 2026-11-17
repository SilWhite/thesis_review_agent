"""Controlled conflicts, valid alternatives, grounded output and metadata limits."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from app.audit.consistency import compare, paper_facts, semantic_review
from app.audit.materials import read_material, save_material
from app.audit.novelty import assess, retrieve
from app.storage import Store


class MaterialAuditTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.store = Store(Path(self.directory.name))

    def material(self, name, text, role, split="unknown", column=""):
        meta = save_material(self.store, name, text.encode(), role, split, column)
        return meta, read_material(self.store, meta["id"])

    def test_data_counts_and_overlap_without_fraud_claim(self):
        paper = dict(id="paper", text="训练集共3条，测试集共2条。", location="段落1")
        facts = paper_facts(paper)
        datasets = []
        for split, text in [
            ("train", "id,label\na,0\nb,1\n"),
            ("test", "id,label\nb,1\nc,0\n"),
        ]:
            meta, (_, extracted, _, ids) = self.material(
                split + ".csv", text, "data", split, "id"
            )
            facts.extend(extracted)
            datasets.append(dict(meta, ids=ids))
        findings, _ = compare(facts, datasets)
        self.assertEqual(
            {f["check"] for f in findings}, {"numeric_consistency", "split_overlap"}
        )
        self.assertTrue(all("核实" in f["status"] for f in findings))
        self.assertTrue(all(len(f["evidence"]) == 2 for f in findings))

    def test_configs_defaults_units_and_multiple_paper_values(self):
        paper = dict(
            id="paper", text="学习率为0.001，训练100轮，准确率为95%。", location="段落1"
        )
        facts = paper_facts(paper)
        _, (_, cfg, _, _) = self.material(
            "run.yaml", "learning_rate: 0.002\nepochs: 50\n", "config"
        )
        _, (_, metrics, _, _) = self.material(
            "metrics.json", '{"accuracy": 0.95}', "result"
        )
        findings, _ = compare(facts + cfg + metrics, [])
        self.assertEqual(len(findings), 2)
        self.assertTrue(all("配置覆盖" in f["suggestion"] for f in findings))
        # A matching effective CLI setting does not turn a default into a proven contradiction.
        _, (_, code, _, _) = self.material(
            "train.py", 'epochs = 50\nraise RuntimeError("never execute")', "code"
        )
        self.assertEqual(code[0]["value"], 50)
        facts += paper_facts(dict(id="p2", text="对照实验训练50轮。", location="段落2"))
        findings, notes = compare(facts + code, [])
        self.assertFalse(any(f["evidence"][0]["field"] == "epochs" for f in findings))
        self.assertTrue(any("多个值" in n for n in notes))

    def test_grounding_rejects_hallucinated_quote_and_numbers(self):
        sources = [
            dict(id="p", role="paper", filename="paper", text="使用macro-F1。"),
            dict(id="c", role="code", filename="eval.py", text="average='micro'"),
        ]
        valid = dict(
            left=dict(source_id="p", quote="macro-F1"),
            right=dict(source_id="c", quote="average='micro'"),
            issue="指标平均方式不同。",
            suggestion="核查实际评价入口。",
        )
        missing = dict(valid, right=dict(source_id="invented", quote="nonexistent"))
        numeric = dict(valid, issue="结果为99.9。")
        client = Mock()
        client.call.return_value = (dict(findings=[valid, missing, numeric]), None)
        findings, notes = semantic_review(client, "local", sources)
        self.assertEqual(len(findings), 1)
        self.assertEqual(len(notes), 2)
        client.call.return_value = (None, "模型失败")
        self.assertEqual(semantic_review(client, "local", sources)[0], [])

    def test_novelty_source_admission_metadata_and_dates(self):
        items = [
            dict(
                DOI="10.1/a",
                title=["Real work"],
                abstract="<jats:p>Uses method A.</jats:p>",
                published={"date-parts": [[2020, 1, 2]]},
            ),
            dict(
                DOI="10.1/b",
                title=["Later work"],
                published={"date-parts": [[2025, 1, 1]]},
            ),
            dict(DOI="10.1/c", title=["Unknown date"]),
        ]
        with patch("app.audit.novelty.search_items", return_value=items):
            sources, searches = retrieve(["public keyword"], "2024-01-01")
        self.assertEqual(len(sources), 1)
        self.assertEqual(sources[0]["abstract"], "Uses method A.")
        self.assertEqual(searches[0]["query"], "public keyword")
        client = Mock()
        record = dict(
            source_id="lit_1",
            paper_quote="提出方法B。",
            source_quote="Uses method A.",
            judgment="初步支持存在研究贡献",
            difference="两者方法不同，需结合全文确认。",
        )
        client.call.return_value = (
            dict(findings=[record, dict(record, source_id="fake")]),
            None,
        )
        result = assess(client, "local", "提出方法B。", sources, "master")
        self.assertEqual(len(result["comparisons"]), 1)
        self.assertEqual(result["status"], "初步支持存在研究贡献")
        client.call.return_value = (
            dict(findings=[dict(record, difference="性能提高99.9%。")]),
            None,
        )
        self.assertEqual(
            assess(client, "local", "提出方法B。", sources, "master")["comparisons"], []
        )
        sources[0].update(abstract="", scope="metadata_only")
        record["source_quote"] = "Real work"
        client.call.return_value = (dict(findings=[record]), None)
        self.assertEqual(
            assess(client, "local", "提出方法B。", sources, "master")["status"],
            "信息不足",
        )

    def test_missing_ids_do_not_imply_no_overlap(self):
        _, (_, _, notes, ids) = self.material(
            "data.jsonl", '{"x":1}\n{"x":2}\n', "data", "test", "id"
        )
        self.assertIsNone(ids)
        self.assertTrue(any("未检查" in note for note in notes))

    def test_metric_rounding_and_result_csv(self):
        facts = paper_facts(dict(id="paper", text="准确率为95.0%。", location="表1"))
        _, (_, metrics, _, _) = self.material(
            "metrics.csv", "accuracy\n0.94996\n", "result"
        )
        self.assertEqual(compare(facts + metrics, [])[0], [])
        _, (_, invalid, notes, _) = self.material(
            "invalid.json", '{"accuracy": NaN}', "result"
        )
        self.assertEqual(invalid, [])
        self.assertTrue(any("非有限" in note for note in notes))


if __name__ == "__main__":
    unittest.main()
