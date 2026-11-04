"""API HTTP del conversor: FastAPI sobre el motor ``convertersmartgrid``, sin reescribirlo.

Las rutas validan, encolan y responden; el trabajo lo hacen :mod:`.services` y el
motor. El progreso y el Registro llegan al navegador por un WebSocket por espacio
de trabajo (``/api/workspaces/{id}/ws``), numerado para que una reconexión no pierda
ni duplique líneas.

Si existe ``frontend/dist`` (``npm run build``), se sirve en ``/`` y la aplicación
entera queda en un solo proceso y un solo puerto.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import sys
import threading
from contextlib import asynccontextmanager
from datetime import date, datetime
from pathlib import Path
from typing import Any, Literal

from fastapi import (
    BackgroundTasks, FastAPI, File, Form, HTTPException, Query, Request, UploadFile, WebSocket,
    WebSocketDisconnect,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .. import __version__, sesion_web
from ..edicion import estado_edicion, es_edicion_producto
from ..identify import comprobar_ranura, identificar
from ..powerfactory_env import project_root
from ..preview import politica_pagina_generada
from ..runtime_paths import rutas_runtime, staging_publicacion, temporal_administrado
from . import services
from .copia_datos import estado_copia
from .jobs import FINISHED, JobManager
from .seguridad import AlcanceEdicion, instalar_seguridad
from .api_contract import (JobRespuesta, HealthRespuesta, EspacioRespuesta,
    ResumenEspacioRespuesta, EntradaAsignadaRespuesta, AutoEntradasRespuesta,
    ArchivoRespuesta, AmbitoFuenteRespuesta, EstadoPowerFactoryRespuesta)
from .services import UserError
from .workspace import (
    BOOL_OPTIONS, DEFAULT_OPTIONS, MAX_WORKERS, SLOTS, EspacioNoUtilizable, Workspace, WorkspaceStore, safe_filename,
)


LOOPBACK_HOSTS = frozenset({'127.0.0.1', 'localhost', '::1'})


def _cerrar_entrenamiento_vigilado(proceso, gemelo: bool, herramienta: str) -> None:
    """Avanza el corte de datos solo si el entrenamiento en segundo plano terminó bien."""
    from ..asistente import almacen

    codigo = proceso.wait()
    if codigo == 0:
        services.asistente_marcar_entrenado(gemelo)
        return
    almacen.anotar('avisos', {
        'clave': f'entrenamiento:{herramienta}',
        'nivel': 'error',
        'texto': f'{herramienta} terminó con código {codigo}; los datos nuevos quedan pendientes.',
    })


def _sin_tumbar_la_web(anotar, *args) -> None:
    """Un registro que no se puede escribir no impide abrir ni cerrar la web (081:RF-42)."""
    try:
        anotar(*args)
    except OSError as exc:
        print(f'No se pudo anotar el arranque o el cierre: {exc}', file=sys.stderr)


def _suite_viva(fila) -> bool:
    """Si vive el proceso que escribió esa fila de la suite (081:RF-41), también con su número reutilizado."""
    from ..pf_arnes import dueno_vivo

    return bool(fila.get('pid')) and dueno_vivo(fila)


def arrancar_vigilancia(jobs: JobManager):
    """La vigilancia del asistente mientras la web está abierta (026:RF-22 a RF-25)."""
    import subprocess

    from ..asistente import almacen
    from ..asistente.vigilancia import Vigilante
    from ..powerfactory_env import tools_dir

    def reintentar(job_id: str) -> None:
        j = jobs.get(job_id)
        if j is not None:
            jobs.submit(j.workspace_id, j.kind, f'{j.title} (reintento)', j.fn, lane=j.lane)

    def lanzar(herramienta: str, gemelo: bool) -> None:
        if es_edicion_producto():                                              # 086:RF-15
            return
        # En su propio proceso, como desde la web (024): un fallo de la GPU no tumba el servidor.
        salida = almacen.raiz() / f'vigilancia_{herramienta}.json'
        salida.parent.mkdir(parents=True, exist_ok=True)
        proceso = subprocess.Popen(
            [sys.executable, str(tools_dir() / f'{herramienta}.py'), '--output-json', str(salida)],
            cwd=str(project_root()), creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
        )
        threading.Thread(
            target=_cerrar_entrenamiento_vigilado,
            args=(proceso, gemelo, herramienta),
            name=f'csg-{herramienta}',
            daemon=True,
        ).start()

    v = Vigilante(listar_trabajos=lambda: [j.public() for j in jobs.list()], reintentar=reintentar,
                  entrenar_gemelo=lambda: lanzar('digital_twin_entrenar', True),
                  entrenar_asistente=lambda: lanzar('asistente_entrenar', False),
                  # 071:RF-6: hasta que haya un solo pipeline por modelo, no lanza entrenamientos
                  # ni anuncia que reentrena, salvo que se pida.
                  contar_nuevos=(services.asistente_nuevos if os.environ.get('CSG_AUTOENTRENAMIENTO') == '1'
                                 else (lambda: (0, 0))),
                  repo=project_root(), proceso_vivo=_suite_viva)
    v.arrancar()
    return v


def _server_paths_allowed(host: str | None) -> bool:
    """Si se puede indicar una ruta del disco del servidor en lugar de subir el fichero.

    Útil en local —la base .mdb pesa cientos de MB y ya está en el disco—, peligroso
    si el servidor se expone en red: cualquiera leería cualquier fichero. Antes lo
    decidía solo la variable ``CSG_WEB_SERVER_PATHS``, que valía ``1`` por defecto y
    que el lanzador ponía a ``0`` con ``setdefault``: con la variable ya a ``1``, o
    arrancando con ``uvicorn --host 0.0.0.0`` sin el lanzador, quedaban abiertas a la
    red (spec 001, RF-15). Ahora manda la interfaz de escucha, y si no se conoce, se
    cierran. La variable solo puede apagarlas en local, nunca abrirlas fuera.
    """
    if (host or '').strip().lower() not in LOOPBACK_HOSTS:
        return False
    return os.environ.get('CSG_WEB_SERVER_PATHS', '1').strip() not in ('0', 'false', 'no', '')


# Cabecera con la que el lanzador pide cerrar el servidor. Una cabecera propia obliga al
# navegador a una consulta CORS previa, que solo pasan los orígenes de desarrollo: una
# página cualquiera no puede cerrar el Conversor con un formulario.
CABECERA_LANZADOR = 'X-CSG-Lanzador'
#: Lo que el lanzador dice para el registro de cierres (081:RF-42).
CABECERA_MOTIVO = 'X-CSG-Motivo'
#: Quien lo cerró, si lo pidió alguien; si no, el servidor se cerró por señal o Ctrl+C.
_motivo_cierre: list[str] = []

_cierre: list = []


def al_pedir_cierre(fn) -> None:
    """Registra cómo se cierra este proceso; lo pone el lanzador, que tiene el servidor."""
    _cierre[:] = [fn]


def frontend_dist() -> Path:
    env = os.environ.get('CSG_WEB_FRONTEND', '').strip()
    return Path(env) if env else project_root() / 'frontend' / 'dist'


# ---------------------------------------------------------------------------
# Modelos de petición
# ---------------------------------------------------------------------------


class DescartarNoDisponibleIn(BaseModel):
    campo: str
    clave: str


class OptionsIn(BaseModel):
    input_mode: Literal['txt', 'mdb', 'vnr'] | None = None
    empresa_espacio: str | None = None                                          # 081:RF-51
    source_crs: str | None = None
    target_crs: str | None = None
    include_geography: bool | None = None
    strict: bool | None = None
    write_preview: bool | None = None
    export_xlsx: bool | None = None
    export_tsv: bool | None = None
    workers: int | None = Field(None, ge=0, le=MAX_WORKERS)
    hoja: Literal['A0', 'A1', 'A2', 'A3', 'A4'] | None = None


class ServerPathIn(BaseModel):
    path: str


# Libros de la demanda medida (spec 004, RF-39).
DemandaTipo = Literal['medidores', 'cabecera', 'suministros', 'clientes', 'estructura']


class DemandaMedidorIn(BaseModel):
    alimentador: str = ''
    medidor: str


class DemandaMedidoresIn(BaseModel):
    medidores: list[DemandaMedidorIn] = Field(default_factory=list)
    # Spec 013, RF-11: la máxima del mes elegido (AAAA-MM); 025:RF-7, la del año (AAAA);
    # vacío, la de todo el registro (solo sin carpetas de año, 025:RF-9).
    periodo: str | None = Field(None, pattern=r'^\d{4}(-(0[1-9]|1[0-2]))?$')
    # Spec 021, RF-50: en vez de la máxima, el registro de esta fecha y hora para todos.
    instante: datetime | None = None
    # Spec 022, RF-39 a RF-41: la máxima de cada barra de SET y sus alimentadores en esa fecha.
    por_barra: bool = False
    # 022:RF-88: las centrales (CT…) conectadas en un tramo de su alimentador, no en la barra:
    # {medidor: alimentador}.
    centrales_tramo: dict[str, str] = Field(default_factory=dict)
    # 028:RF-28: proyecto de alimentadores: su único instante de mayor demanda conjunta, con los
    # medidores de sus centrales: {alimentador: {generacion, llegada, salida}}.
    coincidente: bool = False
    centrales: dict[str, dict[str, str]] = Field(default_factory=dict)
    # 028:RF-31: análisis de sistema eléctrico: el instante común de sus barras de 60 kV (con por_barra).
    sistema_60kv: bool = False


class DemandaClientesIn(BaseModel):
    """Alimentadores de la máxima buscada: el cruce se queda con sus clientes (RF-43)."""

    alimentadores: list[str] = Field(default_factory=list)
    # Spec 013, RF-12: con una carpeta de libros mensuales, el mes que eligió el operador.
    periodo: str | None = Field(default=None, pattern=r'^\d{4}-(0[1-9]|1[0-2])$')
    # 035:RF-1: la máxima buscada de cada alimentador (fecha, kw, kvar, fp): sus clientes
    # con el registro de ese instante y lo que el ajuste escribirá.
    maximas: dict[str, dict[str, Any]] = Field(default_factory=dict)
    # 039:RF-1: las fijas coincidentes con la cabecera (por defecto) o su máximo del mes.
    criterio: Literal['coincidente', 'maximo_mes'] = 'coincidente'


class CompararFijasIn(BaseModel):
    """039:RF-5: los alimentadores de la máxima buscada y el proyecto de su última calibración."""

    project: str = ''
    alimentadores: list[str] = Field(default_factory=list, max_length=2000)
    periodo: str | None = Field(default=None, pattern=r'^\d{4}-(0[1-9]|1[0-2])$')
    maximas: dict[str, dict[str, Any]] = Field(default_factory=dict)


class TransformadoresIn(BaseModel):
    """020:RF-13: las SED marcadas de un alimentador del ajuste; 022:RF-62, las de varios
    a la vez (``por_alimentador``), con una sola recalibración del proyecto."""

    feeder: str = ''
    sed: list[str] = Field(default_factory=list, max_length=2000)
    por_alimentador: dict[str, list[str]] = Field(default_factory=dict)


class CentralIn(BaseModel):
    """Central térmica en el troncal de un alimentador (spec 021, RF-25)."""

    generacion: str = Field(min_length=1)
    llegada: str = Field(min_length=1)
    salida: str = Field(min_length=1)
    nodo: str = ''


class AjusteIn(BaseModel):
    """Ajuste a la máxima de cabecera (spec 006): el trabajo de la máxima que se ve."""

    project: str
    job_id: str
    medidor: str = ''
    # Spec 008, RF-12: un medidor por alimentador, en el orden de ajuste. Vacío: el de
    # ``medidor`` o, si cada alimentador de la máxima tiene uno, todos.
    medidores: list[str] = Field(default_factory=list, max_length=2000)
    # Spec 006, RF-26: Nis de los clientes importantes desmarcados en la tabla del cruce.
    desconectados: list[str] = Field(default_factory=list, max_length=20000)
    # 1 % por defecto; entre 0,1 % y 10 % (requisitos no funcionales de la spec 006).
    tolerancia: float = Field(0.01, ge=0.001, le=0.10)
    # Spec 021: la central de cada alimentador que la tiene, declarada en 2.2.
    centrales: dict[str, CentralIn] = Field(default_factory=dict)
    # Spec 021, RF-61: consigna de tensión de la fuente, en pu; vacío, la que tenga.
    tension_fuente_pu: float | None = Field(None, ge=0.9, le=1.1)
    # Spec 021, RF-64: poner los bancos que falten para el kVAR medido y recalibrar.
    completar_bancos: bool = False
    # 039:RF-1: el mismo criterio de las fijas que se eligió en la tabla cruzada.
    criterio_fijas: Literal['coincidente', 'maximo_mes'] = 'coincidente'


class VerificarIn(BaseModel):
    """Verificación de la convergencia (spec 008): el proyecto y los alimentadores a medir."""

    project: str
    feeders: list[str] = Field(default_factory=list, max_length=2000)


class DemandaExcelIn(BaseModel):
    """Lo que el operador ve en pantalla: el Excel no se arma con estado guardado (RF-38)."""

    cabecera: list[dict[str, Any]] = Field(default_factory=list)
    clientes: list[dict[str, Any]] = Field(default_factory=list)
    no_cruzados: list[dict[str, Any]] = Field(default_factory=list)


class BibliotecasIn(BaseModel):
    """Lectura de alimentadores y tipos para el formulario de obras (spec 011, RF-88 a RF-94)."""

    project: str
    feeders: list[str] = Field(default_factory=list, max_length=2000)
    otro_proyecto: str = ''
    clases: list[str] = Field(default_factory=list)


class ObrasIn(BaseModel):
    """Obras guardadas que se simulan o aplican; sin ``ids``, todas (spec 011)."""

    project: str
    feeders: list[str] = Field(default_factory=list, max_length=2000)
    ids: list[str] = Field(default_factory=list)
    otro_proyecto: str = ''
    # Spec 025, RF-41: las obras de los casos de ese año («Sin/Con proyecto 2025»).
    anio_casos: int | None = Field(None, ge=1900, le=2200)
    # Spec 025, RF-67: el tipo de cambio de los precios de pérdidas a la moneda del costo,
    # que escribe el operador; no sale del perfil.
    tipo_cambio: float | None = Field(None, gt=0, le=100_000)
    # Spec 025, RF-53: el libro CAPEX de la empresa, por su ruta en este equipo.
    capex: str = Field('', max_length=1000)
    # Spec 052, RF-19: el nombre de la SET nueva (p. ej. «SET COPARA»).
    set_nueva_nombre: str = Field('', max_length=40)
    # Sin escalera: todas las cargas nuevas a la SET nueva (usuario, 2026-11-01).
    directo_set_nueva: bool = False
    # 042:RF-17: el operador pide la escalera aunque las cargas pasen del umbral del perfil.
    escalera_primero: bool = False
    # 063:RF-23: la evaluación de la conexión de estas cargas nuevas (por su nombre); sin ellas, todas.
    cargas: list[str] = Field(default_factory=list, max_length=500)
    # Spec 042, RF-6: cuántos alimentadores nuevos puede tener la SET nueva.
    alimentadores_nuevos: int = Field(4, ge=1, le=20)


class SetNuevaOperacionIn(BaseModel):
    """063:RF-36 a RF-38: diagnosticar o reforzar una SET existente, sin recrearla."""

    project: str = Field(min_length=1)
    feeders: list[str] = Field(default_factory=list, max_length=2000)
    accion: Literal['diagnostico', 'evaluar', 'aplicar'] = 'diagnostico'
    cambios: list[dict[str, Any]] = Field(default_factory=list, max_length=1000)
    desactivar_variaciones: list[str] = Field(default_factory=list, max_length=1000)
    sincronizar_cargas: bool = False
    conciliar_fases: bool = False
    verificar_flujos: bool = False
    salidas: list[dict[str, Any]] = Field(default_factory=list, max_length=1000)
    ajustes_flujo: dict[str, int] = Field(default_factory=dict)
    limites: dict[str, float] = Field(default_factory=dict)
    limite_s: float = Field(1200, ge=30, le=86400)
    reabrir: bool = True


class EstudiosIn(BaseModel):
    """Plan de los estudios sobre la base del último ajuste aplicado (spec 011, RF-12, RF-25)."""

    project: str
    feeders: list[str] = Field(default_factory=list, max_length=2000)
    estudios: list[str] = Field(default_factory=list)
    ajuste_job_id: str | None = None
    limites: dict[str, float] = Field(default_factory=dict)
    # RF-39: límite por estudio y caso, entre 10 s y un día.
    limite_s: float | None = Field(None, ge=10, le=86400)
    # Spec 012: objetivo y máximos de reconectadores (RF-37), crecimiento conjunto (RF-45) y
    # contingencias de las curvas PV (RF-53).
    opciones: dict[str, Any] = Field(default_factory=dict)


class DatosEmpresaAplicarIn(BaseModel):
    """Escribir el libro de la empresa en el proyecto (spec 012, RF-21)."""

    project: str
    feeders: list[str] = Field(default_factory=list, max_length=2000)


class InformeEstudioIn(BaseModel):
    """Formulario del informe de estudio (spec 017): todo dato del cliente y del encabezado
    sale de aquí; del modelo de la empresa solo se toma la forma."""

    alimentador: str
    # Los flujos de 4.2 de ese proyecto: un espacio puede haber estudiado otro antes.
    project: str = ''
    fecha: str | None = None
    lugar: str = ''
    numero: str = ''
    asunto: str = ''
    destinatario: str = ''
    antecedentes: list[str] = Field(default_factory=list, max_length=200)
    descripcion: list[str] = Field(default_factory=list, max_length=200)
    limites: dict[str, float] = Field(default_factory=dict)
    # 086:RF-35: las bandas de coloreado que el perfil no da.
    bandas: dict[Literal['tension', 'cargabilidad'], list[float]] = Field(default_factory=dict)
    anio: int | None = None
    imagenes: dict[str, dict[str, str | None]] = Field(default_factory=dict)


class SolicitudIn(BaseModel):
    """Datos de la solicitud de la carga nueva (017:RF-51); el servidor los valida antes de
    empezar (RF-96), para no escribir un Word con antecedentes en blanco."""

    cliente: str = Field(min_length=1)
    ubicacion: str = Field(min_length=1)
    tipo_solicitud: str = Field(min_length=1)
    potencia_kw: float = Field(gt=0)
    fecha_solicitud: date
    set_nombre: str = Field(min_length=1)
    tension_kv: float = Field(gt=0)
    transformador: str = ''
    expediente: str = ''
    en_concesion: bool | None = None
    #: 063:RF-14, RF-15, RF-18: potencia previa de una ampliación, código interno de la
    #: ficha y NIS. El Word ya los escribía, pero la web no los recibía.
    potencia_actual_kw: float | None = Field(None, ge=0)
    codigo_ficha: str = ''
    nis: str = ''


class PuntoFichaIn(BaseModel):
    """063:RF-17: datos del punto de diseño que da la ficha; no son resultados del flujo."""

    pcc_mva: float | None = Field(None, gt=0)
    utm_x: float | None = None
    utm_y: float | None = None


class PerdidasReconocidasIn(BaseModel):
    """Lo que daría el libro de pérdidas de la empresa (RF-62), escrito a mano."""

    sistema_electrico: str = ''
    codigo_sistema: str = ''
    reconocido_kw_pct: float | None = Field(None, ge=0, le=100)
    reconocido_kwh_pct: float | None = Field(None, ge=0, le=100)
    precio_compra: float | None = Field(None, ge=0)


class TransformadorSetIn(BaseModel):
    """Cargabilidad del devanado de la SET (RF-66), leída por el operador en el proyecto
    de transmisión mientras el guion no la obtiene solo (T10 de la spec 017)."""

    kv: float | None = Field(None, gt=0)
    sin_pct: float | None = Field(None, ge=0)
    con_pct: float | None = Field(None, ge=0)
    caso: str = ''


class TransformadorListarIn(BaseModel):
    """Proyecto de transmisión; vacío, el del perfil de empresa (017:RF-95)."""

    transmision: str = ''


class TransformadorCalcularIn(BaseModel):
    """Carga de la barra de la SET en el proyecto de transmisión y su caso (017:RF-65b)."""

    project: str = Field(min_length=1)
    alimentador: str = Field(min_length=1)
    carga: str = Field(min_length=1)
    caso: str = ''
    transmision: str = ''


class InformeFormularioIn(BaseModel):
    """Lo escrito en un formulario de 4.4, para no perderlo al recargar (017:RF-82)."""

    project: str = Field(min_length=1)
    tipo: Literal['estudio', 'factibilidad']
    datos: dict[str, Any] = Field(default_factory=dict)


class InformeFactibilidadIn(BaseModel):
    """Formulario del informe de factibilidad y punto de diseño (spec 017, RF-47 a RF-72)."""

    project: str = Field(min_length=1)
    alimentador: str = Field(min_length=1)
    sed: str = Field(min_length=1)
    fecha: str | None = None
    lugar: str = ''
    numero: str = ''
    asunto: str = ''
    destinatario: str = ''
    solicitud: SolicitudIn
    limites: dict[str, float] = Field(default_factory=dict)
    # 086:RF-35: las bandas de coloreado que el perfil no da.
    bandas: dict[Literal['tension', 'cargabilidad'], list[float]] = Field(default_factory=dict)
    factor_carga: float | None = Field(None, gt=0, le=1)
    perdidas_reconocidas: PerdidasReconocidasIn = Field(default_factory=PerdidasReconocidasIn)
    transformador_set: TransformadorSetIn = Field(default_factory=TransformadorSetIn)
    codigo_punto: str = ''
    punto_ficha: PuntoFichaIn = Field(default_factory=PuntoFichaIn)
    #: 063:RF-1: el botón prepara los casos y corre sus flujos en el mismo trabajo; ``False``
    #: escribe con los flujos ya guardados (las pruebas sin DIgSILENT, o rehacer el Word).
    preparar_casos: bool = True


class VistaUbicacionIn(BaseModel):
    """Vista previa de la ubicación del cliente nuevo (spec 017, RF-124)."""

    project: str = Field(min_length=1)
    alimentador: str = Field(min_length=1)
    sed: str = Field(min_length=1)
    cliente: str = ''
    potencia_kw: float | None = Field(None, gt=0)
    codigo_punto: str = ''


class TransferenciaIn(BaseModel):
    """Transferencia de carga entre dos alimentadores (spec 011, RF-104)."""

    project: str
    feeders: list[str] = Field(default_factory=list, max_length=2)
    casos: list[str] = Field(default_factory=lambda: ['Sin proyecto'])
    limites: dict[str, float] = Field(default_factory=dict)
    # 013:RF-22: la máxima de cabecera buscada en 2.2, con su periodo y sus curvas; sin
    # ella, la última.
    cabecera_job_id: str | None = None


class GuionesIn(BaseModel):
    """Guiones DPL y Python del operador en el proyecto (spec 011, RF-27)."""

    project: str


class GuionIn(BaseModel):
    """Un guion del operador en los casos elegidos, con sus parámetros (RF-28)."""

    project: str
    nombre: str
    origen: Literal['caso', 'proyecto'] = 'caso'
    parametros: dict[str, str] = Field(default_factory=dict)
    casos: list[str] = Field(default_factory=lambda: ['Sin proyecto', 'Con proyecto'])
    limite_s: float | None = Field(None, ge=10, le=86400)
    #: 086:RF-25: el guion hace en la red lo que quiera, y lo decide quien lo escribió: lo dice quien pulsa.
    confirmado: bool = False


class AsistenteOrdenIn(BaseModel):
    """Spec 026, RF-1: la orden escrita."""

    texto: str = Field(min_length=1, max_length=2000)


class AsistenteCorregirIn(BaseModel):
    """Spec 026, RF-15: lo que el operador corrige del plan."""

    tarea: str | None = None
    datos: dict[str, Any] = Field(default_factory=dict)
    tipo_informe: Literal['estudio', 'factibilidad'] | None = None
    subtipo: str | None = Field(None, max_length=200)


class AsistenteLibreriaIn(BaseModel):
    paquete: str = Field(min_length=1, max_length=100, pattern=r'^[A-Za-z0-9._-]+$')
    motivo: str = Field(min_length=1, max_length=1000)


class AsistenteDecisionIn(BaseModel):
    decision: Literal['aceptada', 'rechazada', 'modificada']
    comentario: str = Field('', max_length=2000)


class VnrDownloadIn(BaseModel):
    publication_id: str


class SourceScopeIn(BaseModel):
    company: str | None = None
    period: str | None = None


class SelectionIn(BaseModel):
    feeders: list[str] = Field(default_factory=list)
    all: bool = False
    # Unir la selección en UN solo DGS (red unida), con este nombre.
    unir: bool = False
    nombre: str = ''


class AgenteProyectoListaIn(BaseModel):
    """027:RF-43: el proyecto desde cero de un sistema eléctrico; 067:RF-37: la lista de sus etapas."""

    sistema: str = Field(min_length=1)
    periodo: str = Field(pattern=r'^\d{4}(-\d{2})?$')
    ruta: str | None = None
    ruta_cargas: str | None = None
    formulario: dict[str, Any] | None = None
    reiniciar: bool = False


class AgenteProyectoIn(AgenteProyectoListaIn):
    """067:RF-38: la orden trae la huella de la lista que el operador vio."""

    confirmacion: str = Field(min_length=64, max_length=64)


class RecalibrarIn(BaseModel):
    """028:RF-21, RF-24: recalibrar el sistema o los alimentadores del proyecto ya importado."""

    project: str = Field(min_length=1)
    periodo: str = Field(pattern=r'^\d{4}(-(0[1-9]|1[0-2]))?$')
    zonal: str | None = None
    demanda_dir: str | None = None
    transformadores: bool = False
    # 039:RF-1: el criterio de las fijas, el mismo de la tabla cruzada.
    criterio_fijas: Literal['coincidente', 'maximo_mes'] = 'coincidente'


class EscaneoIn(BaseModel):
    """Spec 028: alimentadores de un proyecto de DIgSILENT a escanear."""

    project: str = Field(min_length=1)
    feeders: list[str] = Field(min_length=1)
    anio: int | None = None


class SistemaIn(BaseModel):
    """Spec 022, RF-48: los zonales a convertir; vacío, todos. RF-61: los alimentadores a
    reconstruir con su medida y las medidas de los demás, en kW."""

    zonales: list[str] = Field(default_factory=list)
    sets: list[str] = Field(default_factory=list)          # 022:RF-82: una SET sola
    reconstruir: dict[str, float] = Field(default_factory=dict)
    medidas_kw: dict[str, float] = Field(default_factory=dict)


class FeedersIn(BaseModel):
    feeders: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Aplicación
# ---------------------------------------------------------------------------


def create_app(
    data_root: Path | None = None, *, host: str | None = None, vnr_settings=None,
) -> FastAPI:
    """La API web, la única (spec 001, RF-11).

    ``host`` es la interfaz donde escucha el servidor; sin él se lee ``CSG_WEB_HOST``,
    que pone el lanzador, y si tampoco está, se trata como red (RF-15).
    ``vnr_settings`` configura las rutas de VNR.
    """
    if host is None:
        host = os.environ.get('CSG_WEB_HOST') or None
    store = WorkspaceStore(data_root)
    errores_observacion: dict[str,str] = {}

    def emit(workspace_id: str, kind: str, data: dict) -> None:
        ws = store.get(workspace_id)
        if ws is not None:
            if kind=='job':
                from ..asistente.observacion import RegistroOperaciones
                import sqlite3
                try:
                    RegistroOperaciones(ws.out_dir/'observacion/operaciones.sqlite3',ws.id).anotar(
                        data,services.contexto_observacion(ws))
                except (OSError,ValueError,TypeError,sqlite3.Error) as exc:
                    errores_observacion[workspace_id]=str(exc)
                    ws.events.append('log',{'job':data.get('id'),'text':f'Observación incompleta: {exc}'})
                    if data.get('status')=='queued':raise OSError('No se pudo registrar la operación nueva') from exc
                # 067:RF-1: todo trabajo pasa por aquí, también los que encola el asistente.
                if data.get('status') in ('done','parcial','no_converge') and (aviso:=services.asistente_custodiar_trabajo(ws,data)):
                    ws.events.append('log',{'job':data.get('id'),'text':aviso})
            ws.events.append(kind, data)

    # 086:RF-9: lo que quede a medias se ve tras reiniciar; vive junto a los espacios.
    jobs = JobManager(emit, diario=store.root / '_trabajos')
    from .retencion import RetencionDiaria
    retencion = RetencionDiaria(store, jobs)
    from .runtime import huella_del_codigo

    huella = huella_del_codigo(frontend_dist())
    # Páginas conectadas por WebSocket (001:RF-35). Solo se toca desde el bucle de eventos.
    paginas = {'abiertas': 0}

    from .cierre import anotar_arranque, anotar_cierre

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        # Solo el servidor real (``__main__`` pone la variable): las pruebas crean la app a
        # cientos y no deben vigilar ni correr la suite de noche.
        vigilante = arrancar_vigilancia(jobs) if os.environ.get('CSG_ASISTENTE_VIGILANCIA') == '1' else None
        if vigilante is not None:                                              # 081:RF-42, RF-43
            _sin_tumbar_la_web(anotar_arranque, huella)
        detener_retencion = asyncio.Event()
        tarea_retencion = asyncio.create_task(retencion.vigilar(detener_retencion))
        try:
            yield
        finally:
            detener_retencion.set()
            await tarea_retencion
            if vigilante is not None:
                _sin_tumbar_la_web(anotar_cierre, _motivo_cierre[0] if _motivo_cierre else 'señal, Ctrl+C o cierre de la ventana')
                vigilante.parar()
            await asyncio.to_thread(jobs.shutdown)

    # Sin /docs ni /redoc: traen su página de un CDN, una salida a la red que nadie pidió (086:RF-22).
    app = FastAPI(title='ConverterSmartGrid', version=__version__, lifespan=lifespan,
                  docs_url=None, redoc_url=None)
    app.state.store = store
    app.state.jobs = jobs
    app.state.retencion = retencion

    from vnr_etl.web.app import create_router

    # Las rutas de VNR-GIS son parte de esta API y usan su cola de trabajos.
    app.include_router(create_router(store.root, jobs, vnr_settings))

    # Solo el servidor de desarrollo de Vite. En producción el front se sirve desde
    # este mismo origen y CORS no interviene.
    dev_origins = os.environ.get('CSG_WEB_DEV_ORIGINS',
                                 '' if es_edicion_producto() else 'http://localhost:5173,http://127.0.0.1:5173')
    origenes_dev = tuple(o.strip() for o in dev_origins.split(',') if o.strip())
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(origenes_dev),
        allow_methods=['*'], allow_headers=['*'],
    )
    # 086:RF-16: dentro de la puerta: una petición sin sesión no llega a saber qué se vende y qué no.
    app.add_middleware(AlcanceEdicion)
    # Por fuera de CORS, y de todo lo demás: Host, Origin, token y política de contenido (086:RF-17 a RF-21).
    if sesion_web.EXIGIR_SEGURIDAD:
        instalar_seguridad(app, origenes_dev)

    @app.exception_handler(UserError)
    async def _user_error(_request: Request, exc: UserError):
        return JSONResponse(status_code=400, content={'detail': str(exc)})

    def ws_or_404(wid: str) -> Workspace:
        ws = store.get(wid)
        if ws is None:
            # 086:RF-2, RF-5: uno dañado o más nuevo existe: dice qué le pasa, no «no encontrado».
            problema = store.problema(wid)
            if problema:
                raise HTTPException(409, problema['motivo'])
            raise HTTPException(404, 'Espacio de trabajo no encontrado.')
        return ws

    # Comprobar el carril y encolar van juntos: las rutas corren en hilos distintos, y dos
    # clics seguidos (o dos pestañas) pasaban los dos la comprobación y encolaban dos veces.
    encolando = threading.Lock()

    def submit(ws: Workspace, kind: str, title: str, fn, *, lane: str = 'engine') -> dict:
        with encolando:
            # 047:RF-24: los vectores del índice ceden ante cualquier orden, no la rechazan.
            busy = [j for j in jobs.active(ws.id) if j.lane == lane and j.kind != 'asistente_indice']
            if busy:
                raise HTTPException(409, f'Ya hay un trabajo en curso en este espacio: «{busy[0].title}». '
                                         'Espere a que termine o cancélelo.')
            try:
                return jobs.submit(ws.id, kind, title, fn, lane=lane).public()
            except OSError as exc:
                raise HTTPException(503,str(exc)) from exc

    # ------------------------------------------------------------ sistema
    @app.get('/api/health', response_model=HealthRespuesta, response_model_exclude_unset=True)
    def health() -> dict:
        return {
            'version': __version__,
            'capabilities': services.capabilities(),
            'crs_presets': services.crs_presets(),
            'perfil_empresa': services.perfil_info(),
            'slots': SLOTS,
            'default_options': DEFAULT_OPTIONS,
            'server_paths': _server_paths_allowed(host),
            'parallel': services.parallel_info(),
            'source_modes': ['txt', 'mdb', 'vnr'],
            # Para el lanzador (spec 001, RF-28 a RF-30): si este servidor es el mismo
            # código, si se puede cerrar sin perder trabajo y qué proceso es.
            'servidor': {'pid': os.getpid(), 'huella': huella,
                         'trabajos_en_curso': jobs.en_curso(),
                         # RF-35: con una página conectada, el lanzador no abre otra pestaña.
                         'paginas_abiertas': paginas['abiertas'],
                         # 081:RF-44: de qué carpeta es; un lanzador de otra no lo sustituye.
                         'raiz': str(project_root())},
            # 086:RF-47: el aviso de que la última copia de los datos es vieja o no existe.
            'copia_datos': estado_copia(store.root),
            'edicion': estado_edicion(),                                       # 086:RF-16
        }

    @app.post('/api/sistema/cerrar', status_code=202)
    def cerrar_servidor(request: Request) -> dict:
        """El lanzador pide cerrar este servidor para arrancar otra versión (RF-29, RF-33)."""
        cliente = request.client.host if request.client else ''
        if request.headers.get(CABECERA_LANZADOR) != '1' or cliente not in LOOPBACK_HOSTS:
            raise HTTPException(403, 'Solo el lanzador de esta máquina puede cerrar el servidor.')
        en_curso = jobs.en_curso()
        if en_curso:
            raise HTTPException(409, f'Hay {en_curso} trabajo(s) en curso: no se cierra.')
        if not _cierre:
            raise HTTPException(503, 'Este servidor no admite el cierre por petición.')
        _motivo_cierre[:] = [request.headers.get(CABECERA_MOTIVO) or 'petición del lanzador, sin motivo']
        # Tras responder: si se cierra antes, el lanzador ve la conexión cortada.
        threading.Timer(0.2, _cierre[0]).start()
        return {'cerrando': True}

    @app.get('/api/powerfactory', response_model=EstadoPowerFactoryRespuesta, response_model_exclude_unset=True)
    def powerfactory(refresh: bool = False) -> dict:
        return services.powerfactory_status(refresh=refresh)

    # ------------------------------------------------------------ catálogo VNR oficial
    def _vnr_catalog_dir() -> Path:
        return store.root / '_vnr_catalog'

    @app.get('/api/vnr/publications')
    def vnr_publications(refresh: bool = False) -> dict:
        from vnr_etl.discovery.catalog import PublicationCatalog
        from vnr_etl.discovery.official import (
            PORTAL_VNR, is_allowed_official_url, is_vnr_data_package,
            publication_evidence_sha256, refresh_official_catalog, vigentes_por_empresa,
        )

        report = None
        if refresh:
            raise HTTPException(409, 'Inicie la búsqueda como trabajo desde el espacio de trabajo.')
        catalog = PublicationCatalog.load(_vnr_catalog_dir())

        def es_paquete(publication) -> bool:
            return (is_vnr_data_package(publication)
                    and is_allowed_official_url(publication.download_url))

        # La vigencia la decide el servidor; la interfaz solo la muestra (080:RF-9).
        por_empresa = vigentes_por_empresa(p for p in catalog.publications() if es_paquete(p))
        rows = []
        for publication in catalog.publications():
            convertible = es_paquete(publication)
            grupo = por_empresa.get(publication.publication_id, {})
            rows.append({
                **publication.as_dict(),
                'empresa': grupo.get('empresa', publication.company),
                'vigente': grupo.get('vigente', False),
                'convertible': convertible,
                'status': (
                    'OFFICIAL_DATA_PACKAGE' if convertible
                    else 'REGULATORY_DOCUMENT_ONLY'
                ),
                'evidence_sha256': publication_evidence_sha256(publication),
            })
        available = any(row['convertible'] for row in rows)
        return {
            'status': (
                'OFFICIAL_PACKAGE_AVAILABLE' if available
                else 'BLOCKED_MISSING_OFFICIAL_PACKAGE'
            ),
            'publications': rows,
            'portal': PORTAL_VNR,
            'refresh': report,
        }

    @app.post('/api/workspaces/{wid}/vnr/publications/refresh', status_code=202, response_model=JobRespuesta, response_model_exclude_unset=True)
    def vnr_publications_refresh(wid: str) -> dict:
        from vnr_etl.discovery.official import refresh_official_catalog

        def refresh(ctx):
            ctx.check_cancel()
            ctx.progress(0, 1, 'Consultar las publicaciones oficiales')
            _catalog, report = refresh_official_catalog(_vnr_catalog_dir())
            ctx.check_cancel()
            ctx.progress(1, 1, 'Catálogo actualizado')
            return {**vnr_publications(), 'refresh': report}

        return submit(ws_or_404(wid), 'vnr_publications', 'Buscar publicación oficial VNR', refresh)

    # ------------------------------------------------------------ espacios
    @app.get('/api/workspaces', response_model=list[ResumenEspacioRespuesta], response_model_exclude_unset=True)
    def list_workspaces() -> list[dict]:
        return store.list()

    @app.post('/api/workspaces', status_code=201, response_model=EspacioRespuesta, response_model_exclude_unset=True)
    def create_workspace() -> dict:
        return store.create().public()

    @app.get('/api/workspaces/{wid}', response_model=EspacioRespuesta, response_model_exclude_unset=True)
    def get_workspace(wid: str) -> dict:
        ws = ws_or_404(wid)
        return {**ws.public(), 'jobs': [j.public() for j in jobs.list(wid)[-20:]]}

    @app.get('/api/workspaces/{wid}/runs')
    def source_runs(wid: str) -> list[dict]:
        """Historial inmutable de fuentes, limitado al espacio solicitado."""
        from .source_runs import load_source_run, valid_run_id

        ws = ws_or_404(wid)
        root = ws.root / 'runs'
        rows: list[dict] = []
        for folder in root.iterdir() if root.is_dir() else ():
            if not folder.is_dir() or not valid_run_id(folder.name):
                continue
            try:
                snapshot = load_source_run(ws, folder.name)
            except (OSError, ValueError, KeyError, TypeError):
                continue
            rows.append({
                'run_id': snapshot.run_id,
                'mode': snapshot.mode,
                'created_at': snapshot.created_at,
                'fingerprint': snapshot.fingerprint,
                'files': len(snapshot.files),
                'active': snapshot.run_id == ws.active_run_id,
                'manifest_url': f'/api/workspaces/{wid}/runs/{snapshot.run_id}/manifest',
            })
        return sorted(rows, key=lambda row: (row['created_at'], row['run_id']), reverse=True)

    @app.get('/api/workspaces/{wid}/runs/{run_id}/manifest')
    def source_manifest(wid: str, run_id: str) -> dict:
        """Manifiesto público sin revelar rutas originales del servidor."""
        from .source_runs import load_source_run, valid_run_id

        ws = ws_or_404(wid)
        if not valid_run_id(run_id):
            raise HTTPException(404, 'Ejecución no encontrada.')
        try:
            snapshot = load_source_run(ws, run_id)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise HTTPException(404, 'Ejecución no encontrada.') from exc
        return {
            'version': 1,
            'run_id': snapshot.run_id,
            'mode': snapshot.mode,
            'created_at': snapshot.created_at,
            'fingerprint': snapshot.fingerprint,
            'files': [
                {
                    'slot': item.slot,
                    'name': item.name,
                    'size': item.size,
                    'sha256': item.sha256,
                    'origin': item.origin,
                }
                for item in sorted(snapshot.files.values(), key=lambda item: item.slot)
            ],
        }

    @app.post('/api/workspaces/{wid}/restaurar-copia', response_model=EspacioRespuesta, response_model_exclude_unset=True)
    def restaurar_copia_espacio(wid: str) -> dict:
        """086:RF-2: un espacio dañado vuelve a su copia anterior; lo dañado se aparta."""
        try:
            return store.restaurar_copia(wid).public()
        except EspacioNoUtilizable as exc:
            raise HTTPException(409, str(exc)) from exc
        except OSError as exc:
            raise HTTPException(500, f'No se pudo restaurar la copia: {exc}') from exc

    @app.post('/api/workspaces/{wid}/no-disponibles/descartar', response_model=EspacioRespuesta, response_model_exclude_unset=True)
    def descartar_no_disponible(wid: str, body: DescartarNoDisponibleIn) -> dict:
        """086:RF-3: el operador da por perdida una referencia a un fichero que no volverá."""
        ws = ws_or_404(wid)
        if not ws.descartar_no_disponible(body.campo, body.clave):
            raise HTTPException(404, 'Esa referencia no está entre las no disponibles.')
        return ws.public()

    @app.delete('/api/workspaces/{wid}', status_code=204)
    def delete_workspace(wid: str) -> None:
        ws = ws_or_404(wid)
        if jobs.active(ws.id):
            raise HTTPException(409, 'Hay trabajos en curso en este espacio.')
        store.delete(wid)

    @app.put('/api/workspaces/{wid}/options', response_model=EspacioRespuesta, response_model_exclude_unset=True)
    def put_options(wid: str, body: OptionsIn) -> dict:
        ws = ws_or_404(wid)
        changes = {
            key: value
            for key, value in body.model_dump(exclude_unset=True).items()
            if value is not None or key == 'hoja'
        }
        for key in ('source_crs', 'target_crs'):
            if key in changes:
                changes[key] = changes[key].strip()
        warning = ''
        crs = changes.get('source_crs')
        if crs and services.capabilities()['geography']:
            from ..geography import assert_metre_source_crs

            try:
                assert_metre_source_crs(crs)
            except ValueError as exc:
                # Se guarda igual —el operador puede estar escribiendo—, pero se avisa
                # ya; convertir con él se rechaza en check_convert_options.
                warning = str(exc)
        with ws.lock:
            if 'input_mode' in changes and changes['input_mode'] != ws.options['input_mode']:
                ws.invalidate()
            ws.options.update(changes)
            for key in BOOL_OPTIONS:
                ws.options[key] = bool(ws.options[key])
            ws.save()
        return {**ws.public(), 'warning': warning}

    @app.get('/api/workspaces/{wid}/source-scope', response_model=AmbitoFuenteRespuesta, response_model_exclude_unset=True)
    def get_source_scope(wid: str) -> dict:
        from .source_scope import inspect_package_scope

        ws = ws_or_404(wid)
        package = ws.input_path('vnr_package')
        if not package:
            raise HTTPException(409, 'Asigne primero un paquete VNR-GIS.')
        try:
            return inspect_package_scope(
                package,
                selected_company=ws.options.get('source_company'),
                selected_period=ws.options.get('source_period'),
            ).as_dict()
        except ValueError as exc:
            raise UserError(str(exc)) from exc

    @app.put('/api/workspaces/{wid}/source-scope', response_model=AmbitoFuenteRespuesta, response_model_exclude_unset=True)
    def put_source_scope(wid: str, body: SourceScopeIn) -> dict:
        from .source_scope import inspect_package_scope

        ws = ws_or_404(wid)
        package = ws.input_path('vnr_package')
        if not package:
            raise HTTPException(409, 'Asigne primero un paquete VNR-GIS.')
        try:
            scope = inspect_package_scope(
                package, selected_company=body.company, selected_period=body.period,
            )
        except ValueError as exc:
            raise UserError(str(exc)) from exc
        if scope.ambiguous:
            raise UserError('SOURCE_SCOPE_SELECTION_REQUIRED')
        with ws.lock:
            ws.invalidate()
            ws.options['source_company'] = scope.selected_company
            ws.options['source_period'] = scope.selected_period
            ws.save()
        return scope.as_dict()

    # ------------------------------------------------------------ entradas
    def _check_slot(slot: str) -> dict:
        spec = SLOTS.get(slot)
        if spec is None:
            raise HTTPException(404, f'Casilla desconocida: {slot}')
        return spec

    def _assign(ws: Workspace, slot: str, path: Path, origin: str) -> dict:
        spec = SLOTS[slot]
        if slot == 'vnr_package':
            from vnr_etl.discovery.official import (
                OfficialDiscoveryError, validate_vnr_package_file,
            )

            try:
                validate_vnr_package_file(path)
            except OfficialDiscoveryError as exc:
                raise UserError(str(exc)) from exc
        group = str(spec.get('grupo') or '')
        if group in ('txt', 'mdb') and slot != 'study':
            # 059:RF-3: cada casilla, con un fichero de su fuente. Una base Access en la casilla
            # de un TXT (o al revés) se rechaza; lo no reconocido sigue con su aviso.
            from ..identify import FUENTE_MDB, FUENTE_TXT, fuente_de

            fuente = fuente_de(path).fuente
            if fuente in (FUENTE_TXT, FUENTE_MDB, 'vnr') and fuente != group:
                nombres = {'txt': 'un TXT de CYMDIST', 'mdb': 'una base Access',
                           'vnr': 'un paquete VNR-GIS'}
                raise UserError(f'«{path.name}» es {nombres[fuente]} y la casilla '
                                f'«{spec["etiqueta"]}» es de {nombres[group]}.')
        warning = comprobar_ranura(path, spec['tipo']) if spec['tipo'] else ''
        meta = ws.set_input(slot, path, origin=origin, warning=warning)
        if group in ('txt', 'mdb', 'vnr'):
            # La fuente es la del fichero asignado (059:RF-3); otra fuente, otro dataset.
            with ws.lock:
                if ws.options.get('input_mode') != group:
                    ws.invalidate()
                ws.options['input_mode'] = group
                ws.save()
        ws.events.append('log', {'text': f'Archivo asignado a {slot}: {path.name}'
                                 + (f'  (AVISO: {warning.splitlines()[0]})' if warning else '')})
        return {'slot': slot, **meta, 'workspace': ws.public()}

    def _save_upload(target: Path, upload: UploadFile) -> None:
        from .operaciones_lentas import presupuesto

        limit = presupuesto('CSG_UPLOAD_MAX_BYTES', 16 * 1024 ** 3)
        target.parent.mkdir(parents=True, exist_ok=True)
        with staging_publicacion(target) as tmp:
            size = 0
            with tmp.open('xb') as fh:
                while block := upload.file.read(1024 * 1024):
                    size += len(block)
                    if size > limit:
                        raise HTTPException(413, 'El archivo supera la cuota de almacenamiento de subida.')
                    fh.write(block)
            tmp.replace(target)

    @app.post('/api/workspaces/{wid}/inputs/{slot}', response_model=EntradaAsignadaRespuesta, response_model_exclude_unset=True)
    def upload_input(wid: str, slot: str, file: UploadFile = File(...)) -> dict:
        ws = ws_or_404(wid)
        _check_slot(slot)
        target = ws.upload_target(slot, file.filename or slot)
        _save_upload(target, file)
        try:
            return _assign(ws, slot, target, 'upload')
        except Exception:
            target.unlink(missing_ok=True)
            raise

    @app.post('/api/workspaces/{wid}/inputs/{slot}/path', response_model=EntradaAsignadaRespuesta, response_model_exclude_unset=True)
    def server_path_input(wid: str, slot: str, body: ServerPathIn) -> dict:
        ws = ws_or_404(wid)
        _check_slot(slot)
        if not _server_paths_allowed(host):
            raise HTTPException(403, 'Este servidor no admite rutas locales: suba el fichero.')
        path = Path(body.path.strip().strip('"'))
        if not path.is_file():
            raise HTTPException(400, f'No existe el fichero: {path}')
        return _assign(ws, slot, path, 'server')

    @app.delete('/api/workspaces/{wid}/inputs/{slot}', response_model=EspacioRespuesta, response_model_exclude_unset=True)
    def delete_input(wid: str, slot: str) -> dict:
        ws = ws_or_404(wid)
        _check_slot(slot)
        ws.clear_input(slot)
        return ws.public()

    @app.post('/api/workspaces/{wid}/vnr/download', status_code=202,
              response_model=JobRespuesta, response_model_exclude_unset=True)
    def download_vnr(wid: str, body: VnrDownloadIn) -> dict:
        from vnr_etl.discovery.catalog import PublicationCatalog
        from vnr_etl.discovery.download import (
            DownloadCancelled, DownloadError, DownloadManager, extraer_copia_sql,
        )
        from vnr_etl.discovery.official import (
            DEFAULT_ALLOWED_HOSTS, is_allowed_official_url, is_vnr_data_package,
            validate_vnr_package_file,
        )

        ws = ws_or_404(wid)
        catalog = PublicationCatalog.load(_vnr_catalog_dir())
        publication = catalog.get(body.publication_id)
        if publication is None:
            raise UserError(f'Publicación VNR desconocida: {body.publication_id}.')
        if not is_vnr_data_package(publication):
            raise UserError(
                f'{publication.file_name or publication.title} no es un paquete de datos VNR-GIS.'
            )
        if not is_allowed_official_url(publication.download_url):
            raise UserError('La descarga no pertenece a un host oficial permitido.')
        target = ws.upload_target('vnr_package', publication.file_name or 'vnr_package.zip')
        def download(ctx):
            from .operaciones_lentas import presupuesto

            ctx.check_cancel()
            ctx.progress(0, 1, 'Descargar y verificar el paquete oficial')
            manager = DownloadManager(
                ws.inputs_dir / '_vnr_downloads',
                max_file_size_bytes=presupuesto('CSG_UPLOAD_MAX_BYTES', 16 * 1024 ** 3),
                verify_archive=True,
                allowed_hosts=DEFAULT_ALLOWED_HOSTS,
            )
            try:
                manifest = manager.download(
                    publication.download_url, target,
                    publication_id=publication.publication_id,
                    company=publication.company, period=publication.period_label,
                    cancelled=ctx.cancel.is_set,
                    on_progress=lambda n, total: ctx.progress(n, total or n or 1, 'Descargar paquete oficial'),
                )
                ctx.check_cancel()
                validate_vnr_package_file(target)
                # 080:RF-18: el paquete oficial es un comprimido con la copia dentro. Asignado
                # tal cual se trataría como un paquete de capas, y la copia no se cargaría.
                copia = extraer_copia_sql(
                    target, target.parent / target.stem, cancelled=ctx.cancel.is_set,
                    on_progress=lambda n, total: ctx.progress(n, total or 1, 'Extraer la copia de la base'),
                )
            except DownloadCancelled as exc:
                from .jobs import JobCancelled

                raise JobCancelled() from exc
            except DownloadError as exc:
                raise UserError(str(exc)) from exc
            ctx.check_cancel()
            assigned = _assign(ws, 'vnr_package', copia or target, 'upload')
            ctx.progress(1, 1, 'Paquete custodiado')
            return {**assigned, 'manifest': manifest.as_dict()}

        return submit(ws, 'vnr_download', 'Descargar paquete oficial VNR', download)

    @app.post('/api/workspaces/{wid}/inputs-auto', response_model=AutoEntradasRespuesta, response_model_exclude_unset=True)
    def auto_inputs(wid: str, files: list[UploadFile] = File(...)) -> dict:
        """Los TXT de la entrada TXT: cada uno a su casilla **por su contenido** (059:RF-3, RF-4).

        Los nombres de la distribuidora no siguen convención; lo que distingue un RED de
        un CARGA son las tablas que declara dentro. Esta zona es de la entrada TXT: una
        base Access o un paquete VNR-GIS soltados aquí no se asignan, se dice qué son y
        que van en su propia entrada. Si dos ficheros son del mismo tipo, el segundo queda
        sin asignar: mejor una casilla vacía que una equivocada.
        """
        from ..identify import FUENTE_TXT, fuente_de

        ws = ws_or_404(wid)
        staging = ws.inputs_dir / '_auto'
        staging.mkdir(parents=True, exist_ok=True)
        slot_of = {'red': 'red', 'carga': 'loads', 'equipos': 'equipment'}
        otra = {'mdb': 'una base Access: va en la entrada «Base Access (.mdb)»',
                'vnr': 'un paquete VNR-GIS: va en la entrada «VNR-GIS»'}
        assigned, unassigned, taken = [], [], set()
        for upload in files:
            tmp = staging / Path(upload.filename or 'fichero.txt').name
            _save_upload(tmp, upload)
            f = fuente_de(tmp)
            slot = slot_of.get(f.tipo) if f.fuente == FUENTE_TXT else None
            if slot is None or slot in taken:
                reason = ('tipo repetido' if slot else
                          f'es {otra[f.fuente]}' if f.fuente in otra else
                          'no declara tablas conocidas de CYMDIST')
                unassigned.append({'name': tmp.name, 'reason': reason})
                tmp.unlink(missing_ok=True)
                continue
            taken.add(slot)
            target = ws.upload_target(slot, tmp.name)
            tmp.replace(target)
            _assign(ws, slot, target, 'upload')
            assigned.append({'slot': slot, 'name': target.name})
        shutil.rmtree(staging, ignore_errors=True)
        return {'assigned': assigned, 'unassigned': unassigned, 'workspace': ws.public()}

    # ------------------------------------------------------------ carga y tabla
    @app.post('/api/workspaces/{wid}/load', status_code=202, response_model=JobRespuesta, response_model_exclude_unset=True)
    def load(wid: str) -> dict:
        ws = ws_or_404(wid)
        services.check_ready(ws)
        return submit(ws, 'load', 'Cargar / listar alimentadores',
                      lambda ctx: services.load_dataset(ws, ctx))

    @app.get('/api/workspaces/{wid}/feeders')
    def feeders(wid: str) -> dict:
        ws = ws_or_404(wid)
        return {'loaded': ws.dataset is not None, 'feeders': services.feeder_rows(ws)}

    @app.get('/api/workspaces/{wid}/feeders/{feeder}/sed')
    def feeder_sed(wid: str, feeder: str) -> dict:
        """070:RF-45: las SED de un alimentador, de su modelo, sin abrir DIgSILENT."""
        return services.sed_de_alimentador(ws_or_404(wid), feeder)

    def _check_selection(ws: Workspace, body: SelectionIn) -> list[str]:
        # Lo que falla por la petición falla aquí, con 400, y no como trabajo fallido.
        from .reconstruction_service import resolve_selection

        services.require_loaded(ws)
        services.require_active_source_run(ws)
        names, _ = resolve_selection(ws, body.feeders, all_feeders=body.all)
        return names

    @app.post('/api/workspaces/{wid}/diagnose', status_code=202, response_model=JobRespuesta, response_model_exclude_unset=True)
    def diagnose(wid: str, body: SelectionIn) -> dict:
        from .reconstruction_service import diagnose_selection

        ws = ws_or_404(wid)
        names = _check_selection(ws, body)
        return submit(ws, 'diagnose', f'Diagnosticar {len(names)} alimentador(es)',
                      lambda ctx: diagnose_selection(
                          ws, body.feeders, all_feeders=body.all, ctx=ctx))

    @app.post('/api/workspaces/{wid}/reconstruct', status_code=202, response_model=JobRespuesta, response_model_exclude_unset=True)
    def reconstruct(wid: str, body: SelectionIn) -> dict:
        from .reconstruction_service import reconstruct_selection

        ws = ws_or_404(wid)
        names = _check_selection(ws, body)
        return submit(ws, 'reconstruct', f'Reconstruir {len(names)} alimentador(es)',
                      lambda ctx: reconstruct_selection(
                          ws, body.feeders, all_feeders=body.all, ctx=ctx))

    # Spec 022, RF-47 a RF-51: la conversión por sistema eléctrico, una opción propia.
    @app.get('/api/workspaces/{wid}/estructura')
    def estructura(wid: str) -> dict:
        ws = ws_or_404(wid)
        services.require_loaded(ws)
        return services.estructura_resumen(ws)

    @app.post('/api/workspaces/{wid}/convert/sistema', status_code=202, response_model=JobRespuesta, response_model_exclude_unset=True)
    def convert_sistema(wid: str, body: SistemaIn) -> dict:
        ws = ws_or_404(wid)
        services.check_ready(ws)
        services.check_convert_options(ws)
        feeders, nombre, estructura = services.sistema_seleccion(ws, body.zonales, body.sets)
        return submit(ws, 'convert_group', f'Sistema eléctrico {nombre}.dgs ({len(feeders)} alimentadores)',
                      lambda ctx: services.convert_group(
                          ws, ctx, feeders, nombre, requested_feeders=feeders,
                          estructura=estructura, tipo='sistema',
                          reconstruir=({'pedidos': body.reconstruir, 'medidas_kw': body.medidas_kw}
                                       if body.reconstruir else None)))

    @app.post('/api/workspaces/{wid}/convert', status_code=202, response_model=JobRespuesta, response_model_exclude_unset=True)
    def convert(wid: str, body: SelectionIn) -> dict:
        ws = ws_or_404(wid)
        services.check_ready(ws)
        services.require_loaded(ws)
        if not body.all and not body.feeders:
            raise UserError('Seleccione al menos un alimentador, o convierta todos.')
        services.check_convert_options(ws)
        if body.unir:
            feeders = services.group_selection(ws, body.feeders, body.all)
            nombre = services.group_name(body.nombre, feeders)
            requested = feeders if body.all else body.feeders
            return submit(ws, 'convert_group', f'Unir {len(feeders)} alimentadores en {nombre}.dgs',
                          lambda ctx: services.convert_group(
                              ws, ctx, feeders, nombre, requested_feeders=requested))
        n = len(ws.inventory['feeders']) if body.all and ws.inventory else len(body.feeders)
        title = f'Convertir {"TODOS" if body.all else ""} {n} alimentador(es) a DGS'.replace('  ', ' ')
        return submit(ws, 'convert', title,
                      lambda ctx: services.convert(ws, ctx, body.feeders, body.all))

    # ------------------------------------------------------------ trabajos y registro
    @app.get('/api/jobs/{job_id}', response_model=JobRespuesta, response_model_exclude_unset=True)
    def get_job(job_id: str) -> dict:
        job = jobs.get(job_id)
        if job is None:
            raise HTTPException(404, 'Trabajo no encontrado.')
        return job.public()

    @app.get('/api/jobs/{job_id}/registro')
    def registro_job(job_id: str, ultimas: int = Query(2000, ge=1, le=20000)) -> dict:
        """086:RF-9: el registro de un trabajo, también de uno interrumpido antes de reiniciar."""
        if jobs.get(job_id) is None:
            raise HTTPException(404, 'Trabajo no encontrado.')
        return {'job': job_id, 'lineas': jobs.registro(job_id, ultimas) or []}

    @app.post('/api/jobs/{job_id}/cancel', response_model=JobRespuesta, response_model_exclude_unset=True)
    def cancel_job(job_id: str) -> dict:
        job = jobs.cancel(job_id)
        if job is None:
            raise HTTPException(404, 'Trabajo no encontrado.')
        return job.public()

    @app.get('/api/workspaces/{wid}/events')
    def events(wid: str, since: int = 0) -> list[dict]:
        return ws_or_404(wid).events.since(since)

    @app.websocket('/api/workspaces/{wid}/ws')
    async def events_ws(websocket: WebSocket, wid: str, since: int = 0) -> None:
        ws = store.get(wid)
        if ws is None:
            await websocket.close(code=4404)
            return
        await websocket.accept()
        # 001:RF-35: cada pestaña abierta tiene su WebSocket; el lanzador lo lee en /api/health.
        paginas['abiertas'] += 1
        seq = since
        try:
            while True:
                batch = await asyncio.to_thread(ws.events.wait, seq, 15.0)
                if batch:
                    await websocket.send_json(batch)
                    seq = batch[-1]['seq']
                else:
                    await websocket.send_json([])  # latido: detecta conexiones muertas
        except (WebSocketDisconnect, RuntimeError):
            return
        finally:
            paginas['abiertas'] -= 1

    # ------------------------------------------------------------ salida
    def _safe_out(ws: Workspace, rel: str) -> Path:
        target = (ws.out_dir / rel).resolve()
        root = ws.out_dir.resolve()
        if target != root and root not in target.parents:
            raise HTTPException(400, 'Ruta fuera de la carpeta de salida.')
        return target

    @app.get('/api/workspaces/{wid}/outputs', response_model=list[ArchivoRespuesta], response_model_exclude_unset=True)
    def outputs(wid: str) -> list[dict]:
        ws = ws_or_404(wid)
        root = ws.out_dir
        if not root.is_dir():
            return []
        rows = []
        for path in sorted(root.rglob('*')):
            if not path.is_file() or any(p.startswith('.csg-stage-') for p in path.parts):
                continue
            try:
                st = path.stat()
            except FileNotFoundError:
                # El ``-wal`` de SQLite de la observación (spec 061) desaparece al cerrarse la
                # base: listado en el ``rglob``, ya no está en el ``stat`` (suite del
                # 2026-11-02, test_sin_georreferenciacion). Un fichero que se fue no se lista.
                continue
            rows.append({'path': path.relative_to(root).as_posix(), 'size': st.st_size,
                         'modified': st.st_mtime})
        return rows

    @app.get('/api/workspaces/{wid}/files/{rel:path}')
    def get_file(wid: str, rel: str, download: bool = False) -> FileResponse:
        ws = ws_or_404(wid)
        path = _safe_out(ws, rel)
        if not path.is_file():
            raise HTTPException(404, 'Fichero no encontrado.')
        media = 'text/html' if path.suffix.lower() == '.html' and not download else None
        # 086:RF-21: una página generada lleva dentro textos de la entrega; aislada, no llega a la API.
        cabeceras = {'Content-Security-Policy': politica_pagina_generada()} if media else None
        return FileResponse(path, media_type=media, headers=cabeceras,
                            filename=path.name if download or media is None else None)

    @app.post('/api/workspaces/{wid}/outputs/archive', status_code=202, response_model=JobRespuesta, response_model_exclude_unset=True)
    def outputs_archive(wid: str, body: FeedersIn) -> dict:
        from .operaciones_lentas import preparar_zip

        ws = ws_or_404(wid)
        source = ws.out_dir.resolve()
        wanted = tuple(body.feeders)
        return submit(ws, 'archive', 'Preparar descarga ZIP',
                      lambda ctx: preparar_zip(ws.id, source, wanted, ctx))

    @app.get('/api/workspaces/{wid}/outputs.zip')
    def outputs_zip(wid: str, background: BackgroundTasks, job: str = Query(...)) -> FileResponse:
        from .operaciones_lentas import retirar_zip

        ws_or_404(wid)
        item = jobs.get(job)
        if item is None or item.workspace_id != wid or item.kind != 'archive':
            raise HTTPException(404, 'Descarga no encontrada en este espacio.')
        path = getattr(item, '_archivo_zip', None)
        if item.status != 'done' or path is None:
            raise HTTPException(409, 'La descarga todavía no está preparada.')
        expected = (rutas_runtime().runtime / 'descargas' / wid / ('csg-job-' + job) / 'salida.zip').resolve()
        if path.resolve() != expected or path.is_symlink():
            raise HTTPException(409, 'La descarga no coincide con su trabajo.')
        if not path.is_file():
            raise HTTPException(410, 'Esta descarga ya fue entregada o expiró. Prepare una nueva.')
        background.add_task(retirar_zip, path, job, wid)
        return FileResponse(path, filename=item.result['nombre'], media_type='application/zip')

    # ------------------------------------------------------------ PowerFactory
    @app.post('/api/workspaces/{wid}/powerfactory/flow', status_code=202, response_model=JobRespuesta, response_model_exclude_unset=True)
    def pf_flow(wid: str, body: FeedersIn) -> dict:
        ws = ws_or_404(wid)
        targets = services.powerfactory_targets(ws, body.feeders)
        services.check_powerfactory_flow(ws, targets)
        return submit(ws, 'powerfactory', f'DigSILENT: import + flujo ({len(targets)})',
                      lambda ctx: services.powerfactory_flow(ws, ctx, targets),
                      lane='powerfactory')

    # ------------------------------------------------------------ cargas en DIgSILENT
    # Spec 004: un módulo aparte de la conversión. No pide entradas cargadas: la web
    # valida los libros y el guion decide en el proyecto de DIgSILENT (RF-1).
    temporales_subida = {}

    def _upload_tmp(ws: Workspace, upload: UploadFile, default: str) -> Path:
        manager = temporal_administrado(propietario=f'subida:{ws.id}')
        folder = manager.__enter__()
        name = Path(upload.filename or default).name
        suffix = Path(name).suffix.lower() or Path(default).suffix
        target = folder / ('entrada' + suffix)
        try:
            _save_upload(target, upload)
        except BaseException:
            manager.__exit__(*sys.exc_info())
            raise
        temporales_subida[target] = manager
        return target

    def _limpiar_upload(path: Path) -> None:
        manager = temporales_subida.pop(path, None)
        if manager is not None:
            manager.__exit__(None, None, None)

    def _json_form(texto: str | None, campo: str) -> dict | None:
        try:
            valor = json.loads(texto) if texto else None
        except ValueError as exc:
            raise HTTPException(422, f'{campo} no es JSON válido: {exc}') from exc
        if valor is not None and not isinstance(valor, dict):
            raise HTTPException(422, f'{campo} debe ser un objeto JSON.')
        return valor

    @app.get('/api/workspaces/{wid}/cargas/plantilla/{tipo}')
    def cargas_plantilla(wid: str, tipo: Literal['demandas', 'nuevas'],
                         format: Literal['xlsx', 'csv'] = 'xlsx') -> FileResponse:
        path = services.cargas_plantilla(ws_or_404(wid), tipo, format)
        return FileResponse(path, filename=path.name)

    @app.post('/api/workspaces/{wid}/powerfactory/projects', status_code=202, response_model=JobRespuesta, response_model_exclude_unset=True)
    def pf_projects(wid: str) -> dict:
        ws = ws_or_404(wid)
        return submit(ws, 'pf_projects', 'Leer proyectos de DIgSILENT',
                      lambda ctx: services.pf_projects(ws, ctx), lane='powerfactory')

    # Spec 028, RF-9: escanear alimentadores antes de recalibrar (solo lectura).
    @app.post('/api/workspaces/{wid}/powerfactory/escanear', status_code=202, response_model=JobRespuesta, response_model_exclude_unset=True)
    def pf_escanear(wid: str, body: EscaneoIn) -> dict:
        ws = ws_or_404(wid)
        quien = body.feeders[0] if len(body.feeders) == 1 else f'{len(body.feeders)} alim.'
        return submit(ws, 'pf_escaneo', f'Escanear {quien} · {body.project}',
                      lambda ctx: services.escanear_alimentadores(ws, ctx, body.project, body.feeders,
                                                                  body.anio),
                      lane='powerfactory')

    # Spec 028, RF-21: recalibrar, aparte de la calibración inicial. Corre ``sistema_web.py``,
    # que usa el carril de DIgSILENT por la API: va en el carril del asistente, o se esperaría a sí mismo.
    @app.get('/api/workspaces/{wid}/demanda/recalibrar')
    def recalibrar_datos(wid: str, project: str) -> dict:
        return services.recalibrar_datos(ws_or_404(wid), project)

    @app.post('/api/workspaces/{wid}/demanda/recalibrar', status_code=202, response_model=JobRespuesta, response_model_exclude_unset=True)
    def recalibrar(wid: str, body: RecalibrarIn) -> dict:
        ws = ws_or_404(wid)
        services.recalibrar_datos(ws, body.project)          # 028:RF-23, antes de encolar
        return submit(ws, 'recalibrar', f'Recalibrar · {body.project}',
                      lambda ctx: services.recalibrar_sistema(ws, ctx, body.project, body.periodo,
                                                              zonal=body.zonal, demanda_dir=body.demanda_dir,
                                                              transformadores=body.transformadores,
                                                              criterio_fijas=body.criterio_fijas),
                      lane='asistente')

    @app.get('/api/workspaces/{wid}/powerfactory/escaneo')
    def pf_escaneo_guardado(wid: str) -> dict:
        return {'escaneo': ws_or_404(wid).escaneo}

    # Spec 018, RF-13: la última lista leída, sin abrir DIgSILENT (los trabajos no sobreviven
    # a un reinicio de la web).
    @app.get('/api/workspaces/{wid}/powerfactory/projects')
    def pf_projects_guardados(wid: str) -> dict:
        return services.pf_proyectos_guardados(ws_or_404(wid))

    # Spec 007, RF-40: el último ajuste aplicado guardado en disco, para la base.
    @app.get('/api/workspaces/{wid}/demanda/ajuste/ultimo')
    def ajuste_ultimo(wid: str, project: str) -> dict:
        return {'ajuste': services.ajuste_aplicado_en_disco(ws_or_404(wid), project)}

    # Spec 018, RF-10: usar la ejecución fuente con la que se aceptó el proyecto. Carril del
    # motor: cambia la ejecución activa, y una conversión en marcha escribe en ella.
    @app.post('/api/workspaces/{wid}/powerfactory/adoptar-fuente', status_code=202, response_model=JobRespuesta, response_model_exclude_unset=True)
    def pf_adoptar_fuente(wid: str, body: VerificarIn) -> dict:
        ws = ws_or_404(wid)
        if not body.project.strip():
            raise HTTPException(422, 'Elija el proyecto de DIgSILENT.')
        return submit(ws, 'pf_adoptar_fuente', f'Usar la fuente de {body.project.strip()}',
                      lambda ctx: services.adoptar_fuente_del_vinculo(ws, body.project),
                      lane='engine')

    # Spec 015, RF-1 a RF-14: verificar el «Caso base» del proyecto, repetible tras corregir.
    @app.post('/api/workspaces/{wid}/powerfactory/caso-base', status_code=202, response_model=JobRespuesta, response_model_exclude_unset=True)
    def pf_verificar_base(wid: str, body: VerificarIn) -> dict:
        ws = ws_or_404(wid)
        if not body.project.strip():
            raise HTTPException(422, 'Elija el proyecto de DIgSILENT.')
        return submit(ws, 'pf_verificar_base', f'Verificar el Caso base · {body.project.strip()}',
                      lambda ctx: services.pf_verificar_base(ws, ctx, body.project, body.feeders),
                      lane='powerfactory')

    # Spec 008, RF-18: el flujo de carga con lo activo, antes de integrar cargas.
    @app.post('/api/workspaces/{wid}/powerfactory/verificar', status_code=202, response_model=JobRespuesta, response_model_exclude_unset=True)
    def pf_verificar(wid: str, body: VerificarIn) -> dict:
        ws = ws_or_404(wid)
        if not body.project.strip():
            raise HTTPException(422, 'Elija el proyecto de DIgSILENT.')
        return submit(ws, 'pf_verificar', f'Verificar la convergencia · {body.project.strip()}',
                      lambda ctx: services.pf_verificar(ws, ctx, body.project, body.feeders),
                      lane='powerfactory')

    @app.post('/api/workspaces/{wid}/lote/plan')
    def lote_plan(
        wid: str,
        project: str = Form(...),
        feeders: list[str] = Form(...),
        update_file: UploadFile | None = File(None),
        create_file: UploadFile | None = File(None),
        nueva: str | None = Form(None),
        economia: str | None = Form(None),
        ajuste_job_id: str | None = Form(None),
        # 016:RF-20, RF-73: a menos de esto de una barra, la carga se engancha en ella.
        minima_m: float | None = Form(None, ge=0, le=100_000),
    ) -> dict:
        ws = ws_or_404(wid)
        eco = _json_form(economia, 'economia')
        una = _json_form(nueva, 'nueva')
        ajuste = _ajuste_aplicado(wid, ajuste_job_id)
        tmps: list[Path] = []
        try:
            upd = cre = None
            if update_file:
                upd = _upload_tmp(ws, update_file, 'demandas.xlsx')
                tmps.append(upd)
            if create_file:
                cre = _upload_tmp(ws, create_file, 'cargas_nuevas.xlsx')
                tmps.append(cre)
            return services.cargas_plan(ws, project, feeders, upd, cre, una, eco, ajuste,
                                        minima_m=minima_m)
        finally:
            for p in tmps:
                _limpiar_upload(p)

    def _cargas_job(wid: str, token: str, simular: bool) -> dict:
        ws = ws_or_404(wid)
        if token not in ws.cargas_planes:
            raise HTTPException(404, 'El plan ya no existe: vuelva a prepararlo.')
        plan = services.cargas_plan_de(ws, token)
        verbo = 'Simular' if simular else 'Aplicar'
        title = f"{verbo} cargas · {plan['project']} ({len(plan['feeders'])} alim.)"
        return submit(ws, 'cargas_simular' if simular else 'cargas_aplicar', title,
                      lambda ctx: services.cargas_ejecutar(ws, ctx, token, simular=simular),
                      lane='powerfactory')

    @app.post('/api/workspaces/{wid}/lote/{token}/simular', status_code=202, response_model=JobRespuesta, response_model_exclude_unset=True)
    def lote_simular(wid: str, token: str) -> dict:
        return _cargas_job(wid, token, True)

    @app.post('/api/workspaces/{wid}/lote/{token}/apply', status_code=202, response_model=JobRespuesta, response_model_exclude_unset=True)
    def lote_apply(wid: str, token: str) -> dict:
        return _cargas_job(wid, token, False)

    # ------------------------------------------------------------ demanda medida
    # Spec 004, RF-22 a RF-39: misma pestaña que las cargas (RF-40), sin entradas cargadas.
    @app.get('/api/workspaces/{wid}/demanda/medidores')
    def demanda_medidores(wid: str, alimentador: str = Query(...)) -> dict:
        return services.demanda_medidores(ws_or_404(wid), alimentador)

    @app.get('/api/workspaces/{wid}/demanda/sistema')
    def demanda_sistema(wid: str, project: str = Query(...), todos: bool = False) -> dict:
        # 022:RF-54: los alimentadores del sistema y sus medidores, para proponerlos todos;
        # 028:RF-24, con ``todos``, también los de un proyecto de uno o varios alimentadores.
        return {'sistema': services.sistema_del_proyecto(ws_or_404(wid), project, todos=todos)}

    @app.get('/api/workspaces/{wid}/demanda/alimentadores')
    def demanda_alimentadores(wid: str) -> dict:
        return services.demanda_alimentadores(ws_or_404(wid))

    @app.post('/api/workspaces/{wid}/demanda/cabecera/buscar', status_code=202, response_model=JobRespuesta, response_model_exclude_unset=True)
    def demanda_cabecera(wid: str, body: DemandaMedidoresIn) -> dict:
        ws = ws_or_404(wid)
        pares = [(m.alimentador.strip(), m.medidor.strip()) for m in body.medidores if m.medidor.strip()]
        if not pares:
            raise HTTPException(422, 'Indique al menos un medidor.')
        if body.coincidente:                                                   # 070:RF-57
            services.comprobar_analisis_por_alimentadores(services.alimentadores_del_analisis(pares))
        return submit(ws, 'demanda_cabecera', f'Máxima de cabecera ({len(pares)} medidor(es))',
                      lambda ctx: services.demanda_cabecera(ws, ctx, pares, periodo=body.periodo,
                                                            instante=body.instante,
                                                            por_barra=body.por_barra,
                                                            centrales_tramo=body.centrales_tramo,
                                                            coincidente=body.coincidente,
                                                            centrales=body.centrales,
                                                            sistema_60kv=body.sistema_60kv))

    @app.get('/api/workspaces/{wid}/demanda/centrales')
    def demanda_centrales(wid: str) -> dict:
        # 022:RF-88: las centrales térmicas (CT…) del libro, para decir dónde se conectan.
        return services.demanda_centrales_de_barra(ws_or_404(wid))

    @app.get('/api/workspaces/{wid}/demanda/cabecera/{job_id}/curva')
    def demanda_curva(wid: str, job_id: str, medidor: str = Query(...),
                      desde: datetime | None = None, hasta: datetime | None = None) -> dict:
        """Spec 006, RF-31 a RF-39: curva del registro del medidor, entera o por tramo."""
        if desde is not None and hasta is not None and desde > hasta:
            raise HTTPException(422, 'El inicio del tramo es posterior a su fin.')
        try:
            return services.demanda_curva(ws_or_404(wid), job_id, medidor, desde, hasta)
        except LookupError as exc:
            raise HTTPException(404, str(exc)) from exc

    @app.get('/api/workspaces/{wid}/demanda/medidores-externos')
    def demanda_medidores_externos(wid: str, red: list[str] = Query(default=[])) -> dict:
        """Spec 021, RF-26 y RF-27: medidores que no son de un alimentador de la red."""
        return services.demanda_medidores_externos(ws_or_404(wid), red)

    @app.get('/api/workspaces/{wid}/demanda/cabecera/{job_id}/central')
    def demanda_central(wid: str, job_id: str, alimentador: str = Query(...),
                        cabecera: str = Query(...), generacion: str = Query(...),
                        llegada: str = Query(...), salida: str = Query(...)) -> dict:
        """Spec 021, RF-28 a RF-34: máxima de demanda de un alimentador con central."""
        try:
            return services.demanda_central(
                ws_or_404(wid), job_id, alimentador=alimentador, cabecera=cabecera,
                generacion=generacion, llegada=llegada, salida=salida)
        except LookupError as exc:
            raise HTTPException(404, str(exc)) from exc

    @app.get('/api/workspaces/{wid}/demanda/cabecera/{job_id}/central/curva')
    def demanda_curva_central(wid: str, job_id: str, alimentador: str = Query(...),
                              cabecera: str = Query(...), generacion: str = Query(...),
                              llegada: str = Query(...), salida: str = Query(...),
                              desde: datetime | None = None, hasta: datetime | None = None) -> dict:
        """Spec 021, RF-47 y RF-48: curva de la demanda de un alimentador con central."""
        if desde is not None and hasta is not None and desde > hasta:
            raise HTTPException(422, 'El inicio del tramo es posterior a su fin.')
        try:
            return services.demanda_curva_central(
                ws_or_404(wid), job_id, alimentador=alimentador, cabecera=cabecera,
                generacion=generacion, llegada=llegada, salida=salida, desde=desde, hasta=hasta)
        except LookupError as exc:
            raise HTTPException(404, str(exc)) from exc

    @app.post('/api/workspaces/{wid}/demanda/clientes/cruzar')
    def demanda_clientes(wid: str, body: DemandaClientesIn | None = None) -> dict:
        return services.demanda_clientes(ws_or_404(wid), body.alimentadores if body else None,
                                         periodo=body.periodo if body else None,
                                         maximas=body.maximas if body else None,
                                         criterio=body.criterio if body else None)

    # 039:RF-5: las fijas con los dos criterios, frente a la cabecera y a la red simulada.
    @app.post('/api/workspaces/{wid}/demanda/clientes/comparar', status_code=202, response_model=JobRespuesta, response_model_exclude_unset=True)
    def demanda_comparar_fijas(wid: str, body: CompararFijasIn) -> dict:
        ws = ws_or_404(wid)
        if not body.maximas:
            raise HTTPException(422, 'Busque antes la máxima de cabecera de los alimentadores.')
        feeders = [a.strip() for a in body.alimentadores if a.strip()] or list(body.maximas)
        return submit(ws, 'demanda_comparar_fijas',
                      f'Comparar los criterios de las fijas ({len(feeders)} alimentador(es))',
                      lambda ctx: services.comparar_criterios_fijas(
                          ws, ctx, body.project, feeders, body.maximas, body.periodo))

    # Spec 006: ajuste de las demandas del alimentador a la máxima de cabecera.
    @app.post('/api/workspaces/{wid}/demanda/ajuste/plan')
    def ajuste_plan(wid: str, body: AjusteIn) -> dict:
        ws = ws_or_404(wid)
        job = jobs.get(body.job_id)
        if job is None or job.workspace_id != wid or job.kind != 'demanda_cabecera':
            raise HTTPException(404, 'No se encuentra la máxima buscada: vuelva a buscarla.')
        if not isinstance(job.result, dict):
            raise HTTPException(409, 'La máxima de cabecera todavía no ha terminado.')
        return services.ajuste_plan(ws, body.project, job.result.get('resultados') or [],
                                    body.medidor, body.tolerancia, body.medidores,
                                    body.desconectados, job_id=body.job_id,
                                    centrales={a: c.model_dump() for a, c in body.centrales.items()},
                                    tension_fuente_pu=body.tension_fuente_pu,
                                    completar_bancos=body.completar_bancos,
                                    barras=job.result.get('barras'),
                                    criterio_fijas=body.criterio_fijas)

    def _ajuste_job(wid: str, token: str, simular: bool) -> dict:
        ws = ws_or_404(wid)
        plan = ws.cargas_planes.get(token)
        if plan is None or plan.get('kind') != 'ajuste_cabecera':
            raise HTTPException(404, 'El plan del ajuste ya no existe: vuelva a prepararlo.')
        verbo = 'Simular' if simular else 'Ajustar'
        quien = plan['feeders'][0] if len(plan['feeders']) == 1 else f"{len(plan['feeders'])} alim."
        return submit(ws, 'ajuste_simular' if simular else 'ajuste_aplicar',
                      f"{verbo} {quien} a la máxima · {plan['project']}",
                      lambda ctx: services.ajuste_ejecutar(ws, ctx, token, simular=simular),
                      lane='powerfactory')

    @app.post('/api/workspaces/{wid}/demanda/ajuste/{token}/simular', status_code=202, response_model=JobRespuesta, response_model_exclude_unset=True)
    def ajuste_simular(wid: str, token: str) -> dict:
        return _ajuste_job(wid, token, True)

    @app.post('/api/workspaces/{wid}/demanda/ajuste/{token}/aplicar', status_code=202, response_model=JobRespuesta, response_model_exclude_unset=True)
    def ajuste_aplicar(wid: str, token: str) -> dict:
        return _ajuste_job(wid, token, False)

    # Spec 020: transformadores nuevos de las SED fijas sobrecargadas y recalibración.
    @app.post('/api/workspaces/{wid}/demanda/ajuste/{token}/transformadores', status_code=202, response_model=JobRespuesta, response_model_exclude_unset=True)
    def ajuste_transformadores(wid: str, token: str, body: TransformadoresIn) -> dict:
        ws = ws_or_404(wid)
        plan = ws.cargas_planes.get(token)
        if plan is None or plan.get('kind') != 'ajuste_cabecera':
            raise HTTPException(404, 'El plan del ajuste ya no existe: vuelva a prepararlo.')
        # 020:RF-13, RF-14: se valida antes de encolar, para decirlo en el acto.
        pedidos = body.por_alimentador or {body.feeder: body.sed}
        if '' in pedidos:
            raise HTTPException(422, 'Indique el alimentador de las SED (020:RF-14).')
        cambios = {f: services.ajuste_transformadores_pedido(ws, token, f, seds)
                   for f, seds in pedidos.items()}
        quien = next(iter(cambios)) if len(cambios) == 1 else f'{len(cambios)} alim.'
        return submit(ws, 'ajuste_transformadores',
                      f"Transformadores nuevos y calibración de {quien} · {plan['project']}",
                      lambda ctx: services.ajuste_transformadores_varios(ws, ctx, token, cambios),
                      lane='powerfactory')

    def _ajuste_aplicado(wid: str, job_id: str | None) -> dict | None:
        """El resultado del ajuste de la base (spec 007, RF-1; spec 011, RF-12).

        Solo uno de este espacio, terminado y aplicado: una simulación no deja variación.
        """
        if not job_id:
            return None
        if job_id.startswith('disco:'):
            # 007:RF-40: el ajuste de una sesión anterior, rehecho con sus informes.
            guardado = services.ajuste_aplicado_en_disco(
                ws_or_404(wid), None, job_id.removeprefix('disco:'))
            if guardado is None:
                raise HTTPException(404, 'No se encuentra el ajuste de la base: quite la base o vuelva a ajustar.')
            return guardado
        job = jobs.get(job_id)
        if job is None or job.workspace_id != wid:
            raise HTTPException(404, 'No se encuentra el ajuste de la base: quite la base o vuelva a ajustar.')
        if job.kind not in ('ajuste_aplicar', 'ajuste_transformadores'):   # 020:RF-28
            raise HTTPException(400, 'La base tiene que ser un ajuste aplicado, no una simulación.')
        if not isinstance(job.result, dict):
            raise HTTPException(409, 'El ajuste de la base todavía no ha terminado.')
        return job.result

    # ------------------------------------------------------------ obras y estudios (spec 011)
    @app.post('/api/workspaces/{wid}/pide', status_code=202, response_model=JobRespuesta, response_model_exclude_unset=True)
    def pide_ejecutar(wid: str, body: dict[str, Any]) -> dict:
        """Metodología del PIDE sobre el proyecto, con obras propias (spec 024, T13 y T14)."""
        ws = ws_or_404(wid)
        project = str(body.get('project') or '').strip()
        if not project:
            raise HTTPException(422, 'Elija el proyecto de DIgSILENT.')
        feeders = [str(f) for f in body.get('feeders') or []]
        try:
            anio = int(body['anio_presentacion']) if body.get('anio_presentacion') else None
        except (TypeError, ValueError) as exc:
            raise HTTPException(422, 'El año de presentación tiene que ser un número.') from exc
        return submit(ws, 'pide', f'PIDE · {project}',
                      lambda ctx: services.pide_ejecutar(ws, ctx, project, feeders,
                                                         capex=body.get('capex'),
                                                         implementar=bool(body.get('implementar', True)),
                                                         anio_presentacion=anio,
                                                         formato_01=body.get('formato_01')),
                      lane='powerfactory')

    @app.post('/api/workspaces/{wid}/digital-twin/aprender', status_code=202, response_model=JobRespuesta, response_model_exclude_unset=True)
    def gemelo_aprender(wid: str, body: dict[str, Any]) -> dict:
        """Aprendizaje activo en una copia del proyecto (spec 024, T10)."""
        ws = ws_or_404(wid)
        project = str(body.get('project') or '').strip()
        if not project:
            raise HTTPException(422, 'Elija el proyecto de DIgSILENT.')
        return submit(ws, 'gemelo_aprender', f'Gemelo · aprender · {project}',
                      lambda ctx: services.gemelo_aprender(
                          ws, ctx, project, [str(f) for f in body.get('feeders') or []],
                          n=int(body.get('n') or 20), segundos=body.get('segundos'),
                          caso=str(body.get('caso') or 'sin_proyecto')),
                      lane='powerfactory')

    @app.post('/api/workspaces/{wid}/digital-twin/temporal', status_code=202, response_model=JobRespuesta, response_model_exclude_unset=True)
    def gemelo_temporal(wid: str, body: dict[str, Any]) -> dict:
        """Gemelo temporal del mes con las curvas de cabecera (spec 024, T12)."""
        ws = ws_or_404(wid)
        # 046:RF-23, RF-24: el pronóstico de cabecera o de clientes, solo si se pide expresamente.
        if body.get('modo') == 'pronostico':
            return submit(ws, 'gemelo_pronostico', 'Gemelo · pronóstico de demanda',
                          lambda ctx: services.gemelo_pronostico(ws, ctx, body))
        alimentadores = {str(k): str(v) for k, v in (body.get('alimentadores') or {}).items()}
        if not body.get('job_id') or not alimentadores:
            raise HTTPException(422, 'Indique la búsqueda de la máxima y los medidores de los alimentadores.')
        return submit(ws, 'gemelo_temporal', 'Gemelo temporal del mes',
                      lambda ctx: services.gemelo_temporal(
                          ws, ctx, str(body['job_id']), alimentadores, barra=body.get('barra'),
                          sin_medidor={str(k): float(v) for k, v in (body.get('sin_medidor') or {}).items()},
                          fijas_kw={str(k): float(v) for k, v in (body.get('fijas_kw') or {}).items()},
                          perdidas_pct=float(body.get('perdidas_pct') or 0.0),
                          umbral_pct=float(body.get('umbral_pct') or 10.0)),
                      lane='engine')

    @app.post('/api/workspaces/{wid}/digital-twin/entrenar', status_code=202, response_model=JobRespuesta, response_model_exclude_unset=True)
    def gemelo_entrenar(wid: str, body: dict[str, Any] | None = None) -> dict:
        """024:RF-39: reentrenar la PINN en otro proceso, también desde el asistente."""
        ws = ws_or_404(wid)
        forzar = bool((body or {}).get('forzar'))
        return submit(ws, 'gemelo_entrenar', 'Gemelo · reentrenar la PINN',
                      lambda ctx: services.gemelo_entrenar(ws, ctx, forzar=forzar))

    @app.post('/api/workspaces/{wid}/digital-twin/evaluar', status_code=202, response_model=JobRespuesta, response_model_exclude_unset=True)
    def gemelo_evaluar(wid: str) -> dict:
        """024:RF-74: cuánto se apartan de DIgSILENT el modelo y la física."""
        ws = ws_or_404(wid)
        return submit(ws, 'gemelo_evaluar', 'Gemelo · evaluar', lambda ctx: services.gemelo_evaluar(ws, ctx))

    @app.post('/api/workspaces/{wid}/digital-twin/deriva', status_code=202, response_model=JobRespuesta, response_model_exclude_unset=True)
    def gemelo_deriva(wid: str) -> dict:
        """027:RF-22, RF-23: deriva por familia y si conviene reentrenar."""
        ws = ws_or_404(wid)
        return submit(ws, 'gemelo_deriva', 'Gemelo · revisar la deriva', lambda ctx: services.gemelo_deriva(ws, ctx))

    @app.post('/api/modelos/{modelo}/volver')
    def volver_al_modelo_anterior(modelo: str) -> dict:
        """027:RF-24: volver al modelo anterior del gemelo o del asistente."""
        return services.volver_al_modelo_anterior(modelo)

    # ------------------------------------------------------------ agente (spec 027, RF-43)
    @app.post('/api/workspaces/{wid}/agente/proyecto', status_code=202, response_model=JobRespuesta, response_model_exclude_unset=True)
    def agente_proyecto(wid: str, body: AgenteProyectoIn, request: Request) -> dict:
        ws = ws_or_404(wid)
        base = str(request.base_url).rstrip('/')
        datos = _datos_del_proyecto(body)
        lista = services.agente_proyecto_lista(ws, datos, body.reiniciar)
        if lista['confirmacion'] != body.confirmacion:                # 067:RF-39
            raise HTTPException(409, 'La lista de etapas cambió desde que se mostró: revísela y confirme de nuevo.')
        trabajo = submit(ws, 'agente_proyecto', f'Agente · proyecto desde cero · {body.sistema}',
                         lambda ctx: services.agente_proyecto(ws, ctx, datos, base, getattr(app.state, 'asistente_http', None),
                                                              reiniciar=body.reiniciar),
                         lane='asistente')
        services.agente_proyecto_anotar(ws, datos, lista)
        return trabajo

    def _datos_del_proyecto(body: AgenteProyectoListaIn) -> dict:
        return {k: v for k, v in body.model_dump().items()
                if k not in ('reiniciar', 'confirmacion') and v not in (None, '', {})}

    @app.post('/api/workspaces/{wid}/agente/proyecto/lista')
    def agente_proyecto_lista(wid: str, body: AgenteProyectoListaIn) -> dict:
        """067:RF-37: lo que hará el proyecto entero, antes del único clic; solo lee."""
        return services.agente_proyecto_lista(ws_or_404(wid), _datos_del_proyecto(body), body.reiniciar)

    # ------------------------------------------------------------ asistente (spec 026)
    @app.get('/api/workspaces/{wid}/asistente/monitor')
    def asistente_monitor(wid: str,limite: int=Query(50,ge=1,le=200)) -> dict:
        ws=ws_or_404(wid)
        result = services.asistente_monitor(ws,[j.public() for j in jobs.list(wid)],limite=limite,
            errores=[errores_observacion[wid]] if wid in errores_observacion else [])
        result['retencion'] = retencion.estado()
        return result

    def _asistente_job(ws: Workspace, plan_id: str, request: Request) -> dict:
        base = str(request.base_url).rstrip('/')
        http = getattr(app.state, 'asistente_http', None)
        plan = services.asistente_plan(ws, plan_id)['plan']
        if plan.tarea == 'cancelar_trabajo':                                   # 070:RF-33
            return submit(ws, 'asistente_control', f'Asistente · {plan.tarea}',
                          lambda ctx: services.asistente_cancelar(ws, ctx, plan_id, jobs.cancel), lane='control')
        return submit(ws, 'asistente', f'Asistente · {plan.tarea}',
                      lambda ctx: services.asistente_ejecutar(ws, ctx, plan_id, base, http), lane='asistente')

    @app.post('/api/workspaces/{wid}/asistente/orden', status_code=202, response_model=JobRespuesta, response_model_exclude_unset=True)
    def asistente_orden(wid: str, body: AsistenteOrdenIn, request: Request) -> dict:
        """065:RF-18: interpretar puede cargar modelos o consultar el LLM; va en cola."""
        ws = ws_or_404(wid)
        if not body.texto.strip() or len(body.texto) > 2000:
            raise HTTPException(422, 'Escriba una orden de entre 1 y 2000 caracteres.')
        base = str(request.base_url).rstrip('/')
        http = getattr(app.state, 'asistente_http', None)

        def interpret(ctx):
            ctx.check_cancel()
            ctx.progress(0, 1, 'Interpretar la orden')
            result = services.asistente_orden(ws, body.texto, [j.public() for j in jobs.list(ws.id)])
            ctx.check_cancel()
            plan = result['plan']
            # 085:RF-31, RF-32: nunca por la confianza del modelo; solo lo que el plan declara que no espera al operador.
            if plan['listo'] and plan['modo'] != 'consulta' and not plan['espera_confirmacion']:
                # El trabajo actual aún ocupa el carril. La cola admite el siguiente
                # paso automático; no se espera a él ni se bloquea a sí misma.
                result['trabajo'] = jobs.submit(
                    ws.id, 'asistente', f"Asistente · {plan['tarea']}",
                    lambda child: services.asistente_ejecutar(ws, child, plan['id'], base, http),
                    lane='asistente').public()
            ctx.progress(1, 1, 'Orden interpretada')
            if plan.get('tarea') == 'pregunta':
                _programar_vectores(ws)
            return result

        # 070:RF-33: con el carril del asistente ocupado daría 409 justo cuando se quiere parar lo que corre.
        return submit(ws, 'asistente_interpretar', 'Interpretar la orden', interpret,
                      lane='control' if services.es_orden_de_cancelar(body.texto) else 'asistente')

    def _programar_vectores(ws: Workspace) -> None:
        """047:RF-22: la pregunta ya tiene respuesta con lo que hay; lo que falte, detrás y sin pedirlo.
        Solo el servidor real: las pruebas crean la app a cientos y no deben usar Ollama por su cuenta."""
        if os.environ.get('CSG_ASISTENTE_VECTORES') != '1' or es_edicion_producto():       # 086:RF-16
            return
        if any(j.kind == 'asistente_indice' and j.status not in FINISHED for j in jobs.list()):
            return
        try:
            if not services.asistente_vectores_pendientes():
                return
        except (OSError, ValueError):                                  # sin vectores se sigue con BM25 (RF-25)
            return

        def ceder() -> bool:
            return any(j.lane == 'asistente' and j.kind != 'asistente_indice' and j.status not in FINISHED
                       for j in jobs.list())

        jobs.submit(ws.id, 'asistente_indice', 'Asistente · vectores del índice',
                    lambda ctx: services.asistente_calcular_vectores(ctx, ceder), lane='asistente')

    @app.get('/api/workspaces/{wid}/asistente/planes')
    def asistente_planes(wid: str) -> dict:
        """067:RF-13, RF-19: los planes que esperan confirmación, también tras un reinicio."""
        return services.asistente_planes_guardados(ws_or_404(wid))

    @app.post('/api/workspaces/{wid}/asistente/{plan_id}/confirmar', status_code=202, response_model=JobRespuesta, response_model_exclude_unset=True)
    def asistente_confirmar(wid: str, plan_id: str, request: Request) -> dict:
        """026:RF-8, RF-10: el plan confirmado, por las rutas y trabajos de la web."""
        ws = ws_or_404(wid)
        plan = services.asistente_plan(ws, plan_id)['plan']
        if not plan.listo:
            raise HTTPException(422, 'El plan no está completo: ' + '; '.join(plan.faltan))
        return _asistente_job(ws, plan_id, request)

    @app.post('/api/workspaces/{wid}/asistente/{plan_id}/corregir')
    def asistente_corregir(wid: str, plan_id: str, body: AsistenteCorregirIn) -> dict:
        """026:RF-15, RF-19: la corrección es un plan nuevo y un ejemplo para aprender."""
        return services.asistente_corregir(ws_or_404(wid), plan_id, tarea=body.tarea, datos=body.datos,
                                           tipo_informe=body.tipo_informe, subtipo=body.subtipo)

    @app.post('/api/workspaces/{wid}/asistente/{plan_id}/rechazar')
    def asistente_rechazar(wid: str, plan_id: str) -> dict:
        """027:RF-35: el operador rechaza el plan (penalización)."""
        return services.asistente_rechazar(ws_or_404(wid), plan_id)

    @app.get('/api/asistente/registro')
    def asistente_registro() -> dict:
        """026:RF-28, RF-31: órdenes, decisiones, mejoras, consultas a internet, suite y avisos."""
        return services.asistente_registro()

    @app.get('/api/asistente/modelos')
    def asistente_modelos() -> dict:
        """043:RF-8 — estados respaldados por informes y candidatos íntegros."""
        return services.asistente_estado_modelos()

    @app.get('/api/asistente/aceptacion')
    def asistente_aceptacion() -> dict:
        """047:RF-16 / RF-17 — propuestas materializadas y observaciones reales separadas."""
        from ..asistente.aceptacion import estado_aceptacion
        return estado_aceptacion()

    @app.post('/api/workspaces/{wid}/asistente/entrenar', status_code=202, response_model=JobRespuesta, response_model_exclude_unset=True)
    def asistente_entrenar(wid: str) -> dict:
        ws = ws_or_404(wid)
        return submit(ws, 'asistente_entrenar', 'Asistente · reentrenar',
                      lambda ctx: services.asistente_entrenar(ws, ctx))

    @app.post('/api/workspaces/{wid}/asistente/mejoras/libreria', status_code=202, response_model=JobRespuesta, response_model_exclude_unset=True)
    def asistente_libreria(wid: str, body: AsistenteLibreriaIn) -> dict:
        """026:RF-32: la ficha de una librería en una rama aparte, que nunca se fusiona sola."""
        ws = ws_or_404(wid)
        return submit(ws, 'asistente_mejora', f'Asistente · propuesta de {body.paquete}',
                      lambda ctx: services.asistente_proponer_libreria(ws, ctx, body.paquete, body.motivo))

    @app.post('/api/asistente/mejoras/{propuesta_id}/decision')
    def asistente_decision(propuesta_id: str, body: AsistenteDecisionIn) -> dict:
        """026:RF-28: lo que el operador decidió de una propuesta."""
        return services.asistente_decision_mejora(propuesta_id, body.decision, body.comentario)

    @app.post('/api/workspaces/{wid}/pide/decision')
    def pide_decision(wid: str, body: dict[str, Any]) -> dict:
        """Lo que decide el operador sobre una propuesta, para aprender de ello (024:RF-48)."""
        return services.pide_decision(ws_or_404(wid), str(body.get('project') or ''),
                                      str(body.get('codigo') or ''), str(body.get('decision') or ''),
                                      str(body.get('comentario') or ''))

    @app.get('/api/workspaces/{wid}/digital-twin/episodes')
    def gemelo_episodios(wid: str, proyecto: str | None = None, alimentador: str | None = None,
                         caso: str | None = None, clase: str | None = None,
                         accion: str | None = None) -> list[dict]:
        """Episodios del gemelo digital de los proyectos vinculados (024:RF-8)."""
        return services.gemelo_episodios(ws_or_404(wid), {
            'proyecto': proyecto, 'alimentador': alimentador, 'caso': caso, 'clase': clase,
            'accion': accion})

    @app.get('/api/workspaces/{wid}/digital-twin/episodes/{episode_id}')
    def gemelo_episodio(wid: str, episode_id: str) -> dict:
        ws = ws_or_404(wid)
        try:
            return services.gemelo_episodio(ws, episode_id)
        except KeyError:
            raise HTTPException(404, 'No existe ese episodio en los proyectos de este espacio.') from None

    @app.get('/api/workspaces/{wid}/obras')
    def obras_listar(wid: str) -> list[dict]:
        return list(ws_or_404(wid).obras)

    @app.post('/api/workspaces/{wid}/obras', status_code=201)
    def obra_anadir(wid: str, body: dict[str, Any]) -> dict:
        return services.obra_anadir(ws_or_404(wid), body)

    @app.delete('/api/workspaces/{wid}/obras/{obra_id}', status_code=204)
    def obra_quitar(wid: str, obra_id: str) -> None:
        services.obra_quitar(ws_or_404(wid), obra_id)

    @app.post('/api/workspaces/{wid}/pf/obras/bibliotecas', status_code=202, response_model=JobRespuesta, response_model_exclude_unset=True)
    def obras_bibliotecas(wid: str, body: BibliotecasIn) -> dict:
        ws = ws_or_404(wid)
        return submit(ws, 'obras_bibliotecas', f'Leer tipos de DIgSILENT · {body.project.strip()}',
                      lambda ctx: services.obras_bibliotecas(ws, ctx, body.project, body.feeders,
                                                             body.otro_proyecto, body.clases),
                      lane='powerfactory')

    @app.get('/api/workspaces/{wid}/pf/obras/bibliotecas')
    def obras_bibliotecas_leidas(wid: str) -> dict:
        return dict(ws_or_404(wid).pf_bibliotecas)

    def _obras_job(wid: str, body: ObrasIn, simular: bool) -> dict:
        ws = ws_or_404(wid)
        verbo = 'Simular' if simular else 'Aplicar'
        return submit(ws, 'obras_simular' if simular else 'obras_aplicar',
                      f'{verbo} obras · {body.project.strip()}',
                      lambda ctx: services.obras_ejecutar(ws, ctx, body.project, body.feeders,
                                                          body.ids, body.otro_proyecto,
                                                          simular=simular,
                                                          anio_casos=body.anio_casos),
                      lane='powerfactory')

    @app.post('/api/workspaces/{wid}/pf/obras/simular', status_code=202, response_model=JobRespuesta, response_model_exclude_unset=True)
    def obras_simular(wid: str, body: ObrasIn) -> dict:
        return _obras_job(wid, body, True)

    @app.post('/api/workspaces/{wid}/pf/obras/aplicar', status_code=202, response_model=JobRespuesta, response_model_exclude_unset=True)
    def obras_aplicar(wid: str, body: ObrasIn) -> dict:
        return _obras_job(wid, body, False)

    @app.post('/api/workspaces/{wid}/pf/obras/escalera', status_code=202, response_model=JobRespuesta, response_model_exclude_unset=True)
    def obras_escalera(wid: str, body: ObrasIn) -> dict:
        """025:RF-44: bancos, sección y terna hasta que «Con proyecto» converja."""
        ws = ws_or_404(wid)
        return submit(ws, 'obras_escalera', f'Obras en escalera · {body.project.strip()}',
                      lambda ctx: services.obras_escalera(ws, ctx, body.project, body.feeders,
                                                          anio_casos=body.anio_casos,
                                                          tipo_cambio=body.tipo_cambio,
                                                          capex=body.capex),
                      lane='powerfactory')

    @app.post('/api/workspaces/{wid}/pf/obras/con-proyecto', status_code=202, response_model=JobRespuesta, response_model_exclude_unset=True)
    def obras_con_proyecto(wid: str, body: ObrasIn) -> dict:
        """042:RF-13: escalera carga a carga y SET nueva para las que no caben."""
        ws = ws_or_404(wid)
        return submit(ws, 'obras_con_proyecto', f'Optimizar «Con proyecto» · {body.project.strip()}',
                      lambda ctx: services.con_proyecto_optimizar(
                          ws, ctx, body.project, body.feeders, anio_casos=body.anio_casos,
                          tipo_cambio=body.tipo_cambio, capex=body.capex,
                          alimentadores_nuevos=body.alimentadores_nuevos,
                          set_nueva_nombre=body.set_nueva_nombre,
                          directo_set_nueva=body.directo_set_nueva, cargas=body.cargas or None,
                          escalera_primero=body.escalera_primero),
                      lane='powerfactory')

    @app.post('/api/workspaces/{wid}/pf/obras/set-nueva/operacion', status_code=202, response_model=JobRespuesta, response_model_exclude_unset=True)
    def set_nueva_operacion(wid: str, body: SetNuevaOperacionIn) -> dict:
        """063:RF-36 a RF-38: un solo dueño del motor, sin duplicar la SET existente."""
        ws = ws_or_404(wid)
        opciones = body.model_dump(exclude={'project', 'feeders'})
        return submit(ws, 'set_nueva_operacion', f'Operación de SET existente · {body.project}',
                      lambda ctx: services.set_nueva_operacion(ws, ctx, body.project, body.feeders,
                                                               **opciones), lane='powerfactory')

    @app.get('/api/pf/estudios')
    def estudios_catalogo() -> dict:
        return services.estudios_catalogo()

    @app.get('/api/workspaces/{wid}/pf/estudios')
    def estudios_catalogo_proyecto(wid: str, project: str = '') -> dict:
        """012:RF-19, RF-4: los estudios según el libro del proyecto y la licencia."""
        return services.estudios_catalogo(ws_or_404(wid), project)

    @app.get('/api/workspaces/{wid}/pf/datos-empresa')
    def datos_empresa_estado(wid: str, project: str = '') -> dict:
        return {'libro': services.datos_empresa_estado(ws_or_404(wid), project)}

    @app.post('/api/workspaces/{wid}/pf/datos-empresa')
    def datos_empresa_subir(wid: str, project: str = Form(...), file: UploadFile = File(...)) -> dict:
        """012:RF-6, RF-16: el libro se valida al subirlo, sin abrir DIgSILENT."""
        ws = ws_or_404(wid)
        tmp = _upload_tmp(ws, file, 'datos_empresa.xlsx')
        try:
            return {'libro': services.datos_empresa_subir(ws, project, tmp, Path(file.filename or 'datos_empresa.xlsx').name)}
        finally:
            _limpiar_upload(tmp)

    @app.get('/api/workspaces/{wid}/pf/datos-empresa/plantilla')
    def datos_empresa_plantilla(wid: str) -> FileResponse:
        """012:RF-7: la plantilla del libro."""
        path = services.datos_empresa_plantilla(ws_or_404(wid))
        return FileResponse(path, filename=path.name)

    @app.post('/api/workspaces/{wid}/pf/datos-empresa/aplicar', status_code=202, response_model=JobRespuesta, response_model_exclude_unset=True)
    def datos_empresa_aplicar(wid: str, body: DatosEmpresaAplicarIn) -> dict:
        """012:RF-21: el libro en la variación «Datos de confiabilidad», como trabajo."""
        ws = ws_or_404(wid)
        return submit(ws, 'datos_confiabilidad', f'Datos de confiabilidad · {body.project.strip()}',
                      lambda ctx: services.datos_empresa_aplicar(ws, ctx, body.project, body.feeders),
                      lane='powerfactory')

    @app.post('/api/workspaces/{wid}/pf/estudios/plan')
    def estudios_plan(wid: str, body: EstudiosIn) -> dict:
        ws = ws_or_404(wid)
        return services.estudios_plan(ws, body.project, body.feeders, body.estudios,
                                      _ajuste_aplicado(wid, body.ajuste_job_id), body.limites,
                                      body.limite_s, body.opciones)

    @app.post('/api/workspaces/{wid}/pf/estudios/{token}/ejecutar', status_code=202, response_model=JobRespuesta, response_model_exclude_unset=True)
    def estudios_ejecutar(wid: str, token: str) -> dict:
        ws = ws_or_404(wid)
        plan = ws.cargas_planes.get(token)
        if plan is None or plan.get('kind') != 'estudios':
            raise HTTPException(404, 'El plan de los estudios ya no existe: vuelva a prepararlo.')
        return submit(ws, 'estudios', f"Estudios · {plan['project']} ({len(plan['feeders'])} alim.)",
                      lambda ctx: services.estudios_ejecutar(ws, ctx, token), lane='powerfactory')

    @app.post('/api/workspaces/{wid}/pf/guiones', status_code=202, response_model=JobRespuesta, response_model_exclude_unset=True)
    def guiones_listar(wid: str, body: GuionesIn) -> dict:
        ws = ws_or_404(wid)
        return submit(ws, 'guiones_listar', f'Leer guiones · {body.project.strip()}',
                      lambda ctx: services.guiones_listar(ws, ctx, body.project), lane='powerfactory')

    @app.post('/api/workspaces/{wid}/pf/guiones/ejecutar', status_code=202, response_model=JobRespuesta, response_model_exclude_unset=True)
    def guion_ejecutar(wid: str, body: GuionIn) -> dict:
        ws = ws_or_404(wid)
        if not body.confirmado:                                                # 086:RF-25
            raise HTTPException(409, f'Confirme que quiere ejecutar el guion {body.nombre.strip()}: '
                                     'hará en el proyecto lo que diga su código.')
        return submit(ws, 'guion_ejecutar', f'Guion {body.nombre.strip()} · {body.project.strip()}',
                      lambda ctx: services.guion_ejecutar(ws, ctx, body.project, body.nombre, body.origen,
                                                          body.parametros, body.casos, body.limite_s),
                      lane='powerfactory')

    @app.post('/api/workspaces/{wid}/informes/estudio', status_code=202, response_model=JobRespuesta, response_model_exclude_unset=True)
    def informe_estudio(wid: str, body: InformeEstudioIn) -> dict:
        """Spec 017: el informe con lo que guardaron los estudios de «Sin proyecto» y «Con proyecto»."""
        ws = ws_or_404(wid)
        formulario = body.model_dump()
        return submit(ws, 'informe_estudio', f'Informe de estudio · {body.alimentador}',
                      lambda ctx: services.informe_estudio(ws, ctx, formulario), lane='engine')

    @app.get('/api/workspaces/{wid}/informes')
    def informes_contexto(wid: str, project: str, feeder: list[str] = Query(default=[]),
                          job_id: str | None = None) -> dict:
        """Spec 017, paso 4.4: lo que la web ya guardó para cada informe, sin DIgSILENT."""
        return services.informes_contexto(ws_or_404(wid), project, feeder, job_id)

    @app.put('/api/workspaces/{wid}/informes/formulario')
    def informes_formulario(wid: str, body: InformeFormularioIn) -> dict:
        """017:RF-82: lo escrito en 4.4 queda en el servidor al recargar la página."""
        return services.informes_formulario_guardar(ws_or_404(wid), body.project, body.tipo, body.datos)

    @app.post('/api/workspaces/{wid}/informes/perdidas')
    def informes_perdidas_subir(wid: str, file: UploadFile = File(...)) -> dict:
        """017:RF-93: el libro de pérdidas de la empresa, guardado con el espacio."""
        ws = ws_or_404(wid)
        carpeta = services.informes_carpeta_perdidas(ws)
        shutil.rmtree(carpeta, ignore_errors=True)
        carpeta.mkdir(parents=True, exist_ok=True)
        destino = carpeta / safe_filename(file.filename or 'perdidas.xlsx')
        _save_upload(destino, file)
        return services.informes_perdidas_asignar(ws, destino, 'upload')

    @app.post('/api/workspaces/{wid}/informes/perdidas/path')
    def informes_perdidas_ruta(wid: str, body: ServerPathIn) -> dict:
        ws = ws_or_404(wid)
        if not _server_paths_allowed(host):
            raise HTTPException(403, 'Este servidor no admite rutas locales: suba el fichero.')
        path = Path(body.path.strip().strip('"'))
        if not path.is_file():
            raise HTTPException(400, f'No existe: {path}')
        return services.informes_perdidas_asignar(ws, path, 'server')

    @app.delete('/api/workspaces/{wid}/informes/perdidas')
    def informes_perdidas_quitar(wid: str) -> dict:
        return services.informes_perdidas_quitar(ws_or_404(wid))

    @app.post('/api/workspaces/{wid}/informes/documentos', status_code=202, response_model=JobRespuesta, response_model_exclude_unset=True)
    def informes_documentos(wid: str, tipo: Literal['factibilidad', 'estudio'] = Form(...),
                            files: list[UploadFile] = File(...)) -> dict:
        """017:RF-136 y RF-137: los PDF del solicitante, leídos en un trabajo (con OCR si hace falta)."""
        ws = ws_or_404(wid)
        malos = [f.filename for f in files if Path(f.filename or '').suffix.lower() != '.pdf']
        if malos:
            raise HTTPException(400, f'Solo se leen PDF: {", ".join(str(m) for m in malos)}.')
        # 017:RF-141: cada lectura en su carpeta del espacio; la anterior se reemplaza.
        carpeta = services.informes_carpeta_documentos(ws, tipo)
        shutil.rmtree(carpeta, ignore_errors=True)
        carpeta.mkdir(parents=True, exist_ok=True)
        rutas = []
        for f in files:
            destino = carpeta / safe_filename(f.filename or 'documento.pdf')
            _save_upload(destino, f)
            rutas.append(destino)
        return submit(ws, 'informe_documentos', f'Leer {len(rutas)} documento(s) del solicitante',
                      lambda ctx: services.informe_documentos(ws, ctx, tipo, rutas), lane='engine')

    @app.post('/api/workspaces/{wid}/informes/transformador/cargas', status_code=202, response_model=JobRespuesta, response_model_exclude_unset=True)
    def informes_trafo_cargas(wid: str, body: TransformadorListarIn) -> dict:
        """Spec 017, T10: cargas de barra y casos del proyecto de transmisión."""
        ws = ws_or_404(wid)
        return submit(ws, 'informe_trafo_cargas', 'Cargas del proyecto de transmisión',
                      lambda ctx: services.transformador_set_listar(ws, ctx, body.transmision),
                      lane='powerfactory')

    @app.post('/api/workspaces/{wid}/informes/transformador', status_code=202, response_model=JobRespuesta, response_model_exclude_unset=True)
    def informes_trafo(wid: str, body: TransformadorCalcularIn) -> dict:
        """Spec 017, T10: cargabilidad del devanado de la SET sin y con proyecto."""
        ws = ws_or_404(wid)
        return submit(ws, 'informe_trafo', f'Transformador de la SET · {body.carga}',
                      lambda ctx: services.transformador_set_calcular(
                          ws, ctx, body.project, body.alimentador, body.carga, body.caso, body.transmision),
                      lane='powerfactory')

    @app.post('/api/workspaces/{wid}/informes/factibilidad', status_code=202, response_model=JobRespuesta, response_model_exclude_unset=True)
    def informe_factibilidad(wid: str, body: InformeFactibilidadIn) -> dict:
        """Spec 017: factibilidad y punto de diseño de una carga nueva ingresada sola."""
        ws = ws_or_404(wid)
        formulario = body.model_dump(mode='json')
        # RF-96: la carga se comprueba antes de poner el trabajo en cola.
        services.carga_del_informe(ws, body.project, body.alimentador, body.sed)
        # 063:RF-1: si prepara los casos usa DIgSILENT, así que va a su carril; solo escribir,
        # al del motor.
        return submit(ws, 'informe_factibilidad', f'Informe de factibilidad · {body.sed}',
                      lambda ctx: services.informe_factibilidad(ws, ctx, formulario),
                      lane='powerfactory' if body.preparar_casos else 'engine')

    @app.post('/api/workspaces/{wid}/informes/ubicacion')
    def informe_vista_ubicacion(wid: str, body: VistaUbicacionIn) -> dict:
        """Spec 017, RF-124: la imagen de ubicación del cliente antes de generar el informe.
        Se dibuja con la geografía guardada en menos de un segundo: no es un trabajo."""
        return services.informe_vista_ubicacion(ws_or_404(wid), body.project, body.alimentador, body.sed,
                                                body.cliente, body.potencia_kw, body.codigo_punto)

    @app.post('/api/workspaces/{wid}/pf/transferencia', status_code=202, response_model=JobRespuesta, response_model_exclude_unset=True)
    def transferencia(wid: str, body: TransferenciaIn) -> dict:
        ws = ws_or_404(wid)
        if len({f.strip() for f in body.feeders if f.strip()}) != 2:
            raise HTTPException(400, 'Elija dos alimentadores distintos.')
        return submit(ws, 'transferencia', f"Transferencia · {' ↔ '.join(body.feeders)}",
                      lambda ctx: services.transferencia_ejecutar(ws, ctx, body.project, body.feeders,
                                                                  body.casos, body.limites,
                                                                  body.cabecera_job_id),
                      lane='powerfactory')

    @app.post('/api/workspaces/{wid}/demanda/excel')
    def demanda_excel(wid: str, body: DemandaExcelIn) -> FileResponse:
        path = services.demanda_excel(ws_or_404(wid), body.model_dump())
        return FileResponse(path, filename=path.name)

    @app.post('/api/workspaces/{wid}/demanda/{tipo}/path')
    def demanda_ruta(wid: str, tipo: DemandaTipo, body: ServerPathIn) -> dict:
        ws = ws_or_404(wid)
        if not _server_paths_allowed(host):
            raise HTTPException(403, 'Este servidor no admite rutas locales: suba el fichero.')
        path = Path(body.path.strip().strip('"'))
        if not (path.is_file() or (tipo in {'cabecera', 'suministros', 'clientes'} and path.is_dir())):
            raise HTTPException(400, f'No existe: {path}')
        return services.demanda_asignar(ws, tipo, path, 'server')

    @app.post('/api/workspaces/{wid}/demanda/clientes/indexar', status_code=202, response_model=JobRespuesta, response_model_exclude_unset=True)
    def demanda_clientes_indexar(wid: str) -> dict:
        ws = ws_or_404(wid)
        return submit(ws, 'demanda_clientes_index', 'Actualizar libros de clientes',
                      lambda ctx: services.demanda_clientes_indexar(ws, ctx), lane='engine')

    @app.post('/api/workspaces/{wid}/demanda/cabecera/indexar', status_code=202, response_model=JobRespuesta, response_model_exclude_unset=True)
    def demanda_cabecera_indexar(wid: str) -> dict:
        """025:RF-28, RF-32: el índice por año abre libros de cientos de MB; es un trabajo."""
        ws = ws_or_404(wid)
        return submit(ws, 'demanda_cabecera_index', 'Actualizar libros de cabecera',
                      lambda ctx: services.demanda_cabecera_indexar(ws, ctx), lane='engine')

    @app.post('/api/workspaces/{wid}/demanda/{tipo}')
    def demanda_subir(wid: str, tipo: DemandaTipo, files: list[UploadFile] = File(...)) -> dict:
        """Subida de libros. Cabecera, suministros y clientes admiten varios."""
        ws = ws_or_404(wid)
        if tipo not in {'cabecera', 'suministros', 'clientes'} and len(files) != 1:
            raise HTTPException(422, 'Suba un solo libro.')
        carpeta = services.demanda_carpeta(ws, tipo)
        if tipo != 'cabecera':
            shutil.rmtree(carpeta, ignore_errors=True)
        carpeta.mkdir(parents=True, exist_ok=True)
        destinos = []
        for f in files:
            destino = carpeta / safe_filename(f.filename or f'{tipo}.xlsx')
            _save_upload(destino, f)
            destinos.append(destino)
        fuente = carpeta if tipo in {'cabecera', 'suministros'} or (tipo == 'clientes' and len(destinos) > 1) else destinos[0]
        return services.demanda_asignar(ws, tipo, fuente, 'upload')

    @app.delete('/api/workspaces/{wid}/demanda/{tipo}')
    def demanda_quitar(wid: str, tipo: DemandaTipo) -> dict:
        return services.demanda_quitar(ws_or_404(wid), tipo)

    # ------------------------------------------------------------ catálogo
    @app.post('/api/workspaces/{wid}/catalog/build', status_code=202, response_model=JobRespuesta, response_model_exclude_unset=True)
    def catalog_build(wid: str, body: FeedersIn) -> dict:
        ws = ws_or_404(wid)
        services.require_loaded(ws)
        return submit(ws, 'catalog', 'Generar catálogo y auditar',
                      lambda ctx: services.build_catalog(ws, ctx, body.feeders))

    @app.post('/api/workspaces/{wid}/catalog/apply')
    def catalog_apply(wid: str, file: UploadFile = File(...),
                      preview_feeder: str | None = Query(default=None)) -> dict:
        ws = ws_or_404(wid)
        tmp = _upload_tmp(ws, file, 'catalogo.xlsx')
        try:
            result = services.apply_catalog(ws, tmp, preview_feeder)
        finally:
            _limpiar_upload(tmp)
        ws.events.append('log', {'text': f"Catálogo corregido aplicado: {result['count']} código(s). "
                                         f"{result['aviso']}"})
        return {**result, 'workspace': ws.public()}

    @app.delete('/api/workspaces/{wid}/catalog')
    def catalog_clear(wid: str) -> dict:
        ws = ws_or_404(wid)
        services.clear_catalog(ws)
        return ws.public()

    # ------------------------------------------------------------ sistema completo
    @app.post('/api/workspaces/{wid}/system/{action}', status_code=202, response_model=JobRespuesta, response_model_exclude_unset=True)
    def system(wid: str, action: Literal['grid', 'base', 'missing-data']) -> dict:
        ws = ws_or_404(wid)
        services.system_command(ws, action)  # valida entradas y guion antes de encolar
        title, lane = services.SYSTEM_ACTIONS[action]
        return submit(ws, 'system', title, lambda ctx: services.run_system(ws, ctx, action),
                      lane=lane)

    from .equipo_api import registrar_rutas_equipo

    registrar_rutas_equipo(app, ws_or_404=ws_or_404, submit=submit)

    # ------------------------------------------------------------ front compilado
    dist = frontend_dist()
    if (dist / 'index.html').is_file():
        from .runtime import integridad_del_front

        problem = integridad_del_front(dist)
        if problem:
            raise ValueError(f'La interfaz compilada está incompleta: {problem}')
        app.mount('/assets', StaticFiles(directory=dist / 'assets'), name='assets')

        @app.get('/{full_path:path}', include_in_schema=False)
        def spa(full_path: str) -> Any:
            if full_path.startswith('api/'):
                raise HTTPException(404)
            candidate = (dist / full_path).resolve()
            if full_path and candidate.is_file() and dist.resolve() in candidate.parents:
                return FileResponse(candidate)
            return FileResponse(dist / 'index.html')

    return app
