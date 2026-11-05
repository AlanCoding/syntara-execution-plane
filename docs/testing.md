# Testing

Run commands from the repository root. The suites below exist in this checkout;
their presence does not establish that a particular deployment or CNI has passed.

## Unit and static checks

```bash
uv sync --locked --all-groups
uv run pytest tests --ignore=tests/integration --ignore=tests/e2e
make lint
make format
make typecheck
```

Unit tests use fake stores, transports, or credentials where appropriate.
They do not require a live AO, PostgreSQL, or Kubernetes stack.
`make test-coverage TEST_ARGS='tests --ignore=tests/integration --ignore=tests/e2e'`
adds branch coverage and JUnit reports. CI combines unit, PostgreSQL, and Kind
reports with `make coverage-combine`; see [.github/workflows/ci.yml](../.github/workflows/ci.yml).

## PostgreSQL integration

Use a disposable database. Set `EP_TEST_DATABASE_URL` to a migration-capable
asyncpg URL and configure `EP_CREDENTIAL_ENCRYPTION_KEY` or its `_PATH` setting.
The shared integration fixture applies Alembic migrations itself.

```bash
uv run pytest tests/integration/postgres -m integration -v
```

These tests cover persistence, command effects, defaults, placement, completion
notifications, filtering, and cursor pagination against PostgreSQL. Do not use a
service database whose contents must be preserved.

## Kind integration

This suite also requires a live Kubernetes cluster and a registered Cluster in
the disposable EP database. Start EP's API against that database and configure
`EP_DEFAULT_WORKLOAD_NAMESPACE=execution-plane`. Register through
`tools.deploy_kind_execution_target` with `--cluster-name integration-test` and
an `--credential-ref` matching `EP_KIND_CREDENTIAL_REF`.

Build the [SDK fixture image](workload-protocol.md#test-workload) and load it into
Kind. Export these values for the test process:

| Variable | Value |
| --- | --- |
| `EP_TEST_DATABASE_URL` | Disposable migrated EP database |
| `EP_IT_K8S_CLUSTER_NAME` | Registered Kind name, default `integration-test` |
| `EP_IT_K8S_ENDPOINT` | Kubernetes API endpoint reachable by the test process |
| `EP_IT_K8S_TOKEN` | Dispatcher ServiceAccount bearer token |
| `EP_IT_K8S_CA_CERT` | Kubernetes API CA PEM |
| `EP_IT_K8S_NAMESPACE` | Workload namespace, default `execution-plane` |
| `EP_KIND_CREDENTIAL_REF` | UUID used during registration |

```bash
uv run pytest tests/integration/kind -m integration -v --timeout=600
```

The tests use an in-memory credential resolver for the live dispatcher token;
that does not test AO credential resolution. They exercise Job/gRPC dispatch,
placement fields, cancellation, concurrent work, health probing, and client tools.
The [CI Kind job](../.github/workflows/ci.yml) provides the exact provisioning,
image loading, API startup, and coordinate-export sequence.

## Combined AO + EP tests

[tests/e2e](../tests/e2e/) exercises a live AO/Temporal stack and standalone EP
API/worker against Kubernetes. The hello-world test submits an AO workflow and
checks its script activity, EP work result, and cleanup. RBAC tests check the
dispatcher's allowed and forbidden API operations.

For a configured local stack, set `AO_API_BASE`, `APP_ADMIN_PASSWORD_PATH` (or
`ADMIN_PASSWORD`), `EP_API_URL`, and `EP_API_CA_FILE`. Supply `EP_SERVICE_TOKEN`
or the signing key used by [the fixtures](../tests/e2e/conftest.py). The live EP
worker needs its credential and completion callbacks configured against AO.

```bash
uv run pytest tests/e2e -m e2e -v
```

The Konflux path is maintained in
[tools/ci/konflux-prepare-execution-plane.sh](../tools/ci/konflux-prepare-execution-plane.sh)
and [tools/konflux-run-e2e.sh](../tools/konflux-run-e2e.sh), with triggers under
[.tekton/](../.tekton/). It prepares the EP stack and runs the E2E suite; it
replaces the historical feature-branch demo helpers.

## Interpreting results

A happy-path workflow does not establish crash recovery or network isolation.
Use an enforcing CNI to test allowed and denied destinations alongside the
API port-forward. Kind's default kindnet does not provide NetworkPolicy enforcement.
For deployment validation, record AO/EP revisions, workload image digest,
Kubernetes version, CNI, and scenario outcomes. Exercise callback outage,
restart, cancellation, startup failure, and lost/ambiguous Execute outcomes before
claiming those deployment properties. An uncertain result must remain visible
without an automatic second execution; see [recovery semantics](execution.md#recovery-and-cancellation).
