"""Extra focus reaches the model without changing the structured return contract."""

from pathlib import Path
import sys, io, json
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from app.review.checks.semantic import SemanticChecker
from app.config import Settings

checker = SemanticChecker(
    Settings(model_url="http://127.0.0.1:9/v1", model_name="fixture")
)
payloads = []


def respond(request, **kwargs):
    payloads.append(json.loads(request.data))
    return io.BytesIO(
        json.dumps({"choices": [{"message": {"content": '{"findings":[]}'}}]}).encode()
    )


with patch("app.model_client.urlopen", respond):
    for focus in ("", "请重点核查实验数据划分。"):
        checker.review_focus = focus
        assert checker._call_llm("【结构化覆盖核查】测试记录", "local") == (
            {"findings": []},
            None,
        )
assert "额外评审重点" not in payloads[0]["messages"][0]["content"]
assert "请重点核查实验数据划分。" in payloads[1]["messages"][0]["content"]
assert "必须逐项返回" in payloads[1]["messages"][0]["content"]
assert payloads[0]["messages"][1:] == payloads[1]["messages"][1:]
print(
    "Extra focus reaches model system context; original source and JSON contract preserved"
)
