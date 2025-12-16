"""
Run ID generation utilities.
"""

import uuid
from datetime import datetime

from .time_utils import get_kst_now


def generate_run_id() -> str:
    """
    Generate a unique run ID.

    Format: YYYYMMDD_HHMMSS_<short_uuid>

    Returns:
        Unique run ID string
    """
    now = get_kst_now()
    timestamp = now.strftime("%Y%m%d_%H%M%S")
    short_uuid = uuid.uuid4().hex[:8]
    return f"{timestamp}_{short_uuid}"


def parse_run_id_date(run_id: str) -> datetime:
    """
    Extract the date from a run ID.

    Args:
        run_id: Run ID string

    Returns:
        Datetime object
    """
    parts = run_id.split('_')
    if len(parts) >= 2:
        date_str = parts[0]
        time_str = parts[1]
        return datetime.strptime(f"{date_str}_{time_str}", "%Y%m%d_%H%M%S")
    raise ValueError(f"Invalid run ID format: {run_id}")
