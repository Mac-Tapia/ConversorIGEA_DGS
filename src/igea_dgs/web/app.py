"""Fábrica FastAPI ligada a una sesión local autenticada."""

import secrets
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


def create_app(*, project_root: Path, session_token: str) -> FastAPI:
    root = project_root.resolve()
    app = FastAPI(title="IGEA-DGS Local API", version="1")
    app.state.project_root = root
    app.state.session_token = session_token

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

    return app
