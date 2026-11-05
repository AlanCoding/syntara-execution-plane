# Integration and API reference

EP owns work, clusters, and targets in its database. AO owns workflows,
authorization of its users, and Temporal activity completion. Participants share
[execution-plane-client](../src/execution_plane_client/README.md) contracts, not
stores or database access.

## Authentication and commands

All mutations use `POST /v1/commands`. Authenticate with an AO-signed ES256
service JWT. EP verifies issuer, audience, signature, expiration, issued-at,
and configured `client_id`. The token's space-separated `scope` must grant the
exact command type. Envelope `source_id` and `scope.client_id` must match the
verified client; `destination_id` must match `EP_SERVICE_JWT_AUDIENCE`.
Project IDs are not part of the EP authentication or work identity contract.

Configure API HTTPS with `EP_API_TLS_CERT_PATH` and `EP_API_TLS_KEY_PATH`.
`EP_API_TLS_CLIENT_CA_PATH` enables client-certificate validation when configured.
Outbound callbacks have their own CA and client certificate/key configuration.

HTTP 202 returns a `TransportReceipt` with `received`, `message_id`, and an
optional resource or result. It confirms that the domain handler returned.
Work execution and deletion draining continue asynchronously; cluster
registration/provisioning applies its resource setup synchronously.
Commands are not persisted and have no status or child-history endpoints.

The body limit is 1 MiB; command payload validation ordinarily limits payloads
to 512 KiB. Duplicate JSON keys, non-finite values, unsupported revisions, and
malformed payloads are rejected. Invalid requests return 422, oversized bodies
413, domain conflicts 409, and missing/other-client resources 404.

## Work submission

```json
{
  "message_id": "00000000-0000-0000-0000-000000000001",
  "command_id": "00000000-0000-0000-0000-000000000002",
  "source_id": "syntara-orchestration",
  "destination_id": "execution-plane",
  "scope": {"client_id": "syntara-orchestration"},
  "command": {
    "command_id": "00000000-0000-0000-0000-000000000002",
    "command_type": "work.execute",
    "command_revision": 1,
    "occurred_at": "2026-11-05T12:00:00Z",
    "payload": {
      "image": "localhost/syntara-sdk-script:dev",
      "selectors": {},
      "invocation": {
        "workflow_run_id": "workflow-1",
        "step_revision_id": "script.v1",
        "inputs": {"language": "python", "code": "print('hello')"},
        "runtime_context": {},
        "timeout_seconds": 60
      }
    }
  }
}
```

The envelope and nested command UUIDs must match. That UUID becomes `WorkItem.id`;
there is no separate request or project correlation key. Reusing a work UUID
returns 409, including when the payload matches. After losing a submission
response, query that UUID before deciding whether to submit again.

