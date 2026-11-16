"""Shared API and model contracts. FastAPI exposes them at /docs."""

from enum import Enum
from typing import Annotated, Literal, Optional
from pydantic import BaseModel, Field


class TextInput(BaseModel):
    title: str = Field(default="粘贴的材料", max_length=200)
    text: str = Field(min_length=1, max_length=1_000_000)


class ReviewRequest(BaseModel):
    document_ids: list[str] = Field(min_length=1, max_length=10)
    policy_ids: list[str] = Field(default_factory=list, max_length=10)
    material_type: Literal["proposal", "progress", "thesis", "paper"] = "thesis"
    degree: Literal["bachelor", "master", "doctor", "unknown"] = "master"
    language: Literal["zh-CN", "en"] = "zh-CN"
    custom_prompt: str = Field(default="", max_length=10000)
    model_mode: Literal["mock", "local"] = "local"


class CheckStatus(str, Enum):
    FINDING = "发现问题"
    PASSED = "检查通过"
    NA = "不适用"
    MISSING_INPUT = "缺少输入"
    UNCERTAIN = "无法可靠判断"
    FAILED = "执行失败"


class ReviewDecisions(BaseModel):
    source_report_sha256: str = Field(pattern=r'^[0-9a-f]{64}$')
    excluded_findings: list[Annotated[int, Field(strict=True, ge=0)]] = Field(default_factory=list, max_length=100000)
    revision: int = Field(default=0, strict=True, ge=0)


class EvidenceLocation(BaseModel):
    page: Optional[int] = None
    block_id: Optional[str] = None
    quote: Optional[str] = None
    bbox: Optional[list[float]] = None
    bboxes: list[list[float]] = Field(default_factory=list)
    text_offset: Optional[int] = None
    description: Optional[str] = None
    context: Optional[str] = None
    highlight_texts: list[str] = Field(default_factory=list)
    verified: bool = False


class Finding(BaseModel):
    rule_id: int = Field(default=0, description="负面清单规则序号(2~38)")
    rule_category: Literal["确定性检查", "版面排版", "语义核查", "通用规范"] = "通用规范"
    dimension: str = "规范与逻辑"
    severity: Literal["major", "minor"] = "minor"
    status: Literal["supported", "pending_verification"] = "supported"
    block_id: str = ""
    quote: str = Field(default="", min_length=0)
    locations: list[EvidenceLocation] = Field(default_factory=list)
    issue: str
    suggestion: str
    measurement: Optional[str] = None
    evidence_note: str = ""


class RuleAuditItem(BaseModel):
    rule_id: int
    rule_name: str
    category: Literal["确定性检查", "版面排版", "语义核查"]
    status: str
    findings_count: int = 0
    note: Optional[str] = None


class Assessment(BaseModel):
    verdict: Literal["基本满足", "需修改", "存在重大问题", "信息不足"]
    summary: str
    findings: list[Finding]
    rule_matrix: list[RuleAuditItem] = Field(default_factory=list)
    priority_actions: list[str]


class SearchRequest(BaseModel):
    query: str = Field(min_length=2, max_length=300)
    approved: bool = False

