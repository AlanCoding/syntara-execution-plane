# Work execution and recovery

A WorkItem is EP's durable unit of execution. Its UUID is the caller's work
command UUID. A claim owner and generation identify the current execution
attempt; Kubernetes Job and Pod names/UIDs are separate infrastructure identities.

## Reservation and dispatch

`WorkStore` reserves pending work with `SELECT ... FOR UPDATE SKIP LOCKED`.
`WorkScheduler` resolves placement and revalidates candidates before assignment.
Lifecycle mutations check claim ownership and generation so a stale worker
cannot update a newer attempt. Cancellation and dispatch transitions serialize
against the locked WorkItem.

The worker wakes through PostgreSQL LISTEN/NOTIFY and polls every five seconds
as a fallback. Each claimed item runs in its own task, bounded by
`EP_MAX_CONCURRENT_DISPATCHES` (default 8 per worker process). This cap bounds EP
in-flight work; it does not measure or reserve Kubernetes capacity.

```text
pending -> claimed -> dispatched -> running -> completed / failed
                                  |          |
                                  +----------+-> cancel_requested -> cancelled
                                  +----------+-> reconciliation_required
```

This sketch shows the main paths. Pending work can be cancelled without starting
an attempt; a received terminal result can win a race with cancellation.

## Kubernetes allocation and transport

`WorkerManager.dispatch(work_item)` owns backend execution. The Kubernetes
manager marks work dispatched before external allocation and uses a deterministic
Job name derived from the work UUID and claim generation. It installs a per-attempt
NetworkPolicy before creating the Job, then finds the Pod by Job label and verifies
its Job owner UID before opening a port-forward.

The Job has one completion, one parallel Pod, `backoffLimit: 0`, an active deadline
covering startup, execution timeout, and grace, and a one-hour finished-Job TTL.
The Pod runs non-root with a read-only root filesystem, dropped capabilities,
no service-account token, bounded CPU/memory, and memory-backed temporary storage.
Typed target placement supplies namespace, node selectors, and tolerations.

Application input, progress, errors, and results use the
[SDK gRPC container service](workload-protocol.md) over the authenticated Kubernetes
API port-forward. EP does not use Pod logs, exec, or workload input Secrets to
carry that data. Progress is currently logged as metadata rather than persisted
as a durable job-event stream.

The NetworkPolicy denies ingress and allows DNS plus operator-configured egress
CIDRs. `EP_WORKLOAD_ALLOWED_EGRESS_CIDRS` and
`EP_WORKLOAD_FORBIDDEN_EGRESS_CIDRS` configure the allowed ranges and exclusions.
Policy enforcement depends on the target CNI; resource creation alone is not
proof of traffic isolation.

## Recovery and cancellation

Before submitting Execute, the manager durably records `running` and renews the
claim lease while transport runs. A positively identified pre-Execute failure,
including credential-resolution failure, can be requeued after
`EP_DISPATCH_RETRY_BACKOFF_SECONDS` (default 5).

If Execute may have been submitted and the outcome is lost, EP records
`reconciliation_required` and does not automatically run another attempt.
Expired leases for uncertain dispatched/running work also require reconciliation.
A completed Kubernetes Job cannot recover the business result. The SDK runtime
has no result replay/status API; operators must investigate before an explicit
retry with a new work UUID. Jobs do not provide exactly-once execution.

Cancellation uses the SDK Cancel RPC first. Deleting the exclusively owned Job
with foreground propagation is the forced-termination fallback. EP reports
`cancelled` only after confirming the invocation stopped; a received terminal
result wins a concurrent cancellation race.

## Results, completion delivery, and cleanup

EP commits the terminal result and inline completion-notification state together
before deleting the Job. Notification status is stored on the WorkItem, rather
than in a separate command journal or completion table. The notifier sends
`work.execute.completed`, validates the receipt's message ID, retries failures
with backoff, and reclaims expired delivery leases. Delivery is at least once;
consumers must handle duplicates by work UUID. `reconciliation_required` produces
an `outcome_unknown` completion without asserting that execution has stopped.

Resource cleanup state (`pending`, `complete`, `deferred`, or `failed`) is
independent of the execution outcome. The Job TTL removes finished Jobs/Pods but
not NetworkPolicies. An orphan-policy reconciler removes aged policies only
after checking that the associated Job and Pods are absent.

Submitted invocation payloads are encrypted at rest with EP's configured
AES-256 key. API, worker, and migration processes need the same key. This does
not encrypt terminal results or make arbitrary workload output non-sensitive.

Sources: [worker loop](../src/execution_plane/worker.py),
[WorkStore](../src/execution_plane/work_item/work_item_store.py),
[Kubernetes backend](../src/execution_plane/worker_manager/vanilla_k8s/), and
[CompletionNotifier](../src/execution_plane/completion_notifier/notifier.py).
