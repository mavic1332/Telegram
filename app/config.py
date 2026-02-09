from __future__ import annotations

from typing import List

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    telegram_bot_token: str = Field(alias="TELEGRAM_BOT_TOKEN")

    resolver_base_url: str = Field(default="mock", alias="RESOLVER_BASE_URL")
    resolver_api_key: str = Field(default="", alias="RESOLVER_API_KEY")

    service_a_base_url: str = Field(default="mock", alias="SERVICE_A_BASE_URL")
    service_a_api_key: str = Field(default="", alias="SERVICE_A_API_KEY")

    service_b_base_url: str = Field(default="mock", alias="SERVICE_B_BASE_URL")
    service_b_api_key: str = Field(default="", alias="SERVICE_B_API_KEY")

    voip_timeout_seconds: int = Field(default=10, alias="VOIP_TIMEOUT_SECONDS")
    allowed_chat_ids: str = Field(default="", alias="ALLOWED_CHAT_IDS")
    audit_db_path: str = Field(default="./audit.db", alias="AUDIT_DB_PATH")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    mask_output: bool = Field(default=False, alias="MASK_OUTPUT")

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", case_sensitive=False)

    @property
    def allowed_chat_ids_list(self) -> List[int]:
        if not self.allowed_chat_ids.strip():
            return []
        return [int(v.strip()) for v in self.allowed_chat_ids.split(",") if v.strip()]


settings = Settings()
