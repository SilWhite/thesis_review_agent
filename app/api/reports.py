from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, Response
from app.schemas import ReviewDecisions
from app.reporting.service import ReportService
from app.evidence.rendering import render_evidence_page


def create_router(store):
    router = APIRouter()
    reports = ReportService(store)

    @router.get("/api/v1/jobs/{identifier}/report")
    def report(identifier: str):
        return reports.get(identifier)

    @router.get("/api/v1/jobs/{identifier}/review-decisions")
    def review_decisions(identifier: str):
        return reports.decisions(identifier)

    @router.post("/api/v1/jobs/{identifier}/review-decisions")
    def update_review_decisions(identifier: str, body: ReviewDecisions):
        with store.lock:
            _, saved = reports.save_decisions(identifier, body)
            return saved

    @router.post("/api/v1/jobs/{identifier}/final-report")
    def final_report(identifier: str, body: ReviewDecisions):
        return reports.final(identifier, body)

    @router.get("/api/v1/jobs/{identifier}/final-reports/{snapshot}/download")
    def download_final_report(identifier: str, snapshot: str):
        reports.get(identifier)
        name = store.folder("reports", snapshot).name
        if not name.startswith("report_"):
            raise ValueError("无效的报告 ID。")
        path = store.folder("jobs", identifier) / "final-reports" / (name + ".md")
        if not path.is_file():
            raise HTTPException(404, "最终报告不存在。")
        return FileResponse(path, filename="final-review-report.md")

    @router.get("/api/v1/jobs/{identifier}/evidence/{finding_index}/{location_index}")
    def evidence_page(
        identifier: str,
        finding_index: int,
        location_index: int,
        full_page: bool = False,
    ):
        result = reports.get(identifier)
        if finding_index < 0 or finding_index >= len(result.get("findings", [])):
            raise HTTPException(404, "未找到这条问题。")
        locations = result["findings"][finding_index].get("locations", [])
        if location_index < 0 or location_index >= len(locations):
            raise HTTPException(404, "未找到这处证据。")
        request = store.read(store.folder("jobs", identifier), "request.json")
        folder = store.folder("documents", request["document_ids"][0])
        meta = store.read(folder, "document.json")
        if meta["suffix"] != ".pdf":
            raise HTTPException(404, "这份材料没有 PDF 原页。")
        png = render_evidence_page(
            folder / ("source" + meta["suffix"]), locations[location_index], full_page
        )
        return Response(
            png,
            media_type="image/png",
            headers={"Cache-Control": "private, max-age=300"},
        )

    @router.get("/api/v1/jobs/{identifier}/download")
    def download(identifier: str):
        reports.get(identifier)
        return FileResponse(
            store.folder("jobs", identifier) / "report.md", filename="review-report.md"
        )

    return router
