# SDK workload protocol

EP consumes the container service owned by `syntara-plugin-sdk`. The SDK is
the source of truth for `container.proto`, generated protobuf messages, gRPC
stubs, JSON encoding, and event validation. EP does not vendor or regenerate
any of those files.

`syntara-plugin-contracts` distributes the protocol source, schema bundle,
generated bindings, and `ContainerClient`. The Python runtime APIs retain their
`syntara_plugin.runtime` import path; there is no separate runtime distribution
in the merged SDK.
EP's adapter in [`sdk_adaptor.py`](../src/execution_plane/worker_manager/vanilla_k8s/sdk_adaptor.py) connects
that client to EP's cancellation, progress, and attempt lifecycle.

## Dependency and ownership

The SDK dependency is declared in [pyproject.toml](../pyproject.toml), resolved
in [uv.lock](../uv.lock), and exported with hashes to
[requirements.txt](../requirements.txt). These files are authoritative for its
version; documentation does not duplicate it.

Use `uv sync --locked --all-groups` (or `make install`) for reproducible
installation. No sibling SDK checkout or developer-local source override is
required. When updating the dependency, regenerate the lockfile and requirement
exports alongside the declaration.

## Command and workload data

`work.execute` retains `image`, `selectors`, and optional `output_config` for
scheduling. Its invocation is:

```json
{
  "workflow_run_id": "workflow-1",
  "step_revision_id": "script.v1",
  "inputs": {
    "language": "bash",
    "code": "printf '%s' \"$GREETING\"",
    "environment": {"GREETING": "hello"}
  },
  "runtime_context": {},
  "timeout_seconds": 60
}
```

The selected workload defines the meaning of inputs and its step revision.
`script.v1` is the integration test workload's revision, not a universal SDK
script identifier. EP supplies an invocation ID derived from the work UUID and
claim generation, and currently supplies an empty credential-file-path map.

Script environment variables are ordinary inputs. There is no released EP
workload credential broker or secret-mount implementation. The command rejects a
`credentials` field and caller-supplied
`credential_file_paths`. The final credential-management design remains unresolved;
see the [active discussion](https://github.com/ansible/handbook/pull/1824).
Cluster API authentication remains internal to EP's Kubernetes transport.

## Execution and outcomes

EP negotiates `Health`, checks that the image advertises the selected step (or
the SDK's platform-runner wildcard), then submits Execute once. It consumes
`ContainerClient.stream` to forward progress and require a valid terminal
outcome. Cancellation calls the SDK's Cancel RPC; after the grace period EP
closes its dedicated channel and cleans up the owned Kubernetes resources.

EP preserves the SDK's output schema digest, status code, status message,
error category/message, retryability, partial output, and object reference.
Zero status is success; any nonzero uint32 status is a deliberate step failure.
Runtime Failure events are separate from deliberate failed Results. Errors
after Execute may have been submitted never cause automatic replay. A lost
terminal outcome requires reconciliation. Results are persisted before cleanup.

Workload images implement `syntara.container.v1alpha1.ContainerService` and
advertise the requested step revision. EP has no legacy NodeService fallback.

## Test workload

The repository includes a small SDK-backed script workload for integration
tests. Build and load it into your test cluster before running Kind dispatch:

```sh
podman build -f tests/fixtures/sdk_script/Containerfile \
  -t localhost/syntara-sdk-script:dev tests/fixtures/sdk_script
# With Docker/Kind, use docker build and then:
kind load docker-image localhost/syntara-sdk-script:dev --name integration-test
```

This is the default local helper image. Set `EP_NODE_IMAGE` (or `--image`) and
`--step-revision-id` to use another SDK-compatible runner. CI builds the fixture
image for dispatch tests. This fixture is a test runner, not the production
script runner release.
