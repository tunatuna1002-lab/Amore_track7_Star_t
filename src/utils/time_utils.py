"""
Time utilities for KST timezone handling.
"""

from datetime import datetime, date
from zoneinfo import ZoneInfo

# Korea Standard Time
KST = ZoneInfo("Asia/Seoul")


def get_kst_now() -> datetime:
    """
    Get current datetime in KST.

    Returns:
        Current datetime in KST timezone
    """
    return datetime.now(KST)


def get_kst_date() -> date:
    """
    Get current date in KST.

    Returns:
        Current date in KST timezone
    """
    return get_kst_now().date()


def format_kst_date(dt: datetime = None) -> str:
    """
    Format a datetime as YYYY-MM-DD in KST.

    Args:
        dt: Datetime to format. If None, uses current time.

    Returns:
        Date string in YYYY-MM-DD format
    """
    if dt is None:
        dt = get_kst_now()
    return dt.strftime("%Y-%m-%d")


def format_kst_datetime(dt: datetime = None) -> str:
    """
    Format a datetime as ISO format in KST.

    Args:
        dt: Datetime to format. If None, uses current time.

    Returns:
        Datetime string in ISO format
    """
    if dt is None:
        dt = get_kst_now()
    return dt.isoformat()
