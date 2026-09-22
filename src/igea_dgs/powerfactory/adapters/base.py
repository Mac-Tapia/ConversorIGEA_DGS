"""Unidad idempotente y reversible de modificación PowerFactory."""

from typing import Any, Mapping

from ..port import PowerFactoryPort


class AdapterApplyError(RuntimeError):
    pass


class EquipmentAdapter:
    class_name = ""

    def __init__(self, port: PowerFactoryPort) -> None:
        self.port = port

    def external_id(self, spec: Any) -> str:
        return str(spec.source_id)

    def attributes(self, spec: Any) -> Mapping[str, Any]:
        raise NotImplementedError

    def preflight(self, spec: Any) -> None:
        if not self.external_id(spec).strip():
            raise AdapterApplyError("external_id is mandatory")

    def apply(self, spec: Any) -> Any:
        self.preflight(spec)
        external_id = self.external_id(spec)
        existing = self.port.find(self.class_name, external_id)
        created = existing is None
        obj = existing if existing is not None else self.port.create(self.class_name, external_id)
        try:
            self.port.set_attributes(obj, self.attributes(spec))
        except Exception as exc:
            if created:
                self.port.delete(obj)
            raise AdapterApplyError(f"Failed applying {self.class_name}:{external_id}") from exc
        return obj

    def inspect(self, external_id: str) -> Any | None:
        return self.port.find(self.class_name, external_id)

    def rollback(self, obj: Any) -> None:
        self.port.delete(obj)

    def report(self, spec: Any) -> dict[str, str]:
        return {"class_name": self.class_name, "external_id": self.external_id(spec)}
