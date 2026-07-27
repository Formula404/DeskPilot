from __future__ import annotations

import json

from backend.app.db.repository import get_setting, set_setting
from backend.app.settings.models import (
    ApplicationSettings,
    ApplicationSettingsUpdate,
    PublicAISettings,
    PublicApplicationSettings,
    RuntimeAISettings,
    RuntimeApplicationSettings,
)
from backend.app.settings.secrets import protect_secret, reveal_secret

SETTINGS_KEY = "application.settings"
API_KEY_SETTING_KEY = "application.ai.api_key"


def _load_non_secret_settings() -> ApplicationSettings:
    raw = get_setting(SETTINGS_KEY)
    if not raw:
        return ApplicationSettings()
    try:
        return ApplicationSettings.model_validate(json.loads(raw))
    except (ValueError, TypeError, json.JSONDecodeError):
        return ApplicationSettings()


def get_runtime_settings() -> RuntimeApplicationSettings:
    settings = _load_non_secret_settings()
    key = reveal_secret(get_setting(API_KEY_SETTING_KEY))
    return RuntimeApplicationSettings(
        schema_version=settings.schema_version,
        ai=RuntimeAISettings(**settings.ai.model_dump(), api_key=key),
        general=settings.general,
        manager=settings.manager,
        specialists=settings.specialists,
    )


def _key_hint(key: str | None) -> str | None:
    if not key:
        return None
    if len(key) <= 8:
        return "••••••••"
    return f"{key[:3]}••••{key[-4:]}"


def get_public_settings() -> PublicApplicationSettings:
    runtime = get_runtime_settings()
    ai_data = runtime.ai.model_dump(exclude={"api_key"})
    return PublicApplicationSettings(
        schema_version=runtime.schema_version,
        ai=PublicAISettings(
            **ai_data,
            api_key_configured=bool(runtime.ai.api_key),
            api_key_hint=_key_hint(runtime.ai.api_key),
        ),
        general=runtime.general,
        manager=runtime.manager,
        specialists=runtime.specialists,
    )


def save_application_settings(update: ApplicationSettingsUpdate) -> PublicApplicationSettings:
    non_secret = ApplicationSettings(
        schema_version=update.schema_version,
        ai=update.ai.model_dump(exclude={"api_key"}),
        general=update.general,
        manager=update.manager,
        specialists=update.specialists,
    )
    set_setting(SETTINGS_KEY, non_secret.model_dump_json())
    if update.ai.api_key is not None:
        set_setting(API_KEY_SETTING_KEY, protect_secret(update.ai.api_key.strip()))
    return get_public_settings()
