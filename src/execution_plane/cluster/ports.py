"""Actor-specific persistence ports for Cluster use cases."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from execution_plane.models.cluster import ClusterType

if TYPE_CHECKING:
    import uuid
    from collections.abc import Sequence

    from execution_plane.models.cluster import Cluster, ClusterStatus
    from execution_plane.models.cluster_binding import ClusterBinding


class ClusterRegistrationStore(Protocol):
    """Transitions needed to register and reconcile a Cluster."""

    async def create(
        self,
        name: str,
        endpoint: str,
        api_key: str,
        created_by: uuid.UUID,
        labels: dict[str, str] | None = None,
        *,
        cluster_type: ClusterType = ClusterType.OPENSHIFT,
        source_client_id: str | None = None,
        source_integration_id: uuid.UUID | None = None,
        source_revision: int = 0,
        project_ids: list[uuid.UUID] | None = None,
        ca_certificate: str | None = None,
    ) -> Cluster:
        """Create a Cluster record."""
        ...

    async def get_by_name(self, name: str) -> Cluster | None:
        """Return one redacted Cluster by name."""
        ...

    async def get_by_source(self, client_id: str, integration_id: uuid.UUID) -> Cluster | None:
        """Return one redacted Cluster by source identity."""
        ...

    async def update(
        self,
        cluster_id: uuid.UUID,
        *,
        updated_by: uuid.UUID,
        name: str | None = None,
        endpoint: str | None = None,
        api_key: str | None = None,
        ca_certificate: str | None = None,
        labels: dict[str, str] | None = None,
    ) -> Cluster:
        """Update mutable Cluster fields."""
        ...

    async def reactivate(
        self,
        cluster_id: uuid.UUID,
        *,
        updated_by: uuid.UUID,
        endpoint: str | None = None,
        api_key: str | None = None,
        ca_certificate: str | None = None,
        labels: dict[str, str] | None = None,
    ) -> Cluster:
        """Reactivate a draining Cluster."""
        ...

    async def record_discovery_state(
        self,
        cluster_id: uuid.UUID,
        status: ClusterStatus,
        status_message: str | None,
        updated_by: uuid.UUID,
    ) -> Cluster:
        """Persist discovery state on a Cluster."""
        ...


class ClusterQueryStore(Protocol):
    """Redacted Cluster reads and client-scoped binding queries."""

    async def get(self, cluster_id: uuid.UUID) -> Cluster | None:
        """Return one redacted Cluster."""
        ...

    async def get_by_name(self, name: str) -> Cluster | None:
        """Return one redacted Cluster by name."""
        ...

    async def get_by_source(self, client_id: str, integration_id: uuid.UUID) -> Cluster | None:
        """Return one redacted Cluster by source identity."""
        ...

    async def list(self, *, status: ClusterStatus | None = None, enabled: bool | None = None) -> list[Cluster]:
        """List redacted Clusters."""
        ...

    async def list_bindings_for_client(self, client_id: str, *, limit: int) -> Sequence[ClusterBinding]:
        """List bindings owned by one client."""
        ...

    async def get_binding_for_client(
        self,
        client_id: str,
        source_integration_id: uuid.UUID,
    ) -> ClusterBinding | None:
        """Return one client-owned binding."""
        ...


class ClusterCredentialStore(Protocol):
    """Credential-bearing Cluster reads for execution paths."""

    async def get_with_credentials(self, cluster_id: uuid.UUID) -> Cluster | None:
        """Return one Cluster with credentials for execution."""
        ...


class ClusterSourceBindingStore(Protocol):
    """Versioned source-binding updates."""

    async def update_source_binding(
        self,
        cluster_id: uuid.UUID,
        *,
        client_id: str,
        integration_id: uuid.UUID,
        revision: int,
        project_ids: list[uuid.UUID] | None,
        ca_certificate: str | None = None,
    ) -> Cluster:
        """Persist a Cluster source binding."""
        ...


class ClusterLifecycleStore(Protocol):
    """Drain and finalization transitions."""

    async def list(self, *, status: ClusterStatus | None = None, enabled: bool | None = None) -> list[Cluster]:
        """List Clusters for drain recovery."""
        ...

    async def request_delete(self, cluster_id: uuid.UUID, updated_by: uuid.UUID) -> Cluster:
        """Mark a Cluster and its targets draining."""
        ...

    async def mark_drain_failed(
        self,
        cluster_id: uuid.UUID,
        status_message: str,
        updated_by: uuid.UUID,
    ) -> Cluster:
        """Record an irrecoverable Cluster drain failure."""
        ...

    async def finalize_delete(self, cluster_id: uuid.UUID) -> None:
        """Delete a drained Cluster when safe."""
        ...


class ClusterBindingReconcilerStore(
    ClusterQueryStore,
    ClusterSourceBindingStore,
    ClusterLifecycleStore,
    Protocol,
):
    """Cluster transitions needed by the desired-state reconciler."""
