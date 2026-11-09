"""HTTP routes only. Run with one worker, bound to 127.0.0.1."""

from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from .config import Settings
from .schemas import TextInput, ReviewRequest, SearchRequest
from .storage import Store, now, new_id
from .service import ReviewService
from .search import search_public

STATIC = Path(__file__).parent / "static"
EXTENSIONS = {".pdf", ".docx", ".txt", ".png", ".jpg", ".jpeg"}


def create_app(settings=None):
    settings = settings or Settings()
    store = Store(settings.data_dir)
    service = ReviewService(store, settings)

    @asynccontextmanager
    async def lifespan(app):
        yield
        service.worker.shutdown(wait=True)

    app = FastAPI(title="Thesis Review Agent", version="0.1.0", lifespan=lifespan)
    app.state.store, app.state.service = store, service

    @app.exception_handler(FileNotFoundError)
    async def missing(request, exc):
        return JSONResponse(
            status_code=404, content={"detail": "资源不存在或尚未生成。"}
        )

    @app.exception_handler(ValueError)
    async def invalid(request, exc):
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    @app.get("/api/v1/config")
    def config():
        return dict(
            local_model_available=bool(settings.model_url and settings.model_name),
            model_name=settings.model_name,
            ocr_available=False,
            storage="local-files",
            version="0.1.0",
        )

    @app.post("/api/v1/documents", status_code=201)
    async def upload(file: UploadFile = File(...), role: str = Form("primary")):
        if role not in {"primary", "policy"}:
            raise ValueError("不支持的材料角色。")
        if Path(file.filename or "").suffix.lower() not in EXTENSIONS:
            raise ValueError("支持 PDF、DOCX、TXT、PNG 和 JPG。")
        data = await file.read(settings.max_upload + 1)
        if not data or len(data) > settings.max_upload:
            raise ValueError("文件必须非空且不超过 30MB。")
        return store.save_document(file.filename, data, role)

    @app.post("/api/v1/documents/text", status_code=201)
    def text_document(body: TextInput):
        if not body.text.strip():
            raise ValueError("材料文本不能为空。")
        return store.save_document(body.title + ".txt", body.text.encode())

    @app.get("/api/v1/documents")
    def documents():
        return store.documents()

    @app.get("/api/v1/documents/{identifier}/content")
    def document_content(identifier: str):
        folder = store.folder("documents", identifier)
        meta = store.read(folder, "document.json")
        return FileResponse(
            folder / ("source" + meta["suffix"]), filename=meta["filename"]
        )

    @app.post("/api/v1/jobs", status_code=202)
    def submit(body: ReviewRequest):
        if body.model_mode == "local" and not settings.model_url:
            raise ValueError("本地模型尚未配置。")
        return service.submit(body)

    @app.get("/api/v1/jobs")
    def jobs():
        return store.jobs()

    @app.get("/api/v1/jobs/{identifier}")
    def job(identifier: str):
        return store.read(store.folder("jobs", identifier), "state.json")

    @app.post("/api/v1/jobs/{identifier}/cancel")
    def cancel(identifier: str):
        return service.cancel(identifier)

    @app.get("/api/v1/jobs/{identifier}/report")
    def report(identifier: str):
        state = job(identifier)
        if state["status"] not in {"completed", "partial"}:
            raise HTTPException(409, "报告尚未发布。")
        return store.read(store.folder("jobs", identifier), "report.json")

    @app.get("/api/v1/jobs/{identifier}/content")
    def content(identifier: str):
        return store.read(store.folder("jobs", identifier), "content.json")

    @app.get("/api/v1/jobs/{identifier}/download")
    def download(identifier: str):
        report(identifier)
        return FileResponse(
            store.folder("jobs", identifier) / "report.md", filename="review-report.md"
        )

    @app.post("/api/v1/search")
    def search(body: SearchRequest):
        if not body.approved:
            raise HTTPException(403, "请先明确批准将这条公开查询发送到 Crossref。")
        try:
            results = search_public(body.query)
        except Exception as exc:
            raise HTTPException(502, f"公开检索失败：{exc}") from exc
        record = dict(
            id=new_id("search"),
            query=body.query,
            approved=True,
            created_at=now(),
            results=results,
        )
        store.write(store.root / "searches", record["id"] + ".json", record)
        return record

    app.mount("/static", StaticFiles(directory=STATIC), name="static")

    @app.get("/")
    def index():
        return FileResponse(STATIC / "index.html")

    return app
