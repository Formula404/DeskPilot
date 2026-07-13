from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from backend.app.knowledge.markdown import atomic_write, slugify
from backend.app.knowledge.paths import from_knowledge_relative, knowledge_root
from backend.app.knowledge.profiles import active_profile_id, get_profile
from backend.app.knowledge.repository import list_notes, list_sources, list_source_snapshots
from backend.app.knowledge.settings import get_knowledge_settings


def vault_path() -> Path:
    return knowledge_root() / "obsidian" / active_profile_id()


def export_obsidian_vault() -> dict[str, Any]:
    settings = get_knowledge_settings()
    if not settings.obsidian_enabled:
        raise ValueError("请先在设置中启用 Obsidian 集成。")
    root = vault_path()
    notes_dir = root / "Notes"
    sources_dir = root / "Sources"
    notes_dir.mkdir(parents=True, exist_ok=True)
    sources_dir.mkdir(parents=True, exist_ok=True)
    profile = get_profile(active_profile_id()) or {"name": "DeskPilot"}
    notes = list_notes(limit=10000)
    sources = list_sources(limit=10000)
    note_names = {item["id"]: f"{slugify(item['title'])}--{item['id'][-8:]}" for item in notes}

    expected: set[Path] = set()
    for note in notes:
        target = notes_dir / f"{note_names[note['id']]}.md"
        content = from_knowledge_relative(note["markdown_path"]).read_text(encoding="utf-8")
        links = [f"- [[{note_names[relation['to_note_id']]}|{relation['target_title']}]] ({relation['relation_type']})" for relation in note.get("relations", []) if relation["to_note_id"] in note_names]
        if links:
            content = content.rstrip() + "\n\n## Obsidian Links\n\n" + "\n".join(links) + "\n"
        atomic_write(target, content)
        expected.add(target)

    if settings.obsidian_include_sources:
        for source in sources:
            if not source.get("current_snapshot_id"):
                continue
            snapshots = list_source_snapshots(source["id"])
            snapshot = next((item for item in snapshots if item["id"] == source["current_snapshot_id"]), None)
            if not snapshot:
                continue
            target = sources_dir / f"{slugify(source['title'])}--{source['id'][-8:]}.md"
            shutil.copyfile(from_knowledge_relative(snapshot["markdown_path"]), target)
            expected.add(target)

    home = root / "Home.md"
    lines = [f"# {profile['name']}", "", "## Knowledge Notes", ""]
    lines.extend(f"- [[Notes/{note_names[item['id']]}|{item['title']}]]" for item in notes)
    atomic_write(home, "\n".join(lines) + "\n")
    expected.add(home)
    config = root / ".obsidian" / "app.json"
    atomic_write(config, json.dumps({"showInlineTitle": True, "newLinkFormat": "relative"}, indent=2) + "\n")
    expected.add(config)
    for directory in (notes_dir, sources_dir):
        for path in directory.glob("*.md"):
            if path not in expected:
                path.unlink()
    return {"profile_id": active_profile_id(), "vault_path": str(root.resolve()), "notes": len(notes), "sources": len(sources) if settings.obsidian_include_sources else 0}


def obsidian_status() -> dict[str, Any]:
    root = vault_path()
    return {"enabled": get_knowledge_settings().obsidian_enabled, "vault_path": str(root.resolve()), "exists": root.exists()}
