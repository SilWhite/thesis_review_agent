"""Optional LangGraph audit using the existing service's single worker and Store."""

import logging
from typing import TypedDict

from langgraph.graph import END, START, StateGraph
from langsmith import tracing_context

from app.documents.parser import parse_document
from app.jobs import TERMINAL
from app.model_client import ModelClient
from app.storage import new_id, now
from .consistency import compare, paper_facts, semantic_review
from .materials import read_material
from .novelty import assess, retrieve
from .reporting import markdown

log = logging.getLogger(__name__)


class AuditState(TypedDict, total=False):
    identifier: str
    request: object
    blocks: list[dict]
    warnings: list[str]
    experiments: list[dict]
    novelty: dict
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
            ("report", self.report),
        ]:
            graph.add_node(name, function)
        for left, right in [
            (START, "parse"),
            ("parse", "experiments"),
            ("experiments", "novelty"),
            ("novelty", "report"),
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
        if not request.public_queries:
            return dict(
                novelty=dict(
                    status="未启用",
                    basis="未提交公开检索词。",
                    comparisons=[],
                    sources=[],
                    notes=[],
                )
            )
        try:
            sources, searches = retrieve(
                request.public_queries, request.literature_cutoff
            )
        except Exception as exc:
            return dict(
                novelty=dict(
                    status="信息不足",
                    basis="公开检索未完成。",
                    comparisons=[],
                    sources=[],
                    searches=[],
                    notes=[f"公开检索失败：{exc}"],
                )
            )
        result = assess(
            state["client"],
            request.model_mode,
            "\n".join(b["text"] for b in state["blocks"]),
            sources,
            request.degree,
        )
        result.update(searches=searches, literature_cutoff=request.literature_cutoff)
        return dict(novelty=result)

    def report(self, state):
        self.enter(state, "reporting")
        report = dict(
            schema_version="audit-1.0",
            id=state["identifier"],
            document_id=state["request"].document_id,
            generated_at=now(),
            document=state["document"],
            mode=state["request"].model_mode,
            experiments=state["experiments"],
            novelty=state["novelty"],
            limitations=state["warnings"]
            + [
                "仅审查指定论文片段和所提供材料，不执行作者代码，不复现训练或评估。",
                "材料关联、样本含义、配置是否生效及材料完整性仍需人工确认。",
                "来源匹配不证明内容真实；不能据此认定或排除伪造、AI生成数据。",
                "创新性为有限候选的书目／摘要初判，非全面查新；不保证语义判断正确。",
                "数值检查只覆盖已识别字段；未完整解析图表、公式和所有代码执行路径。",
            ],
        )
        folder = self.store.folder("audits", state["identifier"])
        partial = (
            state["request"].model_mode == "mock"
            or bool(state["warnings"])
            or any(e["notes"] for e in state["experiments"])
            or state["novelty"]["status"] == "信息不足"
            or bool(state["novelty"]["notes"])
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
