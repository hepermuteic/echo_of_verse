"""Offline configuration/manifest validation, with explicit read-only probes."""
import argparse
import json
import sqlite3
from pathlib import Path
from urllib.request import urlopen

from pydantic import ValidationError
from redis import Redis
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url

from app.configuration import (ROOT, configuration_checks, configured_database_url,
                               configured_redis_url, load_config)
from app.resources import ResourceManifest


def probe(service, config):
    """Probes never initialize tables, seed records or invoke model generation."""
    try:
        if service == "api":
            with urlopen(config.api.base_url + "/health", timeout=config.api.timeout_seconds) as response:
                result = json.loads(response.read(16384))
                if response.status != 200 or result.get("status") != "ok":
                    raise ValueError("Unhealthy response")
        elif service == "database":
            url = configured_database_url(config)
            parsed = make_url(url) if url else None
            if parsed is not None and parsed.drivername == "postgresql+psycopg":
                engine = create_engine(url, connect_args={"connect_timeout": 5})
                try:
                    with engine.connect() as connection:
                        connection.exec_driver_sql("SELECT 1")
                finally:
                    engine.dispose()
            else:
                if parsed is not None and parsed.drivername != "sqlite":
                    return {"service": service, "status": "failed", "reason": "unsupported_database_driver"}
                if parsed is not None and (not parsed.database or parsed.database == ":memory:" or parsed.database.startswith("file:")):
                    return {"service": service, "status": "skipped", "reason": "sqlite_probe_requires_file_path"}
                path = Path(parsed.database if parsed is not None else config.database.sqlite_path)
                # SQLAlchemy explicit SQLite URLs retain their native cwd semantics.
                # EOV_DB_PATH/TOML sqlite_path are always relative to the backend root.
                if parsed is None and not path.is_absolute():
                    path = ROOT / path
                if not path.is_file():
                    return {"service": service, "status": "failed", "reason": "sqlite_file_missing"}
                connection = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=5)
                try:
                    connection.execute("SELECT 1").fetchone()
                finally:
                    connection.close()
        elif service == "redis":
            url = configured_redis_url(config)
            if not url:
                return {"service": service, "status": "skipped", "reason": "not_configured"}
            connection = Redis.from_url(url, socket_connect_timeout=config.redis.timeout_seconds,
                                        socket_timeout=config.redis.timeout_seconds)
            try:
                connection.ping()
            finally:
                connection.close()
        return {"service": service, "status": "reachable"}
    except Exception:
        # Provider/driver exception strings may contain credentials or signed URLs.
        return {"service": service, "status": "failed", "reason": "probe_failed"}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Check settings without model calls or writes")
    parser.add_argument("--config", help="TOML path; relative to backend root")
    parser.add_argument("--manifest", help="Resource manifest JSON path; relative to backend root")
    parser.add_argument("--require-ready", action="store_true", help="Fail if manifest contains non-ready assets")
    parser.add_argument("--probe", action="append", choices=["api", "database", "redis"], default=[])
    args = parser.parse_args(argv)
    if args.require_ready and not args.manifest:
        parser.error("--require-ready requires --manifest")
    try:
        config = load_config(args.config)
        checks = [{"service": "configuration", "status": "valid"}, *configuration_checks(config)]
        if args.manifest:
            path = Path(args.manifest)
            path = path if path.is_absolute() else ROOT / path
            manifest = ResourceManifest.model_validate_json(path.read_text(encoding="utf-8"))
            ready = sum(a.status == "ready" for a in manifest.assets)
            checks.append({"service": "resource_manifest", "status": "incomplete" if args.require_ready and ready != len(manifest.assets) else "valid",
                           "ready": ready, "total": len(manifest.assets)})
        checks.extend(probe(service, config) for service in dict.fromkeys(args.probe))
    except ValidationError as exc:
        # Only locations/types, never validation input or secret-bearing messages.
        checks = [{"service": "configuration_or_manifest", "status": "invalid",
                   "fields": [{"location": list(e["loc"]), "type": e["type"]} for e in exc.errors()]}]
    except (OSError, ValueError):
        checks = [{"service": "configuration_or_manifest", "status": "invalid", "reason": "file_or_syntax_error"}]
    failed = any(check["status"] in ("invalid", "incomplete", "failed") for check in checks)
    print(json.dumps({"ok": not failed, "checks": checks}, ensure_ascii=False, indent=2))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
