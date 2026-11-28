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


class EvaluacionAccionesRespuesta(Respuesta):
    casos: int
    aciertos: int
    acierto: float | None
    aprendidas_de: int


class PuertasAccionesRespuesta(Respuesta):
    superadas: bool
    fallos: list[str]
    acierto_minimo: float
    casos_minimos: int


class AccionesAprendidasRespuesta(Respuesta):
    """026:RF-49: lo aprendido del operador, con su evaluación sobre casos que no vio y sus puertas."""
    tabla: list[list[str]]
    evaluacion: EvaluacionAccionesRespuesta
    puertas: PuertasAccionesRespuesta
    huella: str
    promovido: bool
    intacto: bool
    promovido_por: str | None = None
    promovido_en: str | None = None


class AprendidoRespuesta(Respuesta):
    """026:RF-49: el candidato medido, lo que está en uso y si el operador puede promover el candidato."""
    candidato: AccionesAprendidasRespuesta | None
    en_uso: AccionesAprendidasRespuesta | None
    se_puede_promover: bool
    motivo: str


class AprendidoPreviaRespuesta(AprendidoRespuesta):
    """026:RF-49: lo que se promovería, con la confirmación de un solo uso para ese candidato."""
    confirmacion: str


class PromoverAprendidoPeticion(BaseModel):
    model_config = ConfigDict(extra='forbid')
    huella: str = Field(min_length=1, max_length=128)
    confirmacion: str = Field(min_length=1, max_length=256)


class ProgresoRespuesta(Respuesta):
    index: int
    total: int
    label: str


class JobRespuesta(Respuesta):
    id: str
    kind: str
    title: str
    workspace_id: str
    lane: Literal['engine', 'powerfactory', 'asistente', 'control', 'correo', 'red']
    status: Literal['queued', 'running', 'done', 'parcial', 'no_converge', 'failed', 'cancelled', 'interrumpido']
    progress: ProgresoRespuesta | None
    result: Any = Field(description='Resultado variable según kind; incluye informes nativos y extensiones.')
    error: str | None
    created_at: float
    started_at: float | None
    finished_at: float | None
    cancel_requested: bool
    traza: str | None = None


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
    pf_proyecto_elegido: str | None = None                                     # 072:RF-45
    pf_alimentadores_elegidos: list[str] | None = None


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
    origin: Literal['upload', 'server', 'nube']
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
    # una obra de la escalera daba 500 (CA191 + CHN192, 2026-11-07).
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
    origin: Literal['upload', 'server', 'nube']
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
    # 086:RF-135: las máximas buscadas cuyas curvas sigue teniendo el servidor en memoria.
    curvas_cabecera: list[str] = Field(default_factory=list)
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


class CorreccionMedidorRespuesta(Respuesta):
    """039:RF-23: una corrección fechada del factor del medidor de un cliente."""
    codigo: str
    factor: float
    desde: str
    motivo: str = ''
    registrada: str
    # 039:RF-24: «operador» o «automatico» (deducida por la calibración), con la evidencia que la justifica.
    origen: str = 'operador'
    evidencia: dict[str, JsonValue] | None = None


class CorreccionesMedidorRespuesta(Respuesta):
    """039:RF-23: las correcciones del factor de medidor registradas en el espacio."""
    correcciones: list[CorreccionMedidorRespuesta]


class LibrosNuevosRespuesta(Respuesta):
    """104:RF-1, RF-2, RF-20 a RF-23: avisos sin ver, revisiones y estado del dataset del pronóstico."""
    avisos: list[AvisoLibroRespuesta]
    ultima_revision: float | None
    proxima_revision: float | None
    intervalo_min: float
    repetidos: list[str]
    dataset: dict[str, Any] | None
    #: 104:RF-31: el carril de fondo («libre», «pendiente», «revisando», «en_espera» o «error»), con su texto.
    fondo: dict[str, Any]


class FormatoPeticion(BaseModel):
    """089:RF-110: la huella que cita el aviso y la columna de cada campo (letra, como «K», o índice desde 0)."""
    model_config = ConfigDict(extra='forbid')
    huella: str = Field(pattern=r'^[0-9a-f]{12}$')
    columnas: dict[str, str] = Field(min_length=1, max_length=7)


class RevisarLibrosRespuesta(Respuesta):
    """104:RF-30: la revisión va al carril de fondo, no a la cola: no hay trabajo que seguir."""
    estado: LibrosNuevosRespuesta
    lanzada: bool
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


