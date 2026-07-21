from __future__ import annotations

from fastapi.testclient import TestClient

from backend.app.core.config import get_settings
from backend.app.db.connection import init_db
from backend.app.db.repository import get_setting
from backend.app.main import app
from backend.app.settings.service import API_KEY_SETTING_KEY


def test_application_settings_round_trip_without_exposing_secret(tmp_path) -> None:
    core_settings = get_settings()
    original = core_settings.data_dir
    core_settings.data_dir = tmp_path / "data"
    init_db()
    try:
        client = TestClient(app)
        initial = client.get("/settings")
        assert initial.status_code == 200
        assert initial.json()["ai"]["api_key_configured"] is False

        response = client.put(
            "/settings",
            json={
                "schema_version": 1,
                "ai": {
                    "provider": "openai_compatible",
                    "base_url": "https://example.com/v1/",
                    "model": "example-chat",
                    "temperature": 0.4,
                    "request_timeout_seconds": 90,
                    "api_key": "secret-test-value",
                },
                "general": {"response_language": "en", "motion_mode": "reduced"},
            },
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["ai"]["base_url"] == "https://example.com/v1"
        assert payload["ai"]["api_key_configured"] is True
        assert "secret-test-value" not in response.text
        assert get_setting(API_KEY_SETTING_KEY) != "secret-test-value"

        unchanged = client.put(
            "/settings",
            json={
                "schema_version": 1,
                "ai": {
                    "provider": "openai_compatible",
                    "base_url": "https://example.com/v1",
                    "model": "new-model",
                    "temperature": 0.2,
                    "request_timeout_seconds": 30,
                    "api_key": None,
                },
                "general": {"response_language": "zh-CN", "motion_mode": "system"},
            },
        )
        assert unchanged.json()["ai"]["api_key_configured"] is True
    finally:
        core_settings.data_dir = original


def test_settings_reject_invalid_endpoint(tmp_path) -> None:
    core_settings = get_settings()
    original = core_settings.data_dir
    core_settings.data_dir = tmp_path / "data"
    init_db()
    try:
        response = TestClient(app).put(
            "/settings",
            json={
                "schema_version": 1,
                "ai": {
                    "provider": "openai_compatible",
                    "base_url": "not-a-url",
                    "model": "model",
                    "temperature": 0.2,
                    "request_timeout_seconds": 60,
                    "api_key": None,
                },
                "general": {"response_language": "zh-CN", "motion_mode": "system"},
            },
        )
        assert response.status_code == 422
    finally:
        core_settings.data_dir = original
