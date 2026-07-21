from __future__ import annotations

from pathlib import Path

from backend.app.core.paths import data_dir
from backend.app.db.repository import get_setting

KNOWLEDGE_ROOT_KEY = "knowledge.root_path"


def knowledge_root() -> Path:
    configured = get_setting(KNOWLEDGE_ROOT_KEY)
    configured = configured.strip() if configured else ""
    return Path(configured).expanduser() if configured else data_dir() / "knowledge"


def purpose_path() -> Path:
    return knowledge_root() / "purpose.md"


def profile_workspace(profile_id: str | None = None) -> Path:
    from backend.app.knowledge.profiles import active_profile_id
    return knowledge_root() / "profiles" / (profile_id or active_profile_id())


def ensure_knowledge_dirs() -> None:
    root = knowledge_root()
    for relative in [
        "schema",
        "sources/web",
        "sources/file",
        "sources/user",
        "notes/concept",
        "notes/person",
        "notes/project",
        "notes/tool",
        "notes/method",
        "notes/event",
        "notes/note",
        "proposals/pending",
        "proposals/rejected",
        "outputs/queries",
        "outputs/reports",
        "cache/chunks",
        "trash",
        "profiles",
    ]:
        (root / relative).mkdir(parents=True, exist_ok=True)

    if not purpose_path().exists():
        purpose_path().write_text(
            """# Knowledge Base Purpose

## Scope

- DeskPilot 相关设计、实现依据和技术调研。
- 用户主动收集并希望长期保留的工作知识。

## Exclusions

- 密码、令牌、银行卡号等秘密信息。
- 未经明确要求保存的聊天正文和私人通信。
- 仅对当前任务有用的临时页面内容。

## Writing Rules

- 事实陈述保留来源。
- 不确定内容明确标记，不补造来源。
- 优先更新已有条目，避免创建同义重复条目。
""",
            encoding="utf-8",
        )


def safe_knowledge_path(path: Path) -> Path:
    root = knowledge_root().resolve()
    resolved = path.resolve(strict=False)
    if resolved != root and root not in resolved.parents:
        raise ValueError("知识库路径越界。")
    return resolved


def relative_to_knowledge(path: Path) -> str:
    return safe_knowledge_path(path).relative_to(knowledge_root().resolve()).as_posix()


def from_knowledge_relative(relative: str) -> Path:
    if not relative or Path(relative).is_absolute():
        raise ValueError("知识库相对路径无效。")
    return safe_knowledge_path(knowledge_root() / relative)