class CopiaDatosPeticion(BaseModel):
    """086:RF-85: la carpeta donde se hace la copia; se recuerda en el equipo."""
    model_config = ConfigDict(extra='forbid')
    carpeta: str = Field(min_length=1, max_length=1024)
    sin_modelos: bool = False
    #: Aclaración de 086:RF-82 (2026-11-16): la copia solo empieza tras ver la previa y pulsar «Copiar».
    confirmada: bool = False


class CopiaDatosCarpetaRespuesta(Respuesta):
    """086:RF-85: la carpeta de las copias que recuerda este equipo, si hay."""
    carpeta: str | None


class RaizPreviaCopia(Respuesta):
    """086:RF-108: una de las cosas que se copian, con lo que ocupa (cada fichero físico una vez)."""
    nombre: str
    etiqueta: str
    ruta: str
    ficheros: int
    bytes: int


class CopiaExistente(Respuesta):
    """086:RF-108: una copia que ya está en la carpeta destino, leída de su manifiesto sin tocarla."""
    nombre: str
    ruta: str
    estado: Literal['buena', 'con_errores', 'no_valida', 'a_medias']
    motivo: str | None
    creada: float | None
    bytes: int | None
    ficheros: int | None
    nombres: int | None
    errores: int


class CopiaDatosPreviaRespuesta(Respuesta):
    """086:RF-82, RF-83, RF-108: lo que ocupará la copia, el libre del destino y lo que ya hay, sin escribir nada."""
    destino: str
    ficheros_fisicos: int
    nombres: int
    bytes_fisicos: int
    bytes_logicos: int
    libre: int
    margen: int
    cabe: bool
    texto: str
    raices: list[RaizPreviaCopia]
    copias: list[CopiaExistente]


# ------------------------------------------------------------------ spec 110: envío de informes por correo
EstadoEnvioCorreo = Literal['reservado', 'enviando', 'aceptado', 'rechazado', 'desconocido', 'cancelado']


class CorreoVistaPreviaPeticion(BaseModel):
    """110:RF-1: lo que la ventana (o el asistente, que solo deja el borrador, RF-6) pide preparar."""
    model_config = ConfigDict(extra='forbid')
    informe: str = Field(min_length=1, max_length=255)
    cuenta: str = Field(min_length=3, max_length=320)
    proveedor: Literal['google', 'microsoft']
    para: list[str] = Field(min_length=1, max_length=100)
    cc: list[str] = Field(default_factory=list, max_length=100)
    cco: list[str] = Field(default_factory=list, max_length=100)
    asunto: str = Field(default='', max_length=998)
    cuerpo: str | None = Field(default=None, max_length=100_000)
    enlace: str | None = Field(default=None, max_length=2048)
    expediente: str | None = Field(default=None, max_length=512)
    proyecto: str | None = None
    escenario: str | None = None
    adjuntar: list[Literal['docx', 'pdf', 'xlsx']] = Field(default_factory=lambda: ['docx', 'pdf', 'xlsx'])
    origen: Literal['web', 'asistente', 'documento'] = 'web'


class CorreoAdjuntoRespuesta(Respuesta):
    nombre: str
    tamano: int
    sha256: str


class CorreoValidezRespuesta(Respuesta):
    """110:RF-12: si el informe vale como estudio, y si no, por qué."""
    valido: bool
    motivo: str


class CorreoAvisoRespuesta(Respuesta):
    """110:RF-14: una dirección que no es habitual en el espacio, con la parecida si la hay."""
    aviso: str
    sugerencia: str | None


class CorreoVistaPrevia(Respuesta):
    borrador: str
    firma: str
    cuenta: str
    proveedor: str
    para: list[str]
    cc: list[str]
    cco: list[str]
    asunto: str
    cuerpo: str
    enlace: str | None
    adjuntos: list[CorreoAdjuntoRespuesta]
    validez: CorreoValidezRespuesta
    avisos: dict[str, CorreoAvisoRespuesta]
    limite_bytes: int
    excede_limite: bool
    confirmado: bool
    ventana: str


class CorreoConfirmacionPeticion(BaseModel):
    model_config = ConfigDict(extra='forbid')
    firma: str = Field(min_length=64, max_length=64)


class CorreoResolucionPeticion(BaseModel):
    """110:RF-9: el operador dice si un envío desconocido llegó (lo vio en Enviados) o no."""
    model_config = ConfigDict(extra='forbid')
    llego: bool


