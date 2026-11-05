# Execution Plane documentation

These guides describe the implementation in this repository.

| Guide | Contents |
| --- | --- |
| [Architecture](architecture.md) | Service ownership, processes, persistence, and execution flow |
| [Integration and API](integration.md) | Commands, authentication, queries, callbacks, and resource identities |
| [Clusters and targets](clusters-and-targets.md) | Registration, placement metadata, defaults, and draining |
| [Scheduling](scheduling.md) | Labels, selectors, eligibility, health monitoring, and assignment |
| [Execution](execution.md) | Claims, Kubernetes Jobs, cancellation, recovery, and completion delivery |
| [Workload protocol](workload-protocol.md) | EP's adapter to the SDK container service |
| [Development](development.md) | Standalone local setup and Kubernetes target tools |
| [Testing](testing.md) | Unit, PostgreSQL, Kind, and combined-service suites |

Start with architecture for the service model, integration for API consumers,
or development for a local environment.

[Implementation TODOs](todo/README.md) describe concrete gaps in current behavior.
[Roadmap designs](roadmap/README.md) preserve deferred workspace and OpenShell
material; they are not supported API or runtime contracts.
