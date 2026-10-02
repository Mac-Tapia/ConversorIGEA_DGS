from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from igea_dgs.web import create_app


TOKEN = {"X-Session-Token": "secret"}


def _registered_project(tmp_path: Path, client: TestClient) -> tuple[str, str, Path]:
    red = tmp_path / "RED_BAD.txt"
    carga = tmp_path / "CARGA_BAD.txt"
    equipment = tmp_path / "BD_Equipo.txt"
    red.write_text("[MYSTERY]\nFORMAT_X=A\n1\n", encoding="utf-8")
    carga.write_text("[LOADS]\nFORMAT_LOADS=SectionID,DeviceNumber\n", encoding="utf-8")
    equipment.write_text("[CONDUCTOR]\nFORMAT_C=Code\n", encoding="utf-8")
    project = client.post("/api/projects", headers=TOKEN, json={"name": "strict"}).json()
    response = client.post(
        f"/api/projects/{project['id']}/inputs",
        headers=TOKEN,
        json={
            "red_path": str(red),
            "carga_path": str(carga),
            "equipment_path": str(equipment),
            "output_dir": str(tmp_path / "out"),
            "crs": "EPSG:32718",
        },
    )
    assert response.status_code == 201
    revision = client.post(
        "/api/revisions", headers=TOKEN, json={"initial_state": {}}
    ).json()
    return project["id"], revision["revision_id"], tmp_path / "out"


def test_web_pipeline_stops_at_g1_and_publishes_nothing(tmp_path: Path) -> None:
    client = TestClient(create_app(project_root=tmp_path, session_token="secret"))
    project_id, revision_id, output = _registered_project(tmp_path, client)
    response = client.post(
        f"/api/projects/{project_id}/pipeline/validate/{revision_id}", headers=TOKEN
    )
    assert response.status_code == 200
    body = response.json()
    assert body["exit_code"] == 2
    assert body["last_gate"] == "G1"
    assert not output.exists()


def test_web_modules_do_not_import_legacy_batch() -> None:
    for path in Path("src/igea_dgs/web").rglob("*.py"):
        assert "igea_dgs.batch" not in path.read_text(encoding="utf-8")
