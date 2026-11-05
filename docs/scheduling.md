# Scheduling, labels, and target health

`WorkScheduler` reserves a WorkItem, derives requirements from its persisted
payload, and calls the store-backed `PlacementResolver`. The reconciler returns
an unordered set of eligible target snapshots and reasons for rejected targets.
It neither assigns work nor ranks targets by load.

## Labels and selectors

Cluster and target labels advertise placement attributes. Work `selectors`
express required string values. Effective labels merge Cluster labels with
target labels; target values override matching Cluster keys. Remaining selectors
match by exact equality, with AND across keys. Extra target labels do not improve
rank. EP does not read AO workflow, project, or execution-profile definitions.

Command callers cannot write underscore-prefixed label keys. EP creates immutable
`_cluster_id` and `_execution_target_id` identity labels and preserves them when
public labels are replaced.

### Cluster identity affinity

The matcher also recognizes selector **values** equal to a registered Cluster's
name or UUID. If any such value exists, reconciliation considers only the pinned
Clusters and removes their identity-valued entries before matching other keys.
This behavior applies independently of the selector key. Use values such as
`region=us-east-1` for ordinary label constraints; avoid accidentally using a
Cluster name as an unrelated label value.

## Default routing

With empty selectors, EP keeps only the eligible target where both
`Cluster.is_default` and `ExecutionTarget.is_default` are true. It does not use
all active targets or fall back to another Cluster if the composed default is
unavailable. Non-empty selectors use matching instead; default flags do not
bypass required labels.

## Eligibility and assignment

The source adapter excludes non-active Clusters from eligibility by representing
them as disabled snapshots. Disabled Clusters are skipped. Each remaining target
passes these filters in order:

| Filter | Behavior |
| --- | --- |
| Lifecycle | Denies disabled targets and states other than active/degraded |
| Selector | Matches effective labels; skipped for empty selectors |
| Health | Denies degraded targets with reason `HEALTH` |
| Policy | Pass-through; no isolation-policy evaluation is implemented |

`CAPACITY_EXHAUSTED` and `POLICY` exist as result vocabulary but are not emitted
by the current built-in filters. Kubernetes capacity is not measured or reserved.

The scheduler tries returned candidates in their available order. Assignment
locks the work, target, and Cluster records and rechecks current eligibility.
If all candidates become ineligible during assignment, the scheduler releases
the claim. The worker resolves the chosen backend from its local manager registry;
only `kubernetes` has a registered execution manager.

## No matching targets

If reconciliation returns no eligible targets, the scheduler currently marks the
WorkItem `failed` with error type `TargetUnavailable`. This includes health-only
misses. It does not retry with empty selectors or ignore a selector constraint.

[Health-related placement retries](todo/health-placement-retries.md) records the
concrete intended change and acceptance criteria for a Jira follow-up. That retry
policy is not implemented today.

## Selector examples

Use the [command envelope](integration.md#work-submission) with a `work.execute`
payload such as:

```json
{
  "image": "localhost/syntara-sdk-script:dev",
  "selectors": {"region": "us-east-1", "env": "production"},
  "invocation": {
    "workflow_run_id": "workflow-1",
    "step_revision_id": "script.v1",
    "inputs": {"language": "bash", "code": "echo hello"},
    "runtime_context": {},
    "timeout_seconds": 60
  }
}
```

This image/revision is the repository's test fixture and must be available to the
selected target. For an inventory with an active global default Cluster labelled
`region=us-east-1`, its default target with no public labels, and a second active
target labelled `env=production`:

| Work selectors | Outcome |
| --- | --- |
| `{}` | Default target on the global default Cluster |
| `{"region": "us-east-1", "env": "production"}` | Production target, inheriting the Cluster's region |
| `{"region": "ap-southeast-1"}` | No match; work fails when no Cluster/target advertises that region |

These selectors constrain target placement; the image is a separate payload field.
Workspace sharing and OpenShell examples are preserved as
[roadmap designs](roadmap/README.md), not current dispatch examples.

## Health monitoring

The worker owns a periodic `ResourceMonitor`. Its Kubernetes probe reads the
target namespace through the Cluster endpoint using the resolved Cluster
credential. Success checks reachability, namespace existence, and permission to
read that namespace; it does not establish spare CPU/memory or all dispatch RBAC.
A 404, authorization error, timeout, or unreachable API counts as unhealthy.

| Setting | Default |
| --- | --- |
| `EP_RESOURCE_MONITOR_INTERVAL_SECONDS` | 30 |
| `EP_RESOURCE_MONITOR_PROBE_TIMEOUT_SECONDS` | 10 |
| `EP_RESOURCE_MONITOR_FAILURE_THRESHOLD` | 3 consecutive failures |
| `EP_RESOURCE_MONITOR_SUCCESS_THRESHOLD` | 2 consecutive successes |

The timeout must be shorter than the interval. Hysteresis counters are in memory
and reset on restart. Health writes only change active/degraded state and status
messages; they do not revive registration, failure, or draining states. The probe
skips RHEL, non-HTTP Cluster endpoints, disabled resources, non-active Clusters,
and targets outside active/degraded Kubernetes placement. Credential resolution
happens before probe dispatch; resolution failures are recorded as unhealthy.
One target's failure does not abort the rest of the scan. Existing dispatched
work continues when target health degrades.

Sources: [scheduler](../src/execution_plane/work_item/work_scheduler.py),
[reconciler and matching](../src/execution_plane/execution_target_reconciler/),
[monitor and probes](../src/execution_plane/resource_monitor/), and
[settings](../src/execution_plane/config.py).
