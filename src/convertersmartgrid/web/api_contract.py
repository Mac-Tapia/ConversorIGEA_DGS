"""Contratos públicos de respuesta, compartidos con el frontend mediante OpenAPI.

El resultado de un trabajo y la relectura nativa dependen de la operación/motor;
sus envoltorios se validan sin imponer un falso esquema eléctrico universal.
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator

ModoFuente = Literal['txt', 'mdb', 'vnr']
FaseAprendizaje = Literal['preparacion', 'entrenamiento', 'seleccion', 'evaluacion', 'publicacion',
                          'activacion', 'aceptacion_nativa']


class Respuesta(BaseModel):
    model_config = ConfigDict(extra='forbid')


class FaseAprendizajeRespuesta(Respuesta):
    estado: str
    motivo: str
    versiones: dict[str, str] | None = None


class EstadoAprendizajeRespuesta(Respuesta):
    fases: dict[FaseAprendizaje, FaseAprendizajeRespuesta]
    ultimo_ciclo: dict[str, JsonValue] | None
    conjunto_activo: dict[str, JsonValue] | None
    bloqueos: list[dict[str, JsonValue]]


class CancelacionAprendizajeRespuesta(Respuesta):
    solicitada: bool
    mensaje: str


class ProgresoRespuesta(Respuesta):
    index: int
    total: int
    label: str


class JobRespuesta(Respuesta):
    id: str
    kind: str
    title: str
    workspace_id: str
    lane: Literal['engine', 'powerfactory', 'asistente', 'control']
    status: Literal['queued', 'running', 'done', 'parcial', 'no_converge', 'failed', 'cancelled', 'interrumpido']
    progress: ProgresoRespuesta | None
    result: Any = Field(description='Resultado variable según kind; incluye informes nativos y extensiones.')
    error: str | None
    created_at: float
    started_at: float | None
    finished_at: float | None
    cancel_requested: bool


class OpcionesRespuesta(Respuesta):
    input_mode: ModoFuente | None
    source_company: str | None
    empresa_espacio: str | None = None
    source_period: str | None
    source_crs: str | None
    target_crs: str
    include_geography: bool
    strict: bool
    write_preview: bool
    export_xlsx: bool
    export_tsv: bool
    workers: int
    hoja: Literal['A0', 'A1', 'A2', 'A3', 'A4'] | None


class CapacidadesRespuesta(Respuesta):
    geography: bool
    xlsx: bool
    access: bool
    pandapower: bool


class PerfilRespuesta(Respuesta):
    nombre: str = ''
    crs_origen: str | None = None
    patron_sed_medicion: str | None = None
    escala_diagrama: float | None = None
    forma_alimentador: str | None = None
    patron_libro_clientes: str | list[str] | None = None
    error: str | None


class CasillaRespuesta(Respuesta):
    grupo: Literal['txt', 'mdb', 'vnr', 'comun']
    tipo: str | None
    etiqueta: str
    obligatorio: bool
    extensiones: list[str] = Field(default_factory=list)


class CrsRespuesta(Respuesta):
    code: str
    label: str


class ParalelismoRespuesta(Respuesta):
    cpus: int
    auto: int


class ServidorRespuesta(Respuesta):
    pid: int
    huella: str
    trabajos_en_curso: int
    paginas_abiertas: int
    raiz: str | None = None


class EstadoCopiaRespuesta(Respuesta):
    ultima: float | None
    ruta: str | None
    edad_dias: float | None
    maxima_dias: float
    vencida: bool
    aviso: str | None


class BetaRespuesta(Respuesta):
    clave: str
    nombre: str
    aviso: str
    activa: bool


class EdicionRespuesta(Respuesta):
    producto: bool
    beta: list[BetaRespuesta]


class ComprobacionDoctorRespuesta(Respuesta):
    clave: str
    nombre: str
    ok: bool
    obligatoria: bool
    detalle: str
    afecta: str
    arreglo: str


class DiagnosticoRespuesta(Respuesta):
    version: str
    instalado: bool
    python: str
    listo: bool
    pendientes: int
    comprobaciones: list[ComprobacionDoctorRespuesta]


class VersionRespuesta(Respuesta):
    version: str
    notas: str


class HealthRespuesta(Respuesta):
    version: str
    capabilities: CapacidadesRespuesta
    crs_presets: list[CrsRespuesta]
    perfil_empresa: PerfilRespuesta
    slots: dict[str, CasillaRespuesta]
    default_options: OpcionesRespuesta
    server_paths: bool
    parallel: ParalelismoRespuesta
    source_modes: list[ModoFuente]
    servidor: ServidorRespuesta
    copia_datos: EstadoCopiaRespuesta
    edicion: EdicionRespuesta


class EntradaRespuesta(Respuesta):
    path: str
    name: str
    size: int
    origin: Literal['upload', 'server']
    warning: str
    set_at: float


class TotalesRespuesta(Respuesta):
    feeders: int
    convertible_feeders: int
    stub_feeders: int
    sources: int
    headnodes: int
    nodes: int
    sections: int
    line_configurations: int
    customer_loads: int
    load_placements: int
    switches: int
    sectionalizers: int
    intermediate_nodes: int
    distinct_line_cable_ids: int
    equipment_tables: int
    catalog_line_cable_ids: int


class ConversionEsperadaRespuesta(Respuesta):
    expected_dgs_files: int
    full_topology_feeders: list[str]
    source_only_feeders: list[str]
    convertible_feeders: list[str]
    model: str


class ProblemaInventarioRespuesta(Respuesta):
    __pydantic_extra__: dict[str, JsonValue] = Field(init=False)
    severity: str
    code: str
    message: str
    feeders: list[str] | None = None
    sections: list[str] | None = None
    count: int | None = None
    # Los diagnósticos de fuentes pueden añadir listas de identificadores tipadas JSON.
    model_config = ConfigDict(extra='allow')


class IntegridadRespuesta(Respuesta):
    errors: int
    warnings: int
    issues: list[ProblemaInventarioRespuesta]


class AlimentadorAuditoriaRespuesta(Respuesta):
    feeder: str
    network_id: str
    status: Literal['SOURCE_AUDIT_OK', 'SOURCE_AUDIT_BLOCKED']
    counts: dict[str, int]
    blocking_codes: list[str]
    warning_codes: list[str]


class ProblemaAuditoriaRespuesta(Respuesta):
    code: str
    severity: str
    object_type: str
    object_id: str
    feeder: str
    detail: str


class AuditoriaFuenteRespuesta(Respuesta):
    format: str
    status: Literal['SOURCE_AUDIT_OK', 'SOURCE_AUDIT_BLOCKED']
    source_run_id: str
    source_mode: ModoFuente
    source_fingerprint: str
    totals: dict[str, int]
    feeders: list[AlimentadorAuditoriaRespuesta]
    issues: list[ProblemaAuditoriaRespuesta]


class CatalogoRespuesta(Respuesta):
    initial_coverage: float
    final_coverage: float
    types_in_network: int
    added: dict[str, list[str]]
    unresolved: list[str]
    text: str
    critical: bool


class ReconstruccionRespuesta(Respuesta):
    run_id: str
    selection: list[str]
    report: str
    report_sha256: str


class HojaRespuesta(Respuesta):
    formato: str
    orientacion: str
    escala_1_a: float
    cuadricula_mm: float


class CompletitudRespuesta(Respuesta):
    entrada: dict[str, int | float]
    dgs: dict[str, int | float]
    fallos: list[str]


class ReconstruccionGrupoRespuesta(Respuesta):
    report: str
    report_sha256: str
    repairs: int
    catalog_matches: int
    assumptions: int
    selection: list[str]


class GrupoDgsRespuesta(Respuesta):
    name: str
    feeders: list[str]
    status: Literal['ok', 'failed', 'cancelled']
    requested_feeders: list[str] | None = None
    error: str | None = None
    dgs: str | None = None
    converted_at: float | None = None
    source_run_id: str | None = None
    source_fingerprint: str | None = None
    source_mode: ModoFuente | None = None
    feeder_metadata: str | None = None
    preview_html: str | None = None
    xlsx: str | None = None
    tipo: Literal['sistema', 'unida'] | None = None
    ties: int | None = None
    hoja: HojaRespuesta | None = None
    completitud: CompletitudRespuesta | None = None
    reconstruction: ReconstruccionGrupoRespuesta | None = None
    capacitor_reread: dict[str, JsonValue] | None = None


class VinculoProyectoRespuesta(Respuesta):
    project: str
    folder: str
    source_run_id: str
    source_mode: ModoFuente
    source_fingerprint: str
    feeders: list[str]
    dgs_sha256: dict[str, str]
    native_inventory_sha256: str
    native_reread: dict[str, JsonValue]
    accepted_at: float
    schema_version: str
    binding_sha256: str


class TipoObraRespuesta(Respuesta):
    nombre: str
    clase: str
    origen: str | None = None
    proyecto: str | None = None


class ObraRespuesta(Respuesta):
    """Campos comunes declarados; cada clase de obra guarda además los suyos (065:RF-26).

    Dos espacios reales traían ``enlace`` y ``km``, escritos por versiones anteriores: un contrato cerrado
    devolvía 500 al abrirlos y el operador perdía el espacio entero por un dato de más.
    """

    model_config = ConfigDict(extra='allow')

    clase: str
    alimentador: str
    casos: list[str]
    id: str | None = None
    barra: str | None = None
    tramo: str | None = None
    tramos: list[str] | None = None
    q_kvar: float | None = None
    escalones: int | None = None
    consigna_pu: float | None = None
    rango_pct: float | None = None
    pasos: int | None = None
    tipo: TipoObraRespuesta | None = None
    kv_destino: float | None = None
    toda_troncal: bool | None = None
    tipo_cable: TipoObraRespuesta | None = None
    cede: str | None = None
    minima_m: float | None = None
    origen: str | None = None
    destino: str | None = None
    nodo: str | None = None
    ramas: list[str] | None = None
    mva: float | None = None
    kv_alta: float | None = None
    unidades: int | None = None
    nombre_set: str | None = None


class ObraAplicadaRespuesta(Respuesta):
    project: str
    variacion: str
    obra: ObraRespuesta
    aplicada: float
    # 098:RF-36: lo que hizo en la operación, quién la eligió y con qué datos. Sin estos campos, abrir un espacio con
    # una obra de la escalera daba 500 (CA101 + CHN102, 2026-11-07).
    operacion: dict[str, Any] | None = None
    origen: str | None = None
    eleccion: dict[str, Any] | None = None


class CalibracionRespuesta(Respuesta):
    recalibracion: int
    nombre: str | None
    caso: str | None


class LibroClienteRespuesta(Respuesta):
    nombre: str
    anio: int | None = None
    mes: str | None
    origen_mes: Literal['nombre', 'contenido', 'manual', 'sin_mes']
    activo: bool
    avisos: list[str]


class LibroCabeceraRespuesta(Respuesta):
    """Una fila del índice tal como la guarda ``services`` (025:RF-28): el tamaño y la fecha deciden si se reabre."""

    relativa: str
    anio: int | None
    size: int
    mtime_ns: int
    hojas: list[str]
    meses: list[str]
    error: str | None


class DemandaRespuesta(Respuesta):
    name: str
    origin: Literal['upload', 'server']
    source_kind: Literal['file', 'folder'] | None = None
    libros: list[str] | None = None
    seleccion: str | None = None
    catalogo: list[LibroClienteRespuesta] | None = None
    anios: list[int] | None = None
    indice: list[LibroCabeceraRespuesta] | None = None
    vigente: bool | None = None
    avisos: list[str] | None = None
    indexado_en: float | None = None
    asignaciones: dict[str, str] | None = None
    zonales: int | None = None
    sets: int | None = None
    alimentadores: int | None = None


class NoDisponibleRespuesta(Respuesta):
    campo: str
    clave: str
    nombre: str
    ruta: str


class EspacioRespuesta(Respuesta):
    id: str
    created_at: float
    options: OpcionesRespuesta
    inputs: dict[str, EntradaRespuesta]
    no_disponibles: list[NoDisponibleRespuesta]
    avisos_datos: list[str]
    missing_inputs: list[str]
    loaded: bool
    loaded_at: float | None
    active_run_id: str | None
    loaded_run_id: str | None
    source_mode: ModoFuente | None
    source_fingerprint: str | None
    source_manifest_url: str | None
    totals: TotalesRespuesta | None
    conversion: ConversionEsperadaRespuesta | None
    integrity: IntegridadRespuesta | None
    universal_audit: AuditoriaFuenteRespuesta | None
    catalog_report: CatalogoRespuesta | None
    catalog_applied: bool
    catalog_file: str | None
    reconstruction: ReconstruccionRespuesta | None
    converted: int
    groups: list[GrupoDgsRespuesta]
    pf_projects: dict[str, str]
    pf_project_bindings: dict[str, VinculoProyectoRespuesta]
    obras: list[ObraRespuesta]
    obras_aplicadas: list[ObraAplicadaRespuesta]
    calibraciones: dict[str, dict[str, CalibracionRespuesta]]
    demanda: dict[str, DemandaRespuesta]
    # 039:RF-15: los clientes fijos que el operador subió «a su máxima» en la tabla cruzada.
    fijas_a_su_maxima: list[str] = Field(default_factory=list)
    last_seq: int
    jobs: list[JobRespuesta] | None = None
    warning: str | None = None


class ResumenEspacioRespuesta(Respuesta):
    id: str
    created_at: float | None
    inputs: dict[str, str | None]
    modified_at: float
    estado: Literal['ok', 'danado', 'version_futura']
    motivo: str | None = None
    restaurable: bool = False


class EntradaAsignadaRespuesta(EntradaRespuesta):
    slot: str
    workspace: EspacioRespuesta


class AsignacionEntradaRespuesta(Respuesta):
    slot: str
    name: str


class EntradaRechazadaRespuesta(Respuesta):
    name: str
    reason: str


class AutoEntradasRespuesta(Respuesta):
    assigned: list[AsignacionEntradaRespuesta]
    unassigned: list[EntradaRechazadaRespuesta]
    workspace: EspacioRespuesta


class ArchivoRespuesta(Respuesta):
    path: str
    size: int
    modified: float


class AmbitoFuenteRespuesta(Respuesta):
    companies: list[str]
    periods: list[str]
    selected_company: str | None
    selected_period: str | None
    ambiguous: bool


class InstalacionPowerFactoryRespuesta(Respuesta):
    nombre: str
    carpeta: str
    version: list[int]
    apis: list[str]
    #: La carpeta de la API que se usaría y con qué intérprete; ``None`` si a ninguna le hay intérprete (103:RF-2).
    api: str | None
    interprete: str | None
    motivo: str


class InstalacionesPowerFactoryRespuesta(Respuesta):
    """103:RF-3: las PowerFactory encontradas, la elegida por el operador y la que se usa."""
    instalaciones: list[InstalacionPowerFactoryRespuesta]
    eleccion: str | None
    en_uso: str | None
    fijada_por_variable: bool


class ElegirPowerFactoryPeticion(BaseModel):
    model_config = ConfigDict(extra='forbid')
    #: La carpeta ``Python\3.x`` de una instalación encontrada; ``None`` vuelve a la más nueva que funcione.
    carpeta_api: str | None = None


class EstadoPowerFactoryRespuesta(Respuesta):
    api_dir: str | None
    api_version: str | None
    instalacion: str | None = None
    interpreter: str | None
    interpreter_reason: str
    running_python: str
    available: bool


class SalidaRedRespuesta(Respuesta):
    """086:RF-69: una salida a la red, con quién decide si está encendida."""
    nombre: str
    encendida: bool
    #: ``variable`` (la de entorno, al arrancar), ``equipo`` (guardada desde la web) o ``edicion``.
    origen: Literal['variable', 'equipo', 'edicion']
    variable: str
    destino: str
    para_que: str
    #: Si la web puede cambiarla ahora: solo las de la lista, y no si la fija su variable (086:RF-68).
    cambiable: bool


class SalidasRedRespuesta(Respuesta):
    salidas: list[SalidaRedRespuesta]


class CambiarSalidaPeticion(BaseModel):
    model_config = ConfigDict(extra='forbid')
    encendida: bool
# --------------------------------------------------------------------------- spec 104: libros nuevos de demanda
class AvisoLibroRespuesta(Respuesta):
    """104:RF-20: lo que se dijo de un libro nuevo; ``ficha`` es la verificación entera."""
    id: str
    tipo: str
    libro: str | None = None
    texto: str
    cuando: float
    visto: bool
    ficha: dict[str, Any] | None = None


class LibrosNuevosRespuesta(Respuesta):
    """104:RF-1, RF-2, RF-20 a RF-23: avisos sin ver, revisiones y estado del dataset del pronóstico."""
    avisos: list[AvisoLibroRespuesta]
    ultima_revision: float | None
    proxima_revision: float | None
    intervalo_min: float
    repetidos: list[str]
    dataset: dict[str, Any] | None


class RevisarLibrosRespuesta(Respuesta):
    estado: LibrosNuevosRespuesta
    job: JobRespuesta | None
# --------------------------------------------------------------------------- 105: evolución de los clientes fijos
class EvolucionFijasPeticion(BaseModel):
    """105:RF-18, RF-19: alimentadores y rango de meses; un rango al revés o vacío se rechaza con 422."""
    model_config = ConfigDict(extra='forbid')
    alimentadores: list[str] = Field(min_length=1, max_length=500)
    desde: str = Field(pattern=r'^\d{4}-(0[1-9]|1[0-2])$')
    hasta: str = Field(pattern=r'^\d{4}-(0[1-9]|1[0-2])$')
    #: La participación en la máxima de cabecera lee sus libros, que pesan cientos de MB.
    con_cabecera: bool = True

    @model_validator(mode='after')
    def _rango(self) -> 'EvolucionFijasPeticion':
        limpios = [a.strip() for a in self.alimentadores]
        if not all(limpios):
            raise ValueError('un alimentador vacío')
        if self.hasta < self.desde:
            raise ValueError(f'el rango empieza en {self.desde} y termina antes, en {self.hasta}')
        self.alimentadores = list(dict.fromkeys(limpios))
        return self


class MesClienteFijoRespuesta(Respuesta):
    mes: str
    p_max: float
    fecha_p_max: str
    q_en_p_max: float | None
    q_max: float | None
    fecha_q_max: str | None
    p_media: float
    q_media: float | None
    energia_p: float
    energia_q: float | None
    fp: float | None
    factor_carga: float | None
    registros: int
    esperados: int
    completo: bool
    copia_de: str | None = None


class CrecimientoRespuesta(Respuesta):
    pct: float | None
    desde: str | None
    hasta: str | None


class VariacionMesRespuesta(Respuesta):
    pct: float | None
    respecto: str


class ResumenEvolucionRespuesta(Respuesta):
    p_max: float | None = None
    fecha_p_max: str | None = None
    crecimiento: dict[str, CrecimientoRespuesta]
    tendencia: dict[str, float | None]
    variacion: dict[str, dict[str, VariacionMesRespuesta]]
    mes_mayor: dict[str, str | None]


class VeredictoClienteRespuesta(Respuesta):
    """105:RF-34: cuántas fuentes dicen su alimentador y qué dice cada una que discrepa."""
    estado: Literal['confirmado', 'discrepa', 'una_fuente']
    fuentes: int
    acuerdan: list[str]
    texto: str


class ClienteEvolucionRespuesta(Respuesta):
    codigo: str
    alimentador: str
    sed: str
    cl: str = ''
    nombre: str = ''
    suministrador: str = ''
    #: Un resultado guardado antes de la conciliación no lo trae.
    veredicto: VeredictoClienteRespuesta | None = None
    anteriores: list[str]
    libros: list[str]
    meses: list[MesClienteFijoRespuesta]
    resumen: ResumenEvolucionRespuesta


class MesTotalFijosRespuesta(Respuesta):
    mes: str
    clientes: int
    p_max: float | None = None
    energia_p: float | None = None
    q_max: float | None = None
    energia_q: float | None = None
    p_max_coincidente: float | None = None
    fecha_coincidente: str | None = None
    copia_de: str | None = None


class CabeceraMesRespuesta(Respuesta):
    mes: str
    p_max: float
    fecha: str
    fijas_kw: float | None
    participacion: float | None
    copia_de: str | None = None


class TotalEvolucionRespuesta(Respuesta):
    alimentador: str
    clientes: int
    meses: list[MesTotalFijosRespuesta]
    resumen: ResumenEvolucionRespuesta
    cabecera: list[CabeceraMesRespuesta] | None = None


class AvisoEvolucionRespuesta(Respuesta):
    tipo: Literal['copia', 'incompleto', 'sin_suministro', 'sin_medicion', 'sin_clientes', 'sin_libro',
                  'contradiccion', 'lectura', 'cabecera', 'discrepancia', 'posible_renumeracion',
                  'fijos_sobre_cabecera']
    texto: str


class MesCopiadoRespuesta(Respuesta):
    mes: str
    de: str
    clientes: list[str]
    comparables: int


class LibroDelMesRespuesta(Respuesta):
    libro: str
    mes: str | None


class RenumeracionRespuesta(Respuesta):
    anterior: str
    actual: str
    alimentador: str
    #: Los meses en que los libros de clientes traen el código anterior (105:RF-35).
    meses: list[str] = Field(default_factory=list)


class PropuestaRenumeracionRespuesta(Respuesta):
    """105:RF-36: una renumeración posible, que no se aplica."""
    desaparece: str
    aparece: str
    mes: str
    por: Literal['CL', 'SED']
    valor: str


class ConciliacionRespuesta(Respuesta):
    confirmado: int
    discrepa: int
    una_fuente: int


class ArchivoDelLibroRespuesta(Respuesta):
    ruta: str | None
    aviso: str | None


class EvolucionResultadoRespuesta(Respuesta):
    alimentadores: list[str]
    desde: str
    hasta: str
    meses: list[str]
    libros: list[LibroDelMesRespuesta]
    suministros: str
    renumeraciones: list[RenumeracionRespuesta]
    propuestas: list[PropuestaRenumeracionRespuesta] = Field(default_factory=list)
    conciliacion: ConciliacionRespuesta | None = None
    #: Si la conciliación miró la red convertida del espacio.
    red: bool = False
    copias: list[MesCopiadoRespuesta]
    clientes: list[ClienteEvolucionRespuesta]
    totales: list[TotalEvolucionRespuesta]
    avisos: list[AvisoEvolucionRespuesta]
    libro: str
    archivo: ArchivoDelLibroRespuesta


class EvolucionFijasRespuesta(Respuesta):
    """105:RF-18: lo que el tablero necesita para pedir, y el último resultado del espacio."""
    alimentadores: list[str]
    meses: list[str]
    faltan: list[str]
    cabecera: bool
    archivo: str | None
    resultado: EvolucionResultadoRespuesta | None


class CurvaClienteFijoRespuesta(Respuesta):
    codigo: str
    puntos: list[tuple[str, float, float | None]]


class ArchivoInformesPeticion(BaseModel):
    """105:RF-29: la carpeta de archivo de esta máquina; vacía o ``None`` la quita."""
    model_config = ConfigDict(extra='forbid')
    ruta: str | None = None


class ArchivoInformesRespuesta(Respuesta):
    ruta: str | None
