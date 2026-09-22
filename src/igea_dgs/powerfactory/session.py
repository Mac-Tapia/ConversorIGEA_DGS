from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ManagedPowerFactorySession:
    project_name: str
    run_id: str
    allow_external_project: bool = False

    def assert_project(self, active_project: str) -> None:
        if active_project != self.project_name and not self.allow_external_project:
            raise PermissionError(f"Refusing unmanaged project: {active_project}")
