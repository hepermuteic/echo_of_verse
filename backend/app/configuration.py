"""Typed TOML settings with environment overrides and secret references."""
import os
import tomllib
from pathlib import Path
from typing import Literal, Mapping
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator

ROOT = Path(__file__).resolve().parents[1]


class ConfigContract(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, hide_input_in_errors=True)


def http_endpoint(value: str) -> str:
    if not value:
        return value
    parsed = urlsplit(value)
    if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("Use an HTTP(S) endpoint without credentials, query or fragment")
    try:
        parsed.port
    except ValueError:
        raise ValueError("Endpoint port is invalid") from None
    return value.rstrip("/")


class AppConfig(ConfigContract):
    deployment_name: str = Field(default="local_single_process", min_length=1, max_length=128)
    cors_origins: list[str] = Field(default_factory=list)

    @field_validator("cors_origins")
    @classmethod
    def exact_origins(cls, values):
        for value in values:
            http_endpoint(value)
            if not value or urlsplit(value).path not in ("", "/"):
                raise ValueError("CORS origins must be explicit HTTP(S) origins")
        return [value.rstrip("/") for value in values]


class ApiConfig(ConfigContract):
    base_url: str = Field(default="http://127.0.0.1:8000", min_length=1)
    timeout_seconds: float = Field(default=5, gt=0, le=120, allow_inf_nan=False)
    _endpoint = field_validator("base_url")(http_endpoint)


class DatabaseConfig(ConfigContract):
    sqlite_path: str = Field(default="data/demo.sqlite3", min_length=1)
    url_env: str = Field(default="DATABASE_URL", pattern=r"^[A-Z][A-Z0-9_]*$")


class RedisConfig(ConfigContract):
    url_env: str = Field(default="REDIS_URL", pattern=r"^[A-Z][A-Z0-9_]*$")
    timeout_seconds: float = Field(default=0.2, gt=0, le=30, allow_inf_nan=False)


class ModelConfig(ConfigContract):
    enabled: bool = Field(default=False, strict=True)
    provider: str = Field(default="", max_length=128)
    api_base_url: str = ""
    model: str = Field(default="", max_length=256)
    api_key_env: str = Field(pattern=r"^[A-Z][A-Z0-9_]*$")
    requires_api_key: bool = Field(default=True, strict=True)
    timeout_seconds: float = Field(default=60, gt=0, le=600, allow_inf_nan=False)
    max_retries: int = Field(default=2, ge=0, le=5, strict=True)
    _endpoint = field_validator("api_base_url")(http_endpoint)


class StorageConfig(ConfigContract):
    enabled: bool = Field(default=False, strict=True)
    provider: Literal["local", "minio", "oss"] = "local"
    local_assets_path: str = Field(default="data/assets", min_length=1)
    endpoint: str = ""
    region: str = ""
    bucket: str = ""
    access_key_id_env: str = Field(default="EOV_STORAGE_ACCESS_KEY_ID", pattern=r"^[A-Z][A-Z0-9_]*$")
    secret_access_key_env: str = Field(default="EOV_STORAGE_SECRET_ACCESS_KEY", pattern=r"^[A-Z][A-Z0-9_]*$")
    session_token_env: str = Field(default="EOV_STORAGE_SESSION_TOKEN", pattern=r"^[A-Z][A-Z0-9_]*$")
    timeout_seconds: float = Field(default=10, gt=0, le=120, allow_inf_nan=False)
    presigned_url_ttl_seconds: int = Field(default=900, ge=60, le=86400, strict=True)
    _endpoint = field_validator("endpoint")(http_endpoint)


class ServiceConfig(ConfigContract):
    config_version: Literal["1.0"] = "1.0"
    app: AppConfig = Field(default_factory=AppConfig)
    api: ApiConfig = Field(default_factory=ApiConfig)
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    redis: RedisConfig = Field(default_factory=RedisConfig)
    llm: ModelConfig = Field(default_factory=lambda: ModelConfig(api_key_env="LLM_API_KEY"))
    embedding: ModelConfig = Field(default_factory=lambda: ModelConfig(api_key_env="EMBEDDING_API_KEY", timeout_seconds=30))
    storage: StorageConfig = Field(default_factory=StorageConfig)


