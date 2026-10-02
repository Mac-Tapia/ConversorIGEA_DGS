"""Endpoints del pipeline bloqueante G1-G4."""

from typing import Any

from fastapi import APIRouter, Request


router = APIRouter(prefix="/api/projects/{project_id}/pipeline", tags=["pipeline"])


@router.post("/inspect")
def inspect(project_id: str, request: Request) -> dict[str, Any]:
    return request.app.state.project_pipeline.inspect(project_id).to_dict()


@router.post("/validate/{revision_id}")
def validate(project_id: str, revision_id: str, request: Request) -> dict[str, Any]:
    return request.app.state.project_pipeline.validate_revision(project_id, revision_id).to_dict()


@router.post("/publish/{revision_id}")
def publish(project_id: str, revision_id: str, request: Request) -> dict[str, Any]:
    return request.app.state.project_pipeline.publish_revision(project_id, revision_id).to_dict()
