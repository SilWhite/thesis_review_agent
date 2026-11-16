"""Read body pieces, repair partial records and reassess rules 37 and 38."""

import re
from concurrent.futures import ThreadPoolExecutor
from .reading import (
    pieces,
    batches,
    ask,
    locate,
    finding,
    audit,
    prose_paragraph,
    body_record,
    review_logic_candidates,
)


def body_pieces(tree):
    paths, chapters = {}, {}
    for ci, ch in enumerate(tree.chapters):
        stack = [(1, ch.title)]
        for p in ch.paragraphs:
            if p.is_heading:
                level = max(1, p.heading_level)
                stack = [s for s in stack if s[0] < level] + [(level, p.text)]
            paths[id(p)] = " / ".join(s[1] for s in stack)
            chapters[id(p)] = f"{ci}:{ch.title}"
    body = tree.all_body_paragraphs or [
        p for ch in tree.chapters for p in ch.paragraphs
    ]
    body = [p for p in body if prose_paragraph(p, tree)]
    source = pieces(body, paths=paths)
    for p in source:
        p.chapter = chapters.get(id(p.para), "")
    return body, source


def read_batch(checker, source, batch, mode):
    material = []
    for p in batch:
        index = source.index(p)
        material.append(
            {
                "id": p.key,
                "section": p.section,
                "text": p.text,
                "before": source[index - 1].text[-350:] if index else "",
                "after": (
                    source[index + 1].text[:350] if index + 1 < len(source) else ""
                ),
            }
        )
    return ask(
        checker,
        "逐段核查规则37、38。对每个id必须返回一条记录，包括无问题的段落。"
        "37判断正文与所在章及小节标题的实质关系；合理背景、举例、实验、对比和必要铺垫均可相关。"
        "38逐句理解因果、转折、条件、递进、让步等关系，检查连词是否符合实际含义。"
        "不能仅按固定搭配判断，允许省略半边连词。正常因果或让步不报；引用错误观点不等于作者用错。"
        "只查逻辑连词含义冲突；普通语病、介词误用、漏字、重复和标点不属于38，不能报告。"
        "必须读完整段及邻接上下文，发现多个错误应全部返回。为减少输出，使用以下短键名。"
        '格式 {"findings":[{"id":"材料id","q":"本段逐字原文8至12字，短段全文",'
        '"t":"r","s":"本段主题，最多12字","l":"ok","e":[]}]}。'
        "t取r=主题相关、u=主题不符、?=无法判断；u时q须摘出偏离主题的关键原文，可到40字。"
        "l取ok=已逐句完成逻辑检查、?=已读但有实质语义无法判断。无逻辑连词的正常句子取ok。"
        'e是所有连词错误，格式 [{"q":"包含双方分句的逐字原文","c":"用错的逻辑连词",'
        '"i":"说明双方实际关系以及连词的冲突","a":"修改建议"}]；无错误必须为空数组。'
        "是、在、的等语病不能当作逻辑连词；不要因图表刻度或标签无法对应主题就判正文跑题。",
        material,
        mode,
    )


