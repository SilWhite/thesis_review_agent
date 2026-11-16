from pathlib import Path
from fastapi import APIRouter, UploadFile, File, Form
from fastapi.responses import FileResponse
from app.schemas import TextInput

EXTENSIONS = {".pdf", ".docx", ".txt", ".png", ".jpg", ".jpeg"}


def create_router(store, settings):
    router = APIRouter()

    @router.post("/api/v1/documents", status_code=201)
    async def upload(file: UploadFile = File(...), role: str = Form("primary")):
        if role not in {"primary", "policy"}:
            raise ValueError("不支持的材料角色。")
        if Path(file.filename or "").suffix.lower() not in EXTENSIONS:
            raise ValueError("支持 PDF、DOCX、TXT、PNG 和 JPG。")
        data = await file.read(settings.max_upload + 1)
        if not data or len(data) > settings.max_upload:
            raise ValueError("文件必须非空且不超过 30MB。")
        return store.save_document(file.filename, data, role)

    @router.post("/api/v1/documents/text", status_code=201)
    def text_document(body: TextInput):
        if not body.text.strip():
            raise ValueError("材料文本不能为空。")
        return store.save_document(body.title + ".txt", body.text.encode())

    @router.get("/api/v1/documents")
    def documents():
        return store.documents()

    @router.get("/api/v1/documents/{identifier}/content")
    def document_content(identifier: str):
        folder = store.folder("documents", identifier)
        meta = store.read(folder, "document.json")
        return FileResponse(
            folder / ("source" + meta["suffix"]), filename=meta["filename"]
        )

    return router
