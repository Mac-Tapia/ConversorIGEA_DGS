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
import re
from datetime import date
from pathlib import Path
from typing import Any, Callable, Mapping

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from ...dominio.pit import PitError
from ...dominio.pit.ambito import areas_del_perfil, reunir
from ...adaptadores.pit.armado import armar_expediente, leer_alternativas
from ...adaptadores.pit.diagnostico import diagnosticar, emergencia_rm129, limites_de_tension, limites_del_estudio
from ...adaptadores.pit.motores import ESTUDIOS, MOTORES, capacidad, elegir_motor
from ...dominio.pit.observaciones import escribir_observaciones, registrar
from ...aplicacion.pit.red_area import desde_ambito, leer_libro_red
from ...dominio.registro_normativo import cargar_registro
from ...dominio.util import nombre_seguro, publicar_duradero  # 001:RF-5 (H14): escritura atómica y duradera

__all__ = ['crear_router']


class PedidoDiagnostico(BaseModel):
    workspace_id: str
    area: str
    anios: list[int] = Field(min_length=1)
    #: Cada entrada, por su ruta en el espacio o por su fuente de la empresa (109:RF-25); sin ninguna, la vigente.
    libro_red: str | None = None
    proyeccion: str | None = None
    fuente_red_area: str | None = None
    fuente_proyeccion: str | None = None
    motor: str | None = None


class PedidoExpediente(BaseModel):
    workspace_id: str
    area: str
    periodo: str = Field(min_length=1)
    anios: list[int] = Field(min_length=1)
    libro_red: str | None = None
    proyeccion: str | None = None
    alternativas: str | None = None
    fuente_red_area: str | None = None
    fuente_proyeccion: str | None = None
    fuente_alternativas: str | None = None
    alternativa_elegida: str | None = None
    motor: str | None = None


class PedidoObservaciones(BaseModel):
    workspace_id: str
    expediente: str
    observaciones: list[dict[str, Any]]
    referencias: dict[str, dict[str, Any]]


#: 070:RF-79: lo que se sube para el PIT (el libro de la red, la proyección y las alternativas), con su tope por fichero.
EXTENSIONES_ENTRADA = ('.xlsx', '.xlsm', '.xls', '.xlsb', '.json')  # los cuatro libros del lector común
TOPE_ENTRADA = 200 * 2 ** 20
CARPETA_ENTRADAS = 'entradas_pit'
_RESERVADOS = re.compile(r'^(con|prn|aux|nul|com[1-9]|lpt[1-9])$', re.IGNORECASE)


def _dentro(raiz: Path, relativa: str) -> Path:
    ruta = (raiz / relativa).resolve()
    if not ruta.is_relative_to(raiz.resolve()):
        raise HTTPException(400, f'{relativa}: fuera del espacio de trabajo')
    return ruta


def _relativa(raiz: Path, ruta: str | Path) -> str | None:
    """La ruta de una salida dentro del espacio, con «/», para que el panel la descargue (107 T13); fuera, ``None``."""
    try:
        return Path(ruta).resolve().relative_to(raiz.resolve()).as_posix()
    except ValueError:
        return None


def _entrada(raiz: Path, relativa: str | None, fuente: str | None, clase: str, campo: str, *,
             vigente: bool = True) -> Path | None:
    """107:RF-19: una entrada del PIT por su ruta en el espacio, por su fuente de la empresa o, si se pide, la vigente de
    su clase (109:RF-25). Sin ninguna: ``None`` si es opcional; si no, el error dice qué falta."""
    from ...aplicacion import fuentes_empresa as fe

    if relativa:
        return _dentro(raiz, relativa)
    try:
        if fuente:
            return fe.ruta(raiz, fuente)
    except fe.FuenteError as exc:
        raise HTTPException(404, f'{campo}: {exc}') from None
    vig = fe.vigente(raiz, clase) if vigente else None
    if vig is not None:
        return fe.ruta(raiz, vig.id)
    if not vigente:
        return None
    raise PitError(f'{campo}: falta el libro «{clase}» de la empresa: súbalo una vez y lo usan todos los módulos')


