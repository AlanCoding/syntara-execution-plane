"""TDD tests for sort support on /v1/work-items.

These tests are written BEFORE sort is implemented.  They intentionally fail
until the query layer maps the ``sort`` parameter to a real ORDER BY clause.

Module-level fixtures insert 30 work items once; all test functions in this
module share that data to avoid repeated DB round-trips.

Data layout (items are numbered 0-29, created_at 0s-29s after base):
  Items  0- 9  status=completed  resource_cleanup_status=done
  Items 10-19  status=failed     resource_cleanup_status=done
  Items 20-29  status=pending    resource_cleanup_status=pending

Expected sort orders:
  sort=created_at   → ascending created_at  (item 0 first)
  sort=-created_at  → descending created_at (item 29 first)  ← EP default
  sort=status       → alphabetical: completed < failed < pending
  sort=-status      → reverse: pending > failed > completed
  sort=resource_cleanup_status → "done" (items 0-19) before "pending" (20-29)
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import httpx
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from execution_plane.api.auth import ServiceIdentity, get_service_identity
from execution_plane.api.main import create_app
from execution_plane.models.work_item import WorkItem, WorkItemStatus

pytestmark = pytest.mark.integration

_BASE_TIME = datetime(2025, 6, 1, 12, 0, 0, tzinfo=UTC)

# Status groups — alphabetical order is: completed < failed < pending
_GROUPS = [
    (WorkItemStatus.COMPLETED, "done"),
    (WorkItemStatus.FAILED, "done"),
    (WorkItemStatus.PENDING, "pending"),
]
ITEMS_PER_GROUP = 10
TOTAL_ITEMS = ITEMS_PER_GROUP * len(_GROUPS)  # 30


@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def shared_data(migrated_database):
    """Insert 30 work items once for the whole module; yield (client_id, db_url).

    The engine is disposed before yielding so no asyncio resources from the
    module-scoped event loop bleed into function-scoped test fixtures.
    """
    client_id = f"test-sort-{uuid.uuid4()}"
    engine = create_async_engine(migrated_database)
    sessions = async_sessionmaker(engine, expire_on_commit=False)

    async with sessions() as session:
        for group_index, (status, cleanup_status) in enumerate(_GROUPS):
            for i in range(ITEMS_PER_GROUP):
                item_index = group_index * ITEMS_PER_GROUP + i
                session.add(
                    WorkItem(
                        id=uuid.uuid4(),
                        client_id=client_id,
                        status=status,
                        payload={"index": item_index},
                        resource_cleanup_status=cleanup_status,
                        created_at=_BASE_TIME + timedelta(seconds=item_index),
                    )
                )
        await session.commit()

    await engine.dispose()
    yield client_id, migrated_database


@pytest.fixture
async def sort_client(shared_data):
    """Function-scoped HTTP client; creates a fresh engine per test."""
    client_id, db_url = shared_data
    engine = create_async_engine(db_url)
    app = create_app()
    app.state.ep_engine = engine
    app.state.ep_session_factory = async_sessionmaker(engine, expire_on_commit=False)
    app.dependency_overrides[get_service_identity] = lambda: ServiceIdentity(
        client_id=client_id,
        scopes=frozenset({"work-items:read"}),
    )
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://ep.test") as client:
        yield client
    await engine.dispose()


async def _all_items(client, sort: str, limit: int = 100) -> list[dict]:
    """Fetch all work items for the given sort in one request."""
    response = await client.get("/v1/work-items", params={"limit": limit, "sort": sort})
    assert response.status_code == 200, response.text
    return response.json()["resources"]


async def _paginate_all(client, sort: str, page_size: int = 7) -> list[dict]:
    """Walk all pages for the given sort and return the full ordered list."""
    items: list[dict] = []
    cursor = None
    for _ in range(TOTAL_ITEMS + 5):  # safety ceiling
        params: dict = {"limit": page_size, "sort": sort}
        if cursor:
            params["cursor"] = cursor
        body = (await client.get("/v1/work-items", params=params)).json()
        items.extend(body["resources"])
        cursor = body.get("next")
        if cursor is None:
            break
    return items


# ---------------------------------------------------------------------------
# sort=created_at  (ascending — opposite of EP's current DESC default)
# ---------------------------------------------------------------------------


async def test_sort_created_at_asc_first_item_is_oldest(sort_client):
    """sort=created_at returns the oldest item first."""
    items = await _all_items(sort_client, sort="created_at")
    assert len(items) == TOTAL_ITEMS
    created_ats = [item["created_at"] for item in items]
    assert created_ats == sorted(created_ats), "items must be in ascending created_at order"


async def test_sort_created_at_asc_is_opposite_of_desc(sort_client):
    """Ascending sort is the reverse of descending sort."""
    asc_items = await _all_items(sort_client, sort="created_at")
    desc_items = await _all_items(sort_client, sort="-created_at")
    assert [i["id"] for i in asc_items] == [i["id"] for i in reversed(desc_items)]


# ---------------------------------------------------------------------------
# sort=-created_at  (descending — matches EP's current hard-coded default)
# ---------------------------------------------------------------------------


async def test_sort_created_at_desc_first_item_is_newest(sort_client):
    """sort=-created_at returns the newest item first."""
    items = await _all_items(sort_client, sort="-created_at")
    assert len(items) == TOTAL_ITEMS
    created_ats = [item["created_at"] for item in items]
    assert created_ats == sorted(created_ats, reverse=True)


async def test_sort_created_at_desc_pagination_covers_all_items(sort_client):
    """Paginating with sort=-created_at yields every item exactly once."""
    items = await _paginate_all(sort_client, sort="-created_at", page_size=7)
    assert len(items) == TOTAL_ITEMS
    assert len({i["id"] for i in items}) == TOTAL_ITEMS, "no duplicate items across pages"
    created_ats = [item["created_at"] for item in items]
    assert created_ats == sorted(created_ats, reverse=True)


# ---------------------------------------------------------------------------
# sort=status  (ascending alphabetical: completed < failed < pending)
# ---------------------------------------------------------------------------


async def test_sort_status_asc_order(sort_client):
    """sort=status returns items grouped alphabetically: completed, failed, pending."""
    items = await _all_items(sort_client, sort="status")
    assert len(items) == TOTAL_ITEMS
    statuses = [item["status"] for item in items]
    assert statuses == sorted(statuses), "items must be in ascending status order"
    # The first ITEMS_PER_GROUP must all be 'completed'
    assert all(s == "completed" for s in statuses[:ITEMS_PER_GROUP])
    assert all(s == "failed" for s in statuses[ITEMS_PER_GROUP : ITEMS_PER_GROUP * 2])
    assert all(s == "pending" for s in statuses[ITEMS_PER_GROUP * 2 :])


async def test_sort_status_asc_pagination_covers_all_items(sort_client):
    """Paginating with sort=status yields every item exactly once in status order."""
    items = await _paginate_all(sort_client, sort="status", page_size=7)
    assert len(items) == TOTAL_ITEMS
    assert len({i["id"] for i in items}) == TOTAL_ITEMS, "no duplicate items across pages"
    statuses = [item["status"] for item in items]
    assert statuses == sorted(statuses)


async def test_sort_status_desc_order(sort_client):
    """sort=-status returns items in reverse alphabetical status order."""
    items = await _all_items(sort_client, sort="-status")
    assert len(items) == TOTAL_ITEMS
    statuses = [item["status"] for item in items]
    assert statuses == sorted(statuses, reverse=True)


# ---------------------------------------------------------------------------
# sort=resource_cleanup_status  (string field: "done" < "pending" alphabetically)
# ---------------------------------------------------------------------------


async def test_sort_resource_cleanup_status_asc(sort_client):
    """sort=resource_cleanup_status returns 'done' items before 'pending' items."""
    items = await _all_items(sort_client, sort="resource_cleanup_status")
    assert len(items) == TOTAL_ITEMS
    cleanup_statuses = [item["resource_cleanup_status"] for item in items]
    assert cleanup_statuses == sorted(cleanup_statuses)
    # First 20 items have cleanup_status='done', last 10 have 'pending'
    assert all(s == "done" for s in cleanup_statuses[: ITEMS_PER_GROUP * 2])
    assert all(s == "pending" for s in cleanup_statuses[ITEMS_PER_GROUP * 2 :])
