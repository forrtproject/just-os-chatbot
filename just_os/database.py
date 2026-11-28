import logging
from typing import Optional
from redis import Redis
from redis.backoff import NoBackoff
from redis.retry import Retry

from config.settings import DEFAULT_CONFIG

logger = logging.getLogger(__name__)

_redis_client: Optional[Redis] = None


def redis_timeouts() -> dict:
    """REDIS_TIMEOUT for connecting and for each reply, and no retries: a Redis that stops answering fails once,
    after REDIS_TIMEOUT. redis-py otherwise retries a timed-out or refused command with backoff (11 tries measured),
    so one request or probe could wait many times REDIS_TIMEOUT. Shared by the chat memory client and the limiter."""
    seconds = DEFAULT_CONFIG.get("REDIS_TIMEOUT", 2)
    return {"socket_connect_timeout": seconds, "socket_timeout": seconds,
            "retry": Retry(NoBackoff(), 0)}  # retry_on_timeout is deprecated in redis-py 6+: the Retry decides


def redis_options() -> dict:
    return {"host": DEFAULT_CONFIG["REDIS_HOST"], "port": DEFAULT_CONFIG["REDIS_PORT"],
            "db": DEFAULT_CONFIG["REDIS_DB"], **redis_timeouts()}


def get_redis_client() -> Redis:
    """
    Get or create a Redis client instance.
    Uses a singleton pattern to avoid creating multiple connections.

    Returns:
        Redis: The Redis client instance
    """
    global _redis_client

    if _redis_client is None:
        try:
            _redis_client = Redis(**redis_options())
            logger.debug("Redis client initialized")
        except Exception as e:
            logger.error(f"Failed to initialize Redis client: {str(e)}")
            raise

    return _redis_client
