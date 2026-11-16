from fastapi import APIRouter
from app.schemas import ReviewRequest


def create_router(store, settings, service):
    router = APIRouter()

    @router.post("/api/v1/jobs", status_code=202)
    def submit(body: ReviewRequest):
        if body.model_mode == "local" and not settings.model_url:
            raise ValueError("本地模型尚未配置。")
        return service.submit(body)

    @router.get("/api/v1/jobs")
    def jobs():
        return store.jobs()

    @router.get("/api/v1/jobs/{identifier}")
    def job(identifier: str):
        return store.read(store.folder("jobs", identifier), "state.json")

    @router.post("/api/v1/jobs/{identifier}/cancel")
    def cancel(identifier: str):
        return service.cancel(identifier)

    @router.get("/api/v1/jobs/{identifier}/content")
    def content(identifier: str):
        return store.read(store.folder("jobs", identifier), "content.json")

    return router
