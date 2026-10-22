"""Target CRUD through live AO -> EP HTTP commands, PostgreSQL, and the EP worker.

Run on the dedicated AO+EP E2E stack: default tests temporarily change its default
target. Cleanup restores that target and waits for test targets to drain/delete.
"""

from __future__ import annotations

import os
import time
from typing import TYPE_CHECKING, Any
from uuid import uuid4

import pytest

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

    import httpx
    from conftest import AoClient

pytestmark = [pytest.mark.e2e]
_TARGETS = "/api/execution_plane/v1/execution_targets"
_PRIVATE_FIELDS = {"api_key", "credential", "ca_certificate", "encrypted_api_key"}


def _target(response: httpx.Response, expected_status: int = 200) -> dict[str, Any]:
    assert response.status_code == expected_status, response.text
    target = response.json()
    assert isinstance(target, dict), "Expected a target resource"
    assert target.get("id"), "Expected a target UUID"
    assert not _PRIVATE_FIELDS.intersection(target), "Target response exposed credential fields"
    return target


def _read(ao_client: AoClient, target_id: str) -> dict[str, Any]:
    return _target(ao_client.request("GET", f"{_TARGETS}/{target_id}"))


def _wait_deleted(ao_client: AoClient, target_id: str) -> None:
    deadline = time.monotonic() + float(os.environ.get("E2E_POLL_TIMEOUT", "180"))
    while True:
        response = ao_client.request("GET", f"{_TARGETS}/{target_id}")
        if response.status_code == 404:
            return
        target = _target(response)
        assert target["status"] == "draining", target
        assert target["enabled"] is False, target
        assert time.monotonic() < deadline, f"EP worker did not remove drained target {target_id}"
        time.sleep(float(os.environ.get("E2E_POLL_INTERVAL", "1")))


@pytest.fixture
def targets(ao_client: AoClient) -> Iterator[tuple[dict[str, Any], Callable[..., dict[str, Any]]]]:
    response = ao_client.request("GET", _TARGETS, params={"is_default": "true", "limit": 100})
    assert response.status_code == 200, response.text
    page = response.json()
    assert len(page["resources"]) == 1, "E2E stack must have one installed cluster/default"
    assert not page["next"], "Unexpected additional defaults in the E2E stack"
    original = page["resources"][0]
    assert original["placement"]["type"] == "kubernetes"
    created: list[str] = []

    def create(*, is_default: bool = False) -> dict[str, Any]:
        response = ao_client.request(
            "POST",
            _TARGETS,
            body={
                "name": f"target-e2e-{uuid4().hex[:12]}",
                "placement": {"namespace": original["placement"]["namespace"]},
                "labels": {"test": "target-crud"},
                "is_default": is_default,
            },
        )
        resource = _target(response, 201)
        created.append(resource["id"])
        assert response.headers["location"] == f"{_TARGETS}/{resource['id']}"
        assert resource["cluster_id"] == original["cluster_id"]
        assert resource["is_default"] is is_default
        return resource

    try:
        yield original, create
    finally:
        # Restore first even when a default-protection assertion fails mid-test.
        restored = ao_client.request("PATCH", f"{_TARGETS}/{original['id']}", body={"is_default": True})
        assert _target(restored)["is_default"] is True
        assert _read(ao_client, original["id"])["is_default"] is True
        for target_id in created:
            response = ao_client.request("DELETE", f"{_TARGETS}/{target_id}")
            assert response.status_code in {202, 404}, response.text
            _wait_deleted(ao_client, target_id)


