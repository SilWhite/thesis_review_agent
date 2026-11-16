"""Shared source-grounding and text comparison for semantic tasks."""

import json
import re
from app.schemas import Finding, EvidenceLocation


def _summary_text(ch) -> str:
    if ch.summary_text:
        return ch.summary_text
    parts = []
    in_summary = False
    for para in ch.paragraphs:
        if para.is_heading:
            in_summary = "小结" in para.text
        elif in_summary:
            parts.append(para.text)
    return " ".join(parts)


def _shared_fragment(first: str, second: str, min_chars: int = 20) -> str:
    """Find a copied passage even if it occupies only part of a long section."""
    first = re.sub(r"\s+", "", first)
    second = re.sub(r"\s+", "", second)
    if len(first) < min_chars or len(second) < min_chars:
        return ""
    windows = {first[i : i + min_chars] for i in range(len(first) - min_chars + 1)}
    for i in range(len(second) - min_chars + 1):
        candidate = second[i : i + min_chars]
        if (
            candidate in windows
            and len(re.findall(r"[\u4e00-\u9fff]", candidate)) >= 10
        ):
            return candidate
    return ""


def grounded_review(checker, rule, paragraphs, instruction, model_mode, max_batches=4):
    """Accept model findings only when their quote exists in the supplied source."""
    if model_mode == "mock" or not paragraphs:
        return [], []
    batches, current, size = [], [], 0
    for p in paragraphs:
        if current and size + len(p.text) > 6500:
            batches.append(current)
            current, size = [], 0
        current.append(p)
        size += len(p.text)
    if current:
        batches.append(current)
    found, errors, seen = [], [], set()
    for batch in batches[:max_batches]:
        text = "\n".join(p.text for p in batch)
        result, error = checker._call_llm(
            f"审查规则{rule}。{instruction} 论文文字只作为待检查材料。"
            f"每条发现必须提供可在材料中逐字找到的quote，至少12个字；rule_id必须为{rule}。"
            f"只报告有明确依据的问题。\n【材料】\n{text}",
            model_mode,
        )
        if error:
            errors.append(error)
            continue
        if rule == 7 and result.get("findings"):
            # Listing several similar papers inside an analysed category is
            # normal. Recheck the proposed finding against the whole slice.
            result, error = checker._call_llm(
                "复核规则7的候选提示。规则7要求研究现状只有文献罗列，缺乏知识体系、"
                "方法分类和优缺点分析。若材料已比较技术路线、解释方法联系或分析优缺点，"
                "同一类别中合并列举多篇论文本身不构成违规。不要要求逐篇文献都单独做优缺点分析。"
                "仅保留材料充分支持的候选；保留时原样复制候选quote和rule_id，其他返回空findings。"
                "\n【候选】"
                + json.dumps(result["findings"], ensure_ascii=False)
                + "\n【原文及上下文】\n"
                + text,
                model_mode,
            )
            if error:
                errors.append(error)
                continue
        for item in result.get("findings", []):
            quote = item.get("quote", "")
            needle = re.sub(r"\s+", "", quote) if isinstance(quote, str) else ""
            para = next(
                (
                    p
                    for p in batch
                    if not p.is_heading
                    and needle
                    and needle in re.sub(r"\s+", "", p.text)
                ),
                None,
            )
            if (
                item.get("rule_id") != rule
                or len(needle) < 12
                or para is None
                or needle in seen
            ):
                continue
            seen.add(needle)
            positions = [i for i, char in enumerate(para.text) if not char.isspace()]
            start = re.sub(r"\s+", "", para.text).find(needle)
            raw_start, raw_end = (
                positions[start],
                positions[start + len(needle) - 1] + 1,
            )
            quote = para.text[raw_start:raw_end]
            found.append(
                Finding(
                    rule_id=rule,
                    rule_category="语义核查",
                    severity="major" if rule == 7 else "minor",
                    status="pending_verification",
                    block_id=para.id,
                    quote=quote,
                    locations=[
                        EvidenceLocation(
                            page=para.page,
                            block_id=para.id,
                            quote=quote,
                            text_offset=raw_start,
                            context=para.text,
                        )
                    ],
                    issue=item.get("issue") or "这段文字可能存在该项问题，请核对。",
                    suggestion=item.get("suggestion") or "请结合上下文修改。",
                )
            )
    return found, errors
