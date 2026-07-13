from __future__ import annotations

import json

from backend.app.db.repository import get_setting, set_setting
from backend.app.knowledge.models import KnowledgeSettings
from backend.app.knowledge.profiles import DEFAULT_PROFILE_ID, active_profile_id

SETTING_KEY = "knowledge.settings"


def get_knowledge_settings() -> KnowledgeSettings:
    profile_id = active_profile_id()
    raw = get_setting(f"{SETTING_KEY}.{profile_id}")
    if not raw and profile_id == DEFAULT_PROFILE_ID:
        raw = get_setting(SETTING_KEY)
    if not raw:
        return KnowledgeSettings()
    try:
        return KnowledgeSettings.model_validate(json.loads(raw))
    except (ValueError, TypeError):
        return KnowledgeSettings()


def save_knowledge_settings(settings: KnowledgeSettings) -> KnowledgeSettings:
    set_setting(f"{SETTING_KEY}.{active_profile_id()}", settings.model_dump_json())
    return settings
