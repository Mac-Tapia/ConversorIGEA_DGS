"""Rutas de la web del PIT (``/api/pit/…``), en un ``APIRouter`` propio (spec 107, T13).

El PIT es un estudio aparte del PIDE (107:RF-1), y sus rutas también: ``web/app.py`` solo registra este router
(pactado con el integrador f9; el cableado está en ``para_f9/107_app.txt``). El diagnóstico y las alternativas tardan
más de un segundo, así que son trabajos en cola (P7): carril ``engine`` con el motor abierto, ``powerfactory`` con
DIgSILENT, y progreso por el WebSocket de siempre. Las rutas reciben ficheros del espacio de trabajo; una ruta que
salga de él se rechaza.

El expediente (``POST /api/pit/expediente``, 107-P10c) se arma de punta a punta con ``pit.armado.armar_expediente``,
como trabajo del carril ``engine``. Lo que se puede comprobar antes (las rutas, el área, el libro de la red del perfil
y el JSON de alternativas, campo a campo) da 422 antes de encolar. La carpeta de fuentes normativas llega por
``fuentes`` (en la app, la variable ``CSG_FUENTES_NORMATIVAS``); sin ella, el libro F-000 no sale y se dice por qué.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any, Callable, Mapping

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..pit import PitError
from ..pit.ambito import areas_del_perfil, reunir
from ..pit.armado import armar_expediente, leer_alternativas
from ..pit.diagnostico import diagnosticar, emergencia_rm129, limites_de_tension, limites_del_estudio
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


class PedidoExpediente(BaseModel):
    workspace_id: str
    area: str
    periodo: str = Field(min_length=1)
    anios: list[int] = Field(min_length=1)
    libro_red: str
    proyeccion: str
    alternativas: str | None = None
    alternativa_elegida: str | None = None
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
                 normativa: Path, *, licencia: Callable[[], bool] = lambda: False,
                 fuentes: Callable[[], Path | None] = lambda: None) -> APIRouter:
    """``jobs``: la cola de la web (``JobManager``); ``espacio``: carpeta de un espacio; ``perfil``: el activo;
    ``fuentes``: la carpeta de fuentes normativas, o ``None``."""
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
            registro = cargar_registro(normativa)
            limites = limites_del_estudio(registro, datos)
            emergencia_rm129(datos)  # true sin sustento es un 422 antes de encolar (107 T7, PIT-TEN v2)
        except PitError as exc:
            raise HTTPException(422, str(exc)) from None
        if motor == 'digsilent':
            raise HTTPException(409, 'el diagnóstico con DIgSILENT corre con tools/pit_pf.py en su carril')

        def trabajo(ctx) -> dict[str, Any]:
            elementos = leer_libro_red(libro, cfg)
            red = desde_ambito(reunir(area, elementos))
            red.avisos.extend(elementos.avisos)  # las hojas que no se tomaron, con su nombre (107:RF-12)
            filas = json.loads(proyeccion.read_text(encoding='utf-8'))
            # La tensión, por barra desde la norma; los huecos y las referencias van a la respuesta (107 T7, PIT-TEN).
            diag = diagnosticar(area, red, filas, p.anios, limites, motor=motor, cancel=ctx.cancel,
                                on_progress=lambda i, n, anio: ctx.progress(i, n, f'año {anio}'),
                                tension=limites_de_tension(red, area, registro, datos))
            salida = raiz / 'expedientes_pit' / area.codigo / 'diagnostico_de_trabajo.json'
            salida.parent.mkdir(parents=True, exist_ok=True)
            publicar_duradero(salida, json.dumps(diag.como_dict(), ensure_ascii=False, indent=1, sort_keys=True,
                                                 default=str) + '\n')
            return {'salida': str(salida), 'completo': diag.completo, 'avisos': diag.avisos,
                    'huecos_tension': diag.huecos_tension, 'referencias': diag.referencias}

        job = jobs.submit(p.workspace_id, 'pit_diagnostico', f'Diagnóstico PIT {area.codigo}', trabajo,
                          lane='engine')
        return {'job': job.id}

    @r.post('/expediente')
    def expediente(p: PedidoExpediente) -> dict[str, Any]:
        raiz = espacio(p.workspace_id)
        libro, proyeccion = _dentro(raiz, p.libro_red), _dentro(raiz, p.proyeccion)
        ruta_alternativas = _dentro(raiz, p.alternativas) if p.alternativas else None
        datos = perfil()
        try:
            motor = elegir_motor(p.motor, licencia())
            area = areas_del_perfil(datos, p.area)[0]
            if not (datos.get('pit') or {}).get('libro_red'):
                raise PitError('pit.libro_red: el perfil no describe el libro de la red')
            for ruta, campo in ((libro, 'libro_red'), (proyeccion, 'proyeccion'), (ruta_alternativas, 'alternativas')):
                if ruta is not None and not ruta.is_file():
                    raise PitError(f'{campo}: {ruta.name} no está en el espacio de trabajo')
            alternativas = None
            if p.alternativa_elegida and ruta_alternativas is None:
                raise PitError('alternativa_elegida: hay alternativa elegida y no hay alternativas')
            if ruta_alternativas is not None:
                try:
                    alternativas = json.loads(ruta_alternativas.read_text(encoding='utf-8'))
                except (OSError, json.JSONDecodeError) as exc:
                    raise PitError(f'alternativas: {ruta_alternativas.name} no es un JSON ({exc})') from None
                nombres = [a['nombre'] for a in leer_alternativas(alternativas)]
                if p.alternativa_elegida not in nombres:
                    raise PitError(f'alternativa_elegida: {p.alternativa_elegida!r} no está en {nombres}')
            registro = cargar_registro(normativa)
        except PitError as exc:
            raise HTTPException(422, str(exc)) from None
        if motor == 'digsilent':
            raise HTTPException(409, 'el expediente con DIgSILENT corre con tools/pit_pf.py en su carril')

        def trabajo(ctx) -> dict[str, Any]:
            filas = json.loads(proyeccion.read_text(encoding='utf-8'))
            return armar_expediente(raiz, datos, registro, area=area.codigo, periodo=p.periodo, anios=p.anios,
                                    libro_red=libro, proyeccion=filas, fecha_apertura=date.today().isoformat(),
                                    alternativas=alternativas, alternativa_elegida=p.alternativa_elegida,
                                    fuentes=fuentes(), motor=motor, cancel=ctx.cancel, on_progress=ctx.progress)

        job = jobs.submit(p.workspace_id, 'pit_expediente', f'Expediente PIT {area.codigo} {p.periodo}', trabajo,
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
