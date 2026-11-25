"""Acquire and snapshot reviewable repository text; never import submitted code."""

import hashlib
import os
from pathlib import Path
import re
import subprocess
import tempfile
from urllib.parse import urlparse

SUFFIXES = {
    ".py",
    ".json",
    ".yaml",
    ".yml",
    ".toml",
    ".ini",
    ".cfg",
    ".md",
    ".rst",
    ".txt",
    ".sh",
    ".csv",
    ".jsonl",
}
EXCLUDED = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    "site-packages",
    "vendor",
    "dist",
    "build",
    "checkpoints",
    "wandb",
}
MAX_FILES, MAX_FILE_BYTES, MAX_TOTAL_BYTES = 200, 256_000, 8_000_000


def git(root, *args):
    env = dict(
        os.environ,
        GIT_CONFIG_NOSYSTEM="1",
        GIT_CONFIG_GLOBAL=os.devnull,
        GIT_TERMINAL_PROMPT="0",
        GIT_OPTIONAL_LOCKS="0",
        GIT_LFS_SKIP_SMUDGE="1",
    )
    return subprocess.run(
        [
            "git",
            "-c",
            "core.hooksPath=" + os.devnull,
            "-c",
            "core.fsmonitor=false",
            *args,
        ],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
        check=True,
    ).stdout.strip()


def prepare(spec, folder, checkpoint):
    if spec.kind == "github":
        url = urlparse(spec.location)
        parts = url.path.strip("/").removesuffix(".git").split("/")
        if (
            url.scheme != "https"
            or url.netloc != "github.com"
            or len(parts) != 2
            or not all(
                re.fullmatch(r"[\w.-]+", p) and p not in {".", ".."} for p in parts
            )
        ):
            raise ValueError("请提供 https://github.com/owner/repo 格式的仓库链接。")
        with tempfile.TemporaryDirectory(prefix="thesis-repository-") as directory:
            args = ["clone", "--depth", "1"]
            if spec.ref:
                args.extend(["--branch", spec.ref])
            git(
                directory,
                *args,
                "--",
                f"https://github.com/{parts[0]}/{parts[1]}.git",
                "repo",
            )
            return snapshot(Path(directory) / "repo", folder, spec, checkpoint)
    root = Path(spec.location).expanduser().resolve(strict=True)
    if not root.is_dir():
        raise ValueError("仓库路径必须是服务器可读取的目录。")
    return snapshot(root, folder, spec, checkpoint)


def snapshot(root, folder, spec, checkpoint):
    # Refuse a non-repository directory; never alter a local worktree.
    commit = git(root, "rev-parse", "HEAD")
    dirty = git(root, "status", "--porcelain", "--untracked-files=normal")
    files, notes, total = [], [], 0
    skipped = 0
    for directory, dirs, names in os.walk(root, followlinks=False):
        dirs[:] = sorted(
            d
            for d in dirs
            if d not in EXCLUDED
            and not d.startswith(".")
            and not (Path(directory) / d).is_symlink()
        )
        for name in sorted(names):
            checkpoint()
            path = Path(directory) / name
            if (
                path.is_symlink()
                or name.startswith(".")
                or (
                    path.suffix.lower() not in SUFFIXES
                    and name
                    not in {"Dockerfile", "Containerfile", "Makefile", "Pipfile"}
                )
            ):
                continue
            if path.stat().st_size > MAX_FILE_BYTES or len(files) >= MAX_FILES:
                skipped += 1
                continue
            content = path.read_bytes()
            if len(content) > MAX_FILE_BYTES or total + len(content) > MAX_TOTAL_BYTES:
                skipped += 1
                continue
            try:
                text = content.decode("utf-8-sig")
            except UnicodeDecodeError:
                skipped += 1
                continue
            if "\x00" in text:
                skipped += 1
                continue
            relative = path.relative_to(root).as_posix()
            target = folder / "repository" / "files" / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
            total += len(content)
            files.append(
                dict(
                    id=f"repo_{len(files)+1}",
                    path=relative,
                    text=text,
                    sha256=hashlib.sha256(content).hexdigest(),
                    lines=len(text.splitlines()),
                )
            )
    if skipped:
        notes.append(
            f"{skipped} 个候选文本文件因大小、预算或编码未纳入；未证明全文覆盖。"
        )
    if dirty:
        notes.append("仓库包含工作区修改或未跟踪文件；审查以保存的文本快照为准。")
    if not files:
        raise ValueError("仓库没有可审查的 UTF-8 文本文件。")
    metadata = dict(
        kind=spec.kind,
        location=spec.location,
        ref=spec.ref,
        commit=commit,
        dirty_status=dirty,
        file_count=len(files),
        bytes_read=total,
        files=[{k: v for k, v in f.items() if k != "text"} for f in files],
        notes=notes,
    )
    return metadata, files
