"""Read supplied text/data without importing or executing submitted code."""

import ast
import csv
import hashlib
import io
import json
import math
from pathlib import Path

import yaml

from app.storage import new_id, now

EXTENSIONS = {".py", ".json", ".jsonl", ".yaml", ".yml", ".csv", ".txt", ".log", ".md"}
ROLES = {"code", "config", "data", "result", "log", "description"}
FIELDS = {
    "epochs": "epochs",
    "num_epochs": "epochs",
    "epoch": "epochs",
    "batch_size": "batch_size",
    "learning_rate": "learning_rate",
    "lr": "learning_rate",
    "accuracy": "accuracy",
    "acc": "accuracy",
    "macro_f1": "macro_f1",
    "train_count": "train_count",
    "test_count": "test_count",
    "validation_count": "validation_count",
}


def save_material(store, filename, content, role, split, id_column):
    suffix = Path(filename).suffix.lower()
    if suffix not in EXTENSIONS or role not in ROLES:
        raise ValueError("材料格式或角色不支持。")
    if split not in {"train", "test", "validation", "all", "unknown"}:
        raise ValueError("不支持的数据划分。")
    content.decode("utf-8-sig")
    identifier = new_id("mat")
    folder = store.folder("audit-materials", identifier)
    folder.mkdir(parents=True)
    (folder / ("source" + suffix)).write_bytes(content)
    record = dict(
        id=identifier,
        filename=Path(filename).name,
        suffix=suffix,
        role=role,
        split=split,
        id_column=id_column,
        size_bytes=len(content),
        sha256=hashlib.sha256(content).hexdigest(),
        created_at=now(),
    )
    store.write(folder, "material.json", record)
    return record


def _leaves(value, path=""):
    if isinstance(value, dict):
        for key, item in value.items():
            yield from _leaves(item, f"{path}.{key}" if path else str(key))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from _leaves(item, f"{path}[{index}]")
    else:
        yield path, value


def read_material(store, identifier):
    folder = store.folder("audit-materials", identifier)
    meta = store.read(folder, "material.json")
    text = (folder / ("source" + meta["suffix"])).read_text(encoding="utf-8-sig")
    return parse_material(meta, text)


def parse_material(meta, text):
    """Shared text parser for uploaded materials and repository snapshots."""
    identifier = meta["id"]
    source = dict(
        id=identifier,
        filename=meta["filename"],
        role=meta["role"],
        text=text,
        location="文件全文",
        sha256=meta["sha256"],
    )
    facts, notes, ids = [], [], None

    def fact(field, value, location):
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            if not math.isfinite(value):
                notes.append(f"{location} 为非有限数值，未参与数值比较。")
                return
            facts.append(
                dict(
                    field=field,
                    value=value,
                    source_id=identifier,
                    location=location,
                    origin=meta["role"],
                    method="parsed",
                )
            )

    suffix = meta["suffix"]
    if suffix in {".json", ".yaml", ".yml"} and meta["role"] != "data":
        value = json.loads(text) if suffix == ".json" else yaml.safe_load(text)
        for path, value in _leaves(value):
            key = path.rsplit(".", 1)[-1]
            if key in FIELDS:
                fact(FIELDS[key], value, path)
    elif suffix == ".py" and meta["role"] == "code":
        tree = ast.parse(text)
        # Literal defaults are candidates, never treated as effective run settings.
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id in FIELDS:
                        fact(FIELDS[target.id], node.value.value, f"行 {node.lineno}")
    elif suffix == ".csv" and meta["role"] == "result":
        for row_number, row in enumerate(csv.DictReader(io.StringIO(text)), 2):
            for key, value in row.items():
                if key in FIELDS:
                    try:
                        number = float(value)
                    except (TypeError, ValueError):
                        continue
                    fact(FIELDS[key], number, f"CSV 行 {row_number} / {key}")
    elif meta["role"] == "data":
        if suffix == ".csv":
            rows = list(csv.DictReader(io.StringIO(text)))
        elif suffix == ".jsonl":
            rows = [json.loads(line) for line in text.splitlines() if line.strip()]
        elif suffix == ".json":
            rows = json.loads(text)
            if not isinstance(rows, list):
                raise ValueError("数据 JSON 必须是记录数组。")
        else:
            notes.append("数据仅按文本阅读，未统计样本数。")
            rows = None
        if rows is not None:
            if not all(isinstance(row, dict) for row in rows):
                raise ValueError("数据记录必须是对象。")
            if meta["split"] in {"train", "test", "validation"}:
                fact(meta["split"] + "_count", len(rows), "全部记录数")
            column = meta["id_column"]
            if (
                rows
                and column
                and all(column in row and row[column] not in (None, "") for row in rows)
            ):
                ids = {str(row[column]) for row in rows}
                if len(ids) != len(rows):
                    notes.append(f"列 {column} 存在重复 ID；ID 不一定代表独立样本。")
            else:
                notes.append("未取得完整样本 ID 列，未检查跨划分重叠。")
    return source, facts, notes, ids
