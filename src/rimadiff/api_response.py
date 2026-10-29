from dataclasses import dataclass
from numbers import Number


@dataclass
class APIResponse:
    data: dict[int, dict[int, Number]]
    """data [category] [label_id] = value"""

    labels: dict[int, dict[int, str]]
    """labels [category] [label_id] = label"""

    url: str | None
    """Value None for database-based pseudo-responses."""

    user_id: int | None = None
