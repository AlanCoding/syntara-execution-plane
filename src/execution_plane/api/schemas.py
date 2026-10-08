"""Stable public request and response schemas for the EP API.

Generated models live in generated.py — run `make schemas` to update them.
This module re-exports everything from there and adds the three validators
that cannot be expressed in OpenAPI.
"""

import json
import ssl
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from execution_plane.api.generated import (
    BackendType,
    ClusterBindingRead,
    ExecutionTargetRead,
    KubernetesPlacement,
    RHELPlacement,
    TargetStatus,
    WorkItemCancelRequest,
    WorkItemRead,
    WorkItemStatus,
)
from execution_plane.api.generated import (
    ClusterBindingUpsert as _ClusterBindingUpsert,
)
from execution_plane.api.generated import (
    WorkItemSubmit as _WorkItemSubmit,
)

__all__ = [
    "BackendType",
    "CapabilitiesResponse",
    "ClusterBindingRead",
    "ClusterBindingUpsert",
    "CompletionEventRequest",
    "ExecutionTargetRead",
    "KubernetesPlacement",
    "RHELPlacement",
    "TargetStatus",
    "WorkItemCancelRequest",
    "WorkItemRead",
    "WorkItemStatus",
    "WorkItemSubmit",
]


class CapabilitiesResponse(BaseModel):
    """Contract and workload features implemented by this service release."""

    api_version: str = "v1"
    workloads: list[str] = Field(default_factory=lambda: ["script"])
    result_events: bool = True


class WorkItemSubmit(_WorkItemSubmit):
    """Script work accepted from a trusted client."""

    @field_validator("payload")
    @classmethod
    def limit_payload_size(cls, payload: dict[str, Any]) -> dict[str, Any]:
        """Keep the encoded node request below the HTTP and gRPC framing budgets."""
        if len(json.dumps(payload, separators=(",", ":"), default=str).encode("utf-8")) > 512 * 1024:
            msg = "workload payload exceeds the 512 KiB limit"
            raise ValueError(msg)
        return payload

    @field_validator("payload")
    @classmethod
    def validate_node_invocation(cls, payload: dict[str, Any]) -> dict[str, Any]:
        """Accept only the versioned script invocation contract used by node gRPC."""
        invocation = payload.get("invocation")
        image = payload.get("image")
        output_config = payload.get("output_config")
        if not isinstance(invocation, dict) or not isinstance(image, str) or not image:
            msg = "payload must include a versioned invocation and node image"
            raise ValueError(msg)
        if invocation.get("version") != 1 or invocation.get("operation") != "execute":
            msg = "unsupported node invocation version or operation"
            raise ValueError(msg)
        for key in ("inputs", "credentials", "workflow_context", "settings"):
            if not isinstance(invocation.get(key), dict):
                msg = f"invocation.{key} must be an object"
                raise ValueError(msg)  # noqa: TRY004 — Pydantic maps ValueError to HTTP 422
        timeout = invocation.get("timeout_seconds")
        output_limit = invocation.get("max_output_bytes")
        if isinstance(timeout, bool) or not isinstance(timeout, int) or timeout < 1:
            msg = "invocation.timeout_seconds must be a positive integer"
            raise ValueError(msg)
        if isinstance(output_limit, bool) or not isinstance(output_limit, int) or output_limit < 1:
            msg = "invocation.max_output_bytes must be a positive integer"
            raise ValueError(msg)
        if output_config is not None and not isinstance(output_config, dict):
            msg = "payload.output_config must be an object or null"
            raise ValueError(msg)
        return payload


class ClusterBindingUpsert(_ClusterBindingUpsert):
    """Versioned OpenShift integration desired state supplied by an authorized client."""

    @field_validator("ca_certificate", mode="before")
    @classmethod
    def validate_ca_certificate(cls, certificate: str | None) -> str | None:
        """Accept only parseable PEM used to verify the configured cluster endpoint."""
        if certificate is None:
            return None
        context = ssl.create_default_context()
        context.load_verify_locations(cadata=certificate)
        return certificate


class CompletionEventRequest(BaseModel):
    """Wire form delivered to the client's configured completion callback."""

    event_id: UUID
    event_schema_version: Literal[1] = 1
    client_id: str
    project_id: UUID
    work_id: UUID
    request_id: str
    state_revision: int
    status: WorkItemStatus
    result: dict[str, Any]
    completed_at: datetime