def crear_router(jobs: Any, espacio: Callable[[str], Path], perfil: Callable[[], Mapping[str, Any]],
                 normativa: Path, *, licencia: Callable[[], bool] = lambda: False,
                 fuentes: Callable[[], Path | None] = lambda: None) -> APIRouter:
    """``jobs``: la cola de la web (``JobManager``); ``espacio``: carpeta de un espacio; ``perfil``: el activo;
    ``fuentes``: la carpeta de fuentes normativas, o ``None``."""
    r = APIRouter(prefix='/api/pit', tags=['pit'])

    @r.get('/areas')
    def areas() -> dict[str, Any]:
        try:
            datos = perfil()
            # 107:RF-19: la empresa del perfil, para avisar si la red convertida del espacio es de otra.
            return {'areas': [{'codigo': a.codigo, 'titulares': list(a.titulares), 'set': list(a.set)}
                              for a in areas_del_perfil(datos)],
                    'empresa': str(datos.get('empresa') or datos.get('perfil') or '')}
        except PitError as exc:
            # 107:RF-19 (revisión web del 19-11): un perfil sin áreas del PIT es un estado esperado al abrir la pestaña,
            # no un error: lista vacía con su motivo; antes, un 422 que el navegador apuntaba como error de consola.
            return {'areas': [], 'empresa': '', 'motivo': str(exc)}

    @r.get('/capacidades')
    def capacidades() -> dict[str, Any]:
        return {'motores': list(MOTORES), 'licencia': licencia(),
                'matriz': [{'motor': m, 'estudio': e, 'alcance': capacidad(m, e).alcance,
                            'texto': capacidad(m, e).texto} for m in MOTORES for e in ESTUDIOS]}

    @r.post('/entradas')
    async def entradas(workspace_id: str = Form(...), files: list[UploadFile] = File(...)) -> dict[str, Any]:
        """070:RF-79: el libro de la red, la proyección y las alternativas, dentro del espacio, para pedir el diagnóstico
        o el expediente con sus rutas. Las rutas del PIT solo leen ficheros del espacio."""
        carpeta = espacio(workspace_id) / CARPETA_ENTRADAS
        rutas = []
        for f in files:
            nombre = Path(f.filename or '').name
            raiz = Path(nombre).stem
            if not nombre or Path(nombre).suffix.lower() not in EXTENSIONES_ENTRADA:
                raise HTTPException(422, f'{nombre or "un fichero sin nombre"}: el PIT admite libros de Excel y JSON')
            if nombre_seguro(raiz) != raiz or _RESERVADOS.match(raiz):
                # Lección A8 del 16-11: los nombres reservados de Windows y los caracteres raros no entran en el espacio.
                raise HTTPException(422, f'{nombre}: el nombre solo puede llevar letras, dígitos, «-» y «_»')
            datos = await f.read(TOPE_ENTRADA + 1)
            if len(datos) > TOPE_ENTRADA:
                raise HTTPException(413, f'{nombre}: pasa de {TOPE_ENTRADA // 2 ** 20} MiB')
            carpeta.mkdir(parents=True, exist_ok=True)
            publicar_duradero(carpeta / nombre, datos)
            rutas.append(f'{CARPETA_ENTRADAS}/{nombre}')
        return {'rutas': rutas}

    @r.post('/diagnostico')
    def diagnostico(p: PedidoDiagnostico) -> dict[str, Any]:
        raiz = espacio(p.workspace_id)
        datos = perfil()
        try:
            libro = _entrada(raiz, p.libro_red, p.fuente_red_area, 'red_area', 'libro_red')
            proyeccion = _entrada(raiz, p.proyeccion, p.fuente_proyeccion, 'proyeccion', 'proyeccion')
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
                                tension=limites_de_tension(red, area, registro, datos), registro=registro)
            salida = raiz / 'expedientes_pit' / area.codigo / 'diagnostico_de_trabajo.json'
            salida.parent.mkdir(parents=True, exist_ok=True)
            publicar_duradero(salida, json.dumps(diag.como_dict(), ensure_ascii=False, indent=1, sort_keys=True,
                                                 default=str) + '\n')
            return {'salida': str(salida), 'salida_relativa': _relativa(raiz, salida), 'completo': diag.completo,
                    'avisos': diag.avisos,
                    'huecos_tension': diag.huecos_tension, 'referencias': diag.referencias}

        job = jobs.submit(p.workspace_id, 'pit_diagnostico', f'Diagnóstico PIT {area.codigo}', trabajo,
                          lane='engine')
        return {'job': job.id}

    @r.post('/expediente')
    def expediente(p: PedidoExpediente) -> dict[str, Any]:
        raiz = espacio(p.workspace_id)
        datos = perfil()
        try:
            libro = _entrada(raiz, p.libro_red, p.fuente_red_area, 'red_area', 'libro_red')
            proyeccion = _entrada(raiz, p.proyeccion, p.fuente_proyeccion, 'proyeccion', 'proyeccion')
            # Las alternativas no se toman solas: solo las que se nombran.
            ruta_alternativas = _entrada(raiz, p.alternativas, p.fuente_alternativas, 'alternativas', 'alternativas',
                                         vigente=False)
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
            res = armar_expediente(raiz, datos, registro, area=area.codigo, periodo=p.periodo, anios=p.anios,
                                   libro_red=libro, proyeccion=filas, fecha_apertura=date.today().isoformat(),
                                   alternativas=alternativas, alternativa_elegida=p.alternativa_elegida,
                                   fuentes=fuentes(), motor=motor, cancel=ctx.cancel, on_progress=ctx.progress)
            # 107 T13: el panel descarga las salidas y pide las observaciones con rutas del espacio.
            relativas = {k: _relativa(raiz, v) for k, v in res['salidas'].items()}
            return {**res, 'carpeta_relativa': _relativa(raiz, res['carpeta']),
                    'salidas_relativas': {k: v for k, v in relativas.items() if v is not None}}

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
