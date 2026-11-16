"""Published reports, human decisions and immutable final snapshots."""

from app.storage import new_id
from .final import report_digest, validate_exclusions, build_final_report
from .markdown import markdown


class ReportConflict(ValueError):
    """The report is unpublished, changed, or has stale review decisions."""


class ReportService:
    def __init__(self, store):
        self.store = store

    def get(self, identifier):
        state = self.store.read(self.store.folder("jobs", identifier), "state.json")
        if state["status"] not in {"completed", "partial"}:
            raise ReportConflict("报告尚未发布。")
        return self.store.read(self.store.folder("jobs", identifier), "report.json")

    def decisions(self, identifier: str):
        with self.store.lock:
            original = self.get(identifier)
            digest = report_digest(original)
            folder = self.store.folder("jobs", identifier)
            saved = (
                self.store.read(folder, "review-decisions.json")
                if (folder / "review-decisions.json").exists()
                else {}
            )
            indices = (
                saved.get("excluded_findings", [])
                if saved.get("source_report_sha256") == digest
                else []
            )
            revision = (
                saved.get("revision", 0)
                if saved.get("source_report_sha256") == digest
                else 0
            )
            return dict(
                source_report_sha256=digest,
                excluded_findings=indices,
                revision=revision,
            )

    def save_decisions(self, identifier, body):
        original = self.get(identifier)
        if body.source_report_sha256 != report_digest(original):
            raise ReportConflict("报告已更新，请刷新后重新复核。")
        indices = validate_exclusions(original, body.excluded_findings)
        current = self.decisions(identifier)
        if body.revision != current["revision"]:
            raise ReportConflict("复核选择已在其他页面更新，请刷新页面后继续复核。")
        saved = dict(
            source_report_sha256=body.source_report_sha256,
            excluded_findings=indices,
            revision=current["revision"] + 1,
        )
        self.store.write(
            self.store.folder("jobs", identifier), "review-decisions.json", saved
        )
        return original, saved

    def final(self, identifier, body):
        with self.store.lock:
            original, saved = self.save_decisions(identifier, body)
            result = build_final_report(original, body.excluded_findings)
            result["human_review"]["decisions_revision"] = saved["revision"]
            snapshot = new_id("report")
            folder = self.store.folder("jobs", identifier) / "final-reports"
            self.store.write(folder, snapshot + ".json", result)
            (folder / (snapshot + ".md")).write_text(markdown(result), encoding="utf-8")
            return dict(
                report=result,
                revision=saved["revision"],
                download_url=f"/api/v1/jobs/{identifier}/final-reports/{snapshot}/download",
            )
