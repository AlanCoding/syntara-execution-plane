"""Shared work-item list and response contracts."""

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from execution_plane_client.models.shared import EPListParams, ResourcesResponse


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


class WorkItemListParams(EPListParams):
    """Work-item query controls and documented filter fields."""

    id: str | None = Field(default=None, description="Filter by work item ID")
    status: str | None = Field(default=None, description="Filter by work item status")
    created_at: str | None = Field(default=None, description="Filter by creation time")
    claimed_at: str | None = Field(default=None, description="Filter by claim time")
    completed_at: str | None = Field(default=None, description="Filter by completion time")
    resource_cleanup_status: str | None = Field(default=None, description="Filter by cleanup status")
    resource_cleanup_error: str | None = Field(default=None, description="Filter by cleanup error")


class WorkItemRead(BaseModel):
    """Safe work-item representation; excludes credentials and persistence internals."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    status: WorkItemStatus
    result: dict[str, Any] | None
    result_omitted: bool = False
    result_size_bytes: int | None = None
    created_at: datetime
    claimed_at: datetime | None
    completed_at: datetime | None
    resource_cleanup_status: str
    resource_cleanup_error: str | None


class WorkItemListResponse(ResourcesResponse[WorkItemRead]):
    """Paginated list response for work items."""
