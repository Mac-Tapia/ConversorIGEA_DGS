"""API de custodia de proyectos y manifiestos de entrada."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request, status
from pydantic import BaseModel

from igea_dgs.projects import InputSelection, detect_input_set


class CreateProjectRequest(BaseModel):
    name: str


class DetectInputsRequest(BaseModel):
    folder: str
    crs: str = "EPSG:32718"


class RegisterInputsRequest(BaseModel):
    red_path: str
    carga_path: str
    equipment_path: str
    output_dir: str
    crs: str


router = APIRouter(prefix="/api/projects", tags=["projects"])


@router.post("", status_code=status.HTTP_201_CREATED)
def create_project(payload: CreateProjectRequest, request: Request) -> dict[str, str]:
    return request.app.state.project_store.create(payload.name).to_dict()


@router.get("/{project_id}")
def get_project(project_id: str, request: Request) -> dict[str, str]:
    return request.app.state.project_store.get(project_id).to_dict()


@router.post("/detect-inputs")
def detect_inputs(payload: DetectInputsRequest) -> dict[str, str]:
    selection = detect_input_set(Path(payload.folder), crs=payload.crs)
    return {
        "red_path": str(selection.red_path),
        "carga_path": str(selection.carga_path),
        "equipment_path": str(selection.equipment_path),
        "output_dir": str(selection.output_dir),
        "crs": selection.crs,
    }


@router.post("/{project_id}/inputs", status_code=status.HTTP_201_CREATED)
def register_inputs(
    project_id: str, payload: RegisterInputsRequest, request: Request
) -> dict[str, object]:
    selection = InputSelection(
        Path(payload.red_path),
        Path(payload.carga_path),
        Path(payload.equipment_path),
        Path(payload.output_dir),
        payload.crs,
    )
    return request.app.state.project_store.register_inputs(project_id, selection).to_dict()
