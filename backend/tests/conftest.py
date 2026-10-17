"""Never let a developer's production configuration leak into unit tests."""
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def isolated_service_configuration(monkeypatch):
    template = Path(__file__).resolve().parents[1] / "config/services.example.toml"
    monkeypatch.setenv("EOV_CONFIG_FILE", str(template))
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("REDIS_URL", raising=False)
