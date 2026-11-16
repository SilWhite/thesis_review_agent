from fastapi import APIRouter, HTTPException
from app.schemas import SearchRequest
from app.search import search_public
from app.storage import now, new_id


def create_router(store):
    router = APIRouter()

    @router.post("/api/v1/search")
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

    return router
