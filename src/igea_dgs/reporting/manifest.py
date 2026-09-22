"""Manifiesto de ejecución auditable."""

import json
import platform
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Mapping


@dataclass(frozen=True, slots=True)
class RunManifest:
    run_id: str
    feeder: str
    created_at: str
    python: str
    platform: str
    inputs: Mapping[str, str] = field(default_factory=dict)
    configs: Mapping[str, str] = field(default_factory=dict)
    outputs: Mapping[str, str] = field(default_factory=dict)
    policies: Mapping[str, str] = field(default_factory=dict)
    gates: Mapping[str, str] = field(default_factory=dict)

    @classmethod
    def create(cls, run_id: str, feeder: str, **values) -> "RunManifest":
        return cls(
            run_id,
            feeder,
            datetime.now(timezone.utc).isoformat(),
            sys.version.split()[0],
            platform.platform(),
            **values,
        )

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, ensure_ascii=False, sort_keys=True) + "\n"
