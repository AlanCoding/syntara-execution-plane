# Deferred capability designs

The files below are preserved design material for later work. Their API shapes,
examples, proposed backends, and tradeoffs are not current implementation contracts.
The content is retained as written, with relative links repaired after relocation.
See [current guides](../README.md) for supported behavior.

| Design | Preserved material |
| --- | --- |
| Workspace sharing | [Workspace contract and alternatives](data-sharing-with-workspace.md) |
| Volume workspace | [Example 02](examples/02-data-sharing-with-workspace.md) |
| Object-store workspace | [Example 03](examples/03-data-sharing-with-workspace-object-store.md) |
| OpenShell | [Example 04: target and sandbox policy](examples/04-openshell-sandbox-policy.md) |

EP does not currently implement the workspace API, shared workspace volumes,
object-store snapshots, or an OpenShell execution manager. Credential management
remains unresolved; follow the
[active discussion](https://github.com/ansible/handbook/pull/1824), rather than
assuming the preserved designs settle credential delivery.

Concrete gaps in existing behavior belong in [implementation TODOs](../todo/README.md).
