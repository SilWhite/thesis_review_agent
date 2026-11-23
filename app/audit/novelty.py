"""Idea plagiarism, technical novelty audit, and literature taxonomy tree.

Implements a four-phase Agentic RAG pipeline inspired by OpenNovelty (arXiv:2601.01576v2),
claude-skills-research, and Science-Skill:
1. Multi-angle Claim & Query Extraction (Mechanism, Task, Baseline)
2. Multi-source Federated Retrieval (Semantic Scholar with API key + Crossref)
3. Hierarchical Research Taxonomy Tree Construction & Target Paper Anchor
4. Claim-by-Claim Deep Collision Comparison & Delta Analysis
"""

from difflib import SequenceMatcher
from html import unescape
import json
import logging
import math
import re
from typing import Any
import unicodedata

from app.audit.s2 import search_semantic_scholar
from app.model_client import AUDIT_PREFIX
from app.search import clean_text, search_items
from app.storage import now

log = logging.getLogger(__name__)

EN_STOP_WORDS = {
    "the", "and", "for", "with", "from", "of", "in", "on", "to", "a", "an",
    "by", "via", "using", "based", "method", "methods", "model", "models",
    "approach", "approaches", "system", "systems", "framework", "frameworks",
    "study", "paper", "analysis", "baseline", "baselines", "proposed",
    "propose", "novel", "towards", "into", "through", "over", "under",
    "between", "this", "that", "these", "those", "their", "our", "we",
}

ZH_STOP_BIGRAMS = {
    "研究", "方法", "模型", "系统", "设计", "实现", "分析", "基于", "提出",
    "问题", "算法", "实验", "结果", "应用", "框架", "技术", "本文", "进行",
    "通过", "针对", "有效", "提升", "提高", "能力", "评估", "机制", "策略",
    "方向", "领域", "数据", "信息", "特征", "学习", "深度", "智能", "改进",
    "优化",
}

NON_RESEARCH_CROSSREF_TYPES = {
    "reference-entry",
    "dataset",
    "peer-review",
    "erratum",
    "component",
    "grant",
    "standard",
    "book-track",
}

STANDALONE_NUM_RE = re.compile(r"(?<![A-Za-z])(?<![A-Za-z]-)\d+(?:\.\d+)?(?![A-Za-z])")
_CONTRIB_HEADING_RE = re.compile(
    r"(?im)^[ \t]*(?:\d+(?:\.\d+)*[ \t]+|[一二三四五六七八九十]+[、.．][ \t]*|（[一二三四五六七八九十]+）[ \t]*)?"
    r"(?:本文)?(?:主要(?:研究)?(?:内容与)?创新点|研究主要内容|主要研究内容|主要工作(?:与创新点)?|主要贡献|本文贡献|核心创新|研究内容与创新|Contributions?|Main Contributions?)"
    r"[ \t]*[:：]?[ \t]*$"
)


def _strip_running_headers(paper_text: str) -> str:
    if not paper_text:
        return ""
    lines = paper_text.splitlines()
    counts: dict[str, int] = {}
    for line in lines:
        s = line.strip()
        if 2 <= len(s) <= 45:
            counts[s] = counts.get(s, 0) + 1
    repeated = {
        s
        for s, count in counts.items()
        if count >= 4
        and not re.fullmatch(
            r"(?:摘[ \t]*要|abstract|参考文献|references|bibliography)", s, re.I
        )
    }
    if not repeated:
        return paper_text
    return "\n".join(line for line in lines if line.strip() not in repeated)


def _is_toc_line(line: str) -> bool:
    s = line.strip()
    if not s:
        return False
    if re.search(r"(?:\.{3,}|…{2,}|·{3,}|—{3,})", s):
        return True
    if re.search(r"(?:[ \t]{2,}|\t)\d{1,4}\s*$", line) and len(s) <= 90:
        return True
    return False


def _in_toc_block(text: str, pos: int) -> bool:
    line_start = text.rfind("\n", 0, pos) + 1
    line_end = text.find("\n", pos)
    if line_end < 0:
        line_end = len(text)
    if _is_toc_line(text[line_start:line_end]):
        return True
    before = [ln for ln in text[:line_start].splitlines() if ln.strip()][-2:]
    after = [ln for ln in text[line_end:].splitlines() if ln.strip()][:2]
    toc_neighbors = sum(1 for ln in before + after if _is_toc_line(ln))
    return toc_neighbors >= 2


def _find_references_offset(paper_text: str) -> int | None:
    if not paper_text:
        return None
    pattern = re.compile(r"(?im)^[ \t]*(?:参考\s*文献|References|Bibliography)[ \t]*[:：]?[ \t]*$")
    half = len(paper_text) // 2
    for m in pattern.finditer(paper_text, half):
        if not _in_toc_block(paper_text, m.start()):
            return m.start()
    early_limit = max(0, int(len(paper_text) * 0.3))
    matches = [
        m.start()
        for m in pattern.finditer(paper_text, early_limit)
        if not _in_toc_block(paper_text, m.start())
    ]
    return matches[-1] if matches else None


def _body_without_references(paper_text: str) -> str:
    offset = _find_references_offset(paper_text)
    return paper_text[:offset] if offset is not None else paper_text


def _extract_reference_text(paper_text: str) -> str:
    offset = _find_references_offset(paper_text)
    return paper_text[offset:] if offset is not None else ""


def _extract_terms(text: str) -> set[str]:
    if not text:
        return set()
    terms = set()
    for word in re.findall(r"[a-z][a-z0-9-]{2,}|\d+[a-z]+", text.casefold()):
        if word not in EN_STOP_WORDS:
            terms.add(word)
    for block in re.findall(r"[\u4e00-\u9fff]+", text):
        if len(block) >= 2:
            for i in range(len(block) - 1):
                bg = block[i : i + 2]
                if bg not in ZH_STOP_BIGRAMS:
                    terms.add(bg)
    return terms


def _simplify_query(query: str, max_words: int = 4) -> str:
    tokens = re.findall(r"[A-Za-z0-9-]+|[\u4e00-\u9fff]+", clean_text(query))
    kept = [
        tok
        for tok in tokens
        if len(tok) > 1 and tok.casefold() not in EN_STOP_WORDS
    ]
    if not kept:
        kept = [tok for tok in tokens if len(tok) > 1]
    return " ".join(kept[:max_words]).strip()


