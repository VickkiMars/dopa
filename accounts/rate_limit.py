from django.core.cache import cache
from typing import Optional

RATE_LIMIT_PREFIX = 'login_failed_ip_'


def is_ip_rate_limited(ip_address: Optional[str], max_attempts: int = 5, window_seconds: int = 900) -> bool:
    """Check if the given IP address has exceeded the failed login attempt limit."""
    if not ip_address:
        return False
    key = f"{RATE_LIMIT_PREFIX}{ip_address}"
    attempts = cache.get(key, 0)
    return attempts >= max_attempts


def record_failed_attempt(ip_address: Optional[str], window_seconds: int = 900) -> int:
    """Increment the failed login counter for an IP address."""
    if not ip_address:
        return 0
    key = f"{RATE_LIMIT_PREFIX}{ip_address}"
    attempts = cache.get(key, 0) + 1
    cache.set(key, attempts, timeout=window_seconds)
    return attempts


def clear_failed_attempts(ip_address: Optional[str]) -> None:
    """Clear failed attempts upon successful login."""
    if not ip_address:
        return
    key = f"{RATE_LIMIT_PREFIX}{ip_address}"
    cache.delete(key)
