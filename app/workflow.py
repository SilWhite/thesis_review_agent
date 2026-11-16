"""Four review stages; adapters and artifacts stay in their existing modules."""

from collections.abc import Callable
from pathlib import Path
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from .documents.parser import parse_document
from .review.engine import LocalReviewer, MockReviewer
from .reporting.markdown import markdown
from .evidence.validation import validate_evidence
from .schemas import Assessment, Finding, ReviewRequest
from .storage import now


class ReviewState(TypedDict, total=False):
    job_id: str
    request: ReviewRequest
    blocks: list[dict]
    policies: list[dict]
    warnings: list[str]
    source_path: str
    assessment: Assessment
    findings: list[Finding]


class ReviewCancelled(Exception):
    """Stop between stages without marking a cancelled job as failed."""


def _review_is_partial(warnings, model_mode, audit_items):
    return bool(
        warnings
        or model_mode == "mock"
        or any(
            item.status in ("缺少输入", "无法可靠判断", "执行失败")
            for item in audit_items
        )
    )


def build_workflow(store, settings, advance: Callable[[str, str], bool]):
    def enter(state, stage):
        if not advance(state["job_id"], stage):
            raise ReviewCancelled

    def parse(state: ReviewState):
        enter(state, "parsing")
        request = state["request"]
        blocks, policies, warnings = [], [], []
        for ids, target in [
            (request.document_ids, blocks),
            (request.policy_ids, policies),
        ]:
            for doc_id in ids:
                content, issues = parse_document(store, doc_id)
                target.extend(content)
                warnings.extend(issues)
        content = dict(blocks=blocks, policies=policies, warnings=warnings)
        store.write(store.folder("jobs", state["job_id"]), "content.json", content)
        if not blocks:
            raise ValueError(
                "没有可评审文本。图片或扫描件需要先接入 OCR，或粘贴提取后的文本。"
            )
        source_path = None
        if request.document_ids:
            try:
                first_doc_id = request.document_ids[0]
                folder = store.folder("documents", first_doc_id)
                meta = store.read(folder, "document.json")
                source_path = str(folder / ("source" + meta["suffix"]))
            except Exception:
                pass
        return dict(content, source_path=source_path)

    def review(state: ReviewState):
        enter(state, "reviewing")
        request = state["request"]
        reviewer = (
            MockReviewer() if request.model_mode == "mock" else LocalReviewer(settings)
        )
        src = Path(state["source_path"]) if state.get("source_path") else None
        return {
            "assessment": reviewer.assess(
                request, state["blocks"], state["policies"], source_path=src
            )
        }

    def verify(state: ReviewState):
        enter(state, "verifying")
        return {"findings": validate_evidence(state["assessment"], state["blocks"])}

    def report(state: ReviewState):
        enter(state, "reporting")
        request, identifier = state["request"], state["job_id"]
        lookup = {b["id"]: b for b in state["blocks"]}
        limits = state["warnings"] + [
            "未接入原始实验数据与自动相关工作检索，不能认定造假或断言没有创新。",
            "参考规范的适用范围需结合学校要求核对。",
        ]
        if not state["policies"]:
            limits.append(
                "未取得具体规范文件；按一般学术质量要求审阅，未完成全部合规核验。"
            )
        if request.model_mode == "mock":
            limits.append("本报告为模拟输出，不代表模型已完成学术评审。")
        result = dict(
            state["assessment"].model_dump(),
            schema_version="1.0",
            job_id=identifier,
            mode=request.model_mode,
            model_name=(
                settings.model_name
                if request.model_mode == "local"
                else "deterministic-demo-v1"
            ),
            generated_at=now(),
            findings=[
                dict(
                    f.model_dump(),
                    filename=lookup.get(f.block_id, {}).get(
                        "filename",
                        (
                            state["blocks"][0].get("filename")
                            if state["blocks"]
                            else "全文"
                        ),
                    ),
                    location=(
                        lookup.get(f.block_id, {}).get("location")
                        or (
                            ", ".join(
                                [
                                    f"第{loc.page}页"
                                    for loc in f.locations
                                    if loc.page is not None
                                ]
                            )
                            if f.locations
                            else "全文/全局"
                        )
                    ),
                )
                for f in state["findings"]
            ],
            limitations=limits,
            coverage=dict(
                block_count=len(state["blocks"]),
                document_count=len(request.document_ids),
                scope="extracted_text_only",
            ),
        )
        rendered = markdown(result)
        folder = store.folder("jobs", identifier)
        with store.lock:
            if store.read(folder, "state.json")["status"] == "cancelled":
                raise ReviewCancelled
            store.write(folder, "report.json", result)
            (folder / "report.md").write_text(rendered, encoding="utf-8")
            store.update_job(
                identifier,
                status=(
                    "partial"
                    if _review_is_partial(
                        state["warnings"],
                        request.model_mode,
                        state["assessment"].rule_matrix,
                    )
                    else "completed"
                ),
            )
        return {}

    graph = StateGraph(ReviewState)
    graph.add_node("parse", parse)
    graph.add_node("review", review)
    graph.add_node("verify", verify)
    graph.add_node("report", report)
    graph.add_edge(START, "parse")
    graph.add_edge("parse", "review")
    graph.add_edge("review", "verify")
    graph.add_edge("verify", "report")
    graph.add_edge("report", END)
    return graph.compile()
