"""Shared work-item list and response contracts."""

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from execution_plane_client.models.shared import ResourcesResponse, create_list_params


class WorkItemStatus(StrEnum):
    """Lifecycle states of a dispatched work item."""

    PENDING = "pending"
    CLAIMED = "claimed"
    DISPATCHED = "dispatched"
    RUNNING = "running"
    CANCEL_REQUESTED = "cancel_requested"
    RECONCILIATION_REQUIRED = "reconciliation_required"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class WorkItemRead(BaseModel):
    """Safe work-item representation; excludes credentials and persistence internals."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(description="Work item unique identifier")
    status: WorkItemStatus = Field(description="Work item lifecycle status")
    result: dict[str, Any] | None = Field(default=None, description="Work execution result payload")
    result_omitted: bool = Field(default=False, description="Whether result was omitted due to size")
    result_size_bytes: int | None = Field(default=None, description="Size of the result in bytes")
    created_at: datetime = Field(description="Creation timestamp")
    claimed_at: datetime | None = Field(default=None, description="Claim timestamp")
    completed_at: datetime | None = Field(default=None, description="Completion timestamp")
    resource_cleanup_status: str = Field(description="Resource cleanup status")
    resource_cleanup_error: str | None = Field(default=None, description="Resource cleanup error details")


# Programmatically create WorkItemListParams from WorkItemRead field definitions
WorkItemListParams = create_list_params(
    "WorkItemListParams",
    WorkItemRead,
    filterable_fields=[
        "id",
        "status",
        "created_at",
        "claimed_at",
        "completed_at",
        "resource_cleanup_status",
        "resource_cleanup_error",
    ],
    sort_default="-created_at",  # Work items default to newest first
)


class WorkItemListResponse(ResourcesResponse[WorkItemRead]):
    """Paginated list response for work items."""