class CorreoEnvio(Respuesta):
    """110:RF-8: el recibo de un envío, como lo guarda ``correo.envios``."""
    clave: str
    espacio: str
    borrador: str
    intento: int
    estado: EstadoEnvioCorreo
    hora: str
    #: El orden de la reserva (nanosegundos, creciente): el historial va del más antiguo al más reciente aunque
    #: dos envíos caigan en el mismo segundo de ``hora`` (110:RF-13). Un recibo anterior no lo trae: 0.
    orden: int = 0
    hora_resultado: str | None
    proveedor: str
    cuenta: str
    destinatarios: dict[str, list[str]]
    informe: str | None
    huella_informe: str | None
    adjuntos: list[CorreoAdjuntoRespuesta]
    enlace: str | None
    message_id: str
    id_proveedor: str | None
    codigo: int | None
    motivo: str
    resolucion: Literal['llego', 'no_llego'] | None
    pasos: list[dict[str, JsonValue]]


class CorreoConfirmacion(Respuesta):
    """110:RF-5, RF-7: la clave reservada y el trabajo encolado, o el recibo que ya había (doble clic)."""
    clave: str
    trabajo: JobRespuesta | None
    recibo: CorreoEnvio | None


class CorreoHistorial(Respuesta):
    """110:RF-13: los envíos de un informe, del más antiguo al más reciente."""
    informe: str
    envios: list[CorreoEnvio]


# ------------------------------------------------------------------ 111: el plano de la red (web/plano_api.py)
class DeducidoPlanoRespuesta(Respuesta):
    """111:RF-3: lo que se dedujo de un elemento, con su regla y su motivo."""
    campo: str
    original: JsonValue = None
    valor: JsonValue = None
    regla: str
    motivo: str
    confianza: float | None = None
    nivel: str | None = None


class TramoPlanoRespuesta(Respuesta):
    codigo: str
    nombre_pf: str
    desde: str
    hasta: str
    fases: str
    tipo: str
    aereo: bool
    longitud_m: float
    #: 111:RF-26: la sección del conductor en mm², del código del catálogo; ``None`` si no se deduce.
    seccion_mm2: float | None = None
    vertices: list[list[float]]
    paralelo_con: list[str]
    original: dict[str, JsonValue]
    deducido: list[DeducidoPlanoRespuesta]
    calidad: Literal['ok', 'aviso', 'error', 'sin_coordenadas']
    avisos: list[str]
    errores: list[str]


class BarraPlanoRespuesta(Respuesta):
    codigo: str
    nombre_pf: str
    lat: float | None
    lon: float | None
    deducido: list[DeducidoPlanoRespuesta]
    calidad: Literal['ok', 'aviso', 'error', 'sin_coordenadas']
    avisos: list[str]
    errores: list[str]


class SedPlanoRespuesta(Respuesta):
    codigo: str
    nombre_pf: str
    barra: str | None
    tramo: str | None
    kva: float | None


class ManiobraPlanoRespuesta(Respuesta):
    codigo: str
    nombre_pf: str
    clase: str
    tramo: str | None
    barra: str | None
    estado: Literal['abierto', 'cerrado']


class ColisionPlanoRespuesta(Respuesta):
    tipo: str
    nombre_pf: str
    codigos: list[str]


class BarraUnifilarRespuesta(Respuesta):
    codigo: str
    nivel: int
    orden: int


class UnifilarPlanoRespuesta(Respuesta):
    """111:RF-23: el unifilar del alimentador desde su cabecera; las barras con su nivel y su orden, por su código."""
    fuente: str | None
    barras: list[BarraUnifilarRespuesta]
    niveles: int
    ancho: int
    sin_alcanzar: list[str]


class VistaPlanoRespuesta(Respuesta):
    """111:RF-1 a RF-3, RF-11, RF-23: un alimentador con todos los vértices de su fuente, su revisión de la red y su
    unifilar."""
    alimentador: str
    kv: float
    fuente: str
    unifilar: UnifilarPlanoRespuesta
    source_crs: str | None
    target_crs: str | None
    sin_coordenadas: bool
    tramos: list[TramoPlanoRespuesta]
    barras: list[BarraPlanoRespuesta]
    sed: list[SedPlanoRespuesta]
    maniobras: list[ManiobraPlanoRespuesta]
    tipos_de_linea: list[str]
    colisiones: list[ColisionPlanoRespuesta]
    avisos: list[str]
    revision: str


