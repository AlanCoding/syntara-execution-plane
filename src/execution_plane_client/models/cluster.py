"""Shared cluster list and response contracts."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from execution_plane_client.models._generated_list_params import ClusterListParamsBase


class ClusterListParams(ClusterListParamsBase):
    """Cluster query controls and documented filter fields."""


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
