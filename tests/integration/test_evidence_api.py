import sys, tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from fastapi.testclient import TestClient
from app.main import create_app
from app.config import Settings
from app.storage import new_id

with tempfile.TemporaryDirectory(prefix="review-evidence-") as directory:
    app = create_app(Settings(data_dir=Path(directory)))
    store = app.state.store
    doc = store.save_document(
        "test.pdf",
        (Path(__file__).resolve().parents[1] / "fixtures/cross_page.pdf").read_bytes(),
        "primary",
    )
    identifier = new_id("job")
    folder = store.folder("jobs", identifier)
    store.write(folder, "request.json", {"document_ids": [doc["id"]]})
    store.write(folder, "state.json", {"id": identifier, "status": "partial"})
    store.write(
        folder,
        "report.json",
        {"findings": [{"locations": [{"page": 1, "bbox": [70, 100, 500, 150]}]}]},
    )
    with TestClient(app) as client:
        url = f"/api/v1/jobs/{identifier}/evidence/0/0"
        result = client.get(url)
        assert (
            result.status_code == 200 and result.headers["content-type"] == "image/png"
        )
        assert client.get(url + "?full_page=true").status_code == 200
        assert client.get(f"/api/v1/jobs/{identifier}/evidence/-1/0").status_code == 404
        assert client.get(f"/api/v1/jobs/{identifier}/evidence/0/5").status_code == 404
print("Published-report image endpoint, full page and invalid index tests passed")
