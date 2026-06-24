import json
from typing import Any


def sse_event(event: str, data: dict[str, Any]) -> str:
    """Format a Server-Sent Event string."""
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"
