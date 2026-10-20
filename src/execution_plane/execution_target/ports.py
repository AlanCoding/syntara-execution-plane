"""Actor-specific persistence ports for ExecutionTarget use cases."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    import uuid
    from collections.abc import Sequence

    from execution_plane.models.execution_target import BackendType, ExecutionTarget, TargetStatus
    from execution_plane.models.execution_target_placement import ExecutionTargetPlacement


class ExecutionTargetTransitionStore(Protocol):
    """Target transitions shared by command and registration use cases."""

    async def create(
        self,
        cluster_id: uuid.UUID,
        name: str,
        backend_type: BackendType,
        endpoint: str,
        api_key: str,
        is_default: bool,  # noqa: FBT001
        created_by: uuid.UUID,
        placement: ExecutionTargetPlacement,
        labels: dict[str, str] | None = None,
        *,
        target_id: uuid.UUID | None = None,
    ) -> ExecutionTarget:
        """Create an ExecutionTarget."""
        ...

    async def activate(self, target_id: uuid.UUID, updated_by: uuid.UUID) -> ExecutionTarget:
        """Activate a registered target."""
        ...

    async def update(
        self,
        target_id: uuid.UUID,
        *,
        updated_by: uuid.UUID,
        name: str | None = None,
        endpoint: str | None = None,
        placement: ExecutionTargetPlacement | None = None,
        labels: dict[str, str] | None = None,
        status_message: str | None = None,
        api_key: str | None = None,
    ) -> ExecutionTarget:
        """Update mutable target fields."""
        ...


class ExecutionTargetCommandStore(ExecutionTargetTransitionStore, Protocol):
    """Authenticated target commands from the command ingress."""

    async def request_delete(self, target_id: uuid.UUID, updated_by: uuid.UUID) -> ExecutionTarget:
        """Atomically reject defaults and mark non-defaults draining."""
        ...


class ExecutionTargetClientQueryStore(Protocol):
    """Client-scoped target reads used by REST resource queries."""

    async def list_for_client(
        self,
        client_id: str,
        *,
        limit: int,
        target_id: uuid.UUID | None = None,
    ) -> Sequence[ExecutionTarget]:
        """List targets owned by one client."""
        ...


class ExecutionTargetSnapshotStore(Protocol):
    """Target reads used to build placement snapshots."""

    async def list(
        self,
        cluster_id: uuid.UUID | None = None,
        eligible_only: bool = False,  # noqa: FBT001, FBT002
        status: TargetStatus | None = None,
        limit: int | None = None,
    ) -> Sequence[ExecutionTarget]:
        """List targets."""
        ...


class ExecutionTargetLookupStore(Protocol):
    """Redacted target lookup used after work assignment."""

    async def get(self, target_id: uuid.UUID) -> ExecutionTarget | None:
        """Return one redacted target."""
        ...


class ExecutionTargetCredentialStore(Protocol):
    """Credential-bearing target reads for execution paths."""

    async def get_with_credentials(self, target_id: uuid.UUID) -> ExecutionTarget | None:
        """Return one target with its credential intact."""
        ...


class ExecutionTargetCleanupStore(Protocol):
    """Target reads used by orphan-policy reconciliation."""

    async def list(
        self,
        cluster_id: uuid.UUID | None = None,
        eligible_only: bool = False,  # noqa: FBT001, FBT002
        status: TargetStatus | None = None,
        limit: int | None = None,
    ) -> Sequence[ExecutionTarget]:
        """List targets."""
        ...

    async def get_with_credentials(self, target_id: uuid.UUID) -> ExecutionTarget | None:
        """Return one target with its credential intact."""
        ...


class ExecutionTargetRegistrationStore(ExecutionTargetTransitionStore, Protocol):
    """Target transitions needed to coordinate Cluster registration."""

    async def list(
        self,
        cluster_id: uuid.UUID | None = None,
        eligible_only: bool = False,  # noqa: FBT001, FBT002
        status: TargetStatus | None = None,
        limit: int | None = None,
    ) -> Sequence[ExecutionTarget]:
        """List targets for a Cluster."""
        ...

    async def reactivate(
        self,
        target_id: uuid.UUID,
        *,
        updated_by: uuid.UUID,
        endpoint: str | None = None,
        api_key: str | None = None,
        placement: ExecutionTargetPlacement,
    ) -> ExecutionTarget:
        """Reactivate a draining target."""
        ...


class ExecutionTargetDrainStore(Protocol):
    """Drain recovery and finalization transitions."""

    async def list(
        self,
        cluster_id: uuid.UUID | None = None,
        eligible_only: bool = False,  # noqa: FBT001, FBT002
        status: TargetStatus | None = None,
        limit: int | None = None,
    ) -> Sequence[ExecutionTarget]:
        """List targets for drain recovery."""
        ...

    async def get(self, target_id: uuid.UUID) -> ExecutionTarget | None:
        """Return one redacted target."""
        ...

    async def mark_failed(self, target_id: uuid.UUID, updated_by: uuid.UUID) -> ExecutionTarget:
        """Record an irrecoverable target drain failure."""
        ...

    async def finalize_delete(self, target_id: uuid.UUID) -> None:
        """Delete a drained target when safe."""
        ...
