"""Read-only grouping of existing tasks; no parent task or duplicate artifacts."""

from fastapi import APIRouter


def create_router(store):
    router = APIRouter()

    @router.get("/api/v1/workspace/tasks")
    def tasks():
        groups = {}
        with store.lock:
            for kind, folder in [("review", "jobs"), ("audit", "audits")]:
                for path in (store.root / folder).glob("*/state.json"):
                    state = store.read(path.parent, path.name)
                    request = store.read(path.parent, "request.json")
                    ids = (
                        request["document_ids"]
                        if kind == "review"
                        else [request["document_id"]]
                    )
                    identifier = ids[0]
                    if identifier not in groups:
                        doc = store.read(
                            store.folder("documents", identifier), "document.json"
                        )
                        groups[identifier] = dict(
                            document_id=identifier, title=doc["filename"], tasks=[]
                        )
                    checks = (
                        ["review"]
                        if kind == "review"
                        else (
                            (["novelty"] if request["public_queries"] else [])
                            + (["experiments"] if request["experiments"] else [])
                        )
                    )
                    groups[identifier]["tasks"].append(
                        dict(state, kind=kind, checks=checks, document_ids=ids)
                    )
        for group in groups.values():
            group["tasks"].sort(key=lambda task: task["created_at"], reverse=True)
        return sorted(
            groups.values(),
            key=lambda group: group["tasks"][0]["created_at"],
            reverse=True,
        )

    return router
