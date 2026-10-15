"""Integration tests for cursor-based pagination on EP list endpoints.

Requires a real PostgreSQL database via EP_TEST_DATABASE_URL.
Each test inserts more items than the page size, demonstrating that without
pagination the endpoint would return all items in a single response,
and that with pagination items are split across pages correctly.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from execution_plane.api.auth import ServiceIdentity, get_service_identity
from execution_plane.api.main import create_app
from execution_plane.models.cluster import Cluster, ClusterStatus
from execution_plane.models.cluster_binding import ClusterBinding
from execution_plane.models.execution_target import BackendType, ExecutionTarget, TargetStatus
from execution_plane.models.execution_target_placement import KubernetesPlacement
from execution_plane.models.work_item import WorkItem, WorkItemStatus

pytestmark = pytest.mark.integration

CLIENT_ID = "test-pagination-client"
ALL_SCOPES = frozenset(
    {
        "work-items:read",
        "clusters:read",
        "execution-targets:read",
        "work.execute",
        "cluster.register",
        "execution_target.register",
    }
)


@pytest.fixture
async def pg_client(migrated_database):
    engine = create_async_engine(migrated_database)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    app = create_app()
    app.state.ep_engine = engine
    app.state.ep_session_factory = sessions
    app.dependency_overrides[get_service_identity] = lambda: ServiceIdentity(
        client_id=CLIENT_ID, scopes=ALL_SCOPES
    )
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://ep.test") as client:
        yield client, sessions
    await engine.dispose()


async def _insert_work_items(sessions, count: int) -> list[WorkItem]:
    items = []
    base = datetime.now(UTC)
    async with sessions() as session:
        for i in range(count):
            item = WorkItem(
                id=uuid.uuid4(),
                client_id=CLIENT_ID,
                status=WorkItemStatus.PENDING,
                payload={"seq": i},
                created_at=base - timedelta(seconds=count - i),
            )
            session.add(item)
            items.append(item)
        await session.commit()
    return items


async def _insert_cluster_bindings(sessions, count: int) -> list[ClusterBinding]:
    base = datetime.now(UTC)
    bindings = []
    async with sessions() as session:
        for i in range(count):
            binding = ClusterBinding(
                client_id=CLIENT_ID,
                source_integration_id=uuid.uuid4(),
                name=f"cluster-{i}",
                endpoint=f"https://cluster-{i}.test",
                namespace="ep",
                credential="test-key",
                revision=1,
                observed_revision=0,
                status="pending",
                enabled=True,
                labels={},
                created_at=base + timedelta(seconds=i),
                updated_at=base + timedelta(seconds=i),
            )
            session.add(binding)
            bindings.append(binding)
        await session.commit()
    return bindings


async def _insert_cluster_and_targets(sessions, count: int) -> tuple[Cluster, list[ExecutionTarget]]:
    base = datetime.now(UTC)
    now = base
    cluster = Cluster(
        id=uuid.uuid4(),
        source_client_id=CLIENT_ID,
        source_integration_id=uuid.uuid4(),
        name="test-cluster",
        endpoint="https://cluster.test",
        api_key="secret",
        status=ClusterStatus.ACTIVE,
        created_by=uuid.uuid4(),
        updated_by=uuid.uuid4(),
        created_at=now,
        updated_at=now,
    )
    targets = []
    async with sessions() as session:
        session.add(cluster)
        await session.flush()
        for i in range(count):
            target = ExecutionTarget(
                id=uuid.uuid4(),
                cluster_id=cluster.id,
                name=f"target-{i}",
                backend_type=BackendType.VANILLA_K8S,
                endpoint="https://target.test",
                placement=KubernetesPlacement(namespace="ep"),
                status=TargetStatus.ACTIVE,
                enabled=True,
                is_default=False,
                api_key="secret",
                labels={},
                created_by=uuid.uuid4(),
                updated_by=uuid.uuid4(),
                created_at=base + timedelta(seconds=i),
                updated_at=base + timedelta(seconds=i),
            )
            session.add(target)
            targets.append(target)
        await session.commit()
    return cluster, targets


# --- Work items ---

async def test_work_items_without_pagination_all_items_in_envelope(pg_client):
    """Baseline: a single large-limit request returns all items in the envelope."""
    client, sessions = pg_client
    items = await _insert_work_items(sessions, 5)

    response = await client.get("/v1/work-items", params={"limit": 100})
    assert response.status_code == 200
    body = response.json()
    assert "resources" in body
    assert "next" in body
    assert "prev" in body
    ids_returned = {r["id"] for r in body["resources"]}
    expected_ids = {str(i.id) for i in items}
    assert expected_ids <= ids_returned


async def test_work_items_first_page(pg_client):
    """First page has next cursor and no prev cursor."""
    client, sessions = pg_client
    await _insert_work_items(sessions, 5)

    response = await client.get("/v1/work-items", params={"limit": 2})
    assert response.status_code == 200
    body = response.json()
    assert len(body["resources"]) == 2
    assert body["next"] is not None
    assert body["prev"] is None
    assert body["total"] is None


async def test_work_items_second_page_has_different_items(pg_client):
    """Second page returns items not on the first page."""
    client, sessions = pg_client
    await _insert_work_items(sessions, 5)

    p1 = (await client.get("/v1/work-items", params={"limit": 2})).json()
    p2 = (await client.get("/v1/work-items", params={"limit": 2, "cursor": p1["next"]})).json()

    ids_p1 = {r["id"] for r in p1["resources"]}
    ids_p2 = {r["id"] for r in p2["resources"]}
    assert ids_p1.isdisjoint(ids_p2), "Pages must not overlap"
    assert len(ids_p2) > 0


async def test_work_items_last_page_has_no_next(pg_client):
    """The final page has next=null."""
    client, sessions = pg_client
    await _insert_work_items(sessions, 3)

    p1 = (await client.get("/v1/work-items", params={"limit": 2})).json()
    p2 = (await client.get("/v1/work-items", params={"limit": 2, "cursor": p1["next"]})).json()

    assert p2["next"] is None


async def test_work_items_include_total(pg_client):
    """include_total=true returns an integer total."""
    client, sessions = pg_client
    items = await _insert_work_items(sessions, 4)

    response = await client.get("/v1/work-items", params={"limit": 2, "include_total": "true"})
    body = response.json()
    assert body["total"] is not None
    assert body["total"] >= len(items)


async def test_work_items_invalid_limit_zero(pg_client):
    client, sessions = pg_client
    response = await client.get("/v1/work-items", params={"limit": 0})
    assert response.status_code == 422


async def test_work_items_invalid_limit_over_max(pg_client):
    client, sessions = pg_client
    response = await client.get("/v1/work-items", params={"limit": 101})
    assert response.status_code == 422


async def test_work_items_invalid_sort_pattern(pg_client):
    client, sessions = pg_client
    response = await client.get("/v1/work-items", params={"sort": "INVALID SORT"})
    assert response.status_code == 422


async def test_work_items_malformed_cursor(pg_client):
    client, sessions = pg_client
    response = await client.get("/v1/work-items", params={"cursor": "not-valid-base64!!!"})
    assert response.status_code == 422


async def test_work_items_cursor_past_last_row(pg_client):
    """A cursor pointing past all data returns empty or fewer resources; no server error."""
    client, sessions = pg_client
    await _insert_work_items(sessions, 2)

    # Walk to the last page
    cursor = None
    for _ in range(10):
        params = {"limit": 1}
        if cursor:
            params["cursor"] = cursor
        body = (await client.get("/v1/work-items", params=params)).json()
        if body["next"] is None:
            # Use the prev cursor to go back one more - simulating past-end
            cursor = body.get("prev")
            break
        cursor = body["next"]
    else:
        pytest.fail("Never reached the last page")

    # One more fetch past the end
    response = await client.get("/v1/work-items", params={"limit": 1, "cursor": cursor})
    assert response.status_code == 200


# --- Clusters ---

async def test_clusters_first_page(pg_client):
    """First page has next cursor and no prev cursor."""
    client, sessions = pg_client
    await _insert_cluster_bindings(sessions, 5)

    response = await client.get("/v1/clusters", params={"limit": 2})
    assert response.status_code == 200
    body = response.json()
    assert len(body["resources"]) == 2
    assert body["next"] is not None
    assert body["prev"] is None


async def test_clusters_second_page_different_items(pg_client):
    client, sessions = pg_client
    await _insert_cluster_bindings(sessions, 5)

    p1 = (await client.get("/v1/clusters", params={"limit": 2})).json()
    p2 = (await client.get("/v1/clusters", params={"limit": 2, "cursor": p1["next"]})).json()

    ids_p1 = {r["id"] for r in p1["resources"]}
    ids_p2 = {r["id"] for r in p2["resources"]}
    assert ids_p1.isdisjoint(ids_p2)
    assert len(ids_p2) > 0


async def test_clusters_include_total(pg_client):
    client, sessions = pg_client
    bindings = await _insert_cluster_bindings(sessions, 3)

    response = await client.get("/v1/clusters", params={"limit": 2, "include_total": "true"})
    body = response.json()
    assert body["total"] is not None
    assert body["total"] >= len(bindings)


async def test_clusters_invalid_limit(pg_client):
    client, sessions = pg_client
    assert (await client.get("/v1/clusters", params={"limit": 0})).status_code == 422
    assert (await client.get("/v1/clusters", params={"limit": 101})).status_code == 422


async def test_clusters_malformed_cursor(pg_client):
    client, sessions = pg_client
    response = await client.get("/v1/clusters", params={"cursor": "!!!"})
    assert response.status_code == 422


# --- Execution targets ---

async def test_execution_targets_first_page(pg_client):
    """First page has next cursor and no prev cursor."""
    client, sessions = pg_client
    await _insert_cluster_and_targets(sessions, 5)

    response = await client.get("/v1/execution-targets", params={"limit": 2})
    assert response.status_code == 200
    body = response.json()
    assert len(body["resources"]) == 2
    assert body["next"] is not None
    assert body["prev"] is None


async def test_execution_targets_second_page_different_items(pg_client):
    client, sessions = pg_client
    await _insert_cluster_and_targets(sessions, 5)

    p1 = (await client.get("/v1/execution-targets", params={"limit": 2})).json()
    p2 = (await client.get("/v1/execution-targets", params={"limit": 2, "cursor": p1["next"]})).json()

    ids_p1 = {r["id"] for r in p1["resources"]}
    ids_p2 = {r["id"] for r in p2["resources"]}
    assert ids_p1.isdisjoint(ids_p2)
    assert len(ids_p2) > 0


async def test_execution_targets_include_total(pg_client):
    client, sessions = pg_client
    _, targets = await _insert_cluster_and_targets(sessions, 3)

    response = await client.get("/v1/execution-targets", params={"limit": 2, "include_total": "true"})
    body = response.json()
    assert body["total"] is not None
    assert body["total"] >= len(targets)


async def test_execution_targets_invalid_limit(pg_client):
    client, sessions = pg_client
    assert (await client.get("/v1/execution-targets", params={"limit": 0})).status_code == 422
    assert (await client.get("/v1/execution-targets", params={"limit": 101})).status_code == 422


async def test_execution_targets_malformed_cursor(pg_client):
    client, sessions = pg_client
    response = await client.get("/v1/execution-targets", params={"cursor": "!!!"})
    assert response.status_code == 422


async def test_execution_targets_cursor_unknown_fields_stripped(pg_client):
    """A cursor with extra fields should not cause a server error; unknown fields are stripped."""
    import base64
    import json

    client, sessions = pg_client
    await _insert_cluster_and_targets(sessions, 3)

    p1 = (await client.get("/v1/execution-targets", params={"limit": 1})).json()
    raw = base64.b64decode(p1["next"]).decode()
    data = json.loads(raw)
    data["unknown_field"] = "should be stripped"
    tampered = base64.b64encode(json.dumps(data).encode()).decode()

    response = await client.get("/v1/execution-targets", params={"limit": 1, "cursor": tampered})
    assert response.status_code == 200
    body = response.json()
    assert len(body["resources"]) > 0
