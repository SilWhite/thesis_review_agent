"""Contract tests for exhaustive reading; these do not measure model accuracy."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from app.documents.models import ThesisDocumentTree, ChapterData, ParagraphData
from app.documents.models import PageData
from app.review.checks.semantic import SemanticChecker
from app.review.checks.reading import (
    pieces,
    locate,
    PREFIX,
    body_record,
    prose_paragraph,
    review_logic_candidates,
    finding,
)
from app.review.checks.coverage_body import review_body
from app.review.checks.coverage_intro import review_intro
from app.schemas import CheckStatus


def para(i, text, **kw):
    return ParagraphData(str(i), text, 1, **kw)


def tree(ps, title="第二章 图像分类", role="method"):
    ch = ChapterData(title, 1, 1, role=role, paragraphs=ps)
    return ThesisDocumentTree("control", chapters=[ch], all_body_paragraphs=ps)


def material(prompt):
    return json.loads(prompt.split("【材料JSON】\n")[1])


calls = []


def normal(prompt, mode):
    assert prompt.startswith(PREFIX)
    data = material(prompt)
    calls.append(data)
    return {
        "findings": [
            {
                "id": p["id"],
                "read_quote": p["text"][:20],
                "topic": "related",
                "topic_summary": "图像分类方法。",
                "logic_complete": True,
                "logic_uncertain": False,
                "logic_issues": [],
            }
            for p in data
        ]
    }, None


s = SemanticChecker()
s._call_llm = normal
ps = [para(i, f"第{i}段使用卷积网络提取图像特征。" * 40) for i in range(65)]
ps += [para("long", "这是长段落中的完整正文。" * 1200)]
t = tree(ps)
result = review_body(s, t, "local")
assert len(calls) > 4
assert sum(len(p["text"]) for call in calls for p in call) == sum(
    len(p.text) for p in ps
)
for fs, a in result.values():
    assert not fs and a.status == CheckStatus.PASSED.value, a
assert len(pieces([ps[-1]])) > 2
assert "".join(p.text for p in pieces([ps[-1]])) == ps[-1].text

# Detect a late error beyond both former limits; preserve raw offset and context.
late = "虽然所有电源已经断开，但是设备因此停止运行。"
ps[-1].text += late


def late_model(prompt, mode):
    response, error = normal(prompt, mode)
    for p, r in zip(material(prompt), response["findings"]):
        if late in p["text"]:
            r["logic_issues"] = [
                {"quote": late, "issue": "断电导致停机，连词表达了转折。"}
            ]
    return response, error


s._call_llm = late_model
fs, a = review_body(s, t, "local")[38]
assert len(fs) == 1 and fs[0].quote == late
assert fs[0].locations[0].text_offset == ps[-1].text.index(late)
assert fs[0].status == "pending_verification"

# Figures, cells, formulas, footnotes and headings must never enter prose reading.
excluded = [
    para("excluded" + flag, "图表里的英文和数字不应进入正文。", **{flag: True})
    for flag in (
        "is_heading",
        "is_formula",
        "is_caption",
        "is_table_cell",
        "is_figure_text",
        "is_footnote",
    )
]
calls.clear()
s._call_llm = normal
review_body(s, tree([para("body", "这是需要正常检查的正文。")] + excluded), "local")
assert len(calls) == 1 and len(calls[0]) == 1

# Missing acknowledgements, fabricated quotes and model errors cannot become passes.
for response in (
    {"findings": []},
    {"findings": [{"id": "p0@0:13", "logic_complete": True}]},
):
    s._call_llm = lambda *args: (response, None)
    assert (
        review_body(s, tree([para("one", "正文需要有明确的阅读记录。")]), "local")[38][
            1
        ].status
        != CheckStatus.PASSED.value
    )
s._call_llm = lambda *args: (None, "timeout")
assert review_body(s, t, "local")[38][1].status == CheckStatus.FAILED.value
s._call_llm = lambda *args: ({"findings": []}, None)
assert review_body(s, t, "mock")[38][1].status == CheckStatus.FAILED.value

# Intro map must cover the whole chapter; only the global reduction may find absence.
intro = tree(
    [para(i, "该段介绍已有研究和本论文的工作。" * 110) for i in range(10)],
    "第一章 绪论",
    "intro",
)
quotes = [p.text[:40] for p in intro.chapters[0].paragraphs]
intro_calls = []


def intro_model(prompt, mode):
    data = material(prompt)
    intro_calls.append(data)
    if "第一章阅读记录" in prompt:
        assert "chapter_titles" not in data
        q = data["pieces"][0]["text"][:40]
        return {
            "findings": [
                {
                    "rule_id": r,
                    "complete": True,
                    "summary": "本段介绍研究。",
                    "evidence": [{"quote": q, "meaning": "研究内容"}],
                }
                for r in (8, 9)
            ]
        }, None
    rule = 8 if "全局汇总规则8" in prompt else 9
    return {
        "findings": [
            {
                "rule_id": rule,
                "verdict": "finding" if rule == 9 else "pass",
                "quote": quotes[0],
                "issue": "各章只列内容，没有承接说明。",
            }
        ]
    }, None


s._call_llm = intro_model
fs, aa = review_intro(s, intro, intro.chapters[0], "local")
assert [f.rule_id for f in fs] == [9]
assert (
    aa[0].status == CheckStatus.PASSED.value
    and aa[1].status == CheckStatus.FINDING.value
)
maps = [d for d in intro_calls if "pieces" in d]
assert sum(len(p["text"]) for d in maps for p in d["pieces"]) == sum(
    len(p.text) for p in intro.chapters[0].paragraphs
)


def broken_intro(prompt, mode):
    if "第一章阅读记录" in prompt:
        return None, "timeout"
    raise AssertionError("Cannot decide chapter-wide absence after incomplete reading")


s._call_llm = broken_intro
fs, aa = review_intro(s, intro, intro.chapters[0], "local")
assert not fs and all(a.status == CheckStatus.FAILED.value for a in aa)

# Chapter mismatch gets a global recheck, allowing one harmless digression to pass.
short = tree([para("digression", "这段讨论了与图像分类无关的园林栽培历史。")])


def topic_model(prompt, mode):
    d = material(prompt)
    if isinstance(d, list):
        return {
            "findings": [
                {
                    "id": p["id"],
                    "read_quote": p["text"][:20],
                    "topic": "unrelated",
                    "topic_summary": "园林历史",
                    "topic_quote": p["text"],
                    "logic_complete": True,
                    "logic_uncertain": False,
                    "logic_issues": [],
                }
                for p in d
            ]
        }, None
    return {
        "findings": [{"verdict": "pass", "issue": "短暂离题不足以确认持续跑题。"}]
    }, None


s._call_llm = topic_model
assert review_body(s, short, "local")[37][1].status == CheckStatus.PASSED.value


def topic_bad(prompt, mode):
    if isinstance(material(prompt), list):
        return topic_model(prompt, mode)
    return {
        "findings": [
            {
                "verdict": "finding",
                "quote": short.all_body_paragraphs[0].text,
                "issue": "本章持续介绍园林栽培，与图像分类主题无关。",
            }
        ]
    }, None


s._call_llm = topic_bad
assert len(review_body(s, short, "local")[37][0]) == 1


# A generic acknowledgement without source text is not evidence of reading.
def empty_ack(prompt, mode):
    response, error = normal(prompt, mode)
    for r in response["findings"]:
        r.pop("read_quote")
        r["topic_summary"] = ""
    return response, error


s._call_llm = empty_ack
assert all(
    a.status == CheckStatus.FAILED.value
    for fs, a in review_body(s, short, "local").values()
)

# A missing piece prevents a chapter-wide finding, and normal text cannot be its evidence.
partial = tree(
    [
        para("bad", "本节详细讨论园林栽培管理及花卉育种方法。"),
        para("missing", "第二段应当被模型读取和确认。"),
    ]
)


def partial_model(prompt, mode):
    d = material(prompt)
    assert isinstance(
        d, list
    ), "Incomplete chapter must not reach the chapter-wide decision"
    if d[0]["id"].startswith("p1@"):
        return {"findings": []}, None
    return {
        "findings": [
            {
                "id": d[0]["id"],
                "read_quote": d[0]["text"],
                "topic": "unrelated",
                "topic_summary": "园林栽培",
                "topic_quote": d[0]["text"],
            }
        ]
    }, None


s._call_llm = partial_model
fs, a = review_body(s, partial, "local", (37,))[37]
assert not fs and a.status == CheckStatus.UNCERTAIN.value

repeat = "同一句原文在长段落中出现两次。"
long = para("repeat", repeat + "填充正文内容。" * 900 + repeat)
sp = pieces([long])
located = locate(repeat, [sp[-1]])
assert located and located[1] == long.text.rindex(repeat)

cross = tree(
    [para("cause", "所有电源都已经断开。"), para("effect", "但是设备因此停止运行。")]
)


def cross_model(prompt, mode):
    result, error = normal(prompt, mode)
    for p, r in zip(material(prompt), result["findings"]):
        r["logic_issues"] = [
            {
                "quote": "所有电源都已经断开。但是设备因此停止运行。",
                "issue": "停机是断电的结果，转折连词与实际因果关系冲突。",
            }
        ]
    return result, error


s._call_llm = cross_model
fs, a = review_body(s, cross, "local", (38,))[38]
assert (
    len(fs) == 1 and len(fs[0].locations) == 2 and a.status == CheckStatus.FINDING.value
)
assert (
    fs[0].locations[0].block_id == "cause" and fs[0].locations[1].block_id == "effect"
)

attempts = []


def retry_model(prompt, mode):
    attempts.append(prompt)
    if len(attempts) == 1:
        return {"findings": []}, None
    return normal(prompt, mode)


s._call_llm = retry_model
fs, a = review_body(s, short, "local", (38,))[38]
assert not fs and a.status == CheckStatus.PASSED.value and len(attempts) == 2

# Retry only fills failed rules: keep the first valid topic/logic decision.
mixed_calls = []


def mixed_model(prompt, mode):
    d = material(prompt)
    if not isinstance(d, list):
        return {
            "findings": [
                {
                    "verdict": "finding",
                    "quote": short.all_body_paragraphs[0].text,
                    "issue": "整章持续偏离图像分类主题。",
                }
            ]
        }, None
    mixed_calls.append(prompt)
    r = {
        "id": d[0]["id"],
        "read_quote": d[0]["text"][:20],
        "topic": "unrelated",
        "topic_summary": "园林栽培",
        "topic_quote": d[0]["text"],
    }
    if len(mixed_calls) > 1:
        r.update(
            topic="related",
            topic_summary="模型第二次改变了主题判断",
            logic_complete=True,
            logic_uncertain=False,
            logic_issues=[],
        )
    return {"findings": [r]}, None


s._call_llm = mixed_model
result = review_body(s, short, "local")
assert len(result[37][0]) == 1 and result[38][1].status == CheckStatus.PASSED.value
reverse = tree([para("bad_relation", "虽然所有电源已经断开，但是设备因此停止运行。")])
reverse_calls = []


def reverse_model(prompt, mode):
    result, error = normal(prompt, mode)
    reverse_calls.append(prompt)
    if len(reverse_calls) == 1:
        r = result["findings"][0]
        r.pop("topic")
        r["logic_issues"] = [
            {
                "quote": reverse.all_body_paragraphs[0].text,
                "issue": "因果关系误用转折连词。",
            }
        ]
    return result, error


s._call_llm = reverse_model
result = review_body(s, reverse, "local")
assert result[37][1].status == CheckStatus.PASSED.value and len(result[38][0]) == 1
timeouts = []


def transient_timeout(prompt, mode):
    timeouts.append(prompt)
    if len(timeouts) == 1:
        return None, "timed out"
    return normal(prompt, mode)


s._call_llm = transient_timeout
assert review_body(s, short, "local", (38,))[38][1].status == CheckStatus.PASSED.value
assert len(timeouts) == 2

# Compact records preserve the same explicit acknowledgement contract.
compact = {
    "id": "p",
    "q": "这段正文用于阅读依据。",
    "t": "r",
    "s": "分类方法",
    "l": "ok",
    "e": [],
}
decoded = body_record(compact)
assert (
    decoded["logic_complete"] is True
    and decoded["logic_uncertain"] is False
    and decoded["topic"] == "related"
)
assert body_record({**compact, "l": None})["logic_complete"] is False
assert body_record({**compact, "t": []})["topic"] is None

# Numeric ticks and units are not prose; short real logical sentences are retained.
for text in ("1400", "0.7s", "-5", "续表4-2"):
    assert not prose_paragraph(para("tick", text), short)
assert prose_paragraph(para("sentence", "虽然下雨，所以地湿。"), short)
assert prose_paragraph(para("sentence", "所以设备停机。"), short)
near_graph = tree([])
near_graph.pages = [PageData(1, 595, 842, graphic_regions=[(100, 150, 400, 400)])]
for text in (
    "结果如下",
    "模型因此失效",
    "因此精度下降",
    "训练能够成功",
    "这是实际正文",
):
    assert prose_paragraph(
        para("near", text, bbox=(110, 130, 190, 145)), near_graph
    ), text
for text in ("Loss", "Step", "数据占比", "数量"):
    assert not prose_paragraph(
        para("near", text, bbox=(110, 130, 190, 145)), near_graph
    ), text

# Intro evidence may bridge physical paragraphs; a fabricated map is repaired.
cross_intro = make_intro = tree(
    [
        para("a", "现有系统在弱光条件下会丢失边缘。"),
        para("b", "本文构建能够保留弱光边缘的分类网络。"),
    ],
    "第一章 绪论",
    "intro",
)
intro_attempt = []


def cross_intro_model(prompt, mode):
    d = material(prompt)
    if "第一章阅读记录" in prompt:
        intro_attempt.append(prompt)
        quote = (
            "不存在于原文的模型编造内容。"
            if len(intro_attempt) == 1
            else "".join(p["text"] for p in d["pieces"])
        )
        return {
            "findings": [
                {
                    "rule_id": r,
                    "complete": True,
                    "summary": "弱光问题与保留边缘的方法。",
                    "evidence": [{"quote": quote, "meaning": "问题和方案"}],
                }
                for r in (8, 9)
            ]
        }, None
    r = 8 if "全局汇总规则8" in prompt else 9
    return {
        "findings": [
            {
                "rule_id": r,
                "verdict": "pass",
                "quote": cross_intro.chapters[0].paragraphs[0].text,
                "issue": "已有具体原文支持。",
            }
        ]
    }, None


s._call_llm = cross_intro_model
fs, aa = review_intro(s, cross_intro, cross_intro.chapters[0], "local")
assert (
    not fs
    and all(a.status == CheckStatus.PASSED.value for a in aa)
    and len(intro_attempt) == 3
)

# Ordinary grammar is outside rule38; source-grounded wrong logic is retained.
src = pieces([para("grammar", "模型的训练是Windows系统上的容器中运行。")])
f = finding(38, {"quote": src[0].text, "issue": "是中运行语病。"}, src, "control")
s._call_llm = lambda *args: (
    {"findings": [{"verdict": "remove", "quote": f.quote, "issue": "普通语病。"}]},
    None,
)
assert review_logic_candidates(s, [f], "local") == ([], 0)
s._call_llm = lambda *args: (
    {
        "findings": [
            {
                "verdict": "keep",
                "quote": f.quote,
                "connective": "是",
                "issue": "误归类语病。",
            }
        ]
    },
    None,
)
assert review_logic_candidates(s, [f], "local") == ([], 0)
s._call_llm = lambda *args: (None, "timeout")
kept, unresolved = review_logic_candidates(s, [f], "local")
assert kept == [f] and unresolved == 1
logic_src = pieces([para("logic", "虽然所有电源已经断开，但是设备因此停止运行。")])
logic_f = finding(
    38, {"quote": logic_src[0].text, "issue": "因果与转折冲突。"}, logic_src, "control"
)
s._call_llm = lambda *args: (
    {
        "findings": [
            {
                "verdict": "keep",
                "quote": logic_f.quote,
                "connective": "虽然...但是",
                "issue": "实际为因果，连词表达转折。",
            }
        ]
    },
    None,
)
assert review_logic_candidates(s, [logic_f], "local") == ([logic_f], 0)
print(
    "Semantic coverage contracts passed: complete reading, late errors, grounding, exclusions, failures, global decisions"
)
