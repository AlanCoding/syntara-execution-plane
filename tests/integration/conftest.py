"""Fixtures for execution-plane integration tests.

Tests in this package require a real PostgreSQL database. Set
``EP_TEST_DATABASE_URL`` to a disposable asyncpg-compatible URL before running.

Cluster dispatch tests additionally need a live Kubernetes cluster exported via:

* ``EP_IT_K8S_ENDPOINT``  — API server URL (e.g. ``https://127.0.0.1:PORT``)
* ``EP_IT_K8S_TOKEN``     — bearer token for the ``syntara-dispatcher`` ServiceAccount
* ``EP_IT_K8S_NAMESPACE`` — target namespace (default: ``execution-plane``)
* ``EP_IT_K8S_CA_CERT``   — PEM CA certificate for the API server (optional; skips
                            TLS verification when absent and ``verify_ssl`` is False)

The CI ``test-integration`` job provisions a kind cluster and exports all of these.
Local developers can point at any running cluster that satisfies the RBAC in
``docs/feature-branch-assets/execution-plane-init.yaml``.
"""

from __future__ import annotations

import os
import subprocess
import uuid
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Generator

from execution_plane.cluster.cluster_registry import ClusterRegistry, NoopDiscoveryMechanism
from execution_plane.cluster.cluster_store import ClusterStore
from execution_plane.config import get_ep_settings
from execution_plane.execution_target.execution_target_registry import ExecutionTargetRegistry
from execution_plane.execution_target.execution_target_store import ExecutionTargetStore
from execution_plane.models.cluster import Cluster, ClusterType
from execution_plane.models.execution_target_placement import KubernetesPlacement

_EP_IT_ENDPOINT = "EP_IT_K8S_ENDPOINT"
_EP_IT_TOKEN = "EP_IT_K8S_TOKEN"  # noqa: S105 — env var name, not a secret value
_EP_IT_NAMESPACE = "EP_IT_K8S_NAMESPACE"
_EP_IT_CA_CERT = "EP_IT_K8S_CA_CERT"
_DEFAULT_NAMESPACE = "execution-plane"
_CLUSTER_NAME = "integration-test"
_CLI_ACTOR_ID = uuid.UUID(int=0)
_REPO_ROOT = Path(__file__).resolve().parents[2]


def ep_cluster_configured() -> bool:
    """Return True when kind cluster coordinates are present in the environment."""
    return bool(os.environ.get(_EP_IT_ENDPOINT) and os.environ.get(_EP_IT_TOKEN))


@pytest.fixture(autouse=True)
def _integration_database_env(monkeypatch: pytest.MonkeyPatch) -> Generator[None, None, None]:
    """Override EP_DATABASE_URL with the real test DB for integration tests.

    The root conftest sets EP_DATABASE_URL to a dummy value for unit tests.
    This fixture runs after it (closer-conftest fixtures take priority) and
    re-points the setting at the disposable integration database so that
    get_ep_settings() returns usable credentials during each test function.
    """
    database_url = os.environ.get("EP_TEST_DATABASE_URL")
    if database_url:
        monkeypatch.setenv("EP_DATABASE_URL", database_url)
        get_ep_settings.cache_clear()
    yield
    get_ep_settings.cache_clear()


@pytest.fixture(scope="session")
def integration_database_url() -> str:
    """Return the disposable PostgreSQL URL, or skip the session if absent."""
    url = os.environ.get("EP_TEST_DATABASE_URL")
    if not url:
        pytest.skip("EP_TEST_DATABASE_URL must be set for integration tests")
    return url


@pytest.fixture(scope="session")
def migrated_database(integration_database_url: str) -> str:
    """Run alembic migrations against the test database and return the URL."""
    env = {**os.environ, "DATABASE_URL": integration_database_url}
    subprocess.run(
        ["uv", "run", "alembic", "-c", "alembic.ini", "upgrade", "head"],
        check=True,
        env=env,
        cwd=_REPO_ROOT,
    )
    return integration_database_url


@pytest.fixture(scope="session")
async def ep_cluster(migrated_database: str) -> AsyncGenerator[Cluster, None]:
    """Provision a kind cluster as an ACTIVE Cluster+ExecutionTarget in the test DB.

    Skips when ``EP_IT_K8S_ENDPOINT`` / ``EP_IT_K8S_TOKEN`` are absent so that
    the PostgreSQL-only tests still run on runners without a cluster.

    Yields the provisioned ``Cluster`` and tears it down at the end of the session.
    """
    if not ep_cluster_configured():
        pytest.skip("EP_IT_K8S_ENDPOINT and EP_IT_K8S_TOKEN must be set for cluster dispatch tests")

    endpoint = os.environ[_EP_IT_ENDPOINT]
    token = os.environ[_EP_IT_TOKEN]
    namespace = os.environ.get(_EP_IT_NAMESPACE, _DEFAULT_NAMESPACE)
    ca_cert = os.environ.get(_EP_IT_CA_CERT)

    cluster_store = ClusterStore.from_database_url(migrated_database)
    target_store = ExecutionTargetStore.from_database_url(migrated_database)

    cluster: Cluster | None = None
    try:
        target_registry = ExecutionTargetRegistry(target_store)
        cluster_registry = ClusterRegistry(cluster_store, target_registry, NoopDiscoveryMechanism())

        cluster = await cluster_registry.provision(
            _CLUSTER_NAME,
            endpoint,
            token,
            KubernetesPlacement(namespace=namespace),
            _CLI_ACTOR_ID,
            labels={"provider": "kind", "cluster": _CLUSTER_NAME},
            cluster_type=ClusterType.OPENSHIFT,
        )

        if ca_cert:
            cluster = await cluster_store.update(
                cluster.id,
                updated_by=_CLI_ACTOR_ID,
                ca_certificate=ca_cert,
            )

        yield cluster

    finally:
        if cluster is not None:
            await cluster_store.request_delete(cluster.id, _CLI_ACTOR_ID)
            for target in await target_store.list(cluster_id=cluster.id):
                await target_store.finalize_delete(target.id)
            await cluster_store.finalize_delete(cluster.id)
        await cluster_store.close()
        await target_store.close()
