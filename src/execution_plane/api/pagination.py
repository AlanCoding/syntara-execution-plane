"""Cursor-based pagination utilities for EP list endpoints."""

from __future__ import annotations

import base64
import json
from typing import Annotated, Generic, TypeVar

from pydantic import BaseModel, Field, StringConstraints

T = TypeVar("T")

VALID_CURSOR_FIELDS = {"id", "created_at", "direction", "sort_field", "sort_direction", "sort_value"}
MAX_CURSOR_BYTES = 1024


class EPListParams(BaseModel):
    limit: int = Field(default=20, gt=0, le=100)
    cursor: str | None = Field(default=None)
    sort: Annotated[str, StringConstraints(pattern=r"^-?[a-z][a-z0-9_]*$")] | None = Field(default=None)
    include_total: bool = Field(default=False)


class ResourcesResponse(BaseModel, Generic[T]):  # noqa: UP046
    resources: list[T]
    next: str | None = None
    prev: str | None = None
    total: int | None = None


def encode_cursor(data: dict) -> str:
    return base64.b64encode(json.dumps(data, sort_keys=True).encode()).decode()


def decode_cursor(token: str) -> dict:
    if len(token.encode()) > MAX_CURSOR_BYTES:
        raise ValueError("cursor too large")
    try:
        raw = base64.b64decode(token.encode()).decode()
        data = json.loads(raw)
    except Exception as exc:
        raise ValueError("invalid cursor") from exc
    if not isinstance(data, dict):
        raise ValueError("cursor must be a JSON object")
    return {k: v for k, v in data.items() if k in VALID_CURSOR_FIELDS}


def generate_response(
    items: list,
    limit: int,
    cursor: str | None,
    *,
    sort_field: str = "created_at",
    sort_direction: str = "asc",
    include_total: int | None = None,
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
