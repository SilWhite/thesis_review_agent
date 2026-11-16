"""Application factory. Run app.main:create_app with one worker."""

from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from .api import documents, jobs, reports, search
from .config import Settings
from .jobs import ReviewService
from .storage import Store
from .reporting.service import ReportConflict

STATIC = Path(__file__).parent / "static"


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

    @app.exception_handler(ReportConflict)
    async def conflict(request, exc):
        return JSONResponse(status_code=409, content={"detail": str(exc)})

    app.include_router(documents.create_router(store, settings))
    app.include_router(jobs.create_router(store, settings, service))
    app.include_router(reports.create_router(store))
    app.include_router(search.create_router(store))
    app.mount("/static", StaticFiles(directory=STATIC), name="static")

    @app.get("/")
    def index():
        return FileResponse(STATIC / "index.html")

    return app
