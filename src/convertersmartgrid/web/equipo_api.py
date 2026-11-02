"""065/047: rutas del equipo local; revisión en cola sin autorización de escritura."""
from __future__ import annotations

from fastapi import FastAPI
from pydantic import BaseModel, ConfigDict, Field

from .api_contract import JobRespuesta


class RevisionEquipoIn(BaseModel):
    model_config = ConfigDict(extra='forbid')
    max_rondas: int = Field(default=2, ge=1, le=2, strict=True)


def registrar_rutas_equipo(app: FastAPI, *, ws_or_404, submit) -> None:
    """Monta las rutas usando el almacén y la cola del único servidor existente."""
    from ..asistente.equipo import inventario_equipo
    from . import services

    @app.get('/api/asistente/equipo')
    def inventario() -> dict:
        return inventario_equipo()

    @app.get('/api/workspaces/{wid}/asistente/equipo')
    def estado(wid: str) -> dict:
        return services.asistente_equipo(ws_or_404(wid))

    @app.post('/api/workspaces/{wid}/asistente/{plan_id}/revision', status_code=202,
              response_model=JobRespuesta, response_model_exclude_unset=True)
    def revision(wid: str, plan_id: str, body: RevisionEquipoIn) -> dict:
        ws = ws_or_404(wid)
        services.asistente_plan(ws, plan_id)
        return submit(ws, 'asistente_revision', 'Revisar propuesta por roles',
            lambda ctx: services.asistente_revisar_plan(ws, ctx, plan_id, max_rondas=body.max_rondas),
            lane='asistente')
