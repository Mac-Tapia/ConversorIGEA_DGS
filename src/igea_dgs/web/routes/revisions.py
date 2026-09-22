"""API de revisiones auditables y concurrencia optimista."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request, status
from pydantic import BaseModel

from igea_dgs.revisions import ChangeOperation


class CreateRevisionRequest(BaseModel):
    initial_state: dict[str, Any]


class OperationRequest(BaseModel):
    expected_version: int
    action: str
    target_type: str
    target_id: str
    field: str | None = None
    before: Any = None
    after: Any = None
    justification: str
    unit: str | None = None


class UndoRequest(BaseModel):
    expected_version: int


router = APIRouter(prefix="/api/revisions", tags=["revisions"])


@router.post("", status_code=status.HTTP_201_CREATED)
def create_revision(payload: CreateRevisionRequest, request: Request) -> dict[str, Any]:
    return request.app.state.revision_store.create(payload.initial_state).to_dict()


@router.get("/{revision_id}")
def get_revision(revision_id: str, request: Request) -> dict[str, Any]:
    return request.app.state.revision_store.snapshot(revision_id).to_dict()


@router.get("/{revision_id}/operations")
def get_operations(revision_id: str, request: Request) -> list[dict[str, Any]]:
    return [item.to_dict() for item in request.app.state.revision_store.read_log(revision_id)]


@router.post("/{revision_id}/operations", status_code=status.HTTP_201_CREATED)
def append_operation(
    revision_id: str, payload: OperationRequest, request: Request
) -> dict[str, Any]:
    values = payload.model_dump(exclude={"expected_version"})
    operation = ChangeOperation.request(**values)
    return request.app.state.revision_store.append(
        revision_id, payload.expected_version, operation
    ).to_dict()


@router.post("/{revision_id}/operations/{operation_id}/undo", status_code=status.HTTP_201_CREATED)
def undo_operation(
    revision_id: str, operation_id: str, payload: UndoRequest, request: Request
) -> dict[str, Any]:
    return request.app.state.revision_store.undo(
        revision_id, operation_id, expected_version=payload.expected_version
    ).to_dict()
