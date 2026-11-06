from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "TrustVault"
    environment: str = "development"
    database_url: str = Field(min_length=1)
    migration_database_url: str | None = None
    jwt_secret: SecretStr
    audit_hmac_key: SecretStr | None = None
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = Field(default=30, ge=1, le=1440)
    storage_dir: Path = Path("private_storage")
    max_upload_bytes: int = Field(default=10 * 1024 * 1024, ge=1024, le=100 * 1024 * 1024)

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

    @field_validator("audit_hmac_key")
    @classmethod
    def validate_audit_hmac_key(cls, value: SecretStr | None) -> SecretStr | None:
        if value is not None and len(value.get_secret_value()) < 32:
            raise ValueError("AUDIT_HMAC_KEY must contain at least 32 characters when set")
        return value

    @field_validator("jwt_algorithm")
    @classmethod
    def require_hmac_sha256(cls, value: str) -> str:
        if value != "HS256":
            raise ValueError("Only HS256 is currently supported")
        return value

    @property
    def resolved_storage_dir(self) -> Path:
        path = self.storage_dir.expanduser()
        if not path.is_absolute():
            path = Path(__file__).resolve().parents[2] / path
        return path.resolve()


@lru_cache
def get_settings() -> Settings:
    return Settings()
