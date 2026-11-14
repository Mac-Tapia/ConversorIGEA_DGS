"""017:RF-109, RF-124: el mapa de las cargas nuevas en la web y su punto de diseño leído en DIgSILENT.

Usuario, 2026-11-13: «en la web se debe ver la ubicación en Google Maps o similar de dónde se conectó y la ubicación
de la carga nueva o de los bloques»; «debe haber un botón para actualizar la imagen de la ubicación y el punto de
fijación de diseño cuando el usuario verificó en DIgSILENT, corrigió o asignó otro punto».

- ``GET …/mapa-cargas``: los datos (cargas, nodos, enlaces y red), sin DIgSILENT.
- ``GET …/mapa-cargas/pagina``: el mismo mapa en HTML con Leaflet dentro, aislado como la vista previa (086:RF-21).
- ``POST …/mapa-cargas/digsilent``: trabajo del carril de DIgSILENT que lee, sin escribir, dónde está hoy cada carga
  (``tools/ubicacion_cargas_pf.py``) y devuelve las diferencias con lo guardado.
- ``POST …/mapa-cargas/confirmar``: guarda como punto de diseño lo leído de las cargas que elige el operador.
"""
from __future__ import annotations

import json
import re
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, ConfigDict, Field

from .api_contract import JobRespuesta

KIND = 'mapa_cargas_digsilent'
#: El informe que deja el guion con ``_guion_pf``: solo ese nombre se acepta al confirmar (nada de rutas).
_LECTURA = re.compile(r'^ubicacion_cargas_[0-9a-f]{12}\.json$')


class LecturaMapaPeticion(BaseModel):
    """017:RF-124: qué proyecto leer en DIgSILENT; sin alimentadores, los de sus cargas nuevas."""
    model_config = ConfigDict(extra='forbid')
    project: str = Field(min_length=1, max_length=255)
    alimentadores: list[str] = Field(default_factory=list, max_length=500)
    anio: int | None = Field(default=None, ge=2000, le=2100)


class CargaElegida(BaseModel):
    model_config = ConfigDict(extra='forbid')
    alimentador: str | None = Field(default=None, max_length=255)
    sed: str = Field(min_length=1, max_length=255)


class ConfirmarPuntoPeticion(BaseModel):
    """017:RF-124: las cargas cuyo punto leído en DIgSILENT pasa a ser su punto de diseño."""
    model_config = ConfigDict(extra='forbid')
    project: str = Field(min_length=1, max_length=255)
    lectura: str = Field(min_length=1, max_length=255)
    cargas: list[CargaElegida] = Field(min_length=1, max_length=5000)


def cargas_del_mapa(ws, project: str) -> list[dict]:
    """Las cargas nuevas aplicadas del proyecto, con su punto de diseño confirmado si lo hay."""
    from ..mapa_cargas import aplicar_puntos
    from . import services

    return aplicar_puntos(ws.root, project, services._cargas_nuevas_aplicadas(ws, project))


def datos_para_la_web(ws, project: str, alimentadores: list[str]) -> dict:
    """017:RF-109, RF-124: el mapa con la geografía del último flujo de «Con proyecto» de cada alimentador."""
    from ..mapa_cargas import datos_del_mapa
    from . import services

    cargas = cargas_del_mapa(ws, project)
    feeders = sorted({*(a for a in alimentadores if a), *(str(c['alimentador']) for c in cargas if c.get('alimentador'))})
    geos: dict[str, Any] = {}
    epoca: dict[str, float] = {}
    for f in feeders:
        con = services._ultimo_estudio(ws, 'con', project, f) or {}
        geo = (con.get('geo') or {}).get(f)
        if geo:
            geos[f] = geo
            fichero = ws.out_dir / str(con.get('_fichero') or '')
            try:
                epoca[f] = fichero.stat().st_mtime if con.get('_fichero') else 0.0
            except OSError:
                epoca[f] = 0.0
    return datos_del_mapa(project, cargas, geos, utm=services._utm, flujo_epoca=epoca, alimentadores=alimentadores)