def _passes_cutoff(published: str | None, year: str | None, cutoff: str | None) -> bool:
    if not cutoff:
        return True
    pub = (published or "").strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", pub):
        return pub <= cutoff
    if re.fullmatch(r"\d{4}-\d{2}", pub):
        return pub < cutoff[:7]
    m = re.match(r"(\d{4})", str(year or "").strip() or pub)
    if not m:
        return False
    return m.group(1) < cutoff[:4]


def _normalize_for_match(text: str) -> str:
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", text or "").casefold())


def _quote_tokens(text: str) -> set[str]:
    tokens = set(re.findall(r"[a-z0-9]{3,}", text.casefold()))
    for block in re.findall(r"[\u4e00-\u9fff]+", text):
        if len(block) >= 2:
            tokens.update(block[i : i + 2] for i in range(len(block) - 1))
    return tokens


def locate_claim_sections(paper_text: str) -> str:
    """Find the most informative sections for claim extraction:
    CN Abstract, EN Abstract, Main contributions, Conclusion summary.
    """
    if len(paper_text) <= 12000:
        return paper_text

    cleaned = "\n".join(
        ln
        for ln in _strip_running_headers(_body_without_references(paper_text)).splitlines()
        if not _is_toc_line(ln)
    )
    if len(cleaned) <= 12000:
        return cleaned

    ranges: list[tuple[int, int]] = []

    # 1. Chinese Abstract
    cn_abs = None
    for m in re.finditer(r"(?im)^[ \t]*(?:中\s*文\s*)?摘[ \t]*要[ \t]*[:：]?[ \t]*$", cleaned):
        if not _in_toc_block(cleaned, m.start()):
            cn_abs = m
            break
    if cn_abs:
        tail = cleaned[cn_abs.end() : cn_abs.end() + 2800]
        stop_m = re.search(
            r"(?im)^[ \t]*(?:abstract|目[ \t]*录|第[ \t]*[一1][ \t]*章|1[ \t]+绪论)\b",
            tail,
        )
        stop = cn_abs.end() + (stop_m.start() if stop_m else len(tail))
        ranges.append((cn_abs.start(), min(len(cleaned), stop)))
    else:
        ranges.append((0, min(len(cleaned), 3000)))

    # 2. English Abstract
    en_abs = None
    for m in re.finditer(r"(?im)^[ \t]*abstract[ \t]*[:：]?[ \t]*$", cleaned):
        if not _in_toc_block(cleaned, m.start()):
            en_abs = m
            break
    if en_abs:
        tail = cleaned[en_abs.end() : en_abs.end() + 2000]
        stop_m = re.search(
            r"(?im)^[ \t]*(?:目[ \t]*录|第[ \t]*[一1][ \t]*章|1(?:\.0)?[ \t]+Introduction)\b",
            tail,
        )
        stop = en_abs.end() + (stop_m.start() if stop_m else len(tail))
        ranges.append((en_abs.start(), min(len(cleaned), stop)))

    # 3. Explicit contribution / main research content sections (skipping TOC)
    contrib_count = 0
    for m in _CONTRIB_HEADING_RE.finditer(cleaned):
        if _in_toc_block(cleaned, m.start()):
            continue
        start = max(0, m.start() - 100)
        end = min(len(cleaned), m.start() + 2400)
        if not any(s <= m.start() < e for s, e in ranges):
            ranges.append((start, end))
            contrib_count += 1
        if contrib_count >= 2:
            break

    # 4. Conclusion / Summary section in second half
    half = len(cleaned) // 2
    concl_re = re.compile(
        r"(?im)^[ \t]*(?:\d+(?:\.\d+)*[ \t]+|第[ \t]*[一二三四五六七八九十0-9]+[ \t]*章[ \t]+)?"
        r"(?:总结与展望|全文总结|结论与展望|研究总结与展望|结[ \t]*论|Conclusions?(?: and Future Work)?)"
        r"[ \t]*[:：]?[ \t]*$"
    )
    concl_added = False
    for m in concl_re.finditer(cleaned, half):
        if _in_toc_block(cleaned, m.start()):
            continue
        start = max(0, m.start() - 100)
        end = min(len(cleaned), m.start() + 2200)
        ranges.append((start, end))
        concl_added = True
        break
    if not concl_added:
        ranges.append((max(0, len(cleaned) - 2200), len(cleaned)))

    merged: list[tuple[int, int]] = []
    for start, stop in sorted(ranges):
        if start >= stop:
            continue
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(stop, merged[-1][1]))
        else:
            merged.append((start, stop))

    return "\n\n...\n\n".join(cleaned[s:e] for s, e in merged)[:12000]


def build_method_context(paper_text: str, claims: list[dict] | None) -> str:
    """Build comparison context combining claim sections and claim-matched body paragraphs."""
    if not paper_text:
        return ""
    if len(paper_text) <= 12000:
        return paper_text
    if not claims:
        return locate_claim_sections(paper_text)

    base_slice = locate_claim_sections(paper_text)[:7500]
    cleaned = _strip_running_headers(_body_without_references(paper_text))

    chunks: list[str] = []
    buf: list[str] = []
    buf_len = 0
    for line in cleaned.splitlines():
        if _is_toc_line(line):
            continue
        s = line.strip()
        if not s:
            continue
        buf.append(s)
        buf_len += len(s) + 1
        if buf_len >= 1200:
            chunks.append("\n".join(buf))
            buf, buf_len = [], 0
    if buf:
        chunks.append("\n".join(buf))

    base_norm = _normalize_for_match(base_slice)
    candidate_chunks: list[tuple[str, int]] = []
    for chunk in chunks:
        chunk_norm = _normalize_for_match(chunk)
        if len(chunk_norm) < 80:
            continue
        mid = len(chunk_norm) // 4
        probe = chunk_norm[mid : mid + 100]
        if probe and probe in base_norm:
            continue
        cite_count = len(re.findall(r"\[\d+(?:[-,，]\d+)*\]", chunk))
        candidate_chunks.append((chunk, cite_count))

    additions: list[str] = []
    used_indices: set[int] = set()
    for idx, claim in enumerate(claims[:4], 1):
        c_text = (claim.get("claim") or "") + " " + " ".join(claim.get("queries") or [])
        c_terms = _extract_terms(c_text)
        if not c_terms:
            continue
        best_idx = -1
        best_score = 0.0
        for c_i, (chunk, cite_count) in enumerate(candidate_chunks):
            if c_i in used_indices:
                continue
            overlap = len(c_terms & _extract_terms(chunk))
            penalty = min(8.0, float(cite_count)) if cite_count >= 6 else 0.0
            sc = overlap - penalty
            if sc > best_score:
                best_score = sc
                best_idx = c_i
        if best_idx >= 0 and best_score > 0:
            used_indices.add(best_idx)
            chunk_text = candidate_chunks[best_idx][0][:1400]
            additions.append(f"\n\n[正文方法细节补充 - 对应主张 #{idx}]:\n{chunk_text}")

    return (base_slice + "".join(additions))[:14500]


