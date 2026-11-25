"""Contracts for the optional audit; existing review contracts stay unchanged."""

from typing import Literal
from pydantic import BaseModel, Field, model_validator


class Experiment(BaseModel):
    id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,40}$")
    name: str = Field(min_length=1, max_length=200)
    paper_quote: str = Field(min_length=1, max_length=12000)
    material_ids: list[str] = Field(default_factory=list, max_length=20)


class RepositoryInput(BaseModel):
    kind: Literal["local", "github"]
    location: str = Field(min_length=1, max_length=2000)
    ref: str | None = Field(
        default=None, pattern=r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,199}$"
    )


class AuditRequest(BaseModel):
    document_id: str
    repository: RepositoryInput | None = None
    experiments: list[Experiment] = Field(default_factory=list, max_length=10)
    public_queries: list[str] = Field(default_factory=list, max_length=10)
    search_approved: bool = False
    check_novelty: bool = True
    check_citations: bool = True
    check_experiments: bool = False
    literature_cutoff: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    degree: Literal["bachelor", "master", "doctor", "unknown"] = "master"
    model_mode: Literal["local", "mock"] = "local"

    @model_validator(mode="after")
    def valid_scope(self):
        from datetime import date

        if self.repository:
            for name in ("check_novelty", "check_citations"):
                if name not in self.model_fields_set:
                    setattr(self, name, False)
        if (
            not self.repository
            and not self.experiments
            and not self.public_queries
            and not self.check_citations
            and not self.check_novelty
        ):
            raise ValueError("请提供实验材料关联、公开检索词或勾选审查项。")
        if self.repository and not self.check_experiments:
            raise ValueError("仓库审查需要启用 check_experiments。")
        if len({e.id for e in self.experiments}) != len(self.experiments):
            raise ValueError("实验 ID 不得重复。")
        if any(not 2 <= len(q.strip()) <= 300 for q in self.public_queries):
            raise ValueError("每条公开查询须为 2–300 字符。")
        if self.literature_cutoff:
            date.fromisoformat(self.literature_cutoff)
        return self
