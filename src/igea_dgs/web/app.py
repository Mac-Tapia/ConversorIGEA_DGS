"""Fábrica FastAPI ligada a una sesión local autenticada."""

import secrets
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from igea_dgs.projects import InputResolutionError, ProjectNotFoundError, ProjectStore

from .routes import NativeDialogPort, TkNativeDialog, dialogs_router, projects_router


def create_app(
    *,
    project_root: Path,
    session_token: str,
    native_dialog: NativeDialogPort | None = None,
) -> FastAPI:
    root = project_root.resolve()
    app = FastAPI(title="IGEA-DGS Local API", version="1")
    app.state.project_root = root
    app.state.session_token = session_token
    app.state.project_store = ProjectStore(root / ".igea" / "custody.sqlite3")
    app.state.native_dialog = native_dialog or TkNativeDialog()

    @app.middleware("http")
    async def require_session_token(request: Request, call_next):  # type: ignore[no-untyped-def]
        supplied = request.headers.get("X-Session-Token", "")
        if not secrets.compare_digest(supplied, app.state.session_token):
            return JSONResponse(
                status_code=401,
                content={"code": "INVALID_SESSION_TOKEN", "message": "Sesión local inválida"},
            )
        return await call_next(request)

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "api_version": "1"}

    @app.exception_handler(InputResolutionError)
    def input_resolution_error(_request: Request, exc: InputResolutionError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={
                "code": exc.code,
                "message": str(exc),
                "kind": exc.kind,
                "candidates": list(exc.candidates),
            },
        )

    @app.exception_handler(ProjectNotFoundError)
    def project_not_found(_request: Request, exc: ProjectNotFoundError) -> JSONResponse:
        return JSONResponse(
            status_code=404,
            content={"code": "PROJECT_NOT_FOUND", "message": str(exc)},
        )

    app.include_router(projects_router)
    app.include_router(dialogs_router)

    return app
