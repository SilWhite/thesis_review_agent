"""Read the introduction and assess rules 8 and 9."""

from .reading import pieces, batches, ask, finding, audit


def review_intro(checker, tree, intro, mode):
    # Keep headings and diagram labels here: they may describe the chapter links.
    toc_pages = {p.page_num for p in tree.pages if p.is_toc}
    source = pieces(
        [
            p
            for p in intro.paragraphs
            if p.text.strip() and not p.is_footnote and p.page not in toc_pages
        ],
        intro.title,
    )
    total = sum(len(p.text) for p in source)
    mapped, read, errors = [], 0, 0
    failures = []
    titles = [ch.title for ch in tree.chapters if ch.level == 1]
    # Intro maps return two summaries per batch, rather than a record per piece.
    # Tiny diagram labels therefore do not need the body reader's eight-piece cap.
    work = [(batch, 0) for batch in batches(source, max_pieces=64)]
    for batch, depth in work:
        result, error = ask(
            checker,
            "第一章阅读记录。阅读全部材料，为规则8和9各返回一条记录。此步骤只整理已有内容，不能因一个片段缺少内容判整章缺失。"
            "8关注：现有研究不足、本文具体要解决的问题、二者的联系。9关注：各章共同目标、前后承接、输入输出。"
            "证据须保留完整含义，跨段断句时连续引用。规则9优先摘录方法之间的使用、融合、支撑与系统集成关系，"
            "这些联系可写在研究内容中，无须出现章节编号；只列章名不能代替关系证据。"
            "允许各种同义表达。保留图示可能包含关系的线索。"
            "只能引用pieces中的逐字原文；未写出的章节联系不得靠常识补全。"
            '格式 {"findings":[{"rule_id":8,"complete":true,"summary":"本片段内容摘要，最多200字",'
            '"evidence":[{"quote":"8至240字逐字原文，最多6条，不改写","meaning":"含义"}]},'
            '{"rule_id":9,"complete":true,"summary":"本片段章节联系内容摘要",'
            '"evidence":[{"quote":"8至240字逐字原文，最多6条，不改写","meaning":"含义"}]}]}。'
            "没有相关内容时evidence为空，仍须返回两条complete记录。",
            {
                "pieces": [
                    {
                        "id": p.key,
                        "text": p.text,
                        "kind": (
                            "diagram_text_without_arrows"
                            if p.para.is_figure_text or p.para.is_caption
                            else "text"
                        ),
                    }
                    for p in batch
                ]
            },
            mode,
        )
        records = result.get("findings", []) if result else []
        valid = (
            not error
            and len(records) == 2
            and all(isinstance(r.get("rule_id"), int) for r in records)
            and {r.get("rule_id") for r in records} == {8, 9}
        )
        cleaned = []
        for r in records if valid else []:
            if (
                r.get("complete") is not True
                or not isinstance(r.get("summary"), str)
                or not r["summary"].strip()
                or not isinstance(r.get("evidence"), list)
            ):
                valid = False
                break
            proofs = [
                (
                    finding(
                        r["rule_id"],
                        {**e, "issue": "阅读证据"},
                        batch,
                        "阅读依据",
                        True,
                    )
                    if isinstance(e, dict)
                    else None
                )
                for e in r["evidence"]
            ]
            if any(proof is None for proof in proofs):
                valid = False
                break
            cleaned.append(
                {
                    **r,
                    "evidence": [
                        {
                            **e,
                            "source_kind": (
                                "diagram_text_without_arrows"
                                if all(
                                    any(
                                        p.para.id == loc.block_id
                                        and (p.para.is_figure_text or p.para.is_caption)
                                        for p in batch
                                    )
                                    for loc in proof.locations
                                )
                                else "text"
                            ),
                        }
                        for e, proof in zip(r["evidence"], proofs)
                    ],
                }
            )
        if not valid:
            if (
                depth < 2
                and mode != "mock"
                and not (error and any(w in error for w in ("未配置", "模拟模式")))
            ):
                if len(batch) > 1:
                    middle = len(batch) // 2
                    work.extend(
                        [(batch[:middle], depth + 1), (batch[middle:], depth + 1)]
                    )
                else:
                    work.append((batch, depth + 1))
                continue
            errors += 1
            failures.append(f"第{batch[0].para.page}页起“{batch[0].text[:18].strip()}”")
            continue
        mapped.extend(cleaned)
        read += sum(len(p.text) for p in batch)
    fs, audits = [], []
    for rule in (8, 9):
        own, uncertain = [], 0
        # Absence can only be judged after the entire chapter was read successfully.
        if source and not errors:
            result, error = ask(
                checker,
                f"第一章全局汇总规则{rule}。以下记录覆盖完整第一章，请综合所有片段判断。"
                "规则8要求在现状分析基础上提炼具体待解决问题，说明与已有不足的联系；无须固定词语或固定段落位置。"
                "仅写“解决关键问题”等空泛口号或问题与现状无关，仍可能违规。"
                "规则9要求说明各章如何共同解决问题、如何承接；只列各章名称和内容不足以说明有机联系。"
                "图示可表达联系；若有关系图线索但文字不足以读出箭头含义，返回uncertain。图示本身并非强制。"
                "必须以evidence中的逐字原文为依据，summary中的评价不能代替证据。"
                "已确认读完整章；若全文只有章节列表，没有承接说明，也没有实际存在但无法读取的关系图线索，应判finding。"
                "不得假设未提供的图示存在；uncertain用于确有读取障碍或实质歧义，不能用来回避明确缺失。"
                '返回恰好一条 {"findings":[{"rule_id":数字,"verdict":"pass|finding|uncertain",'
                '"quote":"来自记录的相关完整原文，至少8字","issue":"结合原文说明判断理由","suggestion":"建议"}]}。'
                "pass也必须提供支持判断的原文。finding要说明读完整章后缺少的联系以及引用段落的实际内容，不能把缺失本身伪造成原文。",
                {
                    "chapter_titles": titles,
                    "records": [r for r in mapped if r["rule_id"] == rule],
                },
                mode,
            )
            rs = result.get("findings", []) if result else []
            r = rs[0] if len(rs) == 1 else {}
            if (
                error
                or r.get("rule_id") != rule
                or r.get("verdict") not in ("pass", "finding", "uncertain")
            ):
                uncertain += 1
            elif r["verdict"] == "uncertain":
                uncertain += 1
            else:
                f = finding(
                    rule,
                    r,
                    source,
                    "已读完整第一章；证据展示相关现状、研究目标或章节说明。",
                    True,
                )
                if not f:
                    uncertain += 1
                elif all(
                    any(
                        p.para.id == loc.block_id
                        and (p.para.is_figure_text or p.para.is_caption)
                        for p in source
                    )
                    for loc in f.locations
                ):
                    uncertain += 1
                elif r["verdict"] == "finding":
                    own.append(f)
        fs.extend(own)
        audits.append(
            audit(
                rule,
                own,
                total,
                read,
                errors,
                uncertain,
                "检查范围：完整第一章及全文章标题。"
                + ("未完成：" + "；".join(failures) if failures else ""),
            )
        )
    return fs, audits
