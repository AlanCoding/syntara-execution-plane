"""Domain-facing execution-target lifecycle operations."""

from __future__ import annotations

from typing import TYPE_CHECKING

from execution_plane.execution_target.execution_target_store import (
    DefaultExecutionTargetError,
    ExecutionTargetNotFoundError,
)

if TYPE_CHECKING:
    import uuid

    from execution_plane.execution_target.execution_target_store import ExecutionTargetStore
    from execution_plane.models.execution_target import ExecutionTarget


class ExecutionTargetService:
    """Validate target deletion; expose persistence through the typed store attribute."""

    def __init__(self, store: ExecutionTargetStore) -> None:
        """Use the store for persistence."""
        self.store: ExecutionTargetStore = store

    async def request_delete(self, target_id: uuid.UUID, updated_by: uuid.UUID) -> ExecutionTarget:
        """Disable a non-default target and mark it as DRAINING."""
        target = await self._require_non_default(target_id)
        return await self.store.request_delete(target.id, updated_by)

    async def _require_non_default(self, target_id: uuid.UUID) -> ExecutionTarget:
        """Return a target only if it is not the protected default target."""
        target = await self.store.get(target_id)
        if target is None:
            raise ExecutionTargetNotFoundError(target_id)
        if target.is_default:
            raise DefaultExecutionTargetError
        return target
