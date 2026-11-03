"""Shared list controls and pagination envelopes."""

from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field, create_model

T = TypeVar("T")


class EPListParams(BaseModel):
    """Query parameters accepted by all EP list endpoints."""

    limit: int = Field(default=20, gt=0, le=100)
    cursor: str | None = Field(default=None)
    sort: str = Field(default="-created_at", description="Sort field; prefix with '-' for descending order.")
    include_total: bool = Field(default=False)

    @property
    def sort_order(self) -> tuple[str, str]:
        """Return the selected field and SQL ordering direction."""
        return self.sort.removeprefix("-"), "desc" if self.sort.startswith("-") else "asc"


class ResourcesResponse(BaseModel, Generic[T]):  # noqa: UP046
    """Pagination envelope returned by all EP list endpoints."""

    resources: list[T]
    next: str | None = None
    prev: str | None = None
    total: int | None = None


def create_list_params(
    name: str,
    read_model: type[BaseModel],
    filterable_fields: list[str],
    sort_default: str = "created_at",
) -> type[EPListParams]:
    """Create a list params class from a Read model's field definitions.

    Args:
        name: Name for the generated class
        read_model: The Read model (e.g., ClusterRead) to extract field descriptions from
        filterable_fields: List of field names that should be filterable
        sort_default: Default sort field

    Returns:
        A dynamically created list params class with filter fields derived from the Read model
    """
    filter_fields: dict[str, Any] = {}

    # Create filter fields from Read model fields
    for field_name in filterable_fields:
        if field_name in read_model.model_fields:
            original_field = read_model.model_fields[field_name]
            # All filter fields are optional strings (query params)
            filter_fields[field_name] = (
                str | None,
                Field(default=None, description=original_field.description or f"Filter by {field_name}")
            )

    # Override sort default if different from base
    if sort_default != EPListParams.model_fields['sort'].default:
        filter_fields['sort'] = (
            str,
            Field(default=sort_default, description="Sort field; prefix with '-' for descending order.")
        )

    return create_model(
        name,
        __base__=EPListParams,
        __module__=read_model.__module__,
        **filter_fields
    )