class MotorPlanoRespuesta(Respuesta):
    """111:RF-17, RF-18: con qué motor se estudiaría ahora y por qué; RF-29: si el operador puede pedir DIgSILENT."""
    motor: Literal['DIgSILENT', 'abierto']
    texto: str
    motivo: str
    # 086:RF-60: el título del esquema, con la I mayúscula (Pydantic lo deriva del nombre del campo).
    digsilent_posible: bool = Field(default=False, title='DIgSILENT posible')


class FondoPlanoRespuesta(Respuesta):
    """086:RF-22, RF-65: el mapa base solo con la salida «teselas» encendida."""
    encendido: bool
    motivo: str


class ManiobraTransferenciaRespuesta(Respuesta):
    codigo: str
    clase: str
    estado: Literal['abierto', 'cerrado']
    alimentador: str


class TransferenciaPlanoRespuesta(Respuesta):
    """111:RF-25: una barra donde se tocan dos o más alimentadores del plano, con sus maniobras de la fuente."""
    barra: str
    lat: float | None
    lon: float | None
    alimentadores: list[str]
    maniobras: list[ManiobraTransferenciaRespuesta]


class PlanoRespuesta(Respuesta):
    alimentadores: list[str]
    sin_coordenadas: list[str]
    transferencias: list[TransferenciaPlanoRespuesta] = []
    vistas: list[VistaPlanoRespuesta]
    motor: MotorPlanoRespuesta
    fondo: FondoPlanoRespuesta


class VariacionPlanoRespuesta(Respuesta):
    """111:RF-4, RF-5, RF-9: la variación guardada en el espacio, con su versión y su diario."""
    formato: str
    id: str
    alimentador: str
    caso: str
    revision: str
    revision_cambiada: bool
    version: int
    estado: Literal['abierta', 'confirmada']
    ediciones: list[dict[str, JsonValue]]
    deshechas: list[dict[str, JsonValue]]


class VariacionesPlanoRespuesta(Respuesta):
    """111:RF-4, RF-12: las variaciones guardadas en el servidor y las que ya tienen estudio, para comparar."""
    variaciones: list[VariacionPlanoRespuesta]
    estudiadas: list[str]


class AbrirVariacionPeticion(BaseModel):
    model_config = ConfigDict(extra='forbid')
    alimentador: str = Field(min_length=1, max_length=255)
    caso: str = Field(min_length=1, max_length=255)
    revision: str = Field(pattern=r'^[0-9a-f]{64}$')


class TurnoVariacionPeticion(BaseModel):
    """111:RF-4, RF-9: la versión que el navegador leyó; si ya cambió, 409."""
    model_config = ConfigDict(extra='forbid')
    version: int = Field(ge=0)


class EditarVariacionPeticion(TurnoVariacionPeticion):
    edicion: dict[str, JsonValue]


class AjustePlanoPeticion(BaseModel):
    model_config = ConfigDict(extra='forbid')
    punto: list[float] = Field(min_length=2, max_length=2)


class PropuestaAjusteRespuesta(Respuesta):
    """111:RF-7: el nodo cercano como propuesta, con la distancia; no cambia nada."""
    punto: list[float]
    nodo: str | None
    distancia_m: float | None
    mas_cercano: str | None
    distancia_mas_cercano_m: float | None
    radio_m: float
    radio_origen: str


class EstudiarPlanoPeticion(BaseModel):
    model_config = ConfigDict(extra='forbid')
    project: str | None = Field(default=None, max_length=255)
    #: 111:RF-29: el motor que pide el operador; sin él (o «automatico»), la elección de siempre (RF-17).
    motor: Literal['automatico', 'abierto', 'DIgSILENT'] | None = None


class NormaHallazgoRespuesta(Respuesta):
    """111:RF-21: la norma de la biblioteca que fija el umbral de un hallazgo, o ``falta`` con el motivo de que no la haya."""
    clave: str | None = None
    acto: str | None = None
    articulo: str | None = None
    pagina: str | None = None
    cita: str | None = None
    estado: str | None = None
    obligatoria: bool | None = None
    #: El umbral es un criterio de la empresa (su perfil), no una norma: la clave y su origen.
    criterio_empresa: str | None = None
    origen: str | None = None
    falta: str | None = None


class IncumplePlanoRespuesta(Respuesta):
    """111:RF-13: un incumplimiento con texto, icono, valor y umbral, no solo color; RF-21: y la norma que lo fija."""
    texto: str
    icono: str
    valor: float
    umbral: float
    norma: NormaHallazgoRespuesta | None = None


