"""
Timezone utilities for HSE Monitoring
- BM-APP sends timestamps in China timezone (UTC+8)
- Database stores in UTC
- Frontend displays in WIB (UTC+7)
"""
from datetime import datetime, timezone, timedelta
from typing import Optional

# Timezone definitions
UTC = timezone.utc
WIB = timezone(timedelta(hours=7))   # Western Indonesia Time (UTC+7)
CHINA_TZ = timezone(timedelta(hours=8))  # China Standard Time (UTC+8)


def now_utc() -> datetime:
    """Get current time in UTC (timezone-aware)"""
    return datetime.now(UTC)


def now_wib() -> datetime:
    """Get current time in WIB (timezone-aware)"""
    return datetime.now(WIB)


def utc_to_wib(dt: datetime) -> datetime:
    """Convert UTC datetime to WIB"""
    if dt is None:
        return None
    if dt.tzinfo is None:
        # Assume naive datetime is UTC
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(WIB)


def wib_to_utc(dt: datetime) -> datetime:
    """Convert WIB datetime to UTC"""
    if dt is None:
        return None
    if dt.tzinfo is None:
        # Assume naive datetime is WIB
        dt = dt.replace(tzinfo=WIB)
    return dt.astimezone(UTC)


def parse_bmapp_time(time_str: str) -> datetime:
    """
    Parse BM-APP time string to UTC datetime.
    BM-APP software uses China timezone (UTC+8) internally, but since the
    AI Box is physically in Indonesia, we treat timestamps as WIB (UTC+7)
    so the displayed time matches what's burned on alarm photos.

    Args:
        time_str: Time string from BM-APP (e.g., "2024-01-28 14:30:00")

    Returns:
        UTC datetime (timezone-aware)
    """
    if not time_str:
        return now_utc()

    formats = [
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%d %H:%M:%S.%f",
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%d",
    ]

    for fmt in formats:
        try:
            # Parse as naive datetime
            dt = datetime.strptime(time_str, fmt)
            # Treat as WIB (device is in Indonesia) so display matches photo timestamps
            dt = dt.replace(tzinfo=WIB)
            return dt.astimezone(UTC)
        except ValueError:
            continue

    # Try parsing as unix timestamp
    try:
        ts = float(time_str)
        return datetime.fromtimestamp(ts, tz=UTC)
    except (ValueError, OSError):
        pass

    return now_utc()


def parse_bmapp_timestamp_us(timestamp_us: int) -> datetime:
    """
    Parse BM-APP microsecond timestamp to UTC datetime.

    Args:
        timestamp_us: Unix timestamp in microseconds

    Returns:
        UTC datetime (timezone-aware)
    """
    if not timestamp_us:
        return now_utc()

    try:
        # Convert microseconds to seconds
        return datetime.fromtimestamp(timestamp_us / 1_000_000, tz=UTC)
    except (ValueError, OSError):
        return now_utc()


def format_for_display(dt: datetime, include_seconds: bool = True) -> str:
    """
    Format datetime for display in WIB timezone.

    Args:
        dt: UTC datetime
        include_seconds: Whether to include seconds in output

    Returns:
        Formatted string like "28 Jan 2024, 21:30:00 WIB"
    """
    if dt is None:
        return "-"

    wib_dt = utc_to_wib(dt)

    if include_seconds:
        return wib_dt.strftime("%d %b %Y, %H:%M:%S WIB")
    return wib_dt.strftime("%d %b %Y, %H:%M WIB")


def format_iso_wib(dt: datetime) -> str:
    """
    Format datetime as ISO string with WIB timezone.

    Args:
        dt: UTC datetime

    Returns:
        ISO format string like "2024-01-28T21:30:00+07:00"
    """
    if dt is None:
        return None

    wib_dt = utc_to_wib(dt)
    return wib_dt.isoformat()
