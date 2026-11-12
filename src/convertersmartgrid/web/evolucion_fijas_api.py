"""105: rutas de la evolución de los clientes fijos y de la carpeta de archivo, montadas en la API única."""
from __future__ import annotations

from collections.abc import Callable

from fastapi import FastAPI, HTTPException, Query

from .api_contract import (
    ArchivoInformesPeticion,
    ArchivoInformesRespuesta,
    CurvaClienteFijoRespuesta,
    EvolucionFijasPeticion,
    EvolucionFijasRespuesta,
    JobRespuesta,
)


def registrar_rutas_evolucion(app: FastAPI, *, ws_or_404, submit, rutas_locales: Callable[[], bool]) -> None:
    """Monta las rutas con la cola y los espacios del único servidor (105:RF-18 a RF-20, RF-29)."""
    from . import evolucion_fijas

    ruta = '/api/workspaces/{wid}/clientes-fijos/evolucion'

    @app.get(ruta, response_model=EvolucionFijasRespuesta, response_model_exclude_unset=True)
    def evolucion_estado(wid: str) -> dict:
        """105:RF-18: alimentadores con clientes fijos, meses con libro y el último resultado del espacio."""
        return evolucion_fijas.estado(ws_or_404(wid))

    @app.post(ruta, status_code=202, response_model=JobRespuesta, response_model_exclude_unset=True)
    def evolucion_lanzar(wid: str, body: EvolucionFijasPeticion) -> dict:
        """105:RF-17: lee los libros de clientes del rango en un trabajo del motor, cancelable entre libros."""
        ws = ws_or_404(wid)
        evolucion_fijas.fuentes(ws, body.desde, body.hasta, con_cabecera=False)   # sin libros, error antes de encolar
        return submit(ws, 'clientes_fijos_evolucion', f'Evolución de clientes fijos: {", ".join(body.alimentadores)}',
                      lambda ctx: evolucion_fijas.calcular(ws, ctx, body.alimentadores, body.desde, body.hasta,
                                                           con_cabecera=body.con_cabecera), lane='engine')

    @app.get(ruta + '/curva', response_model=CurvaClienteFijoRespuesta, response_model_exclude_unset=True)
    def evolucion_curva(wid: str, cliente: str = Query(min_length=1, max_length=64)) -> dict:
        """105:RF-25: la curva de 15 minutos de un cliente del último resultado."""
        return evolucion_fijas.curva(ws_or_404(wid), cliente)

    @app.get('/api/archivo', response_model=ArchivoInformesRespuesta, response_model_exclude_unset=True)
    def archivo_ver() -> dict:
        """105:RF-28: la carpeta donde se archivan los informes en esta máquina, si hay."""
        from ..archivo_informes import carpeta_archivo

        carpeta = carpeta_archivo()
        return {'ruta': carpeta.as_posix() if carpeta else None}

    @app.put('/api/archivo', response_model=ArchivoInformesRespuesta, response_model_exclude_unset=True)
    def archivo_poner(body: ArchivoInformesPeticion) -> dict:
        """105:RF-29: pone o quita la carpeta de archivo; solo un servidor que admite rutas locales."""
        from ..archivo_informes import ArchivoError, guardar_carpeta

        if body.ruta and not rutas_locales():
            raise HTTPException(403, 'Este servidor no admite rutas locales.')
        try:
            carpeta = guardar_carpeta(body.ruta)
        except ArchivoError as exc:
            raise HTTPException(400, str(exc)) from exc
        return {'ruta': carpeta.as_posix() if carpeta else None}
