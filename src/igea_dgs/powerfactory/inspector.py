from typing import Any

from .port import PowerFactoryPort


def inspect_object(port: PowerFactoryPort, class_name: str, external_id: str) -> Any | None:
    return port.find(class_name, external_id)
