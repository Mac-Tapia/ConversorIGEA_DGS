"""Aplicación pura y estricta de operaciones de revisión."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from .models import ALLOWED_ACTIONS, ChangeOperation


class OperationValidationError(ValueError):
    pass


def _validate_identity(operation: ChangeOperation) -> None:
    if operation.action not in ALLOWED_ACTIONS:
        raise OperationValidationError("OPERATION_ACTION_INVALID")
    if not operation.target_type.strip() or not operation.target_id.strip():
        raise OperationValidationError("OPERATION_TARGET_INVALID")
    if not operation.justification.strip():
        raise OperationValidationError("OPERATION_JUSTIFICATION_REQUIRED")
    if operation.action in {"update", "move", "connect", "disconnect"} and not operation.field:
        raise OperationValidationError("OPERATION_FIELD_REQUIRED")


def apply_operation(state: dict[str, Any], operation: ChangeOperation) -> dict[str, Any]:
    _validate_identity(operation)
    updated = deepcopy(state)
    collection = updated.setdefault(operation.target_type, {})
    exists = operation.target_id in collection

    if operation.action == "create":
        if exists or operation.before is not None or not isinstance(operation.after, dict):
            raise OperationValidationError("OPERATION_CREATE_INVALID")
        collection[operation.target_id] = deepcopy(operation.after)
        return updated

    if not exists:
        raise OperationValidationError("OPERATION_TARGET_NOT_FOUND")
    target = collection[operation.target_id]

    if operation.action == "delete":
        if target != operation.before or operation.after is not None:
            raise OperationValidationError("OPERATION_BEFORE_MISMATCH")
        del collection[operation.target_id]
        return updated

    if not isinstance(target, dict):
        raise OperationValidationError("OPERATION_TARGET_INVALID")
    current = target.get(operation.field)
    if current != operation.before:
        raise OperationValidationError("OPERATION_BEFORE_MISMATCH")
    target[operation.field] = deepcopy(operation.after)
    return updated