def leer_en_digsilent(ws, ctx, project: str, alimentadores: list[str], anio: int | None) -> dict:
    """017:RF-124: lee en DIgSILENT, sin escribir, la conexión de hoy de cada carga y la compara con lo guardado."""
    from ..mapa_cargas import comparar
    from . import services
    from .requisitos import UserError

    cargas = cargas_del_mapa(ws, project)
    feeders = sorted({*(a for a in alimentadores if a), *(str(c['alimentador']) for c in cargas if c.get('alimentador'))})
    plan = {'project': project.strip(), 'folder': services.carpeta_de(ws, project), 'feeders': feeders,
            'anio_casos': anio,
            'cargas': [{'sed': c.get('sed'), 'alimentador': c.get('alimentador'), 'variacion': c.get('variacion')}
                       for c in cargas]}
    ctx.log(f'Lectura en DIgSILENT, sin escribir, de {len(cargas)} carga(s) nueva(s) de {project}.')
    _rc, informe, report = services._guion_pf(ws, ctx, 'ubicacion_cargas_pf.py', plan, nombre='ubicacion_cargas',
                                              cancelable=False)
    if informe.get('error'):
        raise UserError(f"Lectura de {project} en DIgSILENT: {informe['error']}")
    diferencias = comparar(cargas, informe.get('cargas') or [])
    for d in diferencias:
        texto = '; '.join(d['cambios']) or d.get('error') or 'igual'
        ctx.log(f"  {d['sed']} ({d.get('alimentador')}): {d['estado']} — {texto}")
    for aviso in informe.get('avisos') or []:
        ctx.log(f'  Aviso: {aviso}')
    return {'project': project.strip(), 'lectura': report.name, 'caso': informe.get('caso'),
            'diferencias': diferencias, 'avisos': informe.get('avisos') or []}


def confirmar_puntos(ws, body: ConfirmarPuntoPeticion) -> dict:
    """017:RF-124: guarda como punto de diseño lo que se leyó de las cargas elegidas; avisa de repetir 4.2."""
    from ..mapa_cargas import clave, guardar_puntos
    from .requisitos import UserError

    if not _LECTURA.match(body.lectura):
        raise UserError('Lectura desconocida: vuelva a pulsar «Actualizar desde DIgSILENT».')
    ruta = ws.out_dir / body.lectura
    try:
        informe = json.loads(ruta.read_text(encoding='utf-8'))
    except (OSError, ValueError) as exc:
        raise UserError('No se encuentra la lectura de DIgSILENT: vuelva a pulsar «Actualizar desde DIgSILENT».') \
            from exc
    if str(informe.get('project') or '').strip() != body.project.strip():
        raise UserError(f'Esa lectura es del proyecto {informe.get("project")}, no de {body.project}.')
    leidas = {clave(c.get('alimentador'), c.get('sed')): c for c in informe.get('cargas') or []}
    elegidas = []
    for c in body.cargas:
        fila = leidas.get(clave(c.alimentador, c.sed))
        if fila is None or not fila.get('nodo'):
            raise UserError(f'{c.sed}: la lectura no tiene su nodo de conexión; no se puede usar ese punto.')
        elegidas.append(fila)
    guardados = guardar_puntos(ws.root, body.project, elegidas, lectura=body.lectura)
    feeders = sorted({str(g.get('alimentador')) for g in guardados})
    return {'guardados': guardados, 'repetir_flujos': feeders,
            'aviso': (f'Punto de diseño guardado para {len(guardados)} carga(s). La imagen, el mapa y el informe lo '
                      f'usan desde ahora; repita los flujos de 4.2 de {", ".join(feeders)} para que el informe mida '
                      'la red con este punto.')}


