"""Shared cluster list and response contracts."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from execution_plane_client.models.shared import ResourcesResponse, create_list_params


class ClusterRead(BaseModel):
    """Provisioned cluster state, keyed by the actual cluster UUID."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(description="Cluster unique identifier")
    name: str = Field(description="Cluster name")
    endpoint: str = Field(description="Cluster API endpoint URL")
    status: str = Field(description="Cluster lifecycle status")
    status_message: str | None = Field(default=None, description="Human-readable status message or error details")
    enabled: bool = Field(description="Whether the cluster is enabled for use")
    is_default: bool = Field(description="Whether this is the default cluster")
    labels: dict[str, str] = Field(description="Key-value labels for the cluster")
    created_at: datetime = Field(description="Creation timestamp")
    updated_at: datetime = Field(description="Last update timestamp")


# Programmatically create ClusterListParams from ClusterRead field definitions
ClusterListParams = create_list_params(
    "ClusterListParams",
    ClusterRead,
    filterable_fields=[
        "id",
        "created_at",
        "updated_at",
        "name",
        "endpoint",
        "status",
        "status_message",
        "enabled",
        "is_default",
    ],
    sort_default="created_at",
)


class ClusterListResponse(ResourcesResponse[ClusterRead]):
    """Paginated list response for clusters."""
