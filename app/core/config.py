from __future__ import annotations

import json
from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    bot_token: str = Field(alias="BOT_TOKEN")
    admin_ids: list[int] = Field(default_factory=list, alias="ADMIN_IDS")
    support_username: str = Field(default="HideBroSupport", alias="SUPPORT_USERNAME")

    postgres_dsn: str = Field(alias="POSTGRES_DSN")
    redis_dsn: str = Field(alias="REDIS_DSN")

    remnawave_base_url: str = Field(alias="REMNAWAVE_BASE_URL")
    remnawave_api_token: str | None = Field(default=None, alias="REMNAWAVE_API_TOKEN")
    remnawave_admin_username: str | None = Field(default=None, alias="REMNAWAVE_ADMIN_USERNAME")
    remnawave_admin_password: str | None = Field(default=None, alias="REMNAWAVE_ADMIN_PASSWORD")
    remnawave_internal_squad_uuid: str = Field(alias="REMNAWAVE_INTERNAL_SQUAD_UUID")
    remnawave_timeout_sec: float = Field(default=20.0, alias="REMNAWAVE_TIMEOUT_SEC")

    payments_provider: Literal["yookassa", "mock"] = Field(default="yookassa", alias="PAYMENTS_PROVIDER")
    yookassa_shop_id: str | None = Field(default=None, alias="YOOKASSA_SHOP_ID")
    yookassa_secret_key: str | None = Field(default=None, alias="YOOKASSA_SECRET_KEY")
    yookassa_return_url: str | None = Field(default=None, alias="YOOKASSA_RETURN_URL")

    referral_bonus_days: int = Field(default=5, alias="REFERRAL_BONUS_DAYS")
    device_limit: int = Field(default=3, alias="DEVICE_LIMIT")

    username_prefix: str = Field(default="HideBro_", alias="USERNAME_PREFIX")
    username_min_digits: int = Field(default=6, alias="USERNAME_MIN_DIGITS")
    username_max_digits: int = Field(default=7, alias="USERNAME_MAX_DIGITS")

    free_trial_days: int = Field(default=3, alias="FREE_TRIAL_DAYS")
    timezone: str = Field(default="Europe/Moscow", alias="APP_TIMEZONE")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    @field_validator("admin_ids", mode="before")
    @classmethod
    def parse_admin_ids(cls, value: str | int | list[int] | tuple[int, ...] | None) -> list[int]:
        if value is None:
            return []
        if isinstance(value, int):
            return [value]
        if isinstance(value, tuple):
            return [int(v) for v in value]
        if isinstance(value, list):
            return [int(v) for v in value]

        raw = value.strip()
        if not raw:
            return []

        if raw.startswith("[") and raw.endswith("]"):
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, list):
                    return [int(v) for v in parsed]
            except json.JSONDecodeError:
                pass

        cleaned = [part.strip() for part in raw.split(",") if part.strip()]
        return [int(v) for v in cleaned]

    @field_validator("support_username")
    @classmethod
    def normalize_support_username(cls, value: str) -> str:
        return value.lstrip("@")

    @field_validator("payments_provider")
    @classmethod
    def validate_payment_provider(cls, value: str) -> str:
        return value

    def validate_integrations(self) -> None:
        if not self.remnawave_api_token and not (
            self.remnawave_admin_username and self.remnawave_admin_password
        ):
            raise ValueError(
                "Нужны REMNAWAVE_API_TOKEN или пара REMNAWAVE_ADMIN_USERNAME/REMNAWAVE_ADMIN_PASSWORD"
            )

        if self.payments_provider == "yookassa":
            if not self.yookassa_shop_id or not self.yookassa_secret_key or not self.yookassa_return_url:
                raise ValueError(
                    "Для PAYMENTS_PROVIDER=yookassa нужны YOOKASSA_SHOP_ID, YOOKASSA_SECRET_KEY и YOOKASSA_RETURN_URL"
                )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    settings = Settings()
    settings.validate_integrations()
    return settings
