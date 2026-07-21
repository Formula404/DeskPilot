from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from backend.app.db.repository import set_setting
from backend.app.knowledge.indexer import rebuild_index
from backend.app.knowledge.paths import KNOWLEDGE_ROOT_KEY, ensure_knowledge_dirs, knowledge_root


def choose_storage_directory() -> str | None:
    if os.name != "nt":
        raise ValueError("当前仅支持在 Windows 客户端中选择目录。")
    script = (
        "Add-Type -AssemblyName System.Windows.Forms; "
        "$dialog = New-Object System.Windows.Forms.FolderBrowserDialog; "
        "$dialog.Description = '选择 DeskPilot 知识库存储位置'; "
        "$dialog.ShowNewFolderButton = $true; "
        "if ($dialog.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) "
        "{ [Console]::OutputEncoding = [Text.Encoding]::UTF8; $dialog.SelectedPath }"
    )
    completed = subprocess.run(
        ["powershell.exe", "-NoProfile", "-STA", "-Command", script],
        capture_output=True,
        text=True,
        encoding="utf-8",
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        check=False,
    )
    if completed.returncode != 0:
        raise ValueError("无法打开 Windows 目录选择器。")
    selected = completed.stdout.strip()
    return str(Path(selected).resolve()) if selected else None


def _validate_target(path_value: str) -> Path:
    target = Path(path_value).expanduser().resolve()
    target.mkdir(parents=True, exist_ok=True)
    probe = target / ".deskpilot-write-test"
    try:
        probe.write_text("ok", encoding="utf-8")
    except OSError as exc:
        raise ValueError("所选目录不可写。") from exc
    finally:
        probe.unlink(missing_ok=True)
    return target


def change_storage_directory(path_value: str) -> dict[str, Any]:
    old_root = knowledge_root().resolve()
    target = _validate_target(path_value)
    if target == old_root:
        ensure_knowledge_dirs()
        return {"root_path": str(target), "migrated": False, "rebuild": rebuild_index()}
    if old_root in target.parents or target in old_root.parents:
        raise ValueError("新旧知识库目录不能互相包含。")

    has_content = any(target.iterdir())
    is_knowledge_root = (target / "purpose.md").exists() or (target / "notes").is_dir() or (target / "sources").is_dir()
    if has_content and not is_knowledge_root:
        raise ValueError("所选目录非空且不是 DeskPilot 知识库，请选择空目录或已有知识库目录。")
    migrated = False
    if not has_content and old_root.exists():
        shutil.copytree(old_root, target, dirs_exist_ok=True)
        migrated = True

    set_setting(KNOWLEDGE_ROOT_KEY, str(target))
    try:
        ensure_knowledge_dirs()
        rebuilt = rebuild_index()
    except Exception:
        set_setting(KNOWLEDGE_ROOT_KEY, str(old_root))
        ensure_knowledge_dirs()
        rebuild_index()
        raise
    return {"root_path": str(target), "previous_path": str(old_root), "migrated": migrated, "rebuild": rebuilt}


def open_storage_directory() -> None:
    root = knowledge_root().resolve()
    root.mkdir(parents=True, exist_ok=True)
    if os.name == "nt":
        os.startfile(root)  # type: ignore[attr-defined]
        return
    subprocess.Popen(["open" if __import__("sys").platform == "darwin" else "xdg-open", str(root)])
