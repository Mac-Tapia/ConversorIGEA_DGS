from pathlib import Path

from fastapi.testclient import TestClient

from igea_dgs.web.app import create_app


def test_health_is_token_protected_and_versioned(tmp_path: Path) -> None:
    app = create_app(project_root=tmp_path, session_token="secret")
    response = TestClient(app).get(
        "/api/health", headers={"X-Session-Token": "secret"}
    )
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "api_version": "1"}


def test_missing_session_token_is_rejected(tmp_path: Path) -> None:
    app = create_app(project_root=tmp_path, session_token="secret")
    response = TestClient(app).get("/api/health")
    assert response.status_code == 401
    assert response.json()["code"] == "INVALID_SESSION_TOKEN"
