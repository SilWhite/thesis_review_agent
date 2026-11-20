"""Optional LangGraph audit using the existing service's single worker and Store."""

import logging
import os
from typing import TypedDict

from langgraph.graph import END, START, StateGraph
from langsmith import tracing_context

from app.documents.parser import parse_document
from app.jobs import TERMINAL
from app.model_client import ModelClient
from app.storage import new_id, now
from .citations import audit_citations
from .consistency import compare, paper_facts, semantic_review
from .materials import read_material
from .novelty import assess, extract_claims_from_paper, retrieve
from .reporting import markdown

log = logging.getLogger(__name__)


class AuditState(TypedDict, total=False):
    identifier: str
    request: object
    blocks: list[dict]
    warnings: list[str]
    experiments: list[dict]
    novelty: dict
    citations: dict
    client: ModelClient
    document: dict


class AuditCancelled(Exception):
    pass


class AuditService:
    def __init__(self, store, settings, worker):
        self.store, self.settings, self.worker = store, settings, worker
        self.graph = self._graph()
        for path in (store.root / "audits").glob("*/state.json"):
            state = store.read(path.parent, path.name)
            if state["status"] in {"queued", "running"}:
                state.update(
                    status="interrupted",
                    error="服务重启中断任务，请重新提交。",
                    updated_at=now(),
                )
                store.write(path.parent, path.name, state)

    def submit(self, request):
        self.store.read(
            self.store.folder("documents", request.document_id), "document.json"
        )
        for experiment in request.experiments:
            for identifier in experiment.material_ids:
                self.store.read(
                    self.store.folder("audit-materials", identifier), "material.json"
                )
        identifier = new_id("audit")
        folder = self.store.folder("audits", identifier)
        self.store.write(folder, "request.json", request.model_dump())
        state = dict(
            id=identifier,
            status="queued",
            stage="queued",
            error=None,
            created_at=now(),
            updated_at=now(),
        )
        self.store.write(folder, "state.json", state)
        self.worker.submit(self.run, identifier, request)
        return state

    def state(self, identifier):
        return self.store.read(self.store.folder("audits", identifier), "state.json")

    def cancel(self, identifier):
        with self.store.lock:
            state = self.state(identifier)
            if state["status"] not in TERMINAL:
                state.update(status="cancelled", updated_at=now())
                self.store.write(
                    self.store.folder("audits", identifier), "state.json", state
                )
            return state

    def enter(self, state, stage):
        with self.store.lock:
            current = self.state(state["identifier"])
            if current["status"] == "cancelled":
                raise AuditCancelled
            current.update(status="running", stage=stage, updated_at=now())
            self.store.write(
                self.store.folder("audits", state["identifier"]), "state.json", current
            )

    def _client(self, identifier):
        client = ModelClient(self.settings)
        client.trace_dir = self.store.folder("audits", identifier) / "traces"
        return client

    def _graph(self):
        graph = StateGraph(AuditState)
        for name, function in [
            ("parse", self.parse),
            ("experiments", self.experiments),
            ("novelty", self.novelty),
            ("citations", self.citations),
            ("report", self.report),
        ]:
            graph.add_node(name, function)
        for left, right in [
            (START, "parse"),
            ("parse", "experiments"),
            ("experiments", "novelty"),
            ("novelty", "citations"),
            ("citations", "report"),
            ("report", END),
        ]:
            graph.add_edge(left, right)
        return graph.compile()

    def parse(self, state):
        self.enter(state, "parsing")
        blocks, warnings = parse_document(self.store, state["request"].document_id)
        if not blocks:
            raise ValueError("论文没有可提取文本，补充审查未配置 OCR。")
        document = self.store.read(
            self.store.folder("documents", state["request"].document_id),
            "document.json",
        )
        return dict(blocks=blocks, warnings=warnings, document=document)

    def experiments(self, state):
        self.enter(state, "experiments")
        request = state["request"]
        paper = "\n".join(b["text"] for b in state["blocks"])
        results = []
        client = state["client"]
        for experiment in request.experiments:
            self.enter(state, "experiments")
            if experiment.paper_quote not in paper:
                raise ValueError(f"实验 {experiment.id} 的论文片段不匹配提取原文。")
            block = next(
                (b for b in state["blocks"] if experiment.paper_quote in b["text"]),
                None,
            )
            source = dict(
                id=f"{request.document_id}:{experiment.id}",
                role="paper",
                filename=state["blocks"][0]["filename"],
                text=experiment.paper_quote,
                location=block["location"] if block else "跨文本块片段",
            )
            sources, facts, notes, datasets = [source], paper_facts(source), [], []
            if not experiment.material_ids:
                notes.append("未提供配套实验材料，无法交叉核对。")
            for identifier in dict.fromkeys(experiment.material_ids):
                material, extracted, messages, ids = read_material(
                    self.store, identifier
                )
                sources.append(material)
                facts.extend(extracted)
                notes.extend(f"{material['filename']}：{n}" for n in messages)
                meta = self.store.read(
                    self.store.folder("audit-materials", identifier), "material.json"
                )
                if meta["role"] == "data":
                    datasets.append(dict(meta, ids=ids))
            findings, messages = compare(facts, datasets)
            notes.extend(messages)
            numeric_fields = sorted(
                {f["field"] for f in facts if f["origin"] == "paper"}
                & {f["field"] for f in facts if f["origin"] != "paper"}
            )
            if not numeric_fields:
                notes.append("未取得可直接比较的数值字段，未执行数值一致性核对。")
            if len(sources) > 1:
                semantic, messages = semantic_review(
                    client, request.model_mode, sources
                )
                findings.extend(semantic)
                notes.extend(messages)
            lookup = {s["id"]: s for s in sources}
            for finding in findings:
                for evidence in finding["evidence"]:
                    source = lookup[evidence["source_id"]]
                    evidence.update(
                        filename=source["filename"],
                        location=evidence.get("location", source["location"]),
                    )
            for index, fact in enumerate(facts, 1):
                fact["id"] = f"{experiment.id}:f{index}"
            results.append(
                dict(
                    id=experiment.id,
                    name=experiment.name,
                    status=(
                        "发现差异或疑点，需核实"
                        if findings
                        else "信息不足" if notes else "在已检查范围内未发现明显矛盾"
                    ),
                    sources=[
                        {k: v for k, v in s.items() if k != "text"} for s in sources
                    ],
                    facts=facts,
                    coverage=dict(
                        numeric_fields=numeric_fields,
                        id_files=[d["id"] for d in datasets if d["ids"] is not None],
                    ),
                    findings=findings,
                    notes=notes,
                )
            )
        return dict(experiments=results)

    def novelty(self, state):
        self.enter(state, "novelty")
        request = state["request"]
        if not getattr(request, "check_novelty", True) or (
            not request.public_queries and not getattr(request, "search_approved", False)
        ):
            reason = (
                "已关闭创新性核查。"
                if not getattr(request, "check_novelty", True)
                else "未提交公开检索词或未勾选公开检索授权。"
            )
            return dict(
                novelty=dict(
                    status="未启用",
                    basis=reason,
                    summary=reason,
                    comparisons=[],
                    sources=[],
                    notes=[],
                )
            )

        queries = list(request.public_queries)
        paper_text = "\n".join(b["text"] for b in state["blocks"])

        extract_errors: list[str] = []
        claims = extract_claims_from_paper(
            state.get("client"), request.model_mode, paper_text, errors=extract_errors
        )
        if not queries:
            for c in claims:
                first_en = (c.get("queries") or ([c.get("query")] if c.get("query") else []))[0:1]
                for q in first_en:
                    if q and q not in queries:
                        queries.append(q)
            for c in claims:
                qz = c.get("query_zh")
                if qz and qz not in queries:
                    queries.append(qz)
            for c in claims:
                for q in (c.get("queries") or [])[1:]:
                    if q and q not in queries:
                        queries.append(q)

        if not queries:
            if extract_errors:
                return dict(
                    novelty=dict(
                        status="信息不足",
                        basis="模型创新点提取失败。",
                        summary=f"创新点提取失败：{extract_errors[0]}",
                        claims=[],
                        comparisons=[],
                        sources=[],
                        notes=extract_errors,
                    )
                )
            return dict(
                novelty=dict(
                    status="未启用",
                    basis="未能从论文中提取出有效检索关键词。",
                    summary="未提取出用于检索前人文献的关键词。",
                    comparisons=[],
                    sources=[],
                    notes=[],
                )
            )

        try:
            s2_key = (
                getattr(self.settings, "semantic_scholar_api_key", "")
                or os.getenv("SEMANTIC_SCHOLAR_API_KEY")
                or os.getenv("S2_API_KEY")
                or ""
            )
            sources, searches = retrieve(
                queries,
                request.literature_cutoff,
                s2_api_key=s2_key,
                claims=claims,
                checkpoint=lambda: self.enter(state, "novelty"),
            )
        except AuditCancelled:
            raise
        except Exception as exc:
            return dict(
                novelty=dict(
                    status="信息不足",
                    basis="公开检索未完成。",
                    summary=f"公开文献检索失败：{exc}",
                    comparisons=[],
                    sources=[],
                    searches=[],
                    notes=extract_errors + [f"公开检索失败：{exc}"],
                )
            )
        result = assess(
            state["client"],
            request.model_mode,
            paper_text,
            sources,
            request.degree,
            claims=claims,
        )
        if extract_errors:
            result["notes"] = extract_errors + result.get("notes", [])
        result.update(searches=searches, literature_cutoff=request.literature_cutoff)
        return dict(novelty=result)

    def citations(self, state):
        self.enter(state, "citations")
        request = state["request"]
        if not getattr(request, "check_citations", True):
            return dict(
                citations=dict(
                    status="未启用",
                    summary="未启用参考文献防幻觉核查。",
                    total_checked=0,
                    verified_count=0,
                    mismatch_count=0,
                    phantom_count=0,
                    items=[],
                    notes=[],
                )
            )
        try:
            s2_key = os.getenv("SEMANTIC_SCHOLAR_API_KEY") or os.getenv("S2_API_KEY") or getattr(self.settings, "s2_api_key", "")
            res = audit_citations(state["blocks"], s2_api_key=s2_key)
        except Exception as exc:
            res = dict(
                status="核查异常",
                summary=f"参考文献核查执行失败：{exc}",
                total_checked=0,
                verified_count=0,
                mismatch_count=0,
                phantom_count=0,
                items=[],
                notes=[str(exc)],
            )
        return dict(citations=res)

    def report(self, state):
        self.enter(state, "reporting")
        citations = state.get("citations", {})
        report = dict(
            schema_version="audit-1.0",
            id=state["identifier"],
            document_id=state["request"].document_id,
            generated_at=now(),
            document=state["document"],
            mode=state["request"].model_mode,
            experiments=state["experiments"],
            novelty=state["novelty"],
            citations=citations,
            limitations=state["warnings"]
            + [
                "仅审查指定论文片段和所提供材料，不执行作者代码，不复现训练或评估。",
                "材料关联、样本含义、配置是否生效及材料完整性仍需人工确认。",
                "来源匹配不证明内容真实；不能据此认定或排除伪造、AI生成数据。",
                "创新性初判基于公开学术数据库与大模型对比分析，不能代替正式科技查新报告。",
                "参考文献防幻觉核查基于 Crossref 公开记录匹配，未收录或非标准著录格式文献可能需人工复核。",
            ],
        )
        folder = self.store.folder("audits", state["identifier"])
        partial = (
            state["request"].model_mode == "mock"
            or bool(state["warnings"])
            or any(e["notes"] for e in state["experiments"])
            or state["novelty"]["status"] == "信息不足"
            or bool(state["novelty"]["notes"])
            or bool(citations.get("phantom_count", 0) > 0)
        )
        with self.store.lock:
            if self.state(state["identifier"])["status"] == "cancelled":
                raise AuditCancelled
            self.store.write(folder, "report.json", report)
            (folder / "report.md").write_text(markdown(report), encoding="utf-8")
            current = self.state(state["identifier"])
            current.update(
                status="partial" if partial else "completed", updated_at=now()
            )
            self.store.write(folder, "state.json", current)
        return {}

    def run(self, identifier, request):
        try:
            with tracing_context(enabled=False):
                self.graph.invoke(
                    dict(
                        identifier=identifier,
                        request=request,
                        client=self._client(identifier),
                    )
                )
        except AuditCancelled:
            return
        except Exception as exc:
            log.exception("Supplemental audit failed: %s", identifier)
            with self.store.lock:
                current = self.state(identifier)
                if current["status"] != "cancelled":
                    current.update(status="failed", error=str(exc), updated_at=now())
                    self.store.write(
                        self.store.folder("audits", identifier), "state.json", current
                    )
