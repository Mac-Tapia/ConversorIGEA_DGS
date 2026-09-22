"""Revisiones editables, versionadas y auditables."""

from .apply import OperationValidationError, apply_operation
from .models import ChangeOperation, RevisionSnapshot
from .store import RevisionConflictError, RevisionNotFoundError, RevisionStore

__all__ = [
    "ChangeOperation",
    "OperationValidationError",
    "RevisionConflictError",
    "RevisionNotFoundError",
    "RevisionSnapshot",
    "RevisionStore",
    "apply_operation",
]