def _check_quote_against_candidate_text(quote: str, clean_q: str, q_tokens: set[str], candidate_text: str) -> bool:
    clean_t = _normalize_for_match(candidate_text)
    if not clean_t:
        return False

    # 1. Exact normalized match
    if clean_q in clean_t:
        return True

    # 2. Contiguous 15-char normalized substring match
    if len(clean_q) >= 15:
        for i in range(0, len(clean_q) - 14, 5):
            if clean_q[i : i + 15] in clean_t:
                return True

    # 3. Tightened bigram + English word containment
    if len(q_tokens) >= 4:
        full_tokens = _quote_tokens(candidate_text)
        if len(q_tokens & full_tokens) / len(q_tokens) < 0.75:
            return False
        win_len = max(len(clean_q) * 2, 160)
        step = max(40, len(clean_q) // 2)
        upper = min(len(clean_t), 150000)
        for pos in range(0, max(1, upper - win_len + 1), step):
            win = _quote_tokens(clean_t[pos : pos + win_len])
            if len(q_tokens & win) / len(q_tokens) >= 0.75:
                return True

    return False


def check_quote_in_text(quote: str, full_text: str) -> tuple[bool, str]:
    """Check if quote exists in full_text using normalized substring and bigram containment."""
    if not quote or not full_text:
        return False, ""

    clean_q = _normalize_for_match(quote)
    if not clean_q:
        return False, ""
    q_tokens = _quote_tokens(quote)

    if _check_quote_against_candidate_text(quote, clean_q, q_tokens, full_text):
        return True, quote

    if len(full_text) > 1000:
        stripped = _strip_running_headers(full_text)
        if stripped != full_text and _check_quote_against_candidate_text(
            quote, clean_q, q_tokens, stripped
        ):
            return True, quote

    return False, quote


def extract_claims_from_paper(
    client, mode: str, paper_text: str, errors: list[str] | None = None
) -> list[dict[str, Any]]:
    """Automatically extract 2-4 core technical claims with multi-angle search queries.

    Each claim returns:
    - claim: core technical claim in Chinese
    - query: primary search query
    - queries: 2-3 concise English academic search queries
    - query_zh (optional): concise Chinese search query
    """
    if not paper_text or len(paper_text.strip()) < 50:
        return [
            {
                "claim": "论文核心方法与创新点",
                "query": "deep learning optimization method",
                "queries": [
                    "deep learning optimization method",
                    "adaptive neural architecture",
                    "model efficiency baseline",
                ],
            }
        ]

    snippet = locate_claim_sections(paper_text)

    if mode == "mock" or client is None:
        return [
            {
                "claim": "基于深度特征提取与多模态融合的适老化分析方法",
                "query": "multimodal deep feature fusion analysis",
                "queries": [
                    "multimodal deep feature fusion interaction",
                    "elderly accessibility interface design",
                    "adaptive human centered framework",
                ],
            },
            {
                "claim": "自适应加权机制与对比学习框架",
                "query": "adaptive weighting contrastive learning",
                "queries": [
                    "adaptive weighting contrastive learning",
                    "generative AI adaptive user interface",
                    "intelligent dialogue collaborative framework",
                ],
            },
        ]

    prompt = (
        AUDIT_PREFIX
        + """你是一名资深科研学术规范专家。请从以下论文片段中，提取出作者在文中声称的 2 到 4 个最核心的【技术创新点/方法主张】（Claim-by-Claim）。
针对每个创新点：
1. 提炼出一句话核心技术主张（claim）；
2. 派生 2 到 3 组不同视角的英文学术检索词（queries），每条严格控制在 3 到 6 个核心英文关键词以内（禁止写长句子，避免 method/approach/framework/baseline 等空泛填充词，保留专业缩写），分别面向：
   - 核心机制与算法视角（如：differentiable prototype tree neural network）
   - 具体任务与领域视角（如：tomato disease CLIP multimodal recognition）
   - 相近基线/对比机制视角（如：SwinTransformer cross-attention image text fusion）
3. 可选提供 1 条简短中文学术检索词（query_zh，2 到 4 个核心中文词，如：番茄病害 多模态 图像识别）。

请严格返回 JSON 格式:
{"findings": [
  {
    "claim": "提出基于类别原型表征可导化的树形神经网络自动构建方法",
    "queries": [
      "differentiable category prototype tree neural network",
      "interpretable hierarchical image classification",
      "prototype meta-learning decision tree"
    ],
    "query_zh": "可微原型 树形神经网络 图像分类"
  }
]}
论文内容片段：
"""
        + snippet
    )

    try:
        res, err = client.call(prompt, mode)
        items = (
            res.get("findings")
            or res.get("claims")
            or []
            if isinstance(res, dict)
            else []
        )
        if not err and items:
            claims = []
            for item in items[:4]:
                c = clean_text(item.get("claim", ""))
                raw_queries = item.get("queries") or []
                if isinstance(raw_queries, str):
                    raw_queries = [raw_queries]
                queries = [clean_text(q) for q in raw_queries if clean_text(q)]
                if not queries and item.get("query"):
                    queries = [clean_text(item["query"])]
                if not queries and c:
                    queries = [c[:50]]
                zh_raw = item.get("query_zh")
                query_zh = (
                    clean_text(zh_raw)
                    if isinstance(zh_raw, str) and re.search(r"[\u4e00-\u9fff]", zh_raw)
                    else ""
                )
                if c:
                    entry: dict[str, Any] = {
                        "claim": c,
                        "query": queries[0] if queries else c[:50],
                        "queries": queries[:3],
                    }
                    if query_zh:
                        entry["query_zh"] = query_zh
                    claims.append(entry)
            if claims:
                return claims
        reason = f"创新点提取模型调用失败：{err}" if err else "模型未能从论文中提取出有效创新点。"
        log.warning("extract_claims_from_paper failed: %s", reason)
        if errors is not None:
            errors.append(reason)
        return []
    except Exception as exc:
        log.warning("extract_claims_from_paper error: %s", exc)
        if errors is not None:
            errors.append(f"创新点提取异常：{exc}")
        return []


def _claim_source_relevance(source: dict, claim: dict) -> float:
    claim_text = claim.get("claim") or ""
    queries = list(claim.get("queries") or [])
    if claim.get("query_zh"):
        queries.append(claim["query_zh"])
    c_terms = _extract_terms(claim_text + " " + " ".join(queries))
    if not c_terms:
        return 0.0
    title_terms = _extract_terms(source.get("title") or "")
    body_terms = _extract_terms(
        (source.get("abstract") or "") + " " + (source.get("tldr") or "")
    )
    title_hits = len(c_terms & title_terms)
    body_hits = len(c_terms & (title_terms | body_terms))
    coverage = ((2.0 * title_hits + body_hits) / max(1, len(c_terms))) * 35.0
    claim_q_set = {q.casefold() for q in queries if q}
    source_q_set = set(source.get("matched_queries") or [])
    provenance = 20.0 if (claim_q_set & source_q_set) else 0.0
    return min(100.0, coverage + provenance)


def rank_and_deduplicate_sources(
    sources: list[dict], claims: list[dict] | None = None
) -> list[dict]:
    """Rank literature candidates prioritizing claim relevance and abstract completeness over raw recency."""

    def score(s: dict) -> float:
        year_str = str(s.get("year") or (s.get("published") or "")[:4])
        year = int(year_str) if year_str.isdigit() and len(year_str) == 4 else 2018

        # Relevance (0-100): max per-claim relevance rather than mixing all claims
        if claims:
            relevance = max(_claim_source_relevance(s, c) for c in claims)
        else:
            relevance = 0.0

        # Completeness score (0-30)
        has_abs = 25.0 if s.get("abstract") and len(s["abstract"]) > 40 else 0.0
        has_tldr = 5.0 if s.get("tldr") else 0.0

        title = s.get("title", "")
        if re.search(
            r"proceedings of the|international conference,\s*\w+\s*\d{4}|symposium,\s*\w+\s*\d{4}",
            title,
            re.I,
        ):
            has_abs -= 50.0

        # Recency score (0-25, avoids overwhelming domain mismatch)
        if year >= 2022:
            recency = min(25.0, 20.0 + (year - 2022) * 1.2)
        elif year >= 2019:
            recency = 12.0 + (year - 2019) * 3.0
        elif year >= 2016:
            recency = 6.0 + (year - 2016) * 2.0
        else:
            recency = max(-15.0, (year - 2016) * 3.0)

        # Citation impact (0-15, log-scaled)
        cit = s.get("citation_count")
        cit_score = (
            min(15.0, math.log1p(cit) * 2.5)
            if isinstance(cit, (int, float)) and cit > 0
            else 0.0
        )

        return relevance + has_abs + has_tldr + recency + cit_score

    ranked = sorted(sources, key=score, reverse=True)
    for idx, s in enumerate(ranked):
        s["id"] = f"lit_{idx + 1}"
    return ranked


def _merge_source_record(existing: dict, candidate: dict, query_key: str) -> None:
    if query_key:
        mq = existing.setdefault("matched_queries", [])
        if query_key not in mq:
            mq.append(query_key)
    if len(candidate.get("abstract") or "") > len(existing.get("abstract") or ""):
        existing["abstract"] = candidate["abstract"]
        existing["scope"] = "abstract"
    if len(candidate.get("published") or "") > len(existing.get("published") or ""):
        existing["published"] = candidate["published"]
    for field in ("doi", "url", "authors", "tldr", "venue", "year"):
        if not existing.get(field) and candidate.get(field):
            existing[field] = candidate[field]
    cand_cit = candidate.get("citation_count")
    cur_cit = existing.get("citation_count")
    if isinstance(cand_cit, (int, float)) and (
        cur_cit is None or cand_cit > cur_cit
    ):
        existing["citation_count"] = cand_cit


def retrieve(
    queries: list[str],
    cutoff: str | None = None,
    s2_api_key: str | None = None,
    claims: list[dict] | None = None,
    checkpoint=None,
):
    """Multi-source federated literature retrieval combining Semantic Scholar and Crossref."""
    sources: list[dict] = []
    searches: list[dict] = []
    doi_index: dict[str, dict] = {}
    title_index: dict[str, dict] = {}

    cleaned_queries: list[str] = []
    seen_q: set[str] = set()
    for q in queries:
        cq = clean_text(q)
        if cq and cq.casefold() not in seen_q:
            seen_q.add(cq.casefold())
            cleaned_queries.append(cq)

    def _add_or_merge(record: dict, query_key: str) -> None:
        title = record.get("title", "")
        if not title:
            return
        doi = (record.get("doi") or "").strip().casefold()
        norm_title = "".join(re.findall(r"\w+", title.casefold()))
        existing = (doi_index.get(doi) if doi else None) or (
            title_index.get(norm_title) if norm_title else None
        )
        if existing is not None:
            _merge_source_record(existing, record, query_key)
            if doi:
                doi_index.setdefault(doi, existing)
            if norm_title:
                title_index.setdefault(norm_title, existing)
            return
        record["id"] = f"lit_{len(sources) + 1}"
        record["matched_queries"] = [query_key] if query_key else []
        sources.append(record)
        if doi:
            doi_index[doi] = record
        if norm_title:
            title_index[norm_title] = record

    # 1. Semantic Scholar retrieval (English queries when s2_api_key is configured)
    s2_hit_counts: dict[str, int] = {}
    if s2_api_key:
        s2_year = f"-{cutoff[:4]}" if cutoff else "2018-"
        en_queries = [q for q in cleaned_queries if not re.search(r"[\u4e00-\u9fff]", q)]
        for q in en_queries[:10]:
            try:
                if checkpoint:
                    checkpoint()
                s2_items = search_semantic_scholar(
                    q, api_key=s2_api_key, limit=12, year=s2_year
                )
                searches.append(
                    {
                        "engine": "semantic_scholar",
                        "query": q,
                        "approved": True,
                        "retrieved_at": now(),
                        "count": len(s2_items),
                    }
                )
                if not s2_items and len(re.findall(r"[A-Za-z0-9-]+", q)) > 4:
                    concise = _simplify_query(q, max_words=4)
                    if concise and concise.casefold() != q.casefold():
                        if checkpoint:
                            checkpoint()
                        s2_items = search_semantic_scholar(
                            concise, api_key=s2_api_key, limit=12, year=s2_year
                        )
                        searches.append(
                            {
                                "engine": "semantic_scholar",
                                "query": concise,
                                "approved": True,
                                "retrieved_at": now(),
                                "count": len(s2_items),
                            }
                        )
                kept_for_q = 0
                for item in s2_items:
                    if not _passes_cutoff(
                        item.get("published"), item.get("year"), cutoff
                    ):
                        continue
                    _add_or_merge(item, q.casefold())
                    kept_for_q += 1
                s2_hit_counts[q.casefold()] = kept_for_q
            except Exception as exc:
                log.warning("S2 query %r error: %s", q, exc)

    # 2. Crossref retrieval (primary without S2 key; supplements low-hit S2 & Chinese queries)
    max_sources = max(65, len(sources) + 15) if s2_api_key else 50
    crossref_queue = (
        [q for q in cleaned_queries if re.search(r"[\u4e00-\u9fff]", q)]
        + [q for q in cleaned_queries if not re.search(r"[\u4e00-\u9fff]", q)]
        if s2_api_key
        else cleaned_queries
    )
    for q in crossref_queue:
        if len(sources) >= max_sources:
            break
        is_zh = bool(re.search(r"[\u4e00-\u9fff]", q))
        if s2_api_key and not is_zh and s2_hit_counts.get(q.casefold(), 0) >= 3:
            continue

        query_variants = [q]
        en_tokens = re.findall(r"[A-Za-z0-9-]+", q)
        if not is_zh and len(en_tokens) > 6:
            concise = _simplify_query(q, max_words=4)
            if concise and concise.casefold() != q.casefold():
                query_variants.append(concise)

        for variant_idx, query_str in enumerate(query_variants):
            if len(sources) >= max_sources:
                break
            if checkpoint:
                checkpoint()
            try:
                items = (
                    search_items(query_str, cutoff=cutoff)
                    if cutoff
                    else search_items(query_str)
                )
            except Exception as exc:
                if not sources:
                    raise
                log.warning("Crossref query %r error: %s", query_str, exc)
                searches.append(
                    {
                        "engine": "crossref",
                        "query": query_str,
                        "approved": True,
                        "retrieved_at": now(),
                        "status": "failed",
                        "count": 0,
                    }
                )
                continue

            searches.append(
                {
                    "engine": "crossref",
                    "query": query_str,
                    "approved": True,
                    "retrieved_at": now(),
                    "count": len(items),
                }
            )
            usable = 0
            for item in items:
                if item.get("type") in NON_RESEARCH_CROSSREF_TYPES:
                    continue
                doi = (item.get("DOI") or "").strip().casefold()
                title_list = item.get("title") or []
                title = clean_text(title_list[0]) if title_list else ""
                if not title:
                    continue
                parts = (item.get("published") or {}).get("date-parts", [[]])[0]
                published = "-".join(str(p).zfill(2) for p in parts) if parts else None
                year = str(parts[0]) if parts else None
                if cutoff:
                    if not _passes_cutoff(published, year, cutoff):
                        continue
                elif parts and parts[0] < 2016:
                    continue

                abstract = clean_text(item.get("abstract") or "")
                authors = [
                    f"{a.get('given', '')} {a.get('family', '')}".strip()
                    for a in item.get("author", [])
                    if a.get("family")
                ]
                container = item.get("container-title") or []
                venue = clean_text(container[0]) if container else ""

                _add_or_merge(
                    {
                        "title": title,
                        "doi": doi,
                        "url": f"https://doi.org/{doi}" if doi else "",
                        "authors": authors,
                        "year": year,
                        "published": published,
                        "venue": venue,
                        "citation_count": None,
                        "tldr": "",
                        "abstract": abstract[:3000],
                        "scope": "abstract" if abstract else "metadata_only",
                        "source": "crossref",
                    },
                    q.casefold(),
                )
                usable += 1
            if variant_idx == 0 and usable >= 3:
                break

    sources = rank_and_deduplicate_sources(sources, claims)
    return sources, searches


def _default_taxonomy(sources: list[dict]) -> dict:
    lit_ids = [s["id"] for s in sources]
    half = max(1, len(lit_ids) // 2)
    return {
        "root_topic": "待审课题技术范式与前沿探索",
        "target_position": "本论文归属于垂直场景的自适应技术分支。",
        "branches": [
            {
                "name": "基础框架与传统方法",
                "description": "领域内已有基础框架与前人工作。",
                "papers": lit_ids[:half],
                "is_target_branch": False,
            },
            {
                "name": "自适应与前沿技术方案",
                "description": "面向垂直任务的细化设计与前沿应用。",
                "papers": lit_ids[half:] or lit_ids,
                "is_target_branch": True,
            },
        ],
    }


def _select_candidates_for_prompt(
    sources: list[dict], claims: list[dict] | None, max_total: int = 20
) -> tuple[list[dict], dict[int, list[str]]]:
    if not claims:
        with_content = [s for s in sources if s.get("abstract") or s.get("tldr")]
        rest = [s for s in sources if not (s.get("abstract") or s.get("tldr"))]
        selected = (with_content + rest)[:18]
        return selected, {}

    selected_map: dict[str, dict] = {}
    per_claim_ids: dict[int, list[str]] = {}

    def _year_int(s: dict) -> int:
        ys = str(s.get("year") or (s.get("published") or "")[:4])
        return int(ys) if ys.isdigit() and len(ys) == 4 else 2000

    for idx, claim in enumerate(claims[:4], 1):
        ordered = sorted(
            sources,
            key=lambda s: (
                bool(s.get("abstract") or s.get("tldr")),
                round(_claim_source_relevance(s, claim), 4),
                _year_int(s),
            ),
            reverse=True,
        )
        top_for_claim = ordered[:5]
        per_claim_ids[idx] = [s["id"] for s in top_for_claim]
        for s in top_for_claim:
            if len(selected_map) < max_total:
                selected_map.setdefault(s["id"], s)

    for s in sources:
        if len(selected_map) >= min(max_total, 18):
            break
        selected_map.setdefault(s["id"], s)

    return list(selected_map.values()), per_claim_ids


def _match_claim_index(item_claim: str, claims: list[dict]) -> int | None:
    norm_item = _normalize_for_match(item_claim)
    if not norm_item:
        return None
    for idx, c in enumerate(claims):
        norm_c = _normalize_for_match(c.get("claim", ""))
        if not norm_c:
            continue
        if norm_item == norm_c or (
            min(len(norm_item), len(norm_c)) >= 8
            and (norm_item in norm_c or norm_c in norm_item)
        ):
            return idx
    return None


def _is_self_work(source: dict, front_norm: str) -> bool:
    title_norm = _normalize_for_match(source.get("title", ""))
    if len(title_norm) < 15 or not front_norm:
        return False
    if len(title_norm) >= 18 and title_norm in front_norm:
        return True
    for line in front_norm.splitlines():
        if len(line) >= 15 and SequenceMatcher(None, title_norm, line).ratio() >= 0.85:
            return True
    return False


def _is_referenced(source: dict, ref_text: str, ref_norm: str) -> bool:
    if not ref_text:
        return False
    doi = (source.get("doi") or "").strip().casefold()
    if doi and doi in ref_text.casefold():
        return True
    title_norm = _normalize_for_match(source.get("title", ""))
    return len(title_norm) >= 15 and title_norm in ref_norm


def _classify_verdict(item: dict) -> str:
    vl = str(item.get("verdict_level") or "").strip().lower()
    j = str(item.get("judgment") or "")
    if vl == "duplicate" or "已被前人做过" in j or "抄袭" in j or "核心方法重合" in j:
        return "duplicate"
    if vl == "incremental" or "增量" in j:
        return "incremental"
    if vl == "novel" or "未见相同工作" in j or "原创" in j:
        return "novel"
    if vl == "uncertain" or j == "信息不足":
        return "uncertain"
    return "legacy"


def assess(
    client,
    mode: str,
    paper: str,
    sources: list[dict],
    degree: str,
    claims: list[dict] | None = None,
):
    """Assess whether technical claims collide with prior published literature.

    Implements OpenNovelty's hierarchical taxonomy tree construction and
    Claim-by-Claim fine-grained comparison against prior art in a single coherent prompt.
    """
    base = dict(
        status="信息不足",
        basis="依据公开学术文献检索与核心技术方案对比分析。",
        summary="在已检索到的学术文献范围内进行深入比对。",
        claims=[
            c["claim"]
            for c in (claims or [])
            if isinstance(c, dict) and c.get("claim")
        ],
        comparisons=[],
        taxonomy_tree=_default_taxonomy(sources),
        sources=sources,
        notes=[],
    )

    if not sources:
        base["basis"] = "未能取得符合条件的公开文献。"
        base["summary"] = (
            "由于检索未返回相关公开文献，暂无法充分评估是否存在思想撞车，建议补充关键词核查。"
        )
        base["notes"].append("没有取得符合条件的文献；不能据此认定创新或引用虚构。")
        return base

    if mode == "mock" or client is None:
        first_source = sources[0]
        base["status"] = "主要属于相近工作的增量改进"
        base["summary"] = (
            f"论文提出的方法与前人文献《{first_source['title']}》相近，主要在前序工作基础上进行了增量扩展。"
        )
        base["comparisons"].append(
            dict(
                source_id=first_source["id"],
                paper_quote=paper[:100].strip(),
                source_quote=first_source.get("abstract", first_source["title"])[:100],
                judgment="🟡 存在相近工作（增量改进）",
                verdict_level="incremental",
                difference=f"与 {first_source['title']} 相比具有增量差异。",
                claim=(claims[0]["claim"] if claims else "论文核心方法"),
                taxonomy_branch=base["taxonomy_tree"]["branches"][0]["name"],
            )
        )
        return base

    paper_context = build_method_context(paper, claims) if paper else ""
    selected_sources, per_claim_ids = _select_candidates_for_prompt(sources, claims)

    ref_text = _extract_reference_text(paper)
    ref_norm = _normalize_for_match(ref_text)
    front_lines_norm = "\n".join(
        _normalize_for_match(ln) for ln in (paper or "")[:2000].splitlines() if ln.strip()
    )

    lit_brief = []
    for s in selected_sources:
        abstract = s.get("abstract") or ""
        tldr = s.get("tldr") or ""
        text_content = abstract[:1500] if abstract else tldr
        cit = s.get("citation_count")
        cit_display = str(cit) if cit is not None else "未知"
        tags = []
        if _is_referenced(s, ref_text, ref_norm):
            tags.append("[本文参考文献已引用]")
        if _is_self_work(s, front_lines_norm):
            tags.append("[疑似与待审论文同题/作者本人先发版本]")
        tag_str = (" " + " ".join(tags)) if tags else ""
        lit_brief.append(
            f"[{s['id']}] 《{s['title']}》 ({s.get('year') or s.get('published') or '年份未知'}){tag_str}\n"
            f"刊物/会议: {s.get('venue') or '未知'} | 引用数: {cit_display}\n"
            f"DOI: {s.get('doi')}\n"
            f"核心内容/摘要: {text_content or '（暂无详细摘要）'}\n"
        )

    claims_text = ""
    if claims:
        lines = [
            "\n【待核查的论文核心创新主张清单（必须对以下每一项逐一进行审查，不得遗漏）】:"
        ]
        for i, c in enumerate(claims, 1):
            hint = (
                f"（优先候选池：{', '.join(per_claim_ids[i])}）"
                if per_claim_ids.get(i)
                else ""
            )
            lines.append(f"{i}. {c['claim']} {hint}".strip())
        claims_text = "\n".join(lines)

    degree_map = {
        "bachelor": "本科",
        "master": "硕士",
        "doctor": "博士",
        "unknown": "学位",
    }
    degree_cn = degree_map.get(degree, "学位")

    prompt = (
        AUDIT_PREFIX
        + f"""你是一名资深科研学术规范专家，负责对{degree_cn}学位论文进行严密的创新性审查与思想抄袭核查。
请融合 NoveltyAgent (arXiv:2603.20884) 的逐创新点分析机制（Point-wise Novelty Analysis）与 NoveltyScope (arXiv:2610.22703) 的多角色证据对抗机制（公诉人辩驳 vs 辩护人抗辩 vs 法官终审）：
1. 梳理前人文献的技术路线归类（2 到 3 个主要技术方向），并标明待审论文主要采用的方向；
2. 必须对待审论文声称的【每一个核心创新主张】（Point-wise Claims）进行一对一的深入对标审查，优先参考该主张对应的优先候选池。

{claims_text}

【待审论文正文核心片段（供核验真实引用与方法细节）】:
{paper_context}

【已检索的前人文献库候选（Top 候选）】:
{"".join(lit_brief)}

【逐创新点审查的核心要求】:
针对待审论文声称的【每一项创新点】，必须提供：
1. 【大家都做了哪些工作】（prior_works_summary）：概述前人在该子方向上的已有方案、主流基线与代表文献；
2. 【思想重合指控】（prosecutor_overlap）：充当严苛的学术公诉人，严格指出对标文献（如 lit_X）是否已有相同或高度相近的思想、机制或算法，指出具体雷同点；若未见重合，写“在检索范围内未见与前人实质雷同”；
3. 【增量抗辩说明】（defender_novelty）：充当客观的学术辩护人，指出本文相比该对标文献在算法模型、机制设计、约束条件或应用场景上是否有真正的独特性与增量改进；
4. 【法官最终裁决】（judgment & verdict_level & difference）：
   - 🔴 已被前人做过（撞车/疑似思想抄袭） (verdict_level: "duplicate")：核心思想/机制与前人已有工作完全重合，属于重复或换汤不换药。
   - 🟡 存在相近工作（增量改进） (verdict_level: "incremental")：前人已有相似框架，本文在此基础上有明确的增量扩展、适应性改进或优化。
   - 🟢 未见相同工作（原创性良好） (verdict_level: "novel")：在检索范围内确实涵盖了同任务/同领域文献，但未发现类似核心技术思想。
   - 信息不足 (verdict_level: "uncertain")：当前候选库中缺少同任务/同机制的可比文献，或对标文献缺少摘要/方法细节，无法形成有效比对。
   - difference: 总结两者的关键实质差异（Delta）或当前候选库的覆盖缺口。
5. 【原文佐证】（paper_quote / source_quote）：分别严格摘录待审论文和对照文献摘要中的连续原句（逐字引用，不可改写或编造）。

【严禁跨领域“拉郎配”与文献对标原则】:
1. 严禁跨领域/跨任务强行对标：如果候选文献仅共享“大模型/对比学习/多模态/RAG/微调/知识图谱”等宽泛技术名词，而实际研究领域、输入模态与解决任务完全不同（例如拿生物信息学图网络、中医临床问答或语音识别论文去对标文本安全价值观评估），**不得**强行判为 `duplicate` 或 `incremental`；若无同任务或同核心机制的真正可比文献，必须使用 `verdict_level: "uncertain"`、`judgment: "信息不足"`（`source_id` 可留空 `""`），在 `difference` 中说明缺乏同领域可比文献！
2. 优先对标当代代表文献（2018–2026年），若核心思想源自更早经典方法亦可据实对标；没有摘要/核心内容仅含题目的文献不能用来定性重复或抄袭。
3. 若文献标有 `[本文参考文献已引用]` 或 `[疑似与待审论文同题/作者本人先发版本]`，必须在分析中如实说明，不得将作者本人已发表的小论文/预印本误判为思想抄袭他人。

【全局一致性强制原则】:
- 如果有任意一个创新点被裁决为 🔴（撞车/已有相同工作），全局 status 必须为：“🔴 发现已有相同工作（存在思想撞车/抄袭风险）”！
- 如果没有红项但有 🟡，全局 status 必须为：“🟡 主要属于相近工作的增量改进”！
- 如果全为 🟢，全局 status 为：“🟢 在检索范围内未见实质重叠（原创性较好）”！
- 绝不能出现全局标红但明细全是绿色的自相矛盾！

请严格返回以下 JSON 格式:
{{
  "status": "🔴 发现已有相同工作（存在思想撞车/抄袭风险）" 或 "🟡 主要属于相近工作的增量改进" 或 "🟢 在检索范围内未见实质重叠（原创性较好）" 或 "信息不足",
  "summary": "200字左右总结：全面评析论文声称的各项创新点是否足够创新，哪些点撞车、哪些点是增量、哪些点原创或信息不足。",
  "taxonomy_tree": {{
    "root_topic": "核心研究领域或核心任务名称",
    "target_position": "待审论文所采用的技术方向",
    "branches": [
      {{
        "name": "方向名称",
        "description": "说明该方向技术特征",
        "papers": ["lit_1"],
        "is_target_branch": true
      }}
    ]
  }},
  "comparisons": [
    {{
      "claim": "所审查的完整创新点标题",
      "taxonomy_branch": "归属的技术方向",
      "source_id": "lit_1",
      "judgment": "🔴 已被前人做过（撞车/疑似思想抄袭）" 或 "🟡 存在相近工作（增量改进）" 或 "🟢 未见相同工作（原创性良好）" 或 "信息不足",
      "verdict_level": "duplicate" 或 "incremental" 或 "novel" 或 "uncertain",
      "prior_works_summary": "概括前人在此方向已有的主要做法与代表作",
      "prosecutor_overlap": "指控：指出与对标文献具体重合或相似的思想、机制",
      "defender_novelty": "抗辩：指出待审论文独有的差异化改进或新增机制",
      "difference": "法官裁定：明确指出两者核心思想的实质重合点、增量差异（Delta）或缺乏可比文献的原因",
      "paper_quote": "摘录论文中主张该创新点的连续原句",
      "source_quote": "摘录对标文献中已有类似论述的连续原句"
    }}
  ]
}}
"""
    )

    try:
        res, err = client.call(prompt, mode)
    except Exception as exc:
        log.warning("assess model call error: %s", exc)
        base["summary"] = f"模型比对调用异常，未能完成创新性评估：{exc}"
        base["notes"].append(f"创新性比对模型调用失败：{exc}")
        return base

    if err or not isinstance(res, dict):
        reason = err or "模型返回格式无效"
        log.warning("assess model failed: %s", reason)
        base["summary"] = f"模型比对调用异常，未能完成创新性评估：{reason}"
        base["notes"].append(f"创新性比对模型调用失败：{reason}")
        return base

    lookup = {s["id"]: s for s in sources}
    if res.get("summary"):
        base["summary"] = res["summary"]
    if res.get("taxonomy_tree") and isinstance(res["taxonomy_tree"], dict):
        branches = res["taxonomy_tree"].get("branches")
        if isinstance(branches, list):
            valid_branches = []
            for b in branches:
                if isinstance(b, dict) and b.get("name"):
                    b_copy = dict(b)
                    b_copy["papers"] = [
                        pid for pid in (b.get("papers") or []) if pid in lookup
                    ]
                    valid_branches.append(b_copy)
            if valid_branches:
                res["taxonomy_tree"]["branches"] = valid_branches
                base["taxonomy_tree"] = res["taxonomy_tree"]

    raw_comps = res.get("comparisons") or res.get("findings") or []
    valid_comps: list[dict] = []
    uncovered_claim_idx = 0

    for item in raw_comps:
        if not isinstance(item, dict):
            continue
        item = dict(item)

        if not item.get("claim") and claims and uncovered_claim_idx < len(claims):
            item["claim"] = claims[uncovered_claim_idx]["claim"]
            uncovered_claim_idx += 1

        sid = item.get("source_id") or ""
        source = lookup.get(sid) if sid else None
        is_uncertain_item = (
            item.get("verdict_level") == "uncertain"
            or item.get("judgment") == "信息不足"
        )

        if sid and not source:
            if not is_uncertain_item:
                continue
            sid = ""
            item["source_id"] = ""

        if not source and not is_uncertain_item:
            continue

        pq = clean_text(item.get("paper_quote", ""))
        sq = clean_text(item.get("source_quote", ""))
        diff = clean_text(item.get("difference", ""))

        if is_uncertain_item and not source:
            if not diff:
                diff = "当前候选文献库中缺少同任务或同核心机制的直接可比文献，建议补充检索或人工复核。"
                item["difference"] = diff
            if pq:
                is_pq_grounded, _ = check_quote_in_text(pq, paper)
                item["quote_grounded"] = is_pq_grounded
            else:
                item["quote_grounded"] = False
            item["source_id"] = ""
            item["verdict_level"] = "uncertain"
            item["judgment"] = "信息不足"
            valid_comps.append(item)
            continue

        assert source is not None
        if not pq or not sq or not diff:
            base["notes"].append(f"{sid} 缺少必要引文或差异说明，未计入对比。")
            continue

        # Numerical consistency validation (ignore model/version alphanumeric tokens like YOLOv5s, Llama3-8B)
        diff_clean = re.sub(r"lit_\d+|\[\d+\]", "", diff, flags=re.I)
        source_pool_text = " ".join(
            [
                str(pq),
                str(sq),
                str(source.get("year") or ""),
                str(source.get("title") or ""),
                str(source.get("abstract") or ""),
                str(source.get("tldr") or ""),
                paper_context,
            ]
        )
        source_numbers = set(STANDALONE_NUM_RE.findall(source_pool_text))
        if re.search(r"https?://|10\.\d{4,9}/", diff):
            base["notes"].append("模型比较含未登记的引用表达，未进入报告。")
            continue
        if set(STANDALONE_NUM_RE.findall(diff_clean)) - source_numbers:
            base["notes"].append("模型比较含引文之外的数值，未进入报告。")
            continue

        is_pq_grounded, _ = check_quote_in_text(pq, paper)
        source_text_pool = " ".join(
            filter(None, [source.get("abstract"), source.get("tldr"), source.get("title")])
        )
        is_sq_grounded, _ = check_quote_in_text(sq, source_text_pool)

        item["quote_grounded"] = bool(is_pq_grounded and is_sq_grounded)
        if not is_pq_grounded:
            base["notes"].append(
                f"创新点【{item.get('claim', '')[:20]}】的论文引文片段未在原文匹配，已降级为信息不足。"
            )
            if _classify_verdict(item) in {"duplicate", "incremental", "novel"}:
                item["verdict_level"] = "uncertain"
                item["judgment"] = "信息不足"
        if not is_sq_grounded:
            base["notes"].append(
                f"创新点【{item.get('claim', '')[:20]}】的对标文献引文未在摘要匹配，已降级为信息不足。"
            )
            item["verdict_level"] = "uncertain"
            item["judgment"] = "信息不足"

        if not source.get("abstract") and not source.get("tldr"):
            item["judgment"] = "信息不足"
            item["verdict_level"] = "uncertain"

        valid_comps.append(item)

    # Account for any uncovered or validation-rejected claims honestly as uncertain (never fake novel)
    if claims:
        covered_indices: set[int] = set()
        for c in valid_comps:
            idx = _match_claim_index(c.get("claim", ""), claims)
            if idx is not None:
                covered_indices.add(idx)
        for idx, orig_c in enumerate(claims):
            if idx in covered_indices:
                continue
            claim_str = orig_c.get("claim") if isinstance(orig_c, dict) else str(orig_c)
            if not claim_str:
                continue
            base["notes"].append(
                f"创新点【{claim_str[:20]}】未产生通过引文与一致性核验的比对结论，已标为信息不足。"
            )
            valid_comps.append(
                {
                    "claim": claim_str,
                    "taxonomy_branch": "待人工核实",
                    "source_id": "",
                    "judgment": "信息不足",
                    "verdict_level": "uncertain",
                    "prior_works_summary": "在当前检索与校验范围内，未形成有效可比的先验文献证据。",
                    "prosecutor_overlap": "未取得通过引文核验的重叠证据。",
                    "defender_novelty": "缺少可比对标文献或引文核验未通过，暂不作原创性定论。",
                    "difference": "缺少通过核验的同领域对照文献或引文证据，建议人工补充检索确认。",
                    "paper_quote": "",
                    "source_quote": "",
                    "quote_grounded": False,
                }
            )

    base["comparisons"] = valid_comps
    if not base["comparisons"]:
        base["status"] = "信息不足"
        base["summary"] = (
            "由于未能取得通过双边原文核验的有效对比证据，暂无法形成确切的创新性/思想撞车判断。"
        )
        base["notes"].append("未得到有效的相关工作比较，不能形成创新性判断。")
        return base

    classes = [_classify_verdict(c) for c in valid_comps]
    dup_count = classes.count("duplicate")
    inc_count = classes.count("incremental")
    nov_count = classes.count("novel")
    unc_count = classes.count("uncertain")
    legacy_judgments = [
        c.get("judgment")
        for c, cls in zip(valid_comps, classes)
        if cls == "legacy" and c.get("judgment")
    ]

    if dup_count > 0:
        base["status"] = "🔴 发现已有相同工作（存在思想撞车/抄袭风险）"
    elif inc_count > 0:
        base["status"] = "🟡 主要属于相近工作的增量改进"
    elif nov_count > 0 and unc_count == 0:
        base["status"] = "🟢 在检索范围内未见实质重叠（原创性较好）"
    elif nov_count > 0 and unc_count > 0:
        base["status"] = "🟡 部分创新点信息不足（其余未见实质重叠）"
    elif legacy_judgments:
        base["status"] = (
            "创新差异尚不清楚"
            if "创新差异尚不清楚" in legacy_judgments
            else legacy_judgments[0]
        )
    else:
        base["status"] = "信息不足"

    return base
