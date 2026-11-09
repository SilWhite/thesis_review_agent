"""Shared API and model contracts. FastAPI exposes them at /docs."""

from typing import Literal
from pydantic import BaseModel, Field


class TextInput(BaseModel):
    title: str = Field(default="粘贴的材料", max_length=200)
    text: str = Field(min_length=1, max_length=500_000)


class ReviewRequest(BaseModel):
    document_ids: list[str] = Field(min_length=1, max_length=10)
    policy_ids: list[str] = Field(default_factory=list, max_length=10)
    material_type: Literal["proposal", "progress", "thesis", "paper"] = "thesis"
    degree: Literal["bachelor", "master", "doctor", "unknown"] = "master"
    language: Literal["zh-CN", "en"] = "zh-CN"
    custom_prompt: str = Field(default="", max_length=10000)
    model_mode: Literal["mock", "local"] = "mock"


class Finding(BaseModel):
    dimension: Literal["结果可信度", "内容可靠性", "规范与逻辑", "创新与价值"]
    severity: Literal["major", "minor"]
    status: Literal["supported", "pending_verification"]
    block_id: str
    quote: str = Field(min_length=1)
    issue: str
    suggestion: str


class Assessment(BaseModel):
    verdict: Literal["基本满足", "需修改", "存在重大问题", "信息不足"]
    summary: str
    findings: list[Finding]
    priority_actions: list[str]


class SearchRequest(BaseModel):
    query: str = Field(min_length=2, max_length=300)
    approved: bool = False
