from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    telegram_bot_token: str
    yandex_music_token: str
    redis_url: str = "redis://redis:6379/0"
    log_level: str = "INFO"
    rate_limit_per_minute: int = 10
    songlink_timeout: float = 2.0
    inline_timeout: float = 0.8
