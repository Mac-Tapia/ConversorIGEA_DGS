"""Rutas de la web del PIT (``/api/pit/…``), en un ``APIRouter`` propio (spec 107, T13).

El PIT es un estudio aparte del PIDE (107:RF-1), y sus rutas también: ``web/app.py`` solo registra este router
(pactado con el integrador f9; el cableado está en ``para_f9/107_app.txt``). El diagnóstico y las alternativas tardan
más de un segundo, así que son trabajos en cola (P7): carril ``engine`` con el motor abierto, ``powerfactory`` con
DIgSILENT, y progreso por el WebSocket de siempre. Las rutas reciben ficheros del espacio de trabajo; una ruta que
salga de él se rechaza.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Mapping

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..pit import PitError
from ..pit.ambito import areas_del_perfil, reunir
from ..pit.diagnostico import diagnosticar, limites_del_estudio
from ..pit.motores import ESTUDIOS, MOTORES, capacidad, elegir_motor
from ..pit.observaciones import escribir_observaciones, registrar
from ..pit.red_area import desde_ambito, leer_libro_red
from ..registro_normativo import cargar_registro
from ..util import publicar_duradero  # 001:RF-5 (H14): escritura atómica y duradera

__all__ = ['crear_router']


class PedidoDiagnostico(BaseModel):
    workspace_id: str
    area: str
    anios: list[int] = Field(min_length=1)
    libro_red: str
    proyeccion: str
    motor: str | None = None


class PedidoObservaciones(BaseModel):
    workspace_id: str
    expediente: str
    observaciones: list[dict[str, Any]]
    referencias: dict[str, dict[str, Any]]


def _dentro(raiz: Path, relativa: str) -> Path:
    ruta = (raiz / relativa).resolve()
    if not ruta.is_relative_to(raiz.resolve()):
        raise HTTPException(400, f'{relativa}: fuera del espacio de trabajo')
    return ruta


def crear_router(jobs: Any, espacio: Callable[[str], Path], perfil: Callable[[], Mapping[str, Any]],
                 normativa: Path, *, licencia: Callable[[], bool] = lambda: False) -> APIRouter:
    """``jobs``: la cola de la web (``JobManager``); ``espacio``: carpeta de un espacio; ``perfil``: el activo."""
    r = APIRouter(prefix='/api/pit', tags=['pit'])

    @r.get('/areas')
    def areas() -> dict[str, Any]:
        try:
            return {'areas': [{'codigo': a.codigo, 'titulares': list(a.titulares), 'set': list(a.set)}
                              for a in areas_del_perfil(perfil())]}
        except PitError as exc:
            raise HTTPException(422, str(exc)) from None

    @r.get('/capacidades')
    def capacidades() -> dict[str, Any]:
        return {'motores': list(MOTORES), 'licencia': licencia(),
                'matriz': [{'motor': m, 'estudio': e, 'alcance': capacidad(m, e).alcance,
                            'texto': capacidad(m, e).texto} for m in MOTORES for e in ESTUDIOS]}

    @r.post('/diagnostico')
    def diagnostico(p: PedidoDiagnostico) -> dict[str, Any]:
        raiz = espacio(p.workspace_id)
        libro, proyeccion = _dentro(raiz, p.libro_red), _dentro(raiz, p.proyeccion)
        datos = perfil()
        try:
            motor = elegir_motor(p.motor, licencia())
            area = areas_del_perfil(datos, p.area)[0]
            cfg = (datos.get('pit') or {}).get('libro_red')
            if not cfg:
                raise PitError('pit.libro_red: el perfil no describe el libro de la red')
            limites = limites_del_estudio(cargar_registro(normativa), datos)
        except PitError as exc:
            raise HTTPException(422, str(exc)) from None
        if motor == 'digsilent':
            raise HTTPException(409, 'el diagnóstico con DIgSILENT corre con tools/pit_pf.py en su carril')

        def trabajo(ctx) -> dict[str, Any]:
            elementos = leer_libro_red(libro, cfg)
            red = desde_ambito(reunir(area, elementos))
            red.avisos.extend(elementos.avisos)  # las hojas que no se tomaron, con su nombre (107:RF-12)
            filas = json.loads(proyeccion.read_text(encoding='utf-8'))
            diag = diagnosticar(area, red, filas, p.anios, limites, motor=motor, cancel=ctx.cancel,
                                on_progress=lambda i, n, anio: ctx.progress(i, n, f'año {anio}'))
            salida = raiz / 'expedientes_pit' / area.codigo / 'diagnostico_de_trabajo.json'
            salida.parent.mkdir(parents=True, exist_ok=True)
            publicar_duradero(salida, json.dumps(diag.como_dict(), ensure_ascii=False, indent=1, sort_keys=True,
                                                 default=str) + '\n')
            return {'salida': str(salida), 'completo': diag.completo, 'avisos': diag.avisos}

        job = jobs.submit(p.workspace_id, 'pit_diagnostico', f'Diagnóstico PIT {area.codigo}', trabajo,
                          lane='engine')
        return {'job': job.id}

    @r.post('/observaciones')
    def observaciones(p: PedidoObservaciones) -> dict[str, Any]:
        carpeta = _dentro(espacio(p.workspace_id), p.expediente)
        try:
            obs = registrar(p.observaciones, p.referencias)
        except PitError as exc:
            raise HTTPException(422, str(exc)) from None
        ruta = escribir_observaciones(carpeta / 'observaciones.json', obs)
        return {'observaciones': len(obs), 'fichero': str(ruta)}

    return r
