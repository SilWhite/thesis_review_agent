"""Deterministic text and citation checks (Rules: 2, 12, 17, 18, 19, 20, 24, 35, 36)."""

import re
from typing import List, Tuple
from app.schemas import Finding, EvidenceLocation, RuleAuditItem, CheckStatus
from app.documents.models import ThesisDocumentTree
from app.documents.formula_symbols import unreadable


def _expand_citations_in_text(text: str) -> List[int]:
    """Extract and expand all cited numbers in bracket references, e.g. [1, 3-5], [22−31], ［1-3］ -> 1, 3, 4, 5."""
    cited_nums = []
    # Match both standard [ ... ] and fullwidth ［ ... ］
    for m in re.finditer(r"[\[［]([0-9,，\s\-–—−－~～]+)[\]］]", text):
        content = m.group(1).strip()
        parts = re.findall(r"\d+\s*[-–—−－~～]\s*\d+|\d+", content)
        for part in parts:
            part = part.strip()
            if not part:
                continue
            if re.match(r"^\d+$", part):
                cited_nums.append(int(part))
            elif re.match(r"^(\d+)\s*[-–—−－~～]\s*(\d+)$", part):
                m_range = re.match(r"^(\d+)\s*[-–—−－~～]\s*(\d+)$", part)
                start_n, end_n = int(m_range.group(1)), int(m_range.group(2))
                if start_n <= end_n and end_n - start_n <= 80:
                    cited_nums.extend(range(start_n, end_n + 1))
    return cited_nums


