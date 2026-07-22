from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from backend.app.core.paths import data_dir
from backend.app.knowledge.paths import knowledge_root


def resolve_artifact_file(path_value: str) -> Path:
    if not path_value.strip():
        raise ValueError("文件路径不能为空。")
    try:
        target = Path(path_value).expanduser().resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise ValueError("文件不存在或无法访问。") from exc
    if not target.is_file():
        raise ValueError("目标不是可打开的文件。")

    allowed_roots = {data_dir().resolve(), knowledge_root().resolve()}
    if not any(target == root or root in target.parents for root in allowed_roots):
        raise ValueError("只能打开 DeskPilot 生成的文件。")
    return target


def open_artifact(path_value: str) -> Path:
    target = resolve_artifact_file(path_value)
    if os.name == "nt":
        os.startfile(str(target))  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(target)])
    else:
        subprocess.Popen(["xdg-open", str(target)])
    return target


def reveal_artifact(path_value: str) -> Path:
    target = resolve_artifact_file(path_value)
    if os.name == "nt":
        subprocess.Popen(["explorer.exe", f"/select,{target}"])
    elif sys.platform == "darwin":
        subprocess.Popen(["open", "-R", str(target)])
    else:
        subprocess.Popen(["xdg-open", str(target.parent)])
    return target
