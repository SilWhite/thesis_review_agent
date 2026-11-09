"""Job lifecycle. One worker serializes reviews; each job keeps five small files."""

import logging
from concurrent.futures import ThreadPoolExecutor
from langsmith import tracing_context

from .schemas import ReviewRequest
from .storage import now, new_id
from .workflow import ReviewCancelled, build_workflow

log = logging.getLogger(__name__)
TERMINAL = {"completed", "partial", "failed", "cancelled", "interrupted"}


class ReviewService:
    def __init__(self, store, settings):
        self.store, self.settings = store, settings
        self.worker = ThreadPoolExecutor(max_workers=1)
        self.graph = build_workflow(store, settings, self.advance)
        for job in store.jobs():
            if job["status"] in {"queued", "running"}:
                store.update_job(
                    job["id"],
                    status="interrupted",
                    error="服务重启中断了任务，请重新提交。",
                )

    def submit(self, request):
        for identifier in request.document_ids + request.policy_ids:
            self.store.read(self.store.folder("documents", identifier), "document.json")
        identifier = new_id("job")
        folder = self.store.folder("jobs", identifier)
        self.store.write(folder, "request.json", request.model_dump())
        state = dict(
            id=identifier,
            created_at=now(),
            updated_at=now(),
            status="queued",
            stage="queued",
            error=None,
            title=self.store.read(
                self.store.folder("documents", request.document_ids[0]), "document.json"
            )["filename"],
            mode=request.model_mode,
        )
        self.store.write(folder, "state.json", state)
        self.worker.submit(self.run, identifier, request)
        return state

    def cancel(self, identifier):
        with self.store.lock:
            state = self.store.read(self.store.folder("jobs", identifier), "state.json")
            if state["status"] not in TERMINAL:
                return self.store.update_job(identifier, status="cancelled")
            return state

    def advance(self, identifier, stage):
        with self.store.lock:
            if (
                self.store.read(self.store.folder("jobs", identifier), "state.json")[
                    "status"
                ]
                == "cancelled"
            ):
                return False
            self.store.update_job(identifier, stage=stage, status="running")
            return True

    def run(self, identifier, request: ReviewRequest):
        folder = self.store.folder("jobs", identifier)
        try:
            with tracing_context(enabled=False):
                self.graph.invoke({"job_id": identifier, "request": request})
        except ReviewCancelled:
            return
        except Exception as exc:
            log.exception("Review failed: %s", identifier)
            with self.store.lock:
                if self.store.read(folder, "state.json")["status"] != "cancelled":
                    self.store.update_job(identifier, status="failed", error=str(exc))
