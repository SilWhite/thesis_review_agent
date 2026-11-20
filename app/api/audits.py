"""Additive endpoints for optional material/novelty audit."""

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from app.audit.materials import save_material
from app.audit.schemas import AuditRequest


def create_router(store, settings, service):
    router = APIRouter()

    @router.post("/api/v1/audit-materials", status_code=201)
    async def upload(
        file: UploadFile = File(...),
        role: str = Form(...),
        split: str = Form("unknown"),
        id_column: str = Form(""),
    ):
        limit = min(settings.max_upload, 10 * 1024 * 1024)
        data = await file.read(limit + 1)
        if not data or len(data) > limit:
            raise ValueError("补充材料必须非空且不超过上传限制（最大 10MiB）。")
        return save_material(store, file.filename or "", data, role, split, id_column)

    @router.post("/api/v1/audits", status_code=202)
    def submit(body: AuditRequest):
        if body.check_novelty and body.public_queries and not body.search_approved:
            raise HTTPException(403, "请批准将所填的精确公开查询发送至 Crossref。")
        if body.model_mode == "local" and not (
            settings.model_url and settings.model_name
        ):
            raise ValueError("本地模型尚未配置。")
        return service.submit(body)

    @router.get("/api/v1/audit-materials/{identifier}/content")
    def material_content(identifier: str):
        folder = store.folder("audit-materials", identifier)
        meta = store.read(folder, "material.json")
        return FileResponse(
            folder / ("source" + meta["suffix"]), filename=meta["filename"]
        )

    @router.get("/api/v1/audits/{identifier}")
    def state(identifier: str):
        return service.state(identifier)

    @router.post("/api/v1/audits/{identifier}/cancel")
    def cancel(identifier: str):
        return service.cancel(identifier)

    def published(identifier):
        if service.state(identifier)["status"] not in {"completed", "partial"}:
            raise HTTPException(409, "补充审查报告尚未发布。")
        return store.folder("audits", identifier)

    @router.get("/api/v1/audits/{identifier}/report")
    def report(identifier: str):
        return store.read(published(identifier), "report.json")

    @router.get("/api/v1/audits/{identifier}/download")
    def download(identifier: str):
        return FileResponse(
            published(identifier) / "report.md", filename=f"{identifier}.md"
        )

    return router
