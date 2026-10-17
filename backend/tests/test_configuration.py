import json
import sqlite3
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.check_config import main, probe
from app.configuration import (ROOT, configuration_checks, configured_database_url, load_config, secret)
from app.settings import db_path

TEMPLATE = ROOT / "config/services.example.toml"


def test_canonical_template_defaults_and_cwd_independence(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("EOV_CONFIG_FILE", "config/services.example.toml")
    monkeypatch.delenv("EOV_DB_PATH", raising=False)
    config = load_config(environ={})
    assert config.database.sqlite_path == "data/demo.sqlite3"
    assert db_path() == ROOT / "data/demo.sqlite3"
    assert all(not getattr(config, name).enabled for name in ("llm", "embedding", "storage"))


def test_file_loading_env_precedence_and_secret_references(tmp_path, monkeypatch):
    path = tmp_path / "services.toml"
    path.write_text(TEMPLATE.read_text().replace('model = ""', 'model = "file-model"'), encoding="utf-8")
    env = {"LLM_MODEL": "env-model", "EMBEDDING_MODEL": "", "LLM_API_KEY": "secret-canary",
           "EOV_CORS_ORIGINS": "http://localhost:5173, http://127.0.0.1:5173"}
    config = load_config(path, env)
    assert config.llm.model == "env-model" and config.embedding.model == "file-model"
    assert len(config.app.cors_origins) == 2
    assert "secret-canary" not in config.model_dump_json()
    assert "secret-canary" not in str(secret("LLM_API_KEY", env))
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://user:secret-canary@localhost/test")
    assert configured_database_url(config).endswith("@localhost/test")


@pytest.mark.parametrize("edit", [
    ('config_version = "1.0"', 'config_version = "2.0"'),
    ('timeout_seconds = 60', 'timeout_seconds = 0'),
    ('max_retries = 2', 'max_retries = 10'),
    ('api_key_env = "LLM_API_KEY"', 'api_key_env = "actual-secret"'),
    ('base_url = "http://127.0.0.1:8000"', 'base_url = "https://user:secret-canary@example.com"'),
    ('cors_origins = []', 'cors_origins = ["*"]'),
])
def test_configuration_validation_rejects_bad_values(tmp_path, edit):
    path = tmp_path / "invalid.toml"
    path.write_text(TEMPLATE.read_text().replace(*edit), encoding="utf-8")
    with pytest.raises(ValidationError) as exc:
        load_config(path, {})
    assert "secret-canary" not in str(exc.value)


def test_active_service_readiness_does_not_mean_adapter_connected():
    config = load_config(TEMPLATE, {})
    config.llm.enabled = True
    result = next(c for c in configuration_checks(config, {}) if c["service"] == "llm")
    assert result["status"] == "incomplete"
    config.llm.provider = "test-provider"
    config.llm.api_base_url = "https://example.com/v1"
    config.llm.model = "test-model"
    result = next(c for c in configuration_checks(config, {"LLM_API_KEY": "secret-canary"}) if c["service"] == "llm")
    assert result["status"] == "configured_only"
    assert "secret-canary" not in json.dumps(result)


def test_url_readiness_and_storage_missing_fields():
    config = load_config(TEMPLATE, {})
    config.storage.enabled = True
    config.storage.provider = "oss"
    checks = configuration_checks(config, {"DATABASE_URL": "invalid-secret-canary", "REDIS_URL": "https://example.com"})
    assert next(c for c in checks if c["service"] == "database")["status"] == "invalid"
    assert next(c for c in checks if c["service"] == "redis")["status"] == "invalid"
    assert "region" in next(c for c in checks if c["service"] == "storage")["missing"]


def test_offline_cli_never_probes_and_ready_requirement_is_honest(monkeypatch, capsys):
    monkeypatch.setenv("EOV_CONFIG_FILE", str(TEMPLATE))
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("REDIS_URL", raising=False)
    def unexpected(*args):
        pytest.fail("Offline check attempted a network probe")
    monkeypatch.setattr("app.check_config.probe", unexpected)
    assert main(["--manifest", "examples/resource-manifest.json"]) == 0
    assert json.loads(capsys.readouterr().out)["ok"]
    assert main(["--manifest", "examples/resource-manifest.json", "--require-ready"]) == 1
    assert not json.loads(capsys.readouterr().out)["ok"]


def test_cli_validation_errors_do_not_print_endpoint_credentials(tmp_path, capsys):
    path = tmp_path / "invalid.toml"
    path.write_text(TEMPLATE.read_text().replace('base_url = "http://127.0.0.1:8000"',
                                               'base_url = "https://user:secret-canary@example.com"'), encoding="utf-8")
    assert main(["--config", str(path)]) == 1
    assert "secret-canary" not in capsys.readouterr().out


def test_sqlite_probe_is_read_only_and_does_not_initialize(tmp_path, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    config = load_config(TEMPLATE, {})
    path = tmp_path / "existing.sqlite3"
    config.database.sqlite_path = str(path)
    assert probe("database", config)["reason"] == "sqlite_file_missing"
    assert not path.exists()
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE marker(value TEXT)")
    before = path.read_bytes()
    assert probe("database", config)["status"] == "reachable"
    assert path.read_bytes() == before
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall() == [("marker",)]


def test_explicit_sqlite_url_probe_never_creates_a_file(tmp_path, monkeypatch):
    path = tmp_path / "not-created.sqlite3"
    monkeypatch.setenv("DATABASE_URL", "sqlite:///" + path.as_posix())
    config = load_config(TEMPLATE, {})
    assert probe("database", config)["reason"] == "sqlite_file_missing"
    assert not path.exists()
