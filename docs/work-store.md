# Execution Plane: Work Store and Actor Services

`WorkStore` is the transactional repository for `WorkItem` and
`CompletionEvent` records. Work consumers use actor-specific ports and services
rather than a single record-shaped facade.

**Sources:** `src/execution_plane/work_item/work_item_store.py`,
`src/execution_plane/work_item/ports.py`,
`src/execution_plane/work_item/work_scheduler.py`,
`src/execution_plane/work_item/policy.py`, and
`src/execution_plane/models/work_item.py`

## Boundary

| Layer | Responsibility |
|---|---|
| `WorkCommandStore` / `WorkQueryStore` | Authenticated command submission/cancellation and client-scoped REST reads |
| `WorkScheduler` | Claims queued Work, resolves placement, revalidates candidates, and assigns or releases the claim |
| `WorkProgressStore` | Worker-owned dispatch, resource, result, uncertain-outcome, and requeue transitions |
| `CompletionEventStore` | Reads the due completion-outbox batch and records delivery attempts |
| `TargetDrainStore` | Exposes the Work-owned target-drain predicate |
| `WorkStore` | Implements every actor port with SQLAlchemy sessions, row locks, commits, and atomic transitions |
| Work policy | Pure status, reason-bound, and retry-delay rules shared by services and Store transitions |

Command handlers and REST resource queries are composition roots: they construct
`WorkStore` and use its narrow command/query ports directly. The worker
constructs `WorkStore` once and wires its scheduler, progress, outbox, and drain
ports to the actors that need them. No consumer receives the complete Work
Store contract unless it is a composition root.

## Actor contracts

`WorkScheduler` exposes `claim_and_place_work()`. It combines reservation,
placement, no-match failure, candidate revalidation, assignment, and claim
release so callers cannot observe or leak a half-placed reservation.

Worker managers, the worker loop, and the Kubernetes reconciler depend on
`WorkProgressStore`. `WorkStore` enforces terminal-result status policy, bounded
uncertain-outcome explanations, and claim fencing inside those transitions.

The Completion Notifier depends on `CompletionEventStore`. `WorkStore` rejects
negative retry delays before touching the outbox.

`WorkStore.is_target_drained` remains the Work-owned predicate used by
`DrainMonitor`; that consumer depends on `TargetDrainStore`, not the full Store.

## Persistence invariants

`WorkStore` keeps concurrency-sensitive behavior in one transaction:

- Queue reservation uses `SELECT ... FOR UPDATE SKIP LOCKED` and rotates claim ownership and generation.
- Target assignment locks the Work item and candidate target/Cluster rows before eligibility is rechecked.
- Claim fencing rejects stale owners or generations before lifecycle updates.
- Cancellation and dispatch transitions are serialized against the same locked Work row.
- Terminal results and their `CompletionEvent` outbox rows are committed together.
- Lease-expired uncertain work is moved to `RECONCILIATION_REQUIRED` with a durable event.

The Store does not expose generic entity mutation. Every method represents an
allowed persistence transition and belongs to an actor-specific port.
`ExecutionTargetStore.finalize_delete` owns the narrow cross-aggregate
transition that atomically rechecks active work and detaches historical work
while deleting a drained target.
