# Local development

EP runs independently of AO. The local Compose stack provides EP PostgreSQL,
separate migration/runtime roles, migrations, the API, and the worker. A reachable
Kubernetes/OpenShift target runs workload Jobs. AO and Temporal are only needed
for combined-service workflow testing and the current credential callback.

## Install and start

Requirements: Python in the range declared by [pyproject.toml](../pyproject.toml),
`uv`, Podman with Compose support, and `kind`/`kubectl` for a local target.

```bash
uv sync --locked --all-groups
cp .env.example .env
make setup
uvx podman-compose up --build -d
```

`make setup` installs dependencies and generates local secrets/TLS material.
If a sibling Syntara checkout has `backend/.secrets/jwt-primary.pub`, the secrets
helper copies it to verify local AO-issued tokens. Edit `.env` to match AO's JWT
issuer and the paths in [.env.example](../.env.example). The API publishes HTTPS
on loopback port 8001 by default. The API host/port inside Compose differ from
the published host port; [compose.yaml](../compose.yaml) defines those mappings.

Compose bootstraps the database and runs migrations before API/worker readiness.
For a separately managed database, run migrations with a migration-capable URL:

```bash
DATABASE_URL=postgresql+asyncpg://migrator:password@localhost/execution_plane \
EP_CREDENTIAL_ENCRYPTION_KEY_PATH=/path/to/encryption-key \
uv run alembic -c alembic.ini upgrade head
```

The API and worker use `EP_DATABASE_URL` and the same encryption key. They run as
`uv run execution-plane-api` and `uv run execution-plane-worker` when launched
on the host. Configure their database, key, JWT, and TLS settings from
[EPSettings](../src/execution_plane/config.py). API SIGINT/SIGTERM shutdown uses
`EP_API_GRACEFUL_SHUTDOWN_SECONDS` (default 20) for in-flight requests.

## Register a Kubernetes target

The helper signs an AO service JWT using a local or sibling Syntara ES256 key;
EP does not issue tokens. `make generate-token` prints a token for manual API
calls. Work submission requires `work.execute` scope, not a project-ID claim.

The current implementation needs an AO-managed credential reference and a reachable
credential-resolution callback to execute work. Configure the callback URL and
its TLS settings in the worker environment. The checked-in Compose worker only
forwards a subset of settings; use a local Compose override to add the credential
callback URL/TLS settings and mount their certificate/key files. Add completion
callback TLS settings and mounts there as well when testing delivery to AO.
See [credential management](integration.md#credential-management) for current
mechanics and the unresolved final design.

For an existing AO credential:

```bash
uv run python -m tools.deploy_kind_execution_target \
  --credential-ref 00000000-0000-0000-0000-000000000001
```

Replace the example UUID with the actual credential reference. Alternatively,
create or refresh the AO credential through the helper:

```bash
uv run python -m tools.deploy_kind_execution_target \
  --create-ao-credential \
  --ao-api-url https://localhost:8000 \
  --ao-admin-password-file /path/to/admin-password
```

The helper creates/reuses Kind, applies the maintained
[target RBAC](../deploy/kubernetes/execution-target/rbac.yaml), and registers the
Cluster through EP's command API. Set `KIND_EXPERIMENTAL_PROVIDER=podman` for
Podman. Set `EP_API_CA_FILE` to the trusted EP API CA and
`EP_AO_JWT_ISSUER` to the token issuer. `--host-worker` selects Kind's published
host endpoint; `--recreate` replaces the Kind cluster.

Set `EP_DEFAULT_WORKLOAD_NAMESPACE` on the EP API to the namespace used by the
helper (`execution-plane` by default) before initial provisioning. Namespace is
not a Cluster command field. Existing targets can be edited through target
placement commands. `make kind-target KIND_ARGS='...'` forwards helper options.

## Run a workload

Build and load the [SDK test image](workload-protocol.md#test-workload) into Kind.
The helper defaults to that image; choose another SDK-compatible image with
`EP_NODE_IMAGE` or `--image` and its advertised `--step-revision-id`.

```bash
uv run python -m tools.submit_work_item --language bash --code 'echo hello' --wait
```

`--work-id` sets the stable work UUID; `--env KEY=VALUE` supplies ordinary script
environment inputs. `--payload-file` accepts a complete work payload. A duplicate
work UUID conflicts; inspect the existing resource after an ambiguous response.
See [integration](integration.md) for the command envelope and queries.

## Deployment configuration

The service image builds with `make image`. Maintained Kubernetes service
manifests live in [deploy/kubernetes/base](../deploy/kubernetes/base/); provide
its referenced Secrets and ConfigMap before applying it. Target RBAC grants
Job, Pod observation/port-forward, NetworkPolicy, and namespace-probe permissions.
Workload Secret, Pod-log, and Pod-exec access are not required by the transport.

The worker needs `EP_COMPLETION_CALLBACK_URL` and outbound TLS configuration to
deliver results to AO. Without a completion endpoint, EP retains the result and
retries notifications. Configure workload egress CIDRs on the worker if needed;
by default policy allows DNS without general egress. Confirm policy enforcement
with the target CNI. See [execution](execution.md) and [testing](testing.md).
