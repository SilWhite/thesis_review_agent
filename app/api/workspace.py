"""Read-only grouping of existing tasks; no parent task or duplicate artifacts."""

from fastapi import APIRouter


def create_router(store):
    router = APIRouter()
    doc_cache = {}
    req_cache = {}

    @router.get("/api/v1/workspace/tasks")
    def tasks():
        groups = {}
        with store.lock:
            for kind, folder in [("review", "jobs"), ("audit", "audits")]:
                for path in (store.root / folder).glob("*/state.json"):
                    state = store.read(path.parent, path.name)
                    task_id = path.parent.name
                    if task_id in req_cache:
                        request = req_cache[task_id]
                    else:
                        request = store.read(path.parent, "request.json")
                        if state.get("status") in {"completed", "partial", "failed", "cancelled"}:
                            req_cache[task_id] = request

                    ids = (
                        request["document_ids"]
                        if kind == "review"
                        else [request["document_id"]]
                    )
                    identifier = ids[0]
                    if identifier not in groups:
                        if identifier in doc_cache:
                            doc = doc_cache[identifier]
                        else:
                            doc = store.read(
                                store.folder("documents", identifier), "document.json"
                            )
                            doc_cache[identifier] = doc
                        groups[identifier] = dict(
                            document_id=identifier, title=doc["filename"], tasks=[]
                        )

                    if kind == "review":
                        checks = ["review"]
                    else:
                        checks = []
                        if request.get("check_novelty") or (request.get("public_queries") and request.get("check_novelty") is not False):
                            checks.append("novelty")
                        if request.get("check_citations"):
                            checks.append("citations")
                        if request.get("check_experiments") or request.get("experiments"):
                            checks.append("experiments")
                        if not checks and request.get("public_queries"):
                            checks.append("novelty")
                        if not checks:
                            rep_path = path.parent / "report.json"
                            if rep_path.exists():
                                try:
                                    rep = store.read(path.parent, "report.json")
                                    if rep.get("novelty") and rep["novelty"].get("status") != "未启用":
                                        checks.append("novelty")
                                    if rep.get("citations") and rep["citations"].get("status") != "未启用":
                                        checks.append("citations")
                                    if rep.get("experiments") and rep["experiments"].get("status") != "未启用":
                                        checks.append("experiments")
                                except Exception:
                                    pass
                        if not checks and not request.get("experiments"):
                            checks = ["novelty"]

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
