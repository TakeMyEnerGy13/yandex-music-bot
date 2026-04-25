import pytest
from pydantic import ValidationError

from bot.config import Settings


def test_settings_loads_from_env(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "tg-test")
    monkeypatch.setenv("YANDEX_MUSIC_TOKEN", "ym-test")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/1")

    settings = Settings(_env_file=None)

    assert settings.telegram_bot_token == "tg-test"
    assert settings.yandex_music_token == "ym-test"
    assert settings.redis_url == "redis://localhost:6379/1"
    assert settings.log_level == "INFO"
    assert settings.rate_limit_per_minute == 10
    assert settings.songlink_timeout == 2.0
    assert settings.inline_timeout == 0.8


def test_settings_requires_tokens(monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("YANDEX_MUSIC_TOKEN", raising=False)

    with pytest.raises(ValidationError):
        Settings(_env_file=None)
