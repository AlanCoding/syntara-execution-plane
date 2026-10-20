"""Actor-specific persistence ports for WorkItem use cases."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    import uuid
    from collections.abc import Awaitable, Callable

    from execution_plane.models.cluster import Cluster
    from execution_plane.models.completion_event import CompletionEvent
    from execution_plane.models.execution_target import ExecutionTarget
    from execution_plane.models.work_item import WorkItem, WorkItemStatus


class WorkCommandStore(Protocol):
    """Authenticated Work commands from the command ingress."""

    async def dispatch(
        self,
        client_id: str,
        item_id: uuid.UUID,
        payload: dict[str, Any],
    ) -> WorkItem:
        """Submit caller-identified work."""
        ...

    async def request_cancel(self, item_id: uuid.UUID, *, client_id: str) -> WorkItem:
        """Cancel queued work or request termination."""
        ...


class WorkQueryStore(Protocol):
    """Client-scoped Work reads used by the REST resource queries."""

    async def get(self, item_id: uuid.UUID, *, client_id: str) -> WorkItem | None:
        """Return one client-owned work item."""
        ...

    async def get_completion_event(self, work_item_id: uuid.UUID) -> CompletionEvent | None:
        """Return one terminal completion event."""
        ...

    async def list_for_client(self, *, client_id: str, limit: int) -> list[WorkItem]:
        """List client-owned work."""
        ...


class WorkSchedulingStore(Protocol):
    """Transactional transitions needed to claim and place Work."""

    async def reserve_one(self) -> WorkItem | None:
        """Reserve one queued or recoverable item."""
        ...

    async def assign_target(
        self,
        item_id: uuid.UUID,
        target_id: uuid.UUID,
        *,
        claim_owner_id: uuid.UUID,
        claim_generation: int,
        eligibility: Callable[[Cluster, ExecutionTarget], Awaitable[bool]],
    ) -> WorkItem | None:
        """Atomically assign an eligible target."""
        ...

    async def release_claim(
        self,
        item_id: uuid.UUID,
        *,
        claim_owner_id: uuid.UUID,
        claim_generation: int,
    ) -> bool:
        """Release an unassigned reservation."""
        ...

    async def set_result(
        self,
        item_id: uuid.UUID,
        result: dict[str, Any],
        status: WorkItemStatus,
        *,
        claim_owner_id: uuid.UUID | None = None,
        claim_generation: int | None = None,
    ) -> WorkItem:
        """Persist a terminal result and completion event."""
        ...


class WorkProgressStore(Protocol):
    """Worker-owned transitions after Work has been claimed."""

    async def mark_dispatched(
        self,
        item_id: uuid.UUID,
        *,
        claim_owner_id: uuid.UUID | None = None,
        claim_generation: int | None = None,
    ) -> bool:
        """Mark a current claim dispatched."""
        ...

    async def refresh_claim(
        self,
        item_id: uuid.UUID,
        *,
        claim_owner_id: uuid.UUID | None = None,
        claim_generation: int | None = None,
    ) -> bool | None:
        """Refresh a claim and report cancellation intent."""
        ...

    async def update_backend_resource(
        self,
        item_id: uuid.UUID,
        *,
        resource_name: str,
        resource_uid: str | None,
        cleanup_status: str,
        cleanup_error: str | None = None,
        claim_owner_id: uuid.UUID | None,
        claim_generation: int,
    ) -> None:
        """Persist backend resource identity and cleanup state."""
        ...

    async def set_result(
        self,
        item_id: uuid.UUID,
        result: dict[str, Any],
        status: WorkItemStatus,
        *,
        claim_owner_id: uuid.UUID | None = None,
        claim_generation: int | None = None,
    ) -> WorkItem:
        """Persist a terminal result and completion event."""
        ...

    async def mark_reconciliation_required(
        self,
        item_id: uuid.UUID,
        reason: str,
        *,
        claim_owner_id: uuid.UUID | None = None,
        claim_generation: int | None = None,
    ) -> WorkItem:
        """Persist an uncertain work outcome."""
        ...

    async def requeue_pre_execute_failure(
        self,
        item_id: uuid.UUID,
        *,
        claim_owner_id: uuid.UUID,
        claim_generation: int,
    ) -> WorkItem:
        """Requeue a proven pre-execute failure."""
        ...


class CompletionEventStore(Protocol):
    """Completion outbox operations used by event delivery."""

    async def get_pending_completion_events(self, *, limit: int = 100) -> list[CompletionEvent]:
        """Load a bounded batch of due events."""
        ...

    async def record_completion_event_attempt(
        self,
        event_id: uuid.UUID,
        *,
        delivered: bool,
        error: str | None = None,
        retry_after_seconds: int = 10,
    ) -> None:
        """Record delivery or schedule a retry."""
        ...


class TargetDrainStore(Protocol):
    """Drain predicate owned by the Work repository."""

    async def is_target_drained(self, target_id: uuid.UUID) -> bool:
        """Return whether owned or uncertain work remains on a target."""
        ...