def dar_de_alta(ws, body: ConfirmarPuntoPeticion) -> dict:
    """017:RF-124 ampliada: las cargas de la lectura que solo están en DIgSILENT pasan a ser cargas aplicadas y solas."""
    import uuid

    from ..mapa_cargas import clave, registros_de_alta
    from .requisitos import UserError

    if not _LECTURA.match(body.lectura):
        raise UserError('Lectura desconocida: vuelva a pulsar «Actualizar desde DIgSILENT».')
    try:
        informe = json.loads((ws.out_dir / body.lectura).read_text(encoding='utf-8'))
    except (OSError, ValueError) as exc:
        raise UserError('No se encuentra la lectura de DIgSILENT: vuelva a pulsar «Actualizar desde DIgSILENT».') \
            from exc
    if str(informe.get('project') or '').strip() != body.project.strip():
        raise UserError(f'Esa lectura es del proyecto {informe.get("project")}, no de {body.project}.')
    leidas = {clave(c.get('alimentador'), c.get('sed')): c for c in informe.get('cargas') or []}
    filas = []
    for c in body.cargas:
        fila = leidas.get(clave(c.alimentador, c.sed))
        if fila is None:
            raise UserError(f'{c.sed}: no está en la lectura de DIgSILENT.')
        filas.append(fila)
    token = uuid.uuid4().hex[:12]
    try:
        plan, aplicacion = registros_de_alta(body.project, filas, token)
    except ValueError as exc:
        raise UserError(str(exc)) from exc
    ws.plans_dir.mkdir(parents=True, exist_ok=True)
    ws.out_dir.mkdir(parents=True, exist_ok=True)
    (ws.plans_dir / f'cargas_pf_{token}.json').write_text(json.dumps(plan, indent=2, ensure_ascii=False), encoding='utf-8')
    (ws.out_dir / f'cargas_pf_aplicacion_{token}.json').write_text(
        json.dumps(aplicacion, indent=2, ensure_ascii=False), encoding='utf-8')
    nombres = ', '.join(str(f['sed']) for f in filas)
    return {'altas': [str(f['sed']) for f in filas], 'token': token,
            'aviso': f'{nombres}: dada(s) de alta como carga(s) sola(s) con lo que guarda DIgSILENT; ya sirven para el '
                     'informe de factibilidad. Repita los flujos de 4.2 si aún no la(s) incluyen.'}


def registrar_rutas_mapa(app: FastAPI, *, ws_or_404, submit) -> None:
    """Monta las rutas del mapa de las cargas nuevas con la cola y los espacios del único servidor."""
    from ..preview import politica_pagina_generada

    @app.get('/api/workspaces/{wid}/mapa-cargas')
    def mapa_cargas(wid: str, project: str = Query(..., min_length=1),
                    alimentador: list[str] = Query(default=[])) -> dict:
        """017:RF-109, RF-124: las cargas nuevas con su punto, su nodo, su enlace y la red, sin DIgSILENT."""
        return datos_para_la_web(ws_or_404(wid), project, alimentador)

    @app.get('/api/workspaces/{wid}/mapa-cargas/pagina', response_class=HTMLResponse)
    def mapa_cargas_pagina(wid: str, project: str = Query(..., min_length=1),
                           alimentador: list[str] = Query(default=[])) -> HTMLResponse:
        """017:RF-124; 086:RF-21, RF-63: el mapa con Leaflet dentro, aislado como toda página generada."""
        from ..mapa_cargas import pagina_del_mapa

        html = pagina_del_mapa(datos_para_la_web(ws_or_404(wid), project, alimentador))
        return HTMLResponse(html, headers={'Content-Security-Policy': politica_pagina_generada()})

    @app.post('/api/workspaces/{wid}/mapa-cargas/digsilent', status_code=202, response_model=JobRespuesta,
              response_model_exclude_unset=True)
    def mapa_cargas_leer_en_pf(wid: str, body: LecturaMapaPeticion) -> dict:
        """017:RF-124: «Actualizar desde DIgSILENT», en el carril de DIgSILENT y sin escribir en el proyecto."""
        ws = ws_or_404(wid)
        return submit(ws, 'mapa_cargas_digsilent', f'Ubicación de las cargas nuevas · {body.project}',
                      lambda ctx: leer_en_digsilent(ws, ctx, body.project, body.alimentadores, body.anio),
                      lane='powerfactory')

    @app.post('/api/workspaces/{wid}/mapa-cargas/alta')
    def mapa_cargas_alta(wid: str, body: ConfirmarPuntoPeticion) -> dict:
        """017:RF-124 ampliada: «Dar de alta» la carga que solo está en DIgSILENT, como carga sola aplicada."""
        return dar_de_alta(ws_or_404(wid), body)

    @app.post('/api/workspaces/{wid}/mapa-cargas/confirmar')
    def mapa_cargas_confirmar(wid: str, body: ConfirmarPuntoPeticion) -> dict:
        """017:RF-124: «Usar este punto»; guarda en el espacio, nunca en DIgSILENT."""
        ws = ws_or_404(wid)
        if not body.cargas:
            raise HTTPException(422, 'Elija al menos una carga.')
        return confirmar_puntos(ws, body)
