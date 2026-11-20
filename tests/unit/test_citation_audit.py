"""Unit tests for hallucinated citation audit and metadata verification."""

import unittest
from unittest.mock import patch

from app.audit.citations import (
    audit_citations,
    compute_similarity,
    extract_references_from_text,
    verify_single_reference,
)


class CitationAuditTests(unittest.TestCase):
    def test_extract_references(self):
        text = """
1. 绪论
这是论文正文内容。
参考文献
[1] Vaswani A, Shazeer N, Parmar N, et al. Attention is all you need[J]. NIPS, 2017.
[2] Goodfellow I, Pouget-Abadie J. Generative Adversarial Networks[J]. Communications of the ACM, 2020.
[3] NonExistent 2025. Fantastic Telepathic Transformer Architecture[J]. Dream AI, 2025.
致谢
感谢老师与同学。
"""
        refs = extract_references_from_text(text)
        self.assertEqual(len(refs), 3)
        self.assertEqual(refs[0]["id"], "[1]")
        self.assertEqual(refs[0]["title"], "Attention is all you need")
        self.assertEqual(refs[0]["year"], "2017")
        self.assertEqual(refs[2]["id"], "[3]")
        self.assertEqual(refs[2]["title"], "Fantastic Telepathic Transformer Architecture")

    def test_similarity_computation(self):
        # Exact match
        self.assertEqual(compute_similarity("Attention Is All You Need", "Attention is all you need"), 1.0)
        # Close match
        sim = compute_similarity(
            "Deep Residual Learning for Image Recognition",
            "Deep Residual Learning for Image Recognition: An Overview"
        )
        self.assertGreater(sim, 0.70)
        # Distinct / hallucinated title
        sim_low = compute_similarity(
            "Attention Is All You Need",
            "Quantum Consciousness in Photonic Neural Synthesis"
        )
        self.assertLess(sim_low, 0.40)

    @patch("app.audit.citations.search_items")
    def test_verify_single_reference_verified(self, mock_search):
        mock_search.return_value = [
            dict(
                DOI="10.1145/3422622",
                title=["Generative Adversarial Networks"],
                published={"date-parts": [[2020, 10, 1]]},
            )
        ]
        ref = dict(
            id="[2]",
            raw="Goodfellow I, et al. Generative Adversarial Networks[J]. 2020.",
            title="Generative Adversarial Networks",
            year="2020",
        )
        res = verify_single_reference(ref)
        self.assertEqual(res["verdict"], "VERIFIED")
        self.assertEqual(res["status_cn"], "已核实真实存在")
        self.assertEqual(res["matched_doi"], "10.1145/3422622")

    @patch("app.audit.citations.search_items")
    def test_verify_single_reference_phantom(self, mock_search):
        # Academic search returns completely unrelated papers
        mock_search.return_value = [
            dict(
                DOI="10.1234/random",
                title=["Linear Regression in Agricultural Soil Studies"],
                published={"date-parts": [[2010, 1, 1]]},
            )
        ]
        ref = dict(
            id="[99]",
            raw="FakeAuthor. Quantum Telepathic Neural Networks for Mind Reading[J]. 2025.",
            title="Quantum Telepathic Neural Networks for Mind Reading",
            year="2025",
        )
        res = verify_single_reference(ref)
        self.assertEqual(res["verdict"], "PHANTOM_CITATION")
        self.assertEqual(res["status_cn"], "疑似虚假/编造引用")

    @patch("app.audit.citations.search_items")
    def test_audit_citations_summary(self, mock_search):
        mock_search.side_effect = [
            [dict(DOI="10.1/real", title=["Real Title"], published={"date-parts": [[2021]]})],
            [],  # Empty search -> phantom
        ]
        text = """
参考文献
[1] Author A. Real Title[J]. 2021.
[2] Author B. Hallucinated Paper Never Published[J]. 2024.
"""
        res = audit_citations(text)
        self.assertEqual(res["total_checked"], 2)
        self.assertEqual(res["verified_count"], 1)
        self.assertEqual(res["phantom_count"], 1)
        self.assertIn("疑似虚假/幻觉编造文献", res["status"])


if __name__ == "__main__":
    unittest.main()
