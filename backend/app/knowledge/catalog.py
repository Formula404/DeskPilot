from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from backend.app.knowledge.markdown import atomic_write, parse_markdown_document, split_sections
from backend.app.knowledge.paths import from_knowledge_relative, profile_workspace, relative_to_knowledge
from backend.app.knowledge.profiles import active_profile_id, get_profile
from backend.app.knowledge.repository import knowledge_counts, list_notes, list_sources


DEFAULT_SCHEMA = """# Wiki Schema

## Page Rules

- Create a page for a distinct entity or concept that will be linked from other pages.
- Update an existing page for new attributes, evidence, corrections, or refinements.
- Preserve source evidence and flag contradictions instead of silently resolving them.
- Prefer a small set of well-synthesized pages over one page per source.

## Ingest

- Read the source, find related pages, and emit every justified create, update, relation, or conflict operation.
- Update cross-references whenever a relationship is supported.

## Query

- Read the index first, then summaries, then full pages only when needed.
- Answers promoted to the wiki must preserve their supporting citations.

## Lint

- Check stale claims, contradictions, orphans, missing concepts, weak cross-references, and research gaps.
"""


def ensure_profile_workspace() -> Path:
    root = profile_workspace()
    root.mkdir(parents=True, exist_ok=True)
    schema = root / "schema.md"
    if not schema.exists():
        atomic_write(schema, DEFAULT_SCHEMA)
    log = root / "log.md"
    if not log.exists():
        atomic_write(log, "# Wiki Log\n")
    return root


def append_log(operation: str, title: str, details: str = "") -> None:
    root = ensure_profile_workspace()
    path = root / "log.md"
    timestamp = datetime.now(UTC).isoformat(timespec="seconds")
    entry = f"\n## [{timestamp}] {operation} | {title}\n"
    if details.strip():
        entry += f"\n{details.strip()}\n"
    atomic_write(path, path.read_text(encoding="utf-8").rstrip() + "\n" + entry)


def _summary(note: dict[str, Any]) -> str:
    try:
        content = from_knowledge_relative(note["markdown_path"]).read_text(encoding="utf-8")
        _, body = parse_markdown_document(content)
        _, sections = split_sections(body)
        return " ".join((sections.get("Summary") or sections.get("Overview") or "").split())[:180]
    except (OSError, ValueError):
        return ""


def refresh_catalogs() -> dict[str, Any]:
    root = ensure_profile_workspace()
    profile = get_profile(active_profile_id()) or {"name": "知识库"}
    notes = list_notes(limit=10000)
    sources = list_sources(limit=10000)
    grouped: dict[str, list[dict[str, Any]]] = {}
    for note in notes:
        grouped.setdefault(str(note["entity_type"]), []).append(note)

    index_lines = [f"# {profile['name']} Index", "", f"> {len(notes)} notes · {len(sources)} sources", ""]
    for entity_type, items in sorted(grouped.items()):
        index_lines.extend([f"## {entity_type.title()}", ""])
        for note in sorted(items, key=lambda item: str(item["title"]).casefold()):
            target = Path("../..") / str(note["markdown_path"])
            summary = _summary(note)
            index_lines.append(f"- [[{target.as_posix()}|{note['title']}]] — {summary or '暂无摘要'}")
        index_lines.append("")
    atomic_write(root / "index.md", "\n".join(index_lines))

    concept_lines = [
        "# Concept Index",
        "",
        f"> {len(notes)} knowledge pages. Read summaries here before opening full pages.",
        "",
    ]
    preferred_order = ["concept", "method", "tool", "project", "person", "event", "note"]
    entity_types = [item for item in preferred_order if item in grouped]
    entity_types.extend(sorted(item for item in grouped if item not in preferred_order))
    for entity_type in entity_types:
        concept_lines.extend([f"## {entity_type.title()}", ""])
        for item in sorted(grouped[entity_type], key=lambda note: str(note["title"]).casefold()):
            concept_lines.append(
                f"- [[../../{item['markdown_path']}|{item['title']}]] — {_summary(item) or '暂无摘要'}"
            )
        concept_lines.append("")
    atomic_write(root / "Concept Index.md", "\n".join(concept_lines) + "\n")

    counts = knowledge_counts()
    dashboard = [f"# {profile['name']} Dashboard", "", "## Status", ""]
    dashboard.extend(f"- {key.replace('_', ' ').title()}: {value}" for key, value in counts.items())
    dashboard.extend(["", "## Navigation", "", "- [[index|Wiki Index]]", "- [[Concept Index|Concept Index]]", "- [[log|Activity Log]]", "- [[schema|Wiki Schema]]", ""])
    atomic_write(root / "Dashboard.md", "\n".join(dashboard))
    for legacy_name in ["concept-index.md"]:
        (root / legacy_name).unlink(missing_ok=True)
    return {"profile_id": active_profile_id(), "path": relative_to_knowledge(root), "notes": len(notes), "sources": len(sources)}


def catalog_status() -> dict[str, Any]:
    root = ensure_profile_workspace()
    return {"path": str(root.resolve()), "files": {name: str((root / name).resolve()) for name in ["index.md", "Concept Index.md", "Dashboard.md", "log.md", "schema.md"]}}