class ElementoCapaRespuesta(Respuesta):
    codigo: str
    valor: JsonValue = None
    kv: float | None = None
    banda: str
    incumple: IncumplePlanoRespuesta | None
    motor: str


class LeyendaCapaRespuesta(Respuesta):
    magnitud: str
    unidad: str
    umbral: dict[str, float] | None
    caso: str
    revision: str
    motor: str
    motor_texto: str
    origen_umbral: str


class CapaPlanoRespuesta(Respuesta):
    leyenda: LeyendaCapaRespuesta
    elementos: list[ElementoCapaRespuesta]


class CapasPlanoRespuesta(Respuesta):
    """111:RF-10, RF-11, RF-13, RF-18: lo que se pinta, o por qué no."""
    pintable: bool
    motivo: str
    mensajes: list[str]
    capas: dict[str, CapaPlanoRespuesta]
    motor: str | None
    motor_texto: str
    caso: str | None
    revision: str | None
    origen_umbral: str | None = None
    variacion: str | None = None


class CasoComparadoRespuesta(Respuesta):
    caso: str | None
    variacion: str | None
    motor: str | None


class ElementoComparadoRespuesta(Respuesta):
    codigo: str
    magnitud: Literal['tension', 'corriente', 'cargabilidad', 'estado']
    a: JsonValue = None
    b: JsonValue = None
    diferencia: float | None
    banda_a: str
    banda_b: str
    solo_en: Literal['a', 'b'] | None


class ComparacionPlanoRespuesta(Respuesta):
    """111:RF-12, RF-19: dos casos por elemento; si los motores son distintos, se dice junto a la diferencia."""
    casos: list[CasoComparadoRespuesta]
    mismo_motor: bool
    aviso_motores: str | None
    comparable: bool
    motivo: str
    elementos: list[ElementoComparadoRespuesta]


class EvidenciaMatrizRespuesta(Respuesta):
    """100:RF-9: una spec de la evidencia de una celda y la palabra de su línea ``Estado:`` (``None`` si no se lee)."""
    spec: str
    estado: str | None


class CeldaMatrizRespuesta(Respuesta):
    motor: str
    estado: Literal['validado', 'sin_validar', 'no_disponible']
    motivo: str
    evidencia: list[EvidenciaMatrizRespuesta]


class EstudioMatrizRespuesta(Respuesta):
    clave: str
    nombre: str
    celdas: list[CeldaMatrizRespuesta]


class MotorMatrizRespuesta(Respuesta):
    clave: str
    nombre: str


class AceptacionMatrizRespuesta(Respuesta):
    """100:RF-21, RF-23: la aceptación de la versión que corre la web: su versión y su fecha."""
    version: str
    fecha: str


class MatrizEstudiosRespuesta(Respuesta):
    """100:RF-8, RF-10, RF-13: la matriz estudio × motor que sirve ``GET /api/estudios/matriz`` y de dónde salen sus estados."""
    origen: Literal['specs', 'recurso', 'ninguno']
    aceptacion: AceptacionMatrizRespuesta | None = None
    motores: list[MotorMatrizRespuesta]
    estudios: list[EstudioMatrizRespuesta]


class OpcionEntrenamientoRespuesta(Respuesta):
    """113:RF-16: dónde se puede entrenar; este equipo siempre."""
    donde: Literal['local', 'colab']
    disponible: bool
    texto: str
    motivo: str | None = None


class ColabEstadoRespuesta(Respuesta):
    """113:RF-4, RF-16: las opciones, la carpeta de Drive, las familias y los paquetes ya preparados."""
    opciones: list[OpcionEntrenamientoRespuesta]
    drive: str | None
    familias: list[str]
    paquetes: list[dict[str, JsonValue]]
    #: 113:RF-13: las familias cuyo dataset creció desde que se preparó, para proponer reentrenarlas.
    reentrenar: list[dict[str, JsonValue]]


class ColabPrepararPeticion(BaseModel):
    """113:RF-4: el dataset que sale; sin confirmación es la previa, con ella se prepara el paquete."""
    model_config = ConfigDict(extra='forbid')
    familia: str = Field(min_length=1, max_length=64)
    dataset: str = Field(min_length=1, max_length=1024)
    confirmacion: str | None = Field(default=None, max_length=256)


class ColabPreviaRespuesta(Respuesta):
    """113:RF-4: lo que subiría y a dónde, con la confirmación de un solo uso para ese dataset."""
    revision: str
    en_github: bool
    cambios_sin_commit: list[str]
    ficheros: int
    bytes: int
    prohibidos: list[str]
    anonimizacion: str
    destino: str
    confirmacion: str | None


