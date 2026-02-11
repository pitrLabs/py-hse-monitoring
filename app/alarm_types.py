"""
Alarm Types - Dynamic Configuration

Alarm types are NOT hardcoded. They are fetched dynamically from:
1. Unique alarm_type values in the alarms table (actual data from BM-APP)
2. Description from raw_data.Result.Description (from BM-APP)

Color and severity are derived from keywords in the alarm type name.
"""

# Colors for different severity levels
COLOR_CRITICAL = "#dc2626"  # Red
COLOR_HIGH = "#ea580c"      # Orange
COLOR_MEDIUM = "#ca8a04"    # Yellow
COLOR_LOW = "#2563eb"       # Blue
COLOR_DEFAULT = "#22c55e"   # Green (for unknown types)


def get_alarm_color(alarm_type: str) -> str:
    """
    Get display color for an alarm type.
    Color is derived from keywords in the type name.

    Args:
        alarm_type: The alarm type from BM-APP

    Returns:
        Hex color string
    """
    if not alarm_type:
        return COLOR_DEFAULT

    t = alarm_type.lower()

    # Critical - Red (immediate danger)
    if any(k in t for k in ['fire', 'smoke', 'fall', 'falling']):
        return COLOR_CRITICAL

    # High - Orange (safety violations)
    if any(k in t for k in ['helmet', 'vest', 'intrusion', 'smoking', 'climb', 'goggle', 'glove']):
        return COLOR_HIGH

    # Medium - Yellow (minor violations)
    if any(k in t for k in ['mask', 'crowd']):
        return COLOR_MEDIUM

    # Low - Blue (informational)
    if any(k in t for k in ['loiter', 'person', 'vehicle']):
        return COLOR_LOW

    return COLOR_DEFAULT  # Green for unknown types


def get_alarm_severity(alarm_type: str) -> str:
    """
    Get severity level for an alarm type.
    Severity is derived from keywords in the type name.

    Args:
        alarm_type: The alarm type from BM-APP

    Returns:
        Severity string: "critical", "high", "medium", or "low"
    """
    if not alarm_type:
        return "high"

    t = alarm_type.lower()

    # Critical - immediate danger
    if any(k in t for k in ['fire', 'smoke', 'fall', 'falling']):
        return "critical"

    # High - safety violations
    if any(k in t for k in ['helmet', 'vest', 'intrusion', 'smoking', 'climb', 'goggle', 'glove']):
        return "high"

    # Medium - minor violations
    if any(k in t for k in ['mask', 'crowd']):
        return "medium"

    # Low - informational
    if any(k in t for k in ['loiter', 'person', 'vehicle']):
        return "low"

    return "info"  # Green for unknown types
