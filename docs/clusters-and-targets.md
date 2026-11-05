# Clusters and execution targets

A Cluster identifies a compute environment and its management connection. An
ExecutionTarget belongs to one Cluster and identifies where a worker runs.
For the implemented Kubernetes backend, that location is a namespace with
optional node selectors and tolerations.

## Stored configuration

| Resource | Configuration |
| --- | --- |
| Cluster | Caller-supplied UUID, name, endpoint, credential reference, optional CA, source client, platform type, labels, enabled/default flags, lifecycle and status message |
| ExecutionTarget | UUID, Cluster foreign key, name, backend type, endpoint, credential reference, typed placement, labels, enabled/default flags, lifecycle, status message, and last-run time |

Both resources carry creator/updater UUIDs and timestamps. The global default
Cluster and each Cluster's default target are protected by partial unique indexes.
The database permits no global default before initial provisioning. Stores
promote the first eligible Cluster when necessary and atomically demote an old
default when promoting a replacement.

## Registration and updates

`cluster.register` and `cluster.provision` use the same synchronous provisioning
path through `ClusterRegistrar.provision`. The caller supplies `resource_id`,
which is the physical Cluster UUID. There is no separate binding record or
configuration-revision journal. Another client's Cluster cannot be adopted.

For a new Cluster, provisioning persists the Cluster, creates and activates its
default Kubernetes target, and marks the Cluster active. The target namespace
comes from `EP_DEFAULT_WORKLOAD_NAMESPACE` (default `default` in settings;
[Compose](../compose.yaml) configures `execution-plane`). Provisioning records
configuration; an active record is not proof that connectivity has been tested.
[Health monitoring](scheduling.md#health-monitoring) probes the namespace.

Reapplying an existing active Cluster updates its configuration without rewriting
independently managed target fields. `cluster.update` patches supplied fields.
`execution_target.register` creates an independent target on a client-owned
active Cluster. Target updates retain omitted placement selectors/tolerations;
`cluster_id` cannot be changed through an update.

Target placement has this shape:

```json
{
  "type": "kubernetes",
  "namespace": "execution-plane",
  "node_selectors": ["kubernetes.io/os=linux"],
  "tolerations": ["dedicated=execution:NoSchedule"]
}
```

EP routing labels are separate from Kubernetes node selectors. Labels affect
which ExecutionTarget EP selects; typed placement configures the worker Pod.

## Defaults and lifecycle

Empty work selectors use the default target on the global default Cluster.
Promote replacements with `is_default: true` before deleting or explicitly
demoting a current default. The current default Cluster cannot be explicitly
disabled. See [scheduling](scheduling.md) for eligibility and selector matching.

Cluster states are `registering`, `active`, `draining`, and `error`. Target states
are `registering`, `validating`, `bootstrapping`, `active`, `degraded`, `draining`,
and `failed`. These enums represent stored states; they do not imply every
registration path runs through every intermediate state. Health writes only
transition targets between `active` and `degraded`.

Deletion disables a resource and marks it `draining`. Cluster deletion marks
its targets draining in the same transaction. `DrainMonitor` scans persisted
drains on startup and continues polling. It asks `WorkStore.is_target_drained`
whether active work remains before requesting physical deletion. Target
finalization rechecks work in the transaction and detaches historical WorkItems.
A Cluster can be physically removed only after its targets are gone. Work with
an uncertain execution outcome can prevent a drain from completing.

## Credentials and queries

The current implementation stores AO-owned credential UUIDs. Kubernetes dispatch
and health probing resolve the owning Cluster's reference for the operation;
target credential metadata does not imply a separate workload-secret delivery
mechanism. CA material is encrypted at rest. Public reads omit credential
references and CA contents.

Credential management remains unresolved; see the
[active credential discussion](https://github.com/ansible/handbook/pull/1824)
and the [current integration mechanics](integration.md#credential-management).

Sources: [models](../src/execution_plane/models/),
[ClusterRegistrar](../src/execution_plane/cluster/cluster_registrar.py),
[ClusterStore](../src/execution_plane/cluster/cluster_store.py),
[ExecutionTargetStore](../src/execution_plane/execution_target/execution_target_store.py),
and [DrainMonitor](../src/execution_plane/drain_monitor.py).