def test_target_crud_persists_placement_and_clears(ao_client: AoClient, targets) -> None:
    original, create = targets
    target = create()
    target_id = target["id"]
    assert _read(ao_client, target_id) == target

    placement = {
        "namespace": "default",
        "node_selectors": ["kubernetes.io/os=linux"],
        "tolerations": ["dedicated=batch:NoSchedule"],
    }
    updated = _target(
        ao_client.request(
            "PATCH",
            f"{_TARGETS}/{target_id}",
            body={"name": f"{target['name']}-updated", "placement": placement, "labels": {"pool": "batch"}},
        )
    )
    persisted = _read(ao_client, target_id)
    assert persisted == updated
    assert persisted["name"] == f"{target['name']}-updated"
    assert persisted["placement"] == {"type": "kubernetes", **placement}
    assert persisted["labels"]["pool"] == "batch"

    cleared = _target(
        ao_client.request(
            "PATCH",
            f"{_TARGETS}/{target_id}",
            body={"placement": {"namespace": original["placement"]["namespace"], "node_selectors": []}, "labels": {}},
        )
    )
    assert cleared["name"] == persisted["name"]
    assert cleared["placement"]["namespace"] == original["placement"]["namespace"]
    assert cleared["placement"]["node_selectors"] == []
    assert cleared["placement"]["tolerations"] == placement["tolerations"]
    assert "pool" not in cleared["labels"]
    assert _read(ao_client, target_id)["placement"] == cleared["placement"]

    response = ao_client.request("GET", _TARGETS, params={"id": target_id, "limit": 1, "include_total": "true"})
    assert response.status_code == 200, response.text
    page = response.json()
    assert [item["id"] for item in page["resources"]] == [target_id]
    assert page["total"] == 1

    deleted = ao_client.request("DELETE", f"{_TARGETS}/{target_id}")
    assert deleted.status_code == 202, deleted.text
    assert deleted.json() == {"id": target_id, "accepted": True}
    _wait_deleted(ao_client, target_id)
    response = ao_client.request("GET", _TARGETS, params={"id": target_id, "include_total": "true"})
    assert response.status_code == 200, response.text
    assert response.json()["resources"] == []
    assert response.json()["total"] == 0


def test_default_promotion_and_protected_deletion(ao_client: AoClient, targets) -> None:
    original, create = targets
    first = create(is_default=True)
    assert _read(ao_client, original["id"])["is_default"] is False
    second = create()
    promoted = _target(ao_client.request("PATCH", f"{_TARGETS}/{second['id']}", body={"is_default": True}))
    assert promoted["is_default"] is True
    assert _read(ao_client, first["id"])["is_default"] is False
    assert _read(ao_client, second["id"])["is_default"] is True

    for method, body in [("DELETE", None), ("PATCH", {"is_default": False})]:
        response = ao_client.request(method, f"{_TARGETS}/{second['id']}", body=body)
        assert response.status_code == 409, response.text
        assert _read(ao_client, second["id"])["is_default"] is True

    page = ao_client.request("GET", _TARGETS, params={"is_default": "true"})
    assert page.status_code == 200, page.text
    assert [target["id"] for target in page.json()["resources"]] == [second["id"]]


def test_workflow_uses_new_target_and_fails_after_its_deletion(ao_client: AoClient, targets) -> None:
    original, create = targets
    target = create()
    assert target["is_default"] is False
    marker = f"target-workflow-{uuid4().hex[:12]}"
    definition = {
        "name": marker,
        "schema_version": "2.0.0",
        "triggers": [{"id": "trigger", "type": "manual_trigger", "parameters": {}}],
        "nodes": [
            {
                "id": "script_node",
                "name": "Use newly created target",
                "type": "script",
                "parameters": {
                    "language": "bash",
                    "code": f"printf '%s\\n' '{marker}'",
                    "execution_profile": {"type": "execution_target", "execution_target_id": target["id"]},
                },
            }
        ],
        "edges": [{"from": "trigger", "to": "script_node"}],
    }
    workflow = ao_client.create_workflow(
        {
            "name": marker,
            "project_id": ao_client.default_project_id(),
            "workflow_definition": definition,
        }
    )
    try:
        execution = ao_client.create_execution(workflow["id"])
        completed = ao_client.poll_execution(execution["id"])
        script = next(item for item in completed["activities"] if item["activity_id"] == "script_node")
        assert script["status"] == "completed"
        output = script["output_data"]
        stdout = output.get("stdout", output.get("output", {}).get("stdout", ""))
        assert marker in stdout, "Expected real script output returned through the EP callback"

        deleted = ao_client.request("DELETE", f"{_TARGETS}/{target['id']}")
        assert deleted.status_code == 202, deleted.text
        _wait_deleted(ao_client, target["id"])
        assert _read(ao_client, original["id"])["is_default"] is True

        # A successful second run would mean the profile was ignored or fell back.
        execution = ao_client.create_execution(workflow["id"])
        failed = ao_client.poll_execution(execution["id"], expected_status="failed")
        script = next(item for item in failed["activities"] if item["activity_id"] == "script_node")
        assert script["status"] == "failed"
        assert "No execution target matched placement requirements" in script["error_details"]
    finally:
        response = ao_client.request("DELETE", f"/api/v1/workflows/{workflow['id']}")
        assert response.status_code == 204, response.text


@pytest.mark.parametrize("method", ["GET", "PATCH", "DELETE"])
def test_missing_target_returns_not_found(ao_client: AoClient, method: str) -> None:
    body = {"name": "missing-target"} if method == "PATCH" else None
    response = ao_client.request(method, f"{_TARGETS}/{uuid4()}", body=body)
    assert response.status_code == 404, response.text
