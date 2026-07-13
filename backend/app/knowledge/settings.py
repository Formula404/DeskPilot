from __future__ import annotations

import json

from backend.app.db.repository import get_setting, set_setting
from backend.app.knowledge.models import KnowledgeSettings

SETTING_KEY = "knowledge.settings"


def get_knowledge_settings() -> KnowledgeSettings:
    raw = get_setting(SETTING_KEY)
    if not raw:
        return KnowledgeSettings()
    try:
        return KnowledgeSettings.model_validate(json.loads(raw))
    except (ValueError, TypeError):
        return KnowledgeSettings()


def save_knowledge_settings(settings: KnowledgeSettings) -> KnowledgeSettings:
    set_setting(SETTING_KEY, settings.model_dump_json())
    return settings
