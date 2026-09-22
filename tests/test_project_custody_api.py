from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from igea_dgs.projects.inputs import InputResolutionError, detect_input_set
from igea_dgs.web import create_app

TOKEN = {"X-Session-Token": "secret"}


def _triplet(folder: Path) -> tuple[Path, Path, Path]:
    paths = (
        folder / "RED_ALIMENTADOR.txt",
        folder / "CARGA_ALIMENTADOR.txt",
        folder / "BD_Equipo.txt",
    )
    for index, path in enumerate(paths):
        path.write_text(f"original-{index}\n", encoding="utf-8")
    return paths


def test_register_inputs_hashes_without_modifying_originals(tmp_path: Path) -> None:
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    red, carga, equipment = _triplet(inputs)
    output = tmp_path / "outputs"
    before = {path: path.read_bytes() for path in (red, carga, equipment)}
    client = TestClient(create_app(project_root=tmp_path, session_token="secret"))

    created = client.post("/api/projects", headers=TOKEN, json={"name": "PA-001"})
    assert created.status_code == 201
    project_id = created.json()["id"]
    response = client.post(
        f"/api/projects/{project_id}/inputs",
        headers=TOKEN,
        json={
            "red_path": str(red),
            "carga_path": str(carga),
            "equipment_path": str(equipment),
            "output_dir": str(output),
            "crs": "EPSG:32718",
        },
    )

    assert response.status_code == 201
    assert all(len(item["sha256"]) == 64 for item in response.json()["files"])
    assert {path: path.read_bytes() for path in (red, carga, equipment)} == before
    assert not output.exists(), "registrar entradas no debe crear ni modificar salidas"


def test_folder_with_two_red_candidates_blocks(tmp_path: Path) -> None:
    _triplet(tmp_path)
    (tmp_path / "RED_COPY.txt").write_text("duplicate", encoding="utf-8")

    try:
        detect_input_set(tmp_path)
    except InputResolutionError as exc:
        assert exc.code == "INPUT_FILE_AMBIGUOUS"
        assert exc.kind == "red"
    else:
        raise AssertionError("La carpeta ambigua no fue bloqueada")

    client = TestClient(create_app(project_root=tmp_path, session_token="secret"))
    response = client.post(
        "/api/projects/detect-inputs", headers=TOKEN, json={"folder": str(tmp_path)}
    )
    assert response.status_code == 422
    assert response.json()["code"] == "INPUT_FILE_AMBIGUOUS"


def test_missing_candidate_blocks_and_unknown_project_is_not_registered(tmp_path: Path) -> None:
    (tmp_path / "RED_A.txt").write_text("red", encoding="utf-8")
    client = TestClient(create_app(project_root=tmp_path, session_token="secret"))

    detected = client.post(
        "/api/projects/detect-inputs", headers=TOKEN, json={"folder": str(tmp_path)}
    )
    assert detected.status_code == 422
    assert detected.json()["code"] == "INPUT_TXT_MISSING"

    response = client.post(
        "/api/projects/does-not-exist/inputs",
        headers=TOKEN,
        json={
            "red_path": str(tmp_path / "RED_A.txt"),
            "carga_path": str(tmp_path / "missing.txt"),
            "equipment_path": str(tmp_path / "missing2.txt"),
            "output_dir": str(tmp_path / "out"),
            "crs": "EPSG:32718",
        },
    )
    assert response.status_code == 404


class CancelDialog:
    def select_file(self, patterns: tuple[str, ...]) -> Path | None:
        return None

    def select_folder(self) -> Path | None:
        return None


def test_cancelled_native_dialog_returns_204(tmp_path: Path) -> None:
    app = create_app(
        project_root=tmp_path, session_token="secret", native_dialog=CancelDialog()
    )
    client = TestClient(app)
    assert client.post("/api/dialog/folder", headers=TOKEN).status_code == 204
    assert (
        client.post(
            "/api/dialog/file", headers=TOKEN, json={"patterns": ["RED_*.txt"]}
        ).status_code
        == 204
    )
