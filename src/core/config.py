import logging
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, Field, PostgresDsn, RedisDsn, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent.parent
ENV_FILE = BASE_DIR / ".env"

API_V1_PREFIX = "/api/v1"

ACCESS_TOKEN_TTL_MINUTES = 30
REFRESH_TOKEN_TTL_DAYS = 30
MIN_ACTIVE_DEVICES = 5
MIN_CACHE_TTL_DAYS = 30


class AppConfig(BaseModel):
    env: str = "development"
    base_url: str = "http://localhost:8000"
    allowed_origins: list[str] = Field(default_factory=lambda: ["http://localhost:8000"])
    trusted_proxies: list[str] = Field(default_factory=list)


class PostgresConfig(BaseModel):
    dsn: PostgresDsn
    echo: bool = False
    echo_pool: bool = False
    pool_size: int = Field(default=10, ge=1)
    max_overflow: int = Field(default=5, ge=0)
    pool_pre_ping: bool = True
    pool_timeout: int = Field(default=30, ge=1)

    @property
    def url(self) -> str:
        return self.dsn.unicode_string()


class RedisConfig(BaseModel):
    dsn: RedisDsn
    key_prefix: str = "slouka"
    max_connections: int = Field(default=10, ge=1)
    socket_timeout: float = Field(default=5.0, gt=0)

    @property
    def url(self) -> str:
        return self.dsn.unicode_string()


class AuthConfig(BaseModel):
    jwt_secret: SecretStr
    jwt_algorithm: str = "HS256"
    access_token_ttl_minutes: int = ACCESS_TOKEN_TTL_MINUTES
    refresh_token_ttl_days: int = REFRESH_TOKEN_TTL_DAYS
    max_active_devices: int = Field(default=MIN_ACTIVE_DEVICES, ge=MIN_ACTIVE_DEVICES)

    @field_validator("access_token_ttl_minutes")
    @classmethod
    def access_ttl_is_not_configurable(cls, value: int) -> int:
        if value != ACCESS_TOKEN_TTL_MINUTES:
            raise ValueError(f"access token TTL is fixed at {ACCESS_TOKEN_TTL_MINUTES} minutes")
        return value

    @field_validator("refresh_token_ttl_days")
    @classmethod
    def refresh_ttl_is_not_configurable(cls, value: int) -> int:
        if value != REFRESH_TOKEN_TTL_DAYS:
            raise ValueError(f"refresh token TTL is fixed at {REFRESH_TOKEN_TTL_DAYS} days")
        return value


class SmtpConfig(BaseModel):
    host: str
    port: int = Field(default=1025, ge=1, le=65535)
    from_email: str
    user: str | None = None
    password: SecretStr | None = None
    use_tls: bool = False


class HttpClientConfig(BaseModel):
    timeout_seconds: float = Field(default=10.0, gt=0)
    max_retries: int = Field(default=3, ge=0)


class CacheConfig(BaseModel):
    ttl_days: int = Field(default=MIN_CACHE_TTL_DAYS, ge=MIN_CACHE_TTL_DAYS)


class RateLimitConfig(BaseModel):
    login_window_seconds: int = Field(default=300, ge=1)
    login_max_attempts: int = Field(default=10, ge=1)


class LoggingConfig(BaseModel):
    level: str = "INFO"

    @field_validator("level")
    @classmethod
    def level_is_known(cls, value: str) -> str:
        normalized = value.upper()
        if normalized not in logging.getLevelNamesMapping():
            raise ValueError(f"unknown logging level: {value}")
        return normalized


class Settings(BaseSettings):
    app: AppConfig = Field(default_factory=AppConfig)
    db: PostgresConfig
    redis: RedisConfig
    auth: AuthConfig
    smtp: SmtpConfig
    http: HttpClientConfig = Field(default_factory=HttpClientConfig)
    cache: CacheConfig = Field(default_factory=CacheConfig)
    rate_limit: RateLimitConfig = Field(default_factory=RateLimitConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)

    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        extra="ignore",
    )


class DatabaseSettings(BaseSettings):
    db: PostgresConfig

    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()  # pyright: ignore[reportCallIssue]
