from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
import tempfile
import zipfile
from datetime import UTC, datetime
from pathlib import Path

from backend.app.core.paths import db_path
from backend.app.db.connection import exclusive_database_access
from backend.app.knowledge.paths import knowledge_root


class KnowledgeBackupError(RuntimeError):
    code = "KNOWLEDGE_BACKUP_INVALID"


class KnowledgeRestoreError(KnowledgeBackupError):
    code = "KNOWLEDGE_BACKUP_RESTORE_FAILED"

    def __init__(self, message: str, safety_backup_path: Path) -> None:
        super().__init__(message)
        self.safety_backup_path = str(safety_backup_path)


def _timestamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _copy_database(target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    if not db_path().exists():
        return
    source = sqlite3.connect(db_path(), timeout=30.0)
    destination = sqlite3.connect(target, timeout=30.0)
    try:
        source.execute("PRAGMA busy_timeout = 30000")
        destination.execute("PRAGMA busy_timeout = 30000")
        source.backup(destination, pages=256, sleep=0.05)
    finally:
        destination.close()
        source.close()


def backup_database() -> Path:
    target = knowledge_root() / "cache" / f"deskpilot-before-rebuild-{_timestamp()}.sqlite3"
    _copy_database(target)
    return target


def create_full_backup() -> Path:
    root = knowledge_root().resolve()
    output = root / "cache" / "backups" / f"deskpilot-knowledge-{_timestamp()}.zip"
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="deskpilot-backup-") as temporary:
        staging = Path(temporary)
        database = staging / "database.sqlite3"
        _copy_database(database)
        files: list[dict[str, str | int]] = []
        candidates = [path for path in root.rglob("*") if path.is_file()]
        for path in candidates:
            relative = path.relative_to(root).as_posix()
            if relative.startswith("cache/backups/") or path == output:
                continue
            files.append({"path": f"vault/{relative}", "sha256": _sha256(path), "size": path.stat().st_size})
        if database.exists():
            files.append({"path": "database.sqlite3", "sha256": _sha256(database), "size": database.stat().st_size})
        manifest = {"schema_version": 1, "created_at": datetime.now(UTC).isoformat(), "files": files}
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
            for item in files:
                name = str(item["path"])
                source = database if name == "database.sqlite3" else root / name.removeprefix("vault/")
                archive.write(source, name)
    return output


def _inspect_open_backup(archive: zipfile.ZipFile) -> dict:
    manifest = json.loads(archive.read("manifest.json"))
    if not isinstance(manifest, dict) or not isinstance(manifest.get("files"), list):
        raise KnowledgeBackupError("备份 manifest 结构无效。")
    if len(archive.namelist()) != len(set(archive.namelist())):
        raise KnowledgeBackupError("备份包含重复文件名。")
    names = set(archive.namelist())
    listed_names = {str(item["path"]) for item in manifest.get("files", [])}
    if names != listed_names | {"manifest.json"}:
        raise KnowledgeBackupError("备份包含 manifest 未声明的文件或缺少声明文件。")
    for item in manifest.get("files", []):
        name = str(item["path"])
        member_path = Path(name)
        if member_path.is_absolute() or ".." in member_path.parts or (name != "database.sqlite3" and not name.startswith("vault/")):
            raise KnowledgeBackupError(f"备份包含不安全路径：{name}")
        if name not in names:
            raise KnowledgeBackupError(f"备份缺少文件：{name}")
        member = archive.getinfo(name)
        if (member.external_attr >> 16) & 0o170000 == 0o120000:
            raise KnowledgeBackupError(f"备份包含不允许的符号链接：{name}")
        if hashlib.sha256(archive.read(name)).hexdigest() != item["sha256"]:
            raise KnowledgeBackupError(f"备份文件校验失败：{name}")
    return manifest


def inspect_backup(archive_path: str | Path) -> dict:
    path = Path(archive_path).expanduser().resolve()
    if not path.is_file():
        raise KnowledgeBackupError("备份文件不存在。")
    try:
        with zipfile.ZipFile(path) as archive:
            manifest = _inspect_open_backup(archive)
    except (zipfile.BadZipFile, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise KnowledgeBackupError("备份格式无效或 manifest 已损坏。") from exc
    return {**manifest, "path": str(path), "valid": True}


def _extract_validated_backup(archive: zipfile.ZipFile, manifest: dict, target: Path) -> None:
    for item in manifest.get("files", []):
        name = str(item["path"])
        output = target / Path(name)
        output.parent.mkdir(parents=True, exist_ok=True)
        with archive.open(name) as source, output.open("wb") as destination:
            shutil.copyfileobj(source, destination)


def _restore_database(restored_db: Path) -> None:
    destination_path = db_path()
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    source = sqlite3.connect(restored_db, timeout=30.0)
    destination = sqlite3.connect(destination_path, timeout=30.0)
    try:
        source.execute("PRAGMA busy_timeout = 30000")
        destination.execute("PRAGMA busy_timeout = 30000")
        source.backup(destination, pages=256, sleep=0.05)
    finally:
        destination.close()
        source.close()


def restore_full_backup(archive_path: str | Path) -> dict:
    archive = Path(archive_path).expanduser().resolve()
    if not archive.is_file():
        raise KnowledgeBackupError("备份文件不存在。")
    safety_backup = create_full_backup()
    root = knowledge_root().resolve()
    try:
        with tempfile.TemporaryDirectory(prefix="deskpilot-restore-") as temporary:
            staging = Path(temporary)
            # Validation and extraction deliberately share one open file handle,
            # closing the path-replacement TOCTOU window.
            with zipfile.ZipFile(archive) as bundle:
                manifest = _inspect_open_backup(bundle)
                _extract_validated_backup(bundle, manifest, staging)
            with exclusive_database_access():
                restored_db = staging / "database.sqlite3"
                if restored_db.exists():
                    _restore_database(restored_db)
                for child in root.iterdir():
                    if child.name == "cache":
                        for cached in child.iterdir():
                            if cached.name != "backups":
                                shutil.rmtree(cached) if cached.is_dir() else cached.unlink()
                        continue
                    shutil.rmtree(child) if child.is_dir() else child.unlink()
                vault = staging / "vault"
                if vault.exists():
                    shutil.copytree(vault, root, dirs_exist_ok=True)
    except (zipfile.BadZipFile, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise KnowledgeBackupError("备份格式无效或 manifest 已损坏。") from exc
    except (OSError, sqlite3.Error) as exc:
        raise KnowledgeRestoreError(
            f"完整备份恢复失败；恢复前安全备份保留在：{safety_backup}",
            safety_backup,
        ) from exc
    return {"restored": True, "archive_path": str(archive), "safety_backup_path": str(safety_backup)}
