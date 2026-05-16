"""Google Calendar 'Add to Calendar' URL — zero configuration required."""

from datetime import datetime, timedelta
from urllib.parse import urlencode


def add_to_calendar_url(
    title: str,
    start: datetime,
    duration_minutes: int,
    details: str = "",
) -> str:
    """Return a Google Calendar pre-filled event URL (no auth needed)."""
    end = start + timedelta(minutes=duration_minutes)
    fmt = "%Y%m%dT%H%M%S"
    params: dict = {
        "action": "TEMPLATE",
        "text": title,
        "dates": f"{start.strftime(fmt)}/{end.strftime(fmt)}",
    }
    if details:
        params["details"] = details
    return "https://calendar.google.com/calendar/render?" + urlencode(params)
