"""114: rutas del agente MASAC en sombra, montadas en la API única."""
from __future__ import annotations

from fastapi import FastAPI, Path as Ruta, Query

from .api_contract import (
    AgenteSombraEstadoRespuesta,
    AgenteSombraPeticion,
    DecisionAgentePeticion,
    DecisionAgenteRespuesta,
    JobRespuesta,
)


def registrar_rutas_agente(app: FastAPI, *, ws_or_404, submit) -> None:
    """Pedir la propuesta en sombra, leerla con el marcador y confirmarla o deshacerla (114:RF-7, RF-9, RF-11)."""
    from . import agente_sombra

    ruta = '/api/workspaces/{wid}/agente/sombra'

    @app.post(ruta, status_code=202, response_model=JobRespuesta, response_model_exclude_unset=True)
    def agente_sombra_pedir(wid: str, body: AgenteSombraPeticion) -> dict:
        """114:RF-7: un trabajo en CPU con el motor abierto, sin DIgSILENT: propone y no aplica."""
        ws = ws_or_404(wid)
        agente_sombra.red_del_proyecto(agente_sombra.exigir_vinculado(ws, body.project), body.caso, body.feeders)
        return submit(ws, 'agente_sombra', f'Propuesta del agente (en sombra) · {body.project.strip()}',
                      lambda ctx: agente_sombra.proponer(ws, ctx, body.project, body.feeders, body.caso, body.banco_kvar),
                      lane='asistente')

    @app.get(ruta, response_model=AgenteSombraEstadoRespuesta, response_model_exclude_unset=True)
    def agente_sombra_leer(wid: str, project: str = Query(min_length=1, max_length=200)) -> dict:
        """114:RF-7: las propuestas del proyecto y quién acierta frente a la regla actual."""
        return agente_sombra.estado(ws_or_404(wid), project)

    @app.post(ruta + '/decisiones/{ident}', response_model=DecisionAgenteRespuesta)
    def agente_sombra_decidir(wid: str, body: DecisionAgentePeticion,
                              ident: str = Ruta(pattern=r'^[0-9a-f]{32}$')) -> dict:
        """114:RF-9, RF-11: el operador confirma o deshace; queda en el registro y no se aplica nada."""
        return agente_sombra.decidir(ws_or_404(wid), ident, body.accion)