class ColabPaqueteRespuesta(Respuesta):
    """113:RF-4: el paquete en Drive y el enlace de Colab al cuaderno en la revisión exacta."""
    paquete: str
    huella: str
    ficheros: int
    colab: str


class ColabTraerRespuesta(Respuesta):
    """113:RF-10, RF-11: los candidatos traídos sin activar, y los rechazados con su motivo."""
    candidatos: list[dict[str, JsonValue]]


class CapexVigenteDato(Respuesta):
    """042:RF-113: el libro CAPEX vigente y de dónde sale."""
    ruta: str
    nombre: str
    origen: Literal['perfil', 'referencias']


class CapexVigenteRespuesta(Respuesta):
    """042:RF-113: el libro CAPEX que se usa con la casilla en blanco, o ``None``."""
    vigente: CapexVigenteDato | None


class FilaPerdidas(Respuesta):
    """017:RF-156: un alimentador en un caso: pérdidas, tramo más cargado y punto de MT más bajo."""
    proyecto: str
    alimentador: str
    caso: str
    converge: bool
    cabecera_kw: float | None
    perdidas_kw: float | None
    perdidas_pct: float | None
    tramo: str | None
    cargabilidad_pct: float | None
    barra_mt: str | None
    u_min_pu: float | None
    caida_pct: float | None
    solo_media: bool
    barras_sin_tension: int = 0
    cabecera_calibrada_kw: float | None = None
    aviso: str | None = None


class CasoSinEstudio(Respuesta):
    """017:RF-156: un caso de un proyecto sin estudio de flujo guardado."""
    proyecto: str
    caso: str


class CuadroPerdidasRespuesta(Respuesta):
    """017:RF-156: el cuadro de pérdidas por alimentador y caso, y los casos que faltan."""
    filas: list[FilaPerdidas]
    faltan: list[CasoSinEstudio]


# --------------------------------------------------------------------------- 114: el agente MASAC en sombra
class AgenteSombraPeticion(BaseModel):
    """114:RF-7: el proyecto, sus alimentadores (vacío, todos los de la red capturada) y el caso de su red."""
    model_config = ConfigDict(extra='forbid')
    project: str = Field(min_length=1, max_length=200)
    feeders: list[str] = Field(default_factory=list, max_length=500)
    caso: Literal['sin_proyecto', 'con_proyecto'] = 'sin_proyecto'
    #: Sin él, el del perfil de empresa para la tensión de la red.
    banco_kvar: float | None = Field(default=None, gt=0, le=10000)


class ResultadoAgenteSombra(Respuesta):
    """114:RF-19: cómo queda la red con lo que propone uno y otro, medido igual."""
    en_norma: bool | None
    costo: float | None
    costo_maniobras: float | None
    vm_min: float | None
    perdidas_mw: float | None
    obras: list[str]


class DecisionAgenteSombra(Respuesta):
    """114:RF-11: una decisión del agente con su explicación y lo que hizo con ella el operador."""
    id: str
    agente: str
    tipo: str
    elemento: str
    explicacion: str
    estado: Literal['propuesta', 'confirmada', 'deshecha']
    confirmo: str | None


class PropuestaAgenteSombra(Respuesta):
    propuesta: str
    fecha: str | None
    caso: str | None
    feeders: list[str]
    acierta: Literal['agente', 'regla', 'empate']
    agente: ResultadoAgenteSombra
    regla: ResultadoAgenteSombra
    decisiones: list[DecisionAgenteSombra]


class MarcadorAgenteSombra(Respuesta):
    agente: int
    regla: int
    empate: int


class AgenteSombraEstadoRespuesta(Respuesta):
    """114:RF-7: las propuestas del proyecto y el marcador frente a la regla actual; nada aplicado."""
    project: str
    modo: Literal['sombra']
    aciertos: MarcadorAgenteSombra
    propuestas: list[PropuestaAgenteSombra]
    hay_politica: bool


class DecisionAgentePeticion(BaseModel):
    """114:RF-11: confirmar o deshacer una decisión del agente."""
    model_config = ConfigDict(extra='forbid')
    accion: Literal['confirmar', 'deshacer']


class DecisionAgenteRespuesta(Respuesta):
    """114:RF-9: la decisión queda en el registro; no se aplica nada en DIgSILENT."""
    id: str
    estado: Literal['propuesta', 'confirmada', 'deshecha']
    confirmo: str | None
    aplicada: Literal[False]
