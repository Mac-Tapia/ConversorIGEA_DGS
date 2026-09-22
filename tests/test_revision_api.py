from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi.testclient import TestClient
from hypothesis import given
from hypothesis import strategies as st

from igea_dgs.revisions import ChangeOperation, RevisionStore
from igea_dgs.web import create_app

TOKEN = {"X-Session-Token": "secret"}


def _update(before: int, after: int) -> ChangeOperation:
    return ChangeOperation.request(
        action="update",
        target_type="lines",
        target_id="L1",
        field="circuits",
        before=before,
        after=after,
        justification="Corrección respaldada por TXT",
        unit="count",
    )


def test_change_is_append_only_and_undo_adds_inverse(tmp_path: Path) -> None:
    store = RevisionStore(tmp_path)
    revision_id = store.create({"lines": {"L1": {"circuits": 1}}}).revision_id

    first = store.append(revision_id, 0, _update(1, 2))
    undone = store.undo(revision_id, first.operation_id, expected_version=1)

    assert undone.sequence == 2
    assert store.read_log(revision_id) == [first, undone]
    assert store.snapshot(revision_id).state["lines"]["L1"]["circuits"] == 1


def test_stale_browser_revision_returns_conflict(tmp_path: Path) -> None:
    client = TestClient(create_app(project_root=tmp_path, session_token="secret"))
    created = client.post(
        "/api/revisions", headers=TOKEN, json={"initial_state": {"lines": {"L1": {"circuits": 1}}}}
    )
    revision_id = created.json()["revision_id"]
    operation = {
        "expected_version": 0,
        "action": "update",
        "target_type": "lines",
        "target_id": "L1",
        "field": "circuits",
        "before": 1,
        "after": 2,
        "justification": "Dato confirmado",
        "unit": "count",
    }
    assert client.post(f"/api/revisions/{revision_id}/operations", headers=TOKEN, json=operation).status_code == 201
    operation["after"] = 3
    response = client.post(
        f"/api/revisions/{revision_id}/operations", headers=TOKEN, json=operation
    )
    assert response.status_code == 409
    assert response.json()["code"] == "REVISION_VERSION_CONFLICT"


def test_invalid_operation_does_not_change_log_or_version(tmp_path: Path) -> None:
    store = RevisionStore(tmp_path)
    revision_id = store.create({"lines": {"L1": {"circuits": 1}}}).revision_id
    invalid = _update(99, 2)

    try:
        store.append(revision_id, 0, invalid)
    except ValueError as exc:
        assert "OPERATION_BEFORE_MISMATCH" in str(exc)
    else:
        raise AssertionError("La operación inválida fue aceptada")
    assert store.read_log(revision_id) == []
    assert store.snapshot(revision_id).version == 0


@given(st.integers(min_value=1, max_value=99), st.integers(min_value=100, max_value=999))
def test_operation_plus_inverse_preserves_snapshot(before: int, after: int) -> None:
    with TemporaryDirectory() as directory:
        store = RevisionStore(Path(directory))
        revision_id = store.create({"lines": {"L1": {"circuits": before}}}).revision_id
        first = store.append(revision_id, 0, _update(before, after))
        store.undo(revision_id, first.operation_id, expected_version=1)
        assert store.snapshot(revision_id).state["lines"]["L1"]["circuits"] == before