The example image is the [SDK test workload](workload-protocol.md#test-workload).
Other images must implement the SDK container service and advertise the requested
step revision. EP assigns attempt invocation IDs. Script environment variables
are ordinary `inputs.environment`; workload secret-file delivery is not implemented.

Python callers instantiate a typed command and call
`to_message(source_id=..., destination_id=..., client_id=...)`, then send
`message.model_dump(mode="json")` using their HTTP client. The helper generates
fresh identity/timestamp values by default; retain the message or explicitly
reuse those values when rebuilding it. It does not provide network retries or
generic command deduplication.

## Installed commands

All installed types currently use command revision 1. This wire-schema revision
is distinct from the removed Cluster configuration-revision mechanism.

| Type | Payload and effect |
| --- | --- |
| `work.execute` | Image, invocation, optional selectors/output configuration; persist pending work |
| `command.cancel` | `target_command_id`; request cancellation of existing work |
| `cluster.register`, `cluster.provision` | `resource_id`, name, endpoint, `credential_ref`, optional CA/labels/enabled/default flags; provision Cluster and initial default target |
| `cluster.update` | `resource_id` and changed fields; update Cluster metadata or promote the default |
| `cluster.delete` | `resource_id`; disable and drain a non-default Cluster |
| `execution_target.register` | `resource_id`, owned `cluster_id`, name, backend, placement, endpoint, `credential_ref`, optional labels/default flag |
| `execution_target.update` | `resource_id` and mutable target fields; optionally promote the default |
| `execution_target.delete` | `resource_id`; drain a non-default target |
| `execution_target.health` | `resource_id`; return one on-demand probe result using the owning Cluster credential |

Cluster `resource_id` is the physical Cluster UUID (shared with AO's Integration
UUID in that integration). Registering the same owned Cluster UUID is an upsert;
there is no `resource_key`, `desired_revision`, binding reconciler, or second
physical identifier. Namespace belongs to target placement. Cluster provisioning
seeds it from `EP_DEFAULT_WORKLOAD_NAMESPACE`.

Partial updates retain omitted fields. Cluster update permits explicit null only
for CA; target placement patches preserve omitted selectors/tolerations.
See [cluster and target lifecycle](clusters-and-targets.md) for defaults,
registration, and draining details.

Cancellation before work arrives returns 404; no tombstone or cancellation
journal is retained. Dispatched work cancellation is asynchronous. Query its
resource or observe the completion command for the final outcome.

## Resource queries

| Endpoint | Required scope |
| --- | --- |
| `GET /v1/capabilities` | `capabilities:read` |
| `GET /v1/work-items` and `GET /v1/work-items/{id}` | `work-items:read` |
| `GET /v1/clusters` and `GET /v1/clusters/{id}` | `clusters:read` |
| `GET /v1/execution-targets` and `GET /v1/execution-targets/{id}` | `execution-targets:read` |

Reads are scoped to the authenticated client. Target ownership follows the owning
Cluster. Cluster route IDs are Cluster UUIDs; target IDs are target UUIDs. Responses
exclude management credential references, CA material, and work invocations.
Work lists omit result bodies; individual work reads include the stored result
and its size. Cleanup status/error are separate fields from execution status.

Liveness is `/healthz/live`; readiness is `/healthz/ready` and checks the database.
The running API exposes interactive documentation at `/docs`. The generated
[openapi.yaml](../openapi.yaml) describes queries, installed command variants,
and the outbound completion webhook. Generate it with `make openapi` after
changing API contracts.

### Pagination and filtering

Lists accept `limit` (1–100, default 20), `cursor`, `sort`, and `include_total`.
The response contains `resources`, `next`, `prev`, and optional `total`. Work
sorts newest first (`-created_at`); other resources default to `created_at`.
Prefix a field with `-` for descending order. The UUID breaks sorting ties.

| Resource | Sortable fields |
| --- | --- |
| Work | `id`, `created_at`, `status`, `resource_cleanup_status` |
| Targets | `id`, `created_at`, `name`, `endpoint`, `status`, `backend_type`, `cluster_id`, `enabled`, `is_default` |
| Clusters | `id`, `created_at`, `updated_at`, `name`, `endpoint`, `status`, `enabled`, `is_default` |

Forward opaque cursors unchanged and retain the same filters, sort, and limit.
An absent next/previous page is null. Totals count all matching client-owned
resources, independently of the current cursor. Unsupported sorts and malformed
cursors return 422.

Filters use bracket syntax and run in PostgreSQL before pagination and totals.
Work additionally permits `claimed_at`, `completed_at`, and
`resource_cleanup_error`. Targets additionally permit `last_ran_at`,
`status_message`, and `labels[key]`; Clusters permit `status_message` and
`labels[key]`. Credentials and client ownership are not caller-filterable.

| Syntax | Meaning |
| --- | --- |
| `status=failed` or `status[eq]=failed` | Equality |
| `id[in]=<uuid1>,<uuid2>` | Membership |
| `status=pending,failed` | Either value |
| `name[contains]=worker` | Case-insensitive literal substring |
| `name[starts_with]=prod` | Case-insensitive literal prefix |
| `created_at[gte]=2026-11-01` | Range (`gt`, `gte`, `lt`, `lte`) |
| `claimed_at[isnull]=true` | Null check |
| `enabled=false` | Typed boolean equality |
| `labels[env]=prod` | Label equality; an empty value tests key existence |

Values in one field/operator group use OR; different groups use AND. Dates use
ISO 8601, with timezone-free filter values interpreted as UTC. Invalid values,
unknown fields, and unsupported operators return 422. Query field metadata and
response models live in [client models](../src/execution_plane_client/models/).

## Credential management

The final credential-management design is unresolved. The following describes
current code only; proposals and tradeoffs belong in the
[active credential discussion](https://github.com/ansible/handbook/pull/1824).

EP stores AO-owned `credential_ref` UUIDs. For Cluster operations that need a
credential, `CredentialResolver` posts `credential.resolve` to
`EP_CREDENTIAL_RESOLUTION_CALLBACK_URL`, routed with the owning Cluster's client
identity. It validates the receipt message ID and typed credential result and
uses the returned value in memory for the operation. EP does not persist that
resolved value. Resolution failure before Execute is a retryable dispatch failure.

Configure `EP_CREDENTIAL_RESOLUTION_CALLBACK_CA_CERT_PATH`,
`EP_CREDENTIAL_RESOLUTION_CALLBACK_CERT_PATH`,
`EP_CREDENTIAL_RESOLUTION_CALLBACK_KEY_PATH`, and
`EP_CREDENTIAL_RESOLUTION_CALLBACK_TIMEOUT_SECONDS` for that callback.
This mechanism does not deliver workload secrets; the SDK adapter currently
supplies an empty credential-file-path map.

## Completion commands

EP persists each work result and its notification state together. The notifier
posts `work.execute.completed` to `EP_COMPLETION_CALLBACK_URL`. Configure
`EP_CALLBACK_CA_CERT_PATH`, `EP_CALLBACK_CERT_PATH`, `EP_CALLBACK_KEY_PATH`,
and `EP_CALLBACK_TIMEOUT_SECONDS` for outbound TLS.

The payload contains `status`, `result`, and a `resource` reference. Status is
`succeeded`, `failed`, `cancelled`, or `outcome_unknown`. `parent_command_id`
is the WorkItem UUID; `occurred_at` is its completion time. The receiver returns
a successful HTTP status with a `TransportReceipt` matching the message ID.
Delivery is at least once, so receivers must deduplicate by WorkItem UUID.
Failed requests and invalid receipts are retried with backoff.

See [execution and recovery](execution.md) for claim fencing, uncertain outcomes,
and cleanup. Sources: [API](../src/execution_plane/api/main.py),
[handlers](../src/execution_plane/commands/),
[contracts](../src/execution_plane_client/commands/), and
[credential resolver](../src/execution_plane/credential_resolution/resolver.py).