def review_chapter_topics(
    checker, source, topic_records, chapter_errors, findings, mode
):
    uncertain_count = 0
    for chapter, records in topic_records.items():
        records.sort(key=lambda pair: source.index(pair[0]))
        # Every piece is read; only chapters with an explicit mismatch need a second judgement.
        if (
            not chapter
            or chapter in chapter_errors
            or not any(r["topic"] == "unrelated" for _, r in records)
        ):
            continue
        result, error = ask(
            checker,
            "规则37整章复核。根据完整章节的逐段记录，判断是否存在持续、实质的标题与正文不符。"
            "单个短暂离题、合理背景、例子和对比不足以认定整章不符；小节持续跑题可针对该小节报告。"
            "必须明确实际正文主题、标题承诺主题、偏离范围及原因。"
            '返回 {"findings":[{"verdict":"pass|finding|uncertain","quote":"候选原文",'
            '"issue":"具体范围和主题冲突","suggestion":"建议"}]}；无问题也返回一条pass记录。'
            "多个独立小节存在问题可返回多条finding。",
            {
                "chapter": chapter,
                "records": [
                    {"id": p.key, "section": p.section, "chars": len(p.text), **r}
                    for p, r in records
                ],
            },
            mode,
        )
        rs = result.get("findings", []) if result else []
        if error or not rs:
            uncertain_count += 1
            continue
        for r in rs:
            if r.get("verdict") == "finding":
                f = finding(
                    37,
                    r,
                    [p for p, row in records if row["topic"] == "unrelated"],
                    "整章逐段阅读后复核；问题范围以说明中的章或小节为准。",
                )
                if f:
                    findings.append(f)
                else:
                    uncertain_count += 1
            elif (
                r.get("verdict") != "pass"
                or not isinstance(r.get("issue"), str)
                or not r["issue"].strip()
            ):
                uncertain_count += 1
    return uncertain_count


def index_records(result):
    records = result.get("findings", []) if result else []
    by_id = {}
    duplicate = set()
    for original in records:
        r = body_record(original)
        key = r.get("id")
        if isinstance(key, str):
            if key in by_id:
                duplicate.add(key)
            by_id[key] = r
    return by_id, duplicate


