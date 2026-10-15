"""Cursor-based pagination utilities for EP list endpoints."""

from __future__ import annotations

import base64
import json
from typing import Annotated, Generic, TypeVar

from pydantic import BaseModel, Field, StringConstraints

T = TypeVar("T")

VALID_CURSOR_FIELDS = {"id", "created_at", "direction", "sort_field", "sort_direction", "sort_value"}
MAX_CURSOR_BYTES = 1024
_CURSOR_NOT_OBJECT = "cursor must be a JSON object"


class EPListParams(BaseModel):
    """Query parameters accepted by all EP list endpoints."""

    limit: int = Field(default=20, gt=0, le=100)
    cursor: str | None = Field(default=None)
    sort: Annotated[str, StringConstraints(pattern=r"^-?[a-z][a-z0-9_]*$")] | None = Field(default=None)
    include_total: bool = Field(default=False)


class ResourcesResponse(BaseModel, Generic[T]):  # noqa: UP046
    """Pagination envelope returned by all EP list endpoints."""

    resources: list[T]
    next: str | None = None
    prev: str | None = None
    total: int | None = None


def encode_cursor(data: dict) -> str:
    """Encode a cursor dict to an opaque base64-JSON token."""
    return base64.b64encode(json.dumps(data, sort_keys=True).encode()).decode()


def decode_cursor(token: str) -> dict:
    """Decode and whitelist-filter a cursor token; raise ValueError on invalid input."""
    if len(token.encode()) > MAX_CURSOR_BYTES:
        msg = "cursor too large"
        raise ValueError(msg)
    try:
        raw = base64.b64decode(token.encode()).decode()
        data = json.loads(raw)
    except Exception as exc:
        msg = "invalid cursor"
        raise ValueError(msg) from exc
    if not isinstance(data, dict):
        raise TypeError(_CURSOR_NOT_OBJECT)
    return {k: v for k, v in data.items() if k in VALID_CURSOR_FIELDS}


def generate_response(
    items: list,
    limit: int,
    cursor: str | None,
    *,
    sort_field: str = "created_at",
    sort_direction: str = "asc",
) -> tuple[list, str | None, str | None]:
    """Return (trimmed_items, next_cursor, prev_cursor)."""
    has_more = len(items) > limit
    trimmed = items[:limit]

    next_cursor = None
    if has_more and trimmed:
        last = trimmed[-1]
        next_cursor = encode_cursor({
            "id": str(last.id),
            "created_at": last.created_at.isoformat(),
            "direction": "next",
            "sort_field": sort_field,
            "sort_direction": sort_direction,
            "sort_value": getattr(last, sort_field).isoformat(),
        })

    prev_cursor = None
    if cursor and trimmed:
        first = trimmed[0]
        prev_cursor = encode_cursor({
            "id": str(first.id),
            "created_at": first.created_at.isoformat(),
            "direction": "prev",
            "sort_field": sort_field,
            "sort_direction": sort_direction,
            "sort_value": getattr(first, sort_field).isoformat(),
        })

    return trimmed, next_cursor, prev_cursor
