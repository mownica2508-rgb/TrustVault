from functools import lru_cache

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "TrustVault"
    environment: str = "development"
    database_url: str = Field(min_length=1)
    jwt_secret: SecretStr
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = Field(default=30, ge=1, le=1440)

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @field_validator("jwt_secret")
    @classmethod
    def validate_jwt_secret(cls, value: SecretStr) -> SecretStr:
        if len(value.get_secret_value()) < 32:
            raise ValueError("JWT_SECRET must contain at least 32 characters")
        return value

    @field_validator("jwt_algorithm")
    @classmethod
    def require_hmac_sha256(cls, value: str) -> str:
        if value != "HS256":
            raise ValueError("Only HS256 is currently supported")
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