def review_body(checker, tree, mode, rules=(37, 38)):
    body, source = body_pieces(tree)
    total = sum(len(p.text) for p in source)
    read, errors, uncertain = (
        {r: 0 for r in rules},
        {r: 0 for r in rules},
        {r: 0 for r in rules},
    )
    found = {r: [] for r in rules}
    topic_records, chapter_errors = {}, set()
    diagnostics = {r: [] for r in rules}
    seen = set()

    # The existing inference service handles two independent requests at once.
    # Aggregate results in source order so coverage and deduplication stay deterministic.
    with ThreadPoolExecutor(max_workers=2) as pool:
        work = [
            (batch, False, pool.submit(read_batch, checker, source, batch, mode), {})
            for batch in batches(source)
        ]
        for batch, retried, future, saved in work:
            try:
                result, error = future.result()
            except Exception as exc:
                result, error = None, str(exc)
            by_id, duplicate = index_records(result)
            for p in batch:
                r = by_id.get(p.key, {})
                if error or p.key in duplicate:
                    r = {}
                anchor = locate(
                    r.get("read_quote"), [p], min(8, len(re.sub(r"\s+", "", p.text)))
                )
                if not anchor:
                    r = {}
                if p.key in saved:
                    first, good37, good38 = saved[p.key]
                    r = dict(r)
                    if good37:
                        r.update(
                            {
                                k: first.get(k)
                                for k in ("topic", "topic_summary", "topic_quote")
                            }
                        )
                    if good38:
                        r.update(
                            {
                                k: first.get(k)
                                for k in (
                                    "logic_complete",
                                    "logic_uncertain",
                                    "logic_issues",
                                )
                            }
                        )
                # Repair only failed pieces, once, with full text. Successful pieces
                # never consume a second coverage count or get silently sampled away.
                complete37 = (
                    r.get("topic") in ("related", "unrelated", "uncertain")
                    and isinstance(r.get("topic_summary"), str)
                    and bool(r["topic_summary"].strip())
                    and (r["topic"] != "unrelated" or locate(r.get("topic_quote"), [p]))
                )
                complete38 = (
                    r.get("logic_complete") is True
                    and isinstance(r.get("logic_issues"), list)
                    and isinstance(r.get("logic_uncertain"), bool)
                )
                if complete38:
                    index = source.index(p)
                    for issue in r["logic_issues"]:
                        if not isinstance(issue, dict) or not finding(
                            38,
                            issue,
                            source[max(0, index - 1) : index + 2],
                            "复查原文",
                            True,
                        ):
                            complete38 = False
                            break
                if (
                    (
                        (37 in rules and not complete37)
                        or (38 in rules and not complete38)
                    )
                    and not retried
                    and mode != "mock"
                    and not (
                        error and any(word in error for word in ("未配置", "模拟模式"))
                    )
                ):
                    work.append(
                        (
                            [p],
                            True,
                            pool.submit(read_batch, checker, source, [p], mode),
                            {p.key: (dict(r), bool(complete37), bool(complete38))},
                        )
                    )
                    continue
                if 37 in rules:
                    valid = (
                        r.get("topic") in ("related", "unrelated", "uncertain")
                        and isinstance(r.get("topic_summary"), str)
                        and bool(r["topic_summary"].strip())
                    )
                    if (
                        valid
                        and r["topic"] == "unrelated"
                        and not locate(r.get("topic_quote"), [p])
                    ):
                        valid = False
                    if not valid:
                        errors[37] += 1
                        diagnostics[37].append(
                            f"第{p.para.page}页“{p.text[:18].strip()}”返回无效"
                        )
                        chapter_errors.add(p.chapter)
                    else:
                        read[37] += len(p.text)
                        if r["topic"] == "uncertain" or not p.chapter:
                            uncertain[37] += 1
                            diagnostics[37].append(
                                f"第{p.para.page}页“{p.text[:18].strip()}”主题待核对"
                            )
                        topic_records.setdefault(p.chapter, []).append((p, r))
                if 38 in rules:
                    valid = (
                        r.get("logic_complete") is True
                        and isinstance(r.get("logic_issues"), list)
                        and isinstance(r.get("logic_uncertain"), bool)
                    )
                    own = []
                    for issue in r.get("logic_issues", []) if valid else []:
                        index = source.index(p)
                        neighbors = source[max(0, index - 1) : index + 2]
                        f = (
                            finding(
                                38,
                                issue,
                                [p],
                                "模型已阅读本段及邻接上下文；请核对标出的分句和连词。",
                            )
                            if isinstance(issue, dict)
                            else None
                        )
                        if not f and isinstance(issue, dict):
                            f = finding(
                                38,
                                issue,
                                neighbors,
                                "连词及其前后分句跨段，已分别标出原文位置。",
                                True,
                            )
                            if f and not any(
                                l.block_id == p.para.id
                                and l.text_offset < p.end
                                and l.text_offset + len(l.quote) > p.start
                                for l in f.locations
                            ):
                                # The neighboring piece owns this issue and reads it
                                # independently; contextual repeats are not new errors.
                                continue
                        if not f:
                            valid = False
                            break
                        key = (f.block_id, f.locations[0].text_offset, f.quote)
                        if key not in seen:
                            own.append(f)
                            seen.add(key)
                    if valid:
                        read[38] += len(p.text)
                        uncertain[38] += int(r["logic_uncertain"])
                        if r["logic_uncertain"]:
                            diagnostics[38].append(
                                f"第{p.para.page}页“{p.text[:18].strip()}”逻辑待核对"
                            )
                        found[38].extend(own)
                    else:
                        errors[38] += 1
                        diagnostics[38].append(
                            f"第{p.para.page}页“{p.text[:18].strip()}”返回无效"
                        )
                        found[38].extend(own)
    if 38 in rules and found[38] and checker.settings is not None:
        found[38], extra = review_logic_candidates(checker, found[38], mode)
        uncertain[38] += extra
    if 37 in rules:
        uncertain[37] += review_chapter_topics(
            checker, source, topic_records, chapter_errors, found[37], mode
        )
    return {
        r: (
            found[r],
            audit(
                r,
                found[r],
                total,
                read[r],
                errors[r],
                uncertain[r],
                f"正文共 {len(body)} 段、{len(source)} 个阅读片段；包含各章正文，排除识别出的图表文字、刻度、公式和脚注。"
                + (
                    "待复查位置：" + "；".join(diagnostics[r]) if diagnostics[r] else ""
                ),
            ),
        )
        for r in rules
    }
