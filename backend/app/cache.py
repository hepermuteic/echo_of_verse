import json
import logging
from functools import lru_cache

from redis import Redis
from redis.exceptions import RedisError
from app.configuration import configured_redis_url, load_config

log = logging.getLogger(__name__)


def _client():
    config = load_config()
    return _connection(configured_redis_url(config), config.redis.timeout_seconds)


@lru_cache(maxsize=4)
def _connection(url, timeout):
    return Redis.from_url(url, decode_responses=True, socket_connect_timeout=timeout,
                          socket_timeout=timeout) if url else None


def get(key):
    try:
        client = _client()
        if client is None:
            return None
        value = client.get("eov:" + key)
        return json.loads(value) if value else None
    except (RedisError, ValueError, OSError):
        log.warning("Redis cache read unavailable; cache skipped")
        return None


def put(key, value, seconds=300):
    try:
        client = _client()
        if client is None:
            return
        client.setex("eov:" + key, seconds, json.dumps(value, ensure_ascii=False))
    except (RedisError, ValueError, OSError):
        log.warning("Redis cache write unavailable; cache skipped")


def clear_catalog():
    try:
        client = _client()
        if client is None:
            return
        keys = list(client.scan_iter("eov:catalog:*", count=100))
        if keys:
            client.delete(*keys)
    except (RedisError, ValueError, OSError):
        log.warning("Redis catalog cache invalidation unavailable; cache skipped")
