# Retry health-related placement misses

Status: intended behavior; not implemented. Jira: pending filing by the maintainer.

## Current behavior and source

[WorkScheduler._place_claimed_item](../../src/execution_plane/work_item/work_scheduler.py)
marks claimed work failed with `TargetUnavailable` whenever reconciliation returns
no available targets. It does not inspect ineligibility reasons. The
[HealthFilter](../../src/execution_plane/execution_target_reconciler/filters.py)
excludes degraded targets with `HEALTH`; the monitor can later restore them.

The earlier Resource Monitor and ExecutionTarget Reconciler designs intended
health misses to leave work queued with backoff. This document preserves that
concrete follow-up from AAP-92724/AAP-92722 rather than presenting it as current
behavior. Those references provide context, not a substitute for the new Jira.

## Intended behavior

A temporary health failure should not permanently fail work that could run once
a matching target recovers. When there are no available candidates but otherwise
matching placement is blocked by health, release/requeue the reservation with
bounded backoff. Preserve selectors and default routing; do not dispatch to an
unrelated target. Permanent selector/lifecycle/configuration misses continue to
fail as unschedulable.

`CAPACITY_EXHAUSTED` is reserved for a future trusted capacity signal. If a filter
eventually emits it, its scheduling treatment should also be retryable. This
follow-up does not introduce capacity measurement or a new capacity filter.

## Acceptance criteria for the Jira

- A health-blocked placement keeps work pending and does not emit a terminal
  failure/completion notification merely because the target is degraded.
- Retry timing is bounded and avoids repeatedly reserving the same item in a
  tight loop; other queued work can make progress.
- Once health recovers, the original WorkItem can be assigned without a new UUID.
- Required selectors and the composed default remain enforced. An unrelated
  unhealthy target must not turn a permanent selector miss into indefinite retry.
- Mixed rejection reasons have an explicit policy covered by tests; retry applies
  only when a candidate satisfying the work's placement constraints can recover.
- Cancellation and claim owner/generation fencing remain effective while work waits.
- Unit and PostgreSQL integration tests cover health-only misses, recovery,
  permanent misses, mixed inventories, and cancellation during backoff.

Update [current scheduling documentation](../scheduling.md#no-matching-targets)
when the behavior lands. No runtime changes are part of the documentation cleanup.