def config_path(environ: Mapping[str, str] | None = None) -> Path:
    env = os.environ if environ is None else environ
    if env.get("EOV_CONFIG_FILE"):
        path = Path(env["EOV_CONFIG_FILE"])
        return path if path.is_absolute() else ROOT / path
    private = ROOT / "config/services.toml"
    return private if private.is_file() else ROOT / "config/services.example.toml"


def load_config(path: str | Path | None = None, environ: Mapping[str, str] | None = None) -> ServiceConfig:
    env = os.environ if environ is None else environ
    selected = config_path(env) if path is None else Path(path)
    if not selected.is_absolute():
        selected = ROOT / selected
    with selected.open("rb") as handle:
        data = tomllib.load(handle)
    overrides = {
        "EOV_DB_PATH": ("database", "sqlite_path"), "EOV_DEPLOYMENT_NAME": ("app", "deployment_name"),
        "EOV_API_BASE_URL": ("api", "base_url"),
        "LLM_API_BASE_URL": ("llm", "api_base_url"), "LLM_MODEL": ("llm", "model"),
        "EMBEDDING_API_BASE_URL": ("embedding", "api_base_url"), "EMBEDDING_MODEL": ("embedding", "model"),
        "EOV_STORAGE_ENDPOINT": ("storage", "endpoint"), "EOV_STORAGE_BUCKET": ("storage", "bucket"),
        "EOV_STORAGE_REGION": ("storage", "region"),
    }
    for key, (section, field) in overrides.items():
        # Empty values injected by old Compose templates must not erase TOML defaults.
        if env.get(key):
            data.setdefault(section, {})[field] = env[key]
    if "EOV_CORS_ORIGINS" in env:
        data.setdefault("app", {})["cors_origins"] = [v.strip() for v in env["EOV_CORS_ORIGINS"].split(",") if v.strip()]
    return ServiceConfig.model_validate(data)


def secret(name: str, environ: Mapping[str, str] | None = None) -> SecretStr:
    env = os.environ if environ is None else environ
    return SecretStr(env.get(name, ""))


def configured_database_url(config: ServiceConfig | None = None) -> str:
    config = config or load_config()
    return secret(config.database.url_env).get_secret_value()


def configured_redis_url(config: ServiceConfig | None = None) -> str:
    config = config or load_config()
    return secret(config.redis.url_env).get_secret_value()


def configuration_checks(config: ServiceConfig, environ: Mapping[str, str] | None = None) -> list[dict]:
    """Readiness to configure adapters, never a claim that adapters are connected."""
    env = os.environ if environ is None else environ
    results = []
    from sqlalchemy.engine import make_url
    database_value = secret(config.database.url_env, env).get_secret_value()
    if database_value:
        try:
            parsed = make_url(database_value)
            valid = parsed.drivername in ("sqlite", "postgresql+psycopg") and bool(parsed.database)
        except Exception:
            valid = False
        results.append({"service": "database", "status": "configured_only" if valid else "invalid"})
    else:
        results.append({"service": "database", "status": "local_sqlite"})
    redis_value = secret(config.redis.url_env, env).get_secret_value()
    if redis_value:
        try:
            parsed = urlsplit(redis_value)
            valid = parsed.scheme in ("redis", "rediss") and bool(parsed.hostname) and not parsed.fragment
            parsed.port
        except ValueError:
            valid = False
        results.append({"service": "redis", "status": "configured_only" if valid else "invalid"})
    else:
        results.append({"service": "redis", "status": "disabled"})
    for name in ("llm", "embedding"):
        item = getattr(config, name)
        missing = [field for field in ("provider", "api_base_url", "model") if not getattr(item, field)]
        if item.requires_api_key and not secret(item.api_key_env, env).get_secret_value().strip():
            missing.append("api_key_env")
        results.append({"service": name, "status": "disabled" if not item.enabled else "incomplete" if missing else "configured_only",
                        "missing": missing if item.enabled else []})
    item = config.storage
    missing = []
    if item.provider != "local":
        missing = [field for field in ("endpoint", "bucket") if not getattr(item, field)]
        for field in ("access_key_id_env", "secret_access_key_env"):
            if not secret(getattr(item, field), env).get_secret_value().strip():
                missing.append(field)
        if item.provider == "oss" and not item.region:
            missing.append("region")
    results.append({"service": "storage", "status": "disabled" if not item.enabled else "incomplete" if missing else "configured_only",
                    "missing": missing if item.enabled else []})
    return results
