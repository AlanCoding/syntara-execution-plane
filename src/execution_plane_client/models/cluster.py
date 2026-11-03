"""Shared cluster list and response contracts."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from execution_plane_client.models.shared import EPListParams


class ClusterListParams(EPListParams):
    """Cluster query controls and documented filter fields."""

    sort: str = Field(default="created_at", description="Sort field; prefix with '-' for descending order.")
    id: str | None = Field(default=None, description="Filter by cluster ID")
    created_at: str | None = Field(default=None, description="Filter by creation time")
    updated_at: str | None = Field(default=None, description="Filter by update time")
    name: str | None = Field(default=None, description="Filter by cluster name")
    endpoint: str | None = Field(default=None, description="Filter by cluster endpoint")
    status: str | None = Field(default=None, description="Filter by cluster status")
    status_message: str | None = Field(default=None, description="Filter by status message")
    enabled: str | None = Field(default=None, description="Filter by enabled state")
    is_default: str | None = Field(default=None, description="Filter by default cluster flag")


class ClusterRead(BaseModel):
    """Provisioned cluster state, keyed by the actual cluster UUID."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    endpoint: str
    status: str
    status_message: str | None
    enabled: bool
    is_default: bool
    labels: dict[str, str]
    created_at: datetime
    updated_at: datetime
