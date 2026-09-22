"""Modelos serializables del historial de cambios de red."""

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from typing import Any

ALLOWED_ACTIONS = frozenset({"create", "update", "delete", "connect", "disconnect", "move"})


@dataclass(frozen=True, slots=True)
class ChangeOperation:
    action: str
    target_type: str
    target_id: str
    field: str | None
    before: Any
    after: Any
    justification: str
    unit: str | None = None
    operation_id: str = ""
    sequence: int = 0
    created_at: str = ""
    inverse_of: str | None = None

    @classmethod
    def request(cls, **values: Any) -> ChangeOperation:
        return cls(**values)

    def committed(self, sequence: int, *, inverse_of: str | None = None) -> ChangeOperation:
        return replace(
            self,
            operation_id=str(uuid.uuid4()),
            sequence=sequence,
            created_at=datetime.now(UTC).isoformat(),
            inverse_of=inverse_of,
        )

    def inverse(self) -> ChangeOperation:
        inverse_actions = {
            "create": "delete",
            "delete": "create",
            "connect": "disconnect",
            "disconnect": "connect",
            "update": "update",
            "move": "move",
        }
        return ChangeOperation.request(
            action=inverse_actions[self.action],
            target_type=self.target_type,
            target_id=self.target_id,
            field=self.field,
            before=self.after,
            after=self.before,
            justification=f"Deshacer operación {self.operation_id}: {self.justification}",
            unit=self.unit,
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, values: dict[str, Any]) -> ChangeOperation:
        return cls(**values)


@dataclass(frozen=True, slots=True)
class RevisionSnapshot:
    revision_id: str
    version: int
    state: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
