from pathlib import Path
from app.configuration import ROOT, load_config

def db_path(config=None) -> Path:
    path = Path((config or load_config()).database.sqlite_path)
    return path if path.is_absolute() else ROOT / path


def cors_origins() -> list[str]:
    return load_config().app.cors_origins


DEPLOYMENT_NAME = load_config().app.deployment_name


DB_TIMEOUT_SECONDS = 1
DB_POOL_TIMEOUT_SECONDS = 2
DB_CONNECT_TIMEOUT_SECONDS = 3
