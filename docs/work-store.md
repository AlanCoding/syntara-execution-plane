# Execution Plane: Work Store and Service

`WorkStore` is the persistence boundary for `WorkItem` and
`CompletionEvent` records. `WorkItemService` is the domain-facing boundary used
by command handlers, the worker, Worker Managers, the Completion Notifier, and
the drain monitor.

**Sources:** `src/execution_plane/work_item/work_item_store.py`,
`src/execution_plane/work_item/work_item_service.py`,
`src/execution_plane/models/work_item.py`

## Boundary

| Layer | Responsibility |
|---|---|
| `WorkItemService` | Placement orchestration, terminal-result policy, retry validation, and bounded error messages |
| `WorkStore` | SQLAlchemy sessions and engines, row locks, commits and rollbacks, queue selection, atomic state transitions, and transactional completion-outbox writes |

Composition roots construct `WorkStore` and inject it into `WorkItemService`.
The Service exposes that same instance as a typed public `store` attribute.
Callers use `service.store` for persistence operations and the Service itself
for validation and placement orchestration; method signatures are defined once.

## Service contract

`WorkItemService` exposes its typed `store` and retains operations with policy:

- `store.dispatch`, `store.get`, `store.list_for_client`, and `store.request_cancel` for command and query flows.
- `store.reserve_one` and `place_reserved_item` for worker scheduling.
- `store.mark_dispatched`, `store.refresh_claim`, `update_backend_resource`, `set_result`,
  `mark_reconciliation_required`, and `store.requeue_pre_execute_failure` for execution.
- `store.get_pending_completion_events` and `record_completion_event_attempt` for durable completion delivery.
- `store.is_target_drained` for target and Cluster drain finalization.

The Service validates terminal result statuses and non-negative completion retry
delays. It resolves Work requirements, revalidates candidate targets, fails a
reserved item when no target matches, and releases the reservation when every
candidate becomes ineligible.

## Persistence invariants

`WorkStore` keeps concurrency-sensitive behavior in one transaction:

- Queue reservation uses `SELECT ... FOR UPDATE SKIP LOCKED` and rotates claim ownership and generation.
- Target assignment locks the Work item and candidate target/Cluster rows before eligibility is rechecked.
- Claim fencing rejects stale owners or generations before lifecycle updates.
- Cancellation and dispatch transitions are serialized against the same locked Work row.
- Terminal results and their `CompletionEvent` outbox rows are committed together.
- Lease-expired uncertain work is moved to `RECONCILIATION_REQUIRED` with a durable event.

The Store does not accept SQLAlchemy sessions from callers and does not expose
generic entity mutation. Every method represents an allowed persistence transition.