class DeterministicChecker:
    def check_all(
        self, tree: ThesisDocumentTree
    ) -> Tuple[List[Finding], List[RuleAuditItem]]:
        findings: List[Finding] = []
        audit_items: List[RuleAuditItem] = []

        f_r2, a_r2 = self._check_rule_2_duplicate_sentences(tree)
        findings.extend(f_r2)
        audit_items.append(a_r2)

        f_r12, a_r12 = self._check_rule_12_formula_number(tree)
        findings.extend(f_r12)
        audit_items.append(a_r12)

        f_r17, a_r17 = self._check_rule_17_reference_ordering(tree)
        findings.extend(f_r17)
        audit_items.append(a_r17)

        f_r18, a_r18 = self._check_rule_18_reference_unreferenced(tree)
        findings.extend(f_r18)
        audit_items.append(a_r18)

        f_r19, a_r19 = self._check_rule_19_reference_incomplete(tree)
        findings.extend(f_r19)
        audit_items.append(a_r19)

        f_r20, a_r20 = self._check_rule_20_reference_inconsistent_format(tree)
        findings.extend(f_r20)
        audit_items.append(a_r20)

        f_r24, a_r24 = self._check_rule_24_figures_tables_unreferenced(tree)
        findings.extend(f_r24)
        audit_items.append(a_r24)

        f_r35, a_r35 = self._check_rule_35_punctuation_abuse(tree)
        findings.extend(f_r35)
        audit_items.append(a_r35)

        f_r36, a_r36 = self._check_rule_36_we_usage(tree)
        findings.extend(f_r36)
        audit_items.append(a_r36)

        return findings, audit_items

    def _check_rule_2_duplicate_sentences(
        self, tree: ThesisDocumentTree
    ) -> Tuple[List[Finding], RuleAuditItem]:
        findings = []
        rule_name = "大论文内部重复句子（连续10个词完全相同）"
        if not tree.all_body_paragraphs:
            return findings, RuleAuditItem(
                rule_id=2,
                rule_name=rule_name,
                category="确定性检查",
                status=CheckStatus.MISSING_INPUT.value,
                note="未提取到正文段落",
            )

        titles = []
        if tree.title_cn:
            titles.append(tree.title_cn)
        if tree.title_en:
            titles.append(tree.title_en)

        # Keep character positions: two sentences in one paragraph are distinct
        # occurrences, while repeated extraction of the same block is not.
        sentences = []
        seen_sources = set()
        for p in tree.all_body_paragraphs:
            if (
                p.is_heading
                or p.is_caption
                or p.is_formula
                or p.is_table_cell
                or p.is_figure_text
                or len(p.text) < 10
            ):
                continue
            source = (p.page, p.bbox if any(p.bbox) else p.id, p.text)
            if source in seen_sources:
                continue
            seen_sources.add(source)
            for match in re.finditer(
                r"[^。！？\n]+?(?:[.!?](?=\s|$)|(?=[。！？\n]|$))", p.text
            ):
                raw = match.group().strip()
                if len(raw) >= 10:
                    sentences.append(
                        (
                            raw,
                            p,
                            match.start()
                            + len(match.group())
                            - len(match.group().lstrip()),
                        )
                    )

        seen_grams = {}
        reported_pairs = set()
        for sentence_index, (s_text, p, sentence_start) in enumerate(sentences):
            is_cn = bool(re.search(r"[\u4e00-\u9fff]", s_text))
            if is_cn:
                positions = [i for i, c in enumerate(s_text) if not c.isspace()]
                tokens = [s_text[i] for i in positions]
            else:
                words = list(re.finditer(r"[A-Za-z0-9]+(?:['-][A-Za-z0-9]+)*", s_text))
                positions = [m.start() for m in words]
                tokens = [m.group() for m in words]
            gram_len = 20 if is_cn else 10
            for i in range(len(tokens) - gram_len + 1):
                # Do not begin/end halfway through an English word or number.
                if is_cn and (
                    (
                        i
                        and tokens[i - 1].isascii()
                        and tokens[i - 1].isalnum()
                        and tokens[i].isascii()
                        and tokens[i].isalnum()
                    )
                    or (
                        i + gram_len < len(tokens)
                        and tokens[i + gram_len - 1].isascii()
                        and tokens[i + gram_len - 1].isalnum()
                        and tokens[i + gram_len].isascii()
                        and tokens[i + gram_len].isalnum()
                    )
                ):
                    continue
                gram = (
                    "".join(tokens[i : i + gram_len])
                    if is_cn
                    else " ".join(tokens[i : i + gram_len])
                )
                if not is_cn and not any(
                    re.search(r"[A-Za-z]", word) for word in tokens[i : i + gram_len]
                ):
                    continue  # Numeric axes are not ten repeated words.

                if is_cn and len(re.findall(r"[\u4e00-\u9fff]", gram)) < 10:
                    continue
                if any(gram in t for t in titles):
                    continue
                end = positions[i + gram_len - 1] + (
                    1 if is_cn else len(tokens[i + gram_len - 1])
                )
                excerpt = s_text[positions[i] : end]
                occurrence = (
                    p,
                    s_text,
                    sentence_index,
                    sentence_start + positions[i],
                    excerpt,
                )
                if gram not in seen_grams:
                    seen_grams[gram] = occurrence
                    continue
                prev_p, prev_sent, prev_index, prev_offset, prev_excerpt = seen_grams[
                    gram
                ]
                if re.sub(r"\s+", "", prev_excerpt) != re.sub(r"\s+", "", excerpt):
                    continue
                pair = (prev_index, sentence_index)
                if prev_index == sentence_index or pair in reported_pairs:
                    continue
                reported_pairs.add(pair)
                findings.append(
                    Finding(
                        rule_id=2,
                        rule_category="确定性检查",
                        dimension="规范与逻辑",
                        severity="major",
                        status="supported",
                        block_id=p.id,
                        quote=gram,
                        locations=[
                            EvidenceLocation(
                                page=prev_p.page,
                                block_id=prev_p.id,
                                quote=prev_excerpt,
                                text_offset=prev_offset,
                                context=prev_sent,
                                description="首次出现位置",
                            ),
                            EvidenceLocation(
                                page=p.page,
                                block_id=p.id,
                                quote=excerpt,
                                text_offset=occurrence[3],
                                context=s_text,
                                description="重复出现位置",
                            ),
                        ],
                        issue=f"两处文字有连续相同的片段：{gram}",
                        suggestion="请对照两处原文，核对重复表述是否需要精简或合并。",
                        evidence_note="红框分别标出两处相同文字所在的行；同一段内的两次出现也分别定位。",
                    )
                )

        status = CheckStatus.FINDING.value if findings else CheckStatus.PASSED.value
        return findings, RuleAuditItem(
            rule_id=2,
            rule_name=rule_name,
            category="确定性检查",
            status=status,
            findings_count=len(findings),
        )

    def _check_rule_12_formula_number(
        self, tree: ThesisDocumentTree
    ) -> Tuple[List[Finding], RuleAuditItem]:
        findings = []
        rule_name = "公式缺少编号"
        all_formulas = []
        for ch in tree.chapters:
            all_formulas.extend(ch.formulas)

        if not all_formulas:
            return findings, RuleAuditItem(
                rule_id=12,
                rule_name=rule_name,
                category="确定性检查",
                status=CheckStatus.UNCERTAIN.value,
                note="未识别到独立公式，无法确认编号是否完整",
            )

        uncertain_count = 0
        for f in all_formulas:
            if not f.has_number and f.numbering_status == "uncertain":
                uncertain_count += 1
                continue
            if not f.has_number:
                findings.append(
                    Finding(
                        rule_id=12,
                        rule_category="确定性检查",
                        dimension="规范与逻辑",
                        severity="minor",
                        status="supported",
                        block_id=f"f_p{f.page}",
                        quote=f.text[:40],
                        locations=[
                            EvidenceLocation(
                                page=f.page, quote=f.text, description="缺少编号的公式"
                            )
                        ],
                        issue="检测到该独立行数学公式右侧缺少标准公式编号（如 (3.1)）。",
                        suggestion="请按照学位论文撰写规范，为正文中具有核心推导意义的独立公式在右端添加按章连续编号。",
                    )
                )

        status = (
            CheckStatus.FINDING.value
            if findings
            else (
                CheckStatus.UNCERTAIN.value
                if uncertain_count
                else CheckStatus.PASSED.value
            )
        )
        return findings, RuleAuditItem(
            rule_id=12,
            rule_name=rule_name,
            category="确定性检查",
            status=status,
            findings_count=len(findings),
            note=(
                f"{uncertain_count} 个公式区域读取不完整，未据此判断缺少编号"
                if uncertain_count
                else None
            ),
        )

    def _check_rule_17_reference_ordering(
        self, tree: ThesisDocumentTree
    ) -> Tuple[List[Finding], RuleAuditItem]:
        findings = []
        rule_name = "参考文献未排序"
        if not tree.references:
            return findings, RuleAuditItem(
                rule_id=17,
                rule_name=rule_name,
                category="确定性检查",
                status=CheckStatus.MISSING_INPUT.value,
                note="未提取到文末参考文献列表",
            )

        # 1. Check numeric sequence in reference list
        nums = []
        for r in tree.references:
            if r.id_str.isdigit():
                nums.append((int(r.id_str), r))

        if nums and nums[0][0] != 1:
            first_n, first_r = nums[0]
            findings.append(
                Finding(
                    rule_id=17,
                    rule_category="确定性检查",
                    severity="major",
                    block_id=f"ref_{first_r.id_str}",
                    quote=first_r.raw_text[:60],
                    locations=[
                        EvidenceLocation(
                            page=first_r.page_num,
                            quote=first_r.raw_text,
                            description="首条文献",
                        )
                    ],
                    issue=f"参考文献列表从 [{first_n}] 开始，未从 [1] 开始。",
                    suggestion="请核对参考文献编号是否完整并按要求排序。",
                )
            )

        for idx in range(len(nums) - 1):
            curr_n, curr_r = nums[idx]
            next_n, next_r = nums[idx + 1]
            if next_n != curr_n + 1:
                findings.append(
                    Finding(
                        rule_id=17,
                        rule_category="确定性检查",
                        dimension="规范与逻辑",
                        severity="major",
                        status="supported",
                        block_id=f"ref_{curr_r.id_str}",
                        quote=curr_r.raw_text[:50],
                        locations=[
                            EvidenceLocation(
                                page=curr_r.page_num,
                                quote=curr_r.raw_text[:60],
                                description="前一条目序号",
                            ),
                            EvidenceLocation(
                                page=next_r.page_num,
                                quote=next_r.raw_text[:60],
                                description="后一条目序号异常",
                            ),
                        ],
                        issue=f"参考文献列表序号未连续单调递增（[{curr_n}] 后紧跟 [{next_n}]）。",
                        suggestion="请使用文献管理工具重新生成参考文献列表，确保编号严格自 1 起递增无跳号或错位。",
                    )
                )
                break

        # 2. Check first appearance order in body text
        all_cited = _expand_citations_in_text(tree.body_text_only)
        first_cites = []
        for n in all_cited:
            if n not in first_cites:
                first_cites.append(n)

        # Check for strict sequential first citations (e.g. [2] appears before [1])
        max_seen = 0
        for n in first_cites:
            if n > max_seen:
                max_seen = n
            elif n < max_seen:
                findings.append(
                    Finding(
                        rule_id=17,
                        rule_category="确定性检查",
                        dimension="规范与逻辑",
                        severity="minor",
                        status="supported",
                        block_id="cite_order",
                        quote=f"[{n}]",
                        locations=[
                            EvidenceLocation(
                                description=f"在正文中先首次引用了较大编号，其后才首次出现 [{n}]"
                            )
                        ],
                        issue=f"正文首次引用顺序未按顺序编码制递增：在已引用至 [{max_seen}] 后首次引用了 [{n}]。",
                        suggestion="顺序编码制要求参考文献在正文中首次出现的顺序必须为 1, 2, 3...，请调整引用标号或文末排布顺序。",
                    )
                )
                break

        status = CheckStatus.FINDING.value if findings else CheckStatus.PASSED.value
        return findings, RuleAuditItem(
            rule_id=17,
            rule_name=rule_name,
            category="确定性检查",
            status=status,
            findings_count=len(findings),
        )

    def _check_rule_18_reference_unreferenced(
        self, tree: ThesisDocumentTree
    ) -> Tuple[List[Finding], RuleAuditItem]:
        findings = []
        rule_name = "参考文献未被引用"
        if not tree.references:
            return findings, RuleAuditItem(
                rule_id=18,
                rule_name=rule_name,
                category="确定性检查",
                status=CheckStatus.MISSING_INPUT.value,
                note="未提取到参考文献",
            )

        # Crucial fix: ONLY search inside body_text_only (exclude the reference list itself!)
        all_cited_nums = set(_expand_citations_in_text(tree.body_text_only))

        # If thesis uses footnote citations or Author-Year (very few/no bracket citations in body despite many references)
        if len(tree.references) >= 15 and len(all_cited_nums) < 5:
            return findings, RuleAuditItem(
                rule_id=18,
                rule_name=rule_name,
                category="确定性检查",
                status=CheckStatus.UNCERTAIN.value,
                note="正文识别到的数字引用过少，无法可靠判断引用方式或文献是否被引用",
            )

        for r in tree.references:
            if r.id_str.isdigit():
                num_int = int(r.id_str)
                if num_int not in all_cited_nums:
                    findings.append(
                        Finding(
                            rule_id=18,
                            rule_category="确定性检查",
                            dimension="规范与逻辑",
                            severity="major",
                            status="supported",
                            block_id=f"ref_{r.id_str}",
                            quote=r.raw_text[:60],
                            locations=[
                                EvidenceLocation(
                                    page=r.page_num,
                                    quote=r.raw_text,
                                    description="未被引用的文献条目",
                                )
                            ],
                            issue=f"参考文献条目 [{r.id_str}] 在正文任何位置均未被引用。",
                            suggestion=f"学术论文文末参考文献必须与正文呼应，请在正文相关论述处引用 [{r.id_str}]，或从文末列表中删除该条目。",
                        )
                    )

        status = CheckStatus.FINDING.value if findings else CheckStatus.PASSED.value
        return findings, RuleAuditItem(
            rule_id=18,
            rule_name=rule_name,
            category="确定性检查",
            status=status,
            findings_count=len(findings),
        )

    def _check_rule_19_reference_incomplete(
        self, tree: ThesisDocumentTree
    ) -> Tuple[List[Finding], RuleAuditItem]:
        findings = []
        rule_name = "参考文献信息不全"
        if not tree.references:
            return findings, RuleAuditItem(
                rule_id=19,
                rule_name=rule_name,
                category="确定性检查",
                status=CheckStatus.MISSING_INPUT.value,
                note="未提取到参考文献",
            )

        re_year = re.compile(r"(?<!\d)(19|20)\d{2}(?!\d)")
        re_pages = re.compile(
            r"(\d+\s*[-–—~～]\s*\d+|pp?\.?\s*\d+|:\s*[eE]?\d+|\b\d+\(\d+\)|\b\d+:\s*\d+)"
        )
        re_locator = re.compile(
            r":\s*(?=[A-Za-z0-9_.-]*\d)[A-Za-z][A-Za-z0-9_.-]+|\babs/\d{4}\.\d+", re.I
        )

        unreadable_refs = 0
        for r in tree.references:
            t = r.raw_text
            if unreadable(t):
                unreadable_refs += 1
                continue
            missing = []
            if not re_year.search(t):
                if not re.search(r"arXiv:\s*\d{4}\.\d+", t, re.IGNORECASE):
                    missing.append("缺失出版年份")
            if re.search(r"\[J\]\s*[.。]?\s*[,，]+\s*(?:19|20)\d{2}", t, re.I):
                missing.append("缺失出版来源")
            # Only journals and conference papers need page/article identifiers
            if re.search(r"\[(?:J|C)\]", t, re.I) or "期刊" in t:
                # Online resources or preprints do not require print page numbers
                pageless_venue = bool(
                    re.search(
                        r"international conference on learning representations|\bICLR\b",
                        t,
                        re.I,
                    )
                )
                if not pageless_venue and not any(
                    kw in t.lower()
                    for kw in [
                        "/ol",
                        "eb/ol",
                        "arxiv",
                        "preprint",
                        "doi",
                        "http",
                        "openreview",
                        "in press",
                        "early access",
                        "forthcoming",
                        "online",
                        "ssrn",
                    ]
                ):
                    if (
                        not re_pages.search(t)
                        and not re_locator.search(t)
                        and not re.search(
                            r"\b(article|e\d{4,}|\d{5,})\b", t, re.IGNORECASE
                        )
                    ):
                        if not re.search(r",\s*(19|20)\d{2},\s*\d{1,3}\s*\.?\s*$", t):
                            missing.append("缺失起止页码或文章号")

            if missing:
                locations = []
                for page in r.source_pages or [r.page_num]:
                    segments = [p for p in r.segments if p.page == page]
                    text = " ".join(p.text for p in segments) if segments else t
                    bbox = (
                        [
                            min(p.bbox[0] for p in segments),
                            min(p.bbox[1] for p in segments),
                            max(p.bbox[2] for p in segments),
                            max(p.bbox[3] for p in segments),
                        ]
                        if segments
                        else None
                    )
                    locations.append(
                        EvidenceLocation(
                            page=page,
                            quote=text,
                            context=text,
                            bbox=bbox,
                            verified=bool(segments),
                            description=f"参考文献 [{r.id_str}] 的本页原文",
                        )
                    )
                findings.append(
                    Finding(
                        rule_id=19,
                        rule_category="确定性检查",
                        dimension="规范与逻辑",
                        severity="minor",
                        status=(
                            "supported"
                            if "缺失出版年份" in missing
                            else "pending_verification"
                        ),
                        block_id=f"ref_{r.id_str}",
                        quote=t,
                        locations=locations,
                        evidence_note=f"已合并该条目在 PDF 第 {', '.join(str(p) for p in (r.source_pages or [r.page_num]))} 页的文字后检查：{', '.join(missing)}。",
                        issue=f"参考文献条目 [{r.id_str}] 元数据信息不全：{', '.join(missing)}。",
                        suggestion="请核对原出版记录，补齐缺少年份；页码或文章号须结合在线发表状态确认。",
                    )
                )

        status = (
            CheckStatus.FINDING.value
            if findings
            else (
                CheckStatus.UNCERTAIN.value
                if unreadable_refs
                else CheckStatus.PASSED.value
            )
        )
        return findings, RuleAuditItem(
            rule_id=19,
            rule_name=rule_name,
            category="确定性检查",
            status=status,
            findings_count=len(findings),
            note=(
                f"{unreadable_refs} 条文献含有未识别文字，未据此判断信息缺失"
                if unreadable_refs
                else None
            ),
        )

    def _check_rule_20_reference_inconsistent_format(
        self, tree: ThesisDocumentTree
    ) -> Tuple[List[Finding], RuleAuditItem]:
        findings = []
        rule_name = "参考文献格式不统一"
        if len(tree.references) < 2:
            return findings, RuleAuditItem(
                rule_id=20,
                rule_name=rule_name,
                category="确定性检查",
                status=CheckStatus.UNCERTAIN.value,
                note="参考文献少于两条，无法比较格式",
            )

        has_bracket_type = 0
        no_bracket_type = 0
        for r in tree.references:
            if re.search(r"\[[A-Z]+(/[A-Z]+)?\]", r.raw_text):
                has_bracket_type += 1
            else:
                no_bracket_type += 1

        if has_bracket_type > 0 and no_bracket_type > 0:
            sample_with = next(
                r
                for r in tree.references
                if re.search(r"\[[A-Z]+(/[A-Z]+)?\]", r.raw_text)
            )
            sample_without = next(
                r
                for r in tree.references
                if not re.search(r"\[[A-Z]+(/[A-Z]+)?\]", r.raw_text)
            )
            findings.append(
                Finding(
                    rule_id=20,
                    rule_category="确定性检查",
                    dimension="规范与逻辑",
                    severity="minor",
                    status="supported",
                    block_id="ref_inconsistent",
                    quote=f"[{sample_with.id_str}] vs [{sample_without.id_str}]",
                    locations=[
                        EvidenceLocation(
                            page=sample_with.page_num,
                            quote=sample_with.raw_text[:60],
                            description="含文献类型标识",
                        ),
                        EvidenceLocation(
                            page=sample_without.page_num,
                            quote=sample_without.raw_text[:60],
                            description="缺失文献类型标识",
                        ),
                    ],
                    issue="参考文献条目格式不统一：部分条目带有标准文献类型标识（如 [J], [C]），部分条目则缺失。",
                    suggestion="请全篇统一参考文献格式，统一采用带文献类型标志代码（如 [J]、[M]、[D]）的 GB/T 7714 格式。",
                )
            )

        status = CheckStatus.FINDING.value if findings else CheckStatus.PASSED.value
        return findings, RuleAuditItem(
            rule_id=20,
            rule_name=rule_name,
            category="确定性检查",
            status=status,
            findings_count=len(findings),
        )

    def _check_rule_24_figures_tables_unreferenced(
        self, tree: ThesisDocumentTree
    ) -> Tuple[List[Finding], RuleAuditItem]:
        findings = []
        rule_name = "图表未在正文中提及和引用"
        all_figs = []
        all_tbls = []
        for ch in tree.chapters:
            all_figs.extend(ch.figures)
            all_tbls.extend(ch.tables)

        from app.review.checks.citations import references, number_key

        cited = references(tree.body_text_only)
        seen = set()
        for kind, label, objects in [
            ("figure", "图", all_figs),
            ("table", "表", all_tbls),
        ]:
            for item in objects:
                key = number_key(item.num)
                if (kind, key) in seen or (kind == "figure" and item.is_subfig):
                    continue
                seen.add((kind, key))
                if key in cited[kind]:
                    continue
                findings.append(
                    Finding(
                        rule_id=24,
                        rule_category="确定性检查",
                        dimension="规范与逻辑",
                        severity="major",
                        status="pending_verification",
                        block_id=f"{kind}_{item.num}",
                        quote=item.caption,
                        locations=[
                            EvidenceLocation(
                                page=item.page,
                                quote=item.caption,
                                bbox=list(item.bbox),
                                description=f"{label}题所在位置",
                            )
                        ],
                        evidence_note=f"已检查识别出的正文，未找到{label}{item.num}的引用；请重点核对相关段落。图题和目录不计作正文引用。",
                        measurement=f"查找编号：{label}{item.num}（兼容点号、连接号及成组引用）",
                        issue=f"{label} {item.num} 在已识别正文中未找到显式引用。",
                        suggestion=f"请核对相关正文是否引用了{label}{item.num}；确认缺失后补充引用和分析。",
                    )
                )

        status = CheckStatus.FINDING.value if findings else CheckStatus.PASSED.value
        return findings, RuleAuditItem(
            rule_id=24,
            rule_name=rule_name,
            category="确定性检查",
            status=status,
            findings_count=len(findings),
        )

    def _check_rule_35_punctuation_abuse(
        self, tree: ThesisDocumentTree
    ) -> Tuple[List[Finding], RuleAuditItem]:
        findings = []
        rule_name = "标点符号滥用"
        # 1. 一逗到底
        for p in tree.all_body_paragraphs:
            if p.is_heading:
                continue
            clauses = re.split(r"(?<=[.!?])\s+|[。！？\n]+", p.text)
            for c in clauses:
                # Comma abuse check is primarily for Chinese prose
                if re.search(r"[\u4e00-\u9fa5]", c):
                    comma_count = c.count("，") + c.count(",")
                    if comma_count >= 8 and len(c) > 180:
                        findings.append(
                            Finding(
                                rule_id=35,
                                rule_category="确定性检查",
                                dimension="规范与逻辑",
                                severity="minor",
                                status="supported",
                                block_id=p.id,
                                quote=c[:60] + "...",
                                locations=[
                                    EvidenceLocation(
                                        page=p.page,
                                        block_id=p.id,
                                        quote=c[:80],
                                        description="一逗到底长句",
                                    )
                                ],
                                issue="检测到段落内一'逗号'到底的超长复合句（单句内逗号超过 8 个且连续超 180 字未断句）。",
                                suggestion="建议根据分句语义合理拆分长句，适度使用句号或分号，增强学术论述的可读性与呼吸感。",
                            )
                        )
                        break

        # 2. 图题结尾加句号
        all_figs = []
        for ch in tree.chapters:
            all_figs.extend(ch.figures)
            all_figs.extend(ch.tables)
        for f in all_figs:
            c = f.caption.strip()
            if (c.endswith("。") or c.endswith(".")) and not re.search(
                r"[a-zA-Z]\.$", c
            ):
                findings.append(
                    Finding(
                        rule_id=35,
                        rule_category="确定性检查",
                        dimension="规范与逻辑",
                        severity="minor",
                        status="supported",
                        block_id=f"fig_{f.num}",
                        quote=c,
                        locations=[
                            EvidenceLocation(
                                page=f.page, quote=c, description="末尾带句号的图题"
                            )
                        ],
                        issue=f"短语型图题末尾不应加句号（检测到图题末尾带有句号：'{c[-5:]}'）。",
                        suggestion="根据标准规范，短语型图题和表题末尾通常不加句号，请删去末尾标点。",
                    )
                )

        status = CheckStatus.FINDING.value if findings else CheckStatus.PASSED.value
        return findings, RuleAuditItem(
            rule_id=35,
            rule_name=rule_name,
            category="确定性检查",
            status=status,
            findings_count=len(findings),
        )

    def _check_rule_36_we_usage(
        self, tree: ThesisDocumentTree
    ) -> Tuple[List[Finding], RuleAuditItem]:
        findings = []
        rule_name = "大论文中出现'我们'"
        re_we = re.compile(r"我们")

        paragraphs = [p for page in tree.pages for p in page.paragraphs]
        paragraphs.extend(tree.abstract_cn)
        paragraphs.extend(tree.abstract_en)
        paragraphs.extend(tree.all_body_paragraphs)
        seen = set()
        for p in paragraphs:
            identity = (p.page, p.id)
            if identity in seen:
                continue
            seen.add(identity)
            matches = list(re_we.finditer(p.text))
            if matches:
                m = matches[0]
                start = max(0, m.start() - 15)
                end = min(len(p.text), m.end() + 20)
                snippet = p.text[start:end]
                findings.append(
                    Finding(
                        rule_id=36,
                        rule_category="确定性检查",
                        dimension="规范与逻辑",
                        severity="minor",
                        status="supported",
                        block_id=p.id,
                        quote=snippet,
                        locations=[
                            EvidenceLocation(
                                page=p.page,
                                block_id=p.id,
                                quote=snippet,
                                description="包含'我们'的句子",
                            )
                        ],
                        issue=f"论文中出现'我们'（原句片段：'…{snippet}…'）。",
                        suggestion="中文学位论文应遵循客观、严谨的第三人称学术行文风格，建议将'我们'替换为'本文'、'本章'或'研究团队'，或直接转换为被动句式表达。",
                    )
                )

        status = CheckStatus.FINDING.value if findings else CheckStatus.PASSED.value
        return findings, RuleAuditItem(
            rule_id=36,
            rule_name=rule_name,
            category="确定性检查",
            status=status,
            findings_count=len(findings),
        )
