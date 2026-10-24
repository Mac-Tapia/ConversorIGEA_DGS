// Tipos de la API (src/igea_dgs/web). Se mantienen a mano: son pocos y cambian poco.

export type InputMode = 'txt' | 'mdb' | 'vnr';

export interface Options {
  input_mode: InputMode;
  source_company: string | null;
  source_period: string | null;
  /** null: el del perfil de empresa; sin perfil, hay que elegirlo (spec 002, RF-32). */
  source_crs: string | null;
  target_crs: string;
  include_geography: boolean;
  strict: boolean;
  write_preview: boolean;
  export_xlsx: boolean;
  export_tsv: boolean;
  /** Procesos en paralelo: 0 automático, 1 en serie. */
  workers: number;
  /** Formato fijo opcional. null ajusta el lienzo a la red a escala real. */
  hoja: 'A0' | 'A1' | 'A2' | 'A3' | 'A4' | null;
}

export interface SourceScope {
  companies: string[];
  periods: string[];
  selected_company: string | null;
  selected_period: string | null;
  ambiguous: boolean;
}

export type FeederReadiness =
  | 'INVENTORY_ONLY'
  | 'CONVERSION_READY'
  | 'READY_ORIGINAL'
  | 'READY_RECONSTRUCTED'
  | 'CONVERTED_WITH_ASSUMPTIONS'
  | 'NEEDS_OPERATOR_REVIEW'
  | 'DGS_READY'
  | 'POWERFACTORY_VERIFIED';

export interface ReconstructionEvidence {
  report: string;
  report_sha256: string;
  repairs: number;
  catalog_matches: number;
  assumptions: number;
  selection: string[];
}

export interface ReconstructionFeeder {
  feeder: string;
  network_id: string;
  readiness: FeederReadiness;
  blocking_codes: string[];
  source_quality: string;
  repair_count: number;
  assumption_count: number;
  catalog_sources: string[];
  convergence_state: string | null;
}

export interface ReconstructionResponse {
  source_run_id: string;
  source_fingerprint: string;
  source_sha256: Record<string, string>;
  feeders: ReconstructionFeeder[];
  repairs: number;
  catalog_matches: number;
  assumptions: number;
  report: string;
  report_sha256: string;
}

export interface DiagnosisResponse {
  source_run_id: string;
  source_mode: InputMode;
  source_fingerprint: string;
  feeders: ReconstructionFeeder[];
}

export interface ReconstructionDecision {
  entity_type: string;
  entity_id: string;
  field: string;
  original_value: unknown;
  applied_value: unknown;
  level: 'catalog_match' | 'engineering_assumption';
  rule: string;
  reason: string;
  confidence: number;
  candidates: string[];
  provenance: Record<string, unknown>;
}

export interface ReconstructionReport {
  version: number;
  report_sha256: string;
  source_sha256: Record<string, string>;
  decisions: ReconstructionDecision[];
  counts: Record<string, number>;
  feeders: ReconstructionFeeder[];
}

/** DGS de red unida: varios alimentadores en un solo fichero. */
export interface GroupDgs {
  name: string;
  feeders: string[];
  requested_feeders?: string[];
  status: 'ok' | 'failed' | 'cancelled';
  error: string | null;
  dgs: string | null;
  feeder_metadata?: string | null;
  converted_at?: number | null;
  preview_html?: string | null;
  xlsx?: string | null;
  hoja: { formato: string; orientacion: string; escala_1_a: number; cuadricula_mm: number } | null;
  ties: number | null;
  completitud: { fallos: string[] } | null;
  /** Spec 022, RF-49: «sistema» (por sistema eléctrico) o «unida» (dos o más). */
  tipo?: 'sistema' | 'unida';
}

export interface SlotSpec {
  grupo: 'txt' | 'mdb' | 'vnr' | 'comun';
  tipo: string | null;
  etiqueta: string;
  obligatorio: boolean;
  /** Formatos que el servidor admite en la casilla, si los fija él (VNR-GIS). */
  extensiones?: string[];
}

export interface InputMeta {
  path: string;
  name: string;
  size: number;
  origin: 'upload' | 'server';
  warning: string;
  set_at: number;
}

export interface CatalogReport {
  initial_coverage: number;
  final_coverage: number;
  types_in_network: number;
  added: Record<string, string[]>;
  unresolved: string[];
  text: string;
  critical: boolean;
}

export interface Totals {
  feeders: number;
  convertible_feeders: number;
  stub_feeders: number;
  sections: number;
  customer_loads: number;
  switches: number;
  [k: string]: number;
}

export interface UniversalSourceAudit {
  format: string;
  status: 'SOURCE_AUDIT_OK' | 'SOURCE_AUDIT_BLOCKED';
  source_run_id: string;
  source_mode: InputMode;
  source_fingerprint: string;
  totals: Record<string, number>;
  feeders: Array<{
    feeder: string;
    network_id: string;
    status: 'SOURCE_AUDIT_OK' | 'SOURCE_AUDIT_BLOCKED';
    counts: Record<string, number>;
    blocking_codes: string[];
    warning_codes: string[];
  }>;
  issues: Array<{
    code: string;
    severity: string;
    object_type: string;
    object_id: string;
    feeder: string;
    detail: string;
  }>;
}

export interface WorkspaceState {
  id: string;
  created_at: number;
  options: Options;
  inputs: Record<string, InputMeta>;
  missing_inputs: string[];
  loaded: boolean;
  loaded_at: number | null;
  active_run_id: string | null;
  loaded_run_id: string | null;
  source_mode: InputMode | null;
  source_fingerprint: string | null;
  source_manifest_url: string | null;
  totals: Totals | null;
  conversion: { expected_dgs_files: number } | null;
  integrity: { errors: number; warnings: number } | null;
  universal_audit: UniversalSourceAudit | null;
  catalog_report: CatalogReport | null;
  catalog_applied: boolean;
  catalog_file: string | null;
  reconstruction: {
    run_id: string;
    selection: string[];
    report: string;
    report_sha256: string;
  } | null;
  converted: number;
  groups?: GroupDgs[];
  /** Obras de mejora definidas y aún sin aplicar (spec 011, RF-95). */
  obras?: ObraGuardada[];
  /** Libros de la demanda medida guardados en el espacio (spec 004, RF-39). */
  demanda?: Partial<Record<'medidores' | 'cabecera' | 'suministros' | 'clientes' | 'estructura', DemandaLibro>>;
  last_seq: number;
  jobs?: Job[];
  warning?: string;
}

export interface PerfilEmpresa {
  nombre?: string;
  crs_origen?: string | null;
  patron_sed_medicion?: string | null;
  escala_diagrama?: number | null;
  forma_alimentador?: string | null;
  error: string | null;
}

export interface Health {
  version: string;
  capabilities: { geography: boolean; xlsx: boolean; access: boolean; pandapower: boolean };
  crs_presets: { code: string; label: string }[];
  /** Perfil de empresa activo (config/perfil_empresa.json); `error` si no se pudo leer. */
  perfil_empresa: PerfilEmpresa;
  slots: Record<string, SlotSpec>;
  default_options: Options;
  server_paths: boolean;
  /** Núcleos del servidor y cuántos procesos usa el modo automático. */
  parallel: { cpus: number; auto: number };
  source_modes: InputMode[];
}

export interface PowerFactoryStatus {
  api_dir: string | null;
  api_version: string | null;
  interpreter: string | null;
  interpreter_reason: string;
  running_python: string;
  available: boolean;
}

export type JobStatus = 'queued' | 'running' | 'done' | 'failed' | 'cancelled';

export interface Job {
  id: string;
  kind: string;
  title: string;
  workspace_id: string;
  lane: 'engine' | 'powerfactory';
  status: JobStatus;
  progress: { index: number; total: number; label: string } | null;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  result: any;
  error: string | null;
  created_at: number;
  started_at: number | null;
  finished_at: number | null;
  cancel_requested: boolean;
}

export interface Conversion {
  status: 'ok' | 'failed' | 'skipped' | null;
  error: string | null;
  errors_total: number | null;
  warnings: number;
  unresolved_line_types: string[];
  dgs: string | null;
  preview_html: string | null;
  xlsx: string | null;
  validation_txt: string | null;
  counts: Record<string, number> | null;
  converted_at: number | null;
  output_name: string | null;
  capacitor_banks: CapacitorBankEvidence[];
  capacitor_issues: Array<{
    capacitor_id: string;
    feeder: string;
    network_id: string;
    node_id: string;
    codes: string[];
  }>;
  capacitor_reread: CapacitorReread | null;
}

export interface CapacitorBankEvidence {
  loc_name: string;
  terminal: string;
  feeder: string;
  network_id: string;
  grid: string;
  phases: string;
  ctech: number;
  shtype: number;
  qcapn: number;
  ncapx: number;
  ncapa: number;
  ushnm: number;
  outserv: number;
  total_source_mvar: number | null;
  total_effective_mvar: number;
  capacity_origin: 'source' | 'catalog_voltage';
  correction: {
    code: string;
    node_id: string;
    nominal_kv?: number;
    before_total_kvar?: number | null;
    after_total_kvar?: number;
  } | null;
}

export interface CapacitorReread {
  status: 'VERIFICADO_PERSISTENCIA' | 'AVISO_PERSISTENCIA_CORREGIDA' | 'AVISO_PERSISTENCIA_NO_CORREGIDA';
  blocks_conversion: false;
  expected: number;
  reread: number;
  banks: Array<CapacitorBankEvidence & { total_native_mvar: number | null }>;
  mismatches: string[];
  corrections: Array<{
    loc_name: string;
    terminal: string;
    grid: string;
    field: string;
    before: unknown;
    after: unknown;
    message: string;
  }>;
}

export interface FeederRow {
  feeder: string;
  network_id: string;
  nominal_kv: string | number;
  sections: number;
  loads: number;
  switches: number;
  convertible: boolean;
  readiness: FeederReadiness;
  blocking_codes: string[];
  source_quality: string | null;
  repair_count: number;
  assumption_count: number;
  catalog_sources: string[];
  convergence_state: string | null;
  source_audit_status: 'SOURCE_AUDIT_OK' | 'SOURCE_AUDIT_BLOCKED' | 'SOURCE_AUDIT_NOT_AVAILABLE';
  source_audit_counts: Record<string, number>;
  source_run_id: string | null;
  source_mode: InputMode | null;
  source_fingerprint: string | null;
  conversion: Conversion | null;
}

export interface VnrPublication {
  publication_id: string;
  title: string;
  company: string;
  period_label: string;
  file_name: string;
  published_at?: string | null;
  download_url: string;
  convertible: boolean;
  status: 'OFFICIAL_DATA_PACKAGE' | 'REGULATORY_DOCUMENT_ONLY';
  evidence_sha256: string;
}

export interface VnrPublications {
  status: 'OFFICIAL_PACKAGE_AVAILABLE' | 'BLOCKED_MISSING_OFFICIAL_PACKAGE';
  publications: VnrPublication[];
  refresh: unknown;
}

export interface SourceRun {
  run_id: string;
  mode: InputMode;
  created_at: number;
  fingerprint: string;
  files: number;
  active: boolean;
  manifest_url: string;
}

export interface EventItem {
  seq: number;
  ts: number;
  type: 'log' | 'job';
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  data: any;
}

export interface OutputFile {
  path: string;
  size: number;
  modified: number;
}

export interface PfProject {
  name: string;
  /** Ruta dentro de la carpeta de importación (spec 005), p. ej. «2026-10/SI213». Las
   *  lecturas anteriores a la spec 005 no la traen: entonces vale el nombre. */
  path?: string;
  feeders: string[];
  native_inventory_sha256?: string | null;
  native_reread_at?: number | null;
  native_warning?: string | null;
  binding?: PowerFactoryProjectBinding | null;
  binding_blocked_reason?: string | null;
  /** Código estable de PROJECT_BINDING_* (p. ej. PROJECT_BINDING_MISSING), para elegir el texto. */
  binding_blocked_code?: string | null;
  /** Spec 018, RF-9: la ejecución fuente del vínculo sigue en disco y se puede usar aquí. */
  binding_fuente_disponible?: boolean;
  binding_warnings?: ProjectBindingWarning[];
}

export interface ProjectBindingWarning {
  code: 'PROJECT_BINDING_SOURCE_RUN_CHANGED' | 'PROJECT_BINDING_NATIVE_MODIFIED';
  message: string;
  elements: Array<{
    change: 'added' | 'removed' | 'modified';
    class: string;
    full_name: string;
  }>;
}

export interface PowerFactoryProjectBinding {
  schema_version: 'igea-dgs-powerfactory-project-binding-v1';
  project: string;
  folder: string;
  source_run_id: string;
  source_mode: InputMode;
  source_fingerprint: string;
  feeders: string[];
  dgs_sha256: Record<string, string>;
  native_inventory_sha256: string;
  native_reread: {
    status: string;
    recorded_at?: number;
    effective_reread?: Record<string, unknown>;
    /** Spec 015: estado del «Caso base» de cada alimentador, tal como lo dejó la aceptación. */
    caso_base?: Record<string, CasoBaseEstado>;
  };
  accepted_at: number;
  binding_sha256: string;
}

/** Resultado de «Leer proyectos de DIgSILENT». */
export interface PfInventario {
  folder?: string;
  exists?: boolean;
  aviso?: string | null;
  projects: PfProject[];
}

/** Plan validado de la spec 004: la web solo lee los libros; DIgSILENT decide qué coincide. */
export interface CargasPlan {
  token: string;
  kind: 'cargas_pf';
  project: string;
  /** Orden en que se aplicarán: el de la selección. */
  feeders: string[];
  variacion: string;
  demandas: { sed: string; hoja: string; kw: number; kvar: number; fp: number }[];
  nuevas: {
    sed: string; hoja: string; alimentador: string; barra: string;
    lat: number | null; lon: number | null; kva_instalado: number;
    kw: number; kvar: number; fp: number; tipo_linea: string; tension_bt_kv: number | null;
  }[];
  n_demandas: number;
  n_nuevas: number;
  row_errors: string[];
  omitidas_por_el_operador: string[];
  sin_datos: string[];
  applicable: boolean;
  tec: EconomiaTec | null;
  /** Spec 007: el ajuste sobre el que se integra, o null si se aplica sobre lo activo. */
  base: CargasBase | null;
  avisos: string[];
  calibradas_cambiadas: CalibradaCambiada[];
  variacion_demandas: string;
}

/** Spec 007, RF-1: las variaciones del ajuste aplicado, una por alimentador. */
export interface CargasBase {
  variaciones: string[];
  feeders: string[];
  ajustes: {
    feeder: string; variacion: string; cuadrado?: boolean;
    desvio?: { kw: number | null; kvar: number | null } | null;
    cabecera?: { kw: number; kvar: number } | null;
    objetivo?: { kw: number; kvar: number; medidor: string } | null;
  }[];
  excluidos: { feeder: string; motivo: string }[];
}

/** Spec 007, RF-21: una SED calibrada por el ajuste que el libro de demandas cambia. */
export interface CalibradaCambiada {
  sed: string;
  feeder: string | null;
  calibrada: { kw: number | null; kvar: number | null };
  libro: { kw: number; kvar: number };
}

/** Spec 007: lo que entra por la cabecera de un alimentador, sus pérdidas y su tensión mínima. */
export interface EstadoAlimentador {
  cabecera: { kw: number; kvar: number } | null;
  perdidas_kw: number | null;
  vm_min: number | null;
  vm_min_bus: string | null;
  motivo: string | null;
}

export interface EstadoRed {
  converged: boolean;
  vm_min?: number | null;
  vm_min_bus?: string | null;
  feeders: Record<string, EstadoAlimentador>;
}

/** Spec 007: una carga nueva en su variación, con proyecto frente a sin proyecto (RF-33). */
export interface CargaIntegrada {
  sed: string;
  alimentador: string;
  variacion: string;
  barra: string;
  criterio: string;
  distancia_m: number | null;
  nota: string | null;
  con_proyecto: EstadoRed | null;
  delta: { kw: number; kvar: number; perdidas_kw: number | null; vm_min: number | null } | null;
  economia?: { InvCosts: number } | null;
  tecnico_economico?: { ok: boolean; error?: string; resumen?: string[] } | null;
}

export interface CargasMotivo { sed: string; motivo: string }

/** Foto de una carga de DIgSILENT: los atributos de demanda tal como estaban. */
export type FotoCarga = Record<string, number | string | null>;

export interface CargaConectada {
  sed: string;
  barra: string;
  criterio: string;
  distancia_m: number | null;
  tipo_linea: string | null;
  origen_tipo_linea: string | null;
  tension_mt_kv: number | null;
  tension_bt_kv: number | null;
  kva_instalado?: number;
  aviso?: string | null;
  error_relectura?: string | null;
  /** Spec 007: la variación de esta carga (al simular, la que tendría). */
  variacion?: string;
  nota?: string | null;
}

export interface CargasFeederInforme {
  feeder: string;
  // Al simular
  actualizarian?: { sed: string; antes: FotoCarga; despues: { kw: number; kvar: number } }[];
  crearian?: CargaConectada[];
  // Al aplicar
  actualizadas?: { sed: string; antes: FotoCarga; despues: FotoCarga }[];
  creadas?: CargaConectada[];
  fallos?: { sed: string; error: string }[];
}

/** Informe de ``tools/cargas_pf.py``, uno por simulación o aplicación (RF-17, RF-20). */
export interface CargasInforme {
  project: string;
  modo: 'simular' | 'aplicar';
  variacion?: string;
  feeders: CargasFeederInforme[];
  avisos: string[];
  cancelado: boolean;
  sin_alimentador: CargasMotivo[];
  ambiguas: CargasMotivo[];
  no_creadas: CargasMotivo[];
  flujo?: {
    converged: boolean; return_code: number; ldf_valid: boolean;
    vm_min?: number; vm_min_bus?: string; vm_max?: number; vm_max_bus?: string;
  };
  tecnico_economico?: { ok: boolean; error?: string; resumen?: string[] };
  plan_errores_de_fila?: string[];
  // Spec 007
  base?: CargasBase | null;
  base_activada?: string[];
  variacion_demandas?: string;
  variaciones_activas_inicio?: string[];
  variaciones_activas_fin?: string[];
  sin_proyecto?: EstadoRed;
  cargas?: CargaIntegrada[];
  calibradas_cambiadas?: CalibradaCambiada[];
  // Spec 025
  casos?: { demandas: string; cargas: string };
  anio_casos?: number | null;
  /** RF-43: las cargas nuevas con las que «Con proyecto» no converge, probadas una a una. */
  no_convergen_juntas?: {
    caso: string; cargas: string[]; solas_que_no_convergen: string[]; basta_quitar_una_de: string[];
  };
  /** RF-61 a RF-66: «Cargas nuevas <año>», las cargas una a una hasta donde converge. */
  cargas_nuevas?: {
    caso: string; escenario?: string; converge: boolean | null; activas: string[];
    no_convergen: { variacion: string; sed?: string; alimentador?: string | null; kw?: number | null; texto?: string }[];
  };
}

/** Spec 025, RF-49 a RF-58: cada variante probada, con su fracción de sorteos y su costo. */
export interface EscaleraVariante {
  nombre: string;
  maxima: boolean;
  fraccion: number | null;
  factible: boolean;
  motivo: string;
  inversion: number | null;
  costo_anual: number | null;
  perdidas_kw: number | null;
  error: string | null;
}

/** Spec 025, RF-44, RF-54 a RF-56: la escalera optimizada de cada alimentador. */
export interface EscaleraResultado {
  project: string;
  anio_casos: number | null;
  moneda: string;
  tipo_cambio: number | null;
  sorteos: number;
  avisos: string[];
  alimentadores: {
    alimentador: string;
    avisos: string[];
    elegida: string | null;
    mas_cercana: string | null;
    aplicada: string[] | null;
    tabla: EscaleraVariante[];
  }[];
}

export interface CargasResultado {
  returncode: number;
  modo: string;
  report: string;
  project: string;
  informe: CargasInforme;
}

/** Parámetros de la evaluación técnico-económica (ComTececo). Años y %, US$/kWh. */
export interface EconomiaTec {
  inicio: number;
  fin: number;
  interes_pct: number;
  perdidas_usd_kwh: number;
  perdidas_vacio_usd_kwh: number;
  puntos: 'anual' | 'etapas';
}

/** Costes unitarios en US$ con los que se valora cada SED nueva. */
export interface Economia {
  costos: {
    sed_fijo_usd: number;
    trafo_usd_por_kva: number;
    linea_usd_por_km: number;
    vida_util_anios: number;
    valor_residual_pct: number;
    om_pct_anual: number;
  };
  tec: EconomiaTec | null;
}

// ------------------------------------------------------------ demanda medida (spec 004)

export interface DemandaLibro {
  name: string;
  origin: 'upload' | 'server';
  source_kind?: 'file' | 'folder';
  /** Cabecera o clientes: los libros de la carpeta. */
  libros?: string[];
  /** Suministros: el libro elegido; null si el hueco no tiene ninguno (004:RF-64). */
  seleccion?: string | null;
  catalogo?: LibroClientesMes[];
  /** Spec 025, RF-4: años con libro (subcarpetas de cuatro cifras). */
  anios?: number[];
  /** Spec 025, RF-28: índice de la cabecera, un libro por fila. */
  indice?: LibroCabeceraIndice[];
  vigente?: boolean;
  avisos?: string[];
  indexado_en?: number;
}

/** Un libro de la medición de cabecera en el índice por año (025:RF-28, RF-29). */
export interface LibroCabeceraIndice {
  relativa: string;
  anio: number | null;
  hojas: string[];
  meses: string[];
  error: string | null;
}

export interface LibroClientesMes {
  nombre: string;
  /** Spec 025, RF-1: año de su carpeta, o null si está suelto. */
  anio?: number | null;
  mes: string | null;
  origen_mes: 'nombre' | 'contenido' | 'manual' | 'sin_mes';
  activo: boolean;
  avisos: string[];
}

export interface DemandaMedidores {
  alimentador: string;
  medidores: string[];
  encontrado: boolean;
}

/** kW máximo de un medidor; kVAR, kVA y FP son del mismo registro (RF-27, RF-28). */
export interface MaximaCabecera {
  medidor: string;
  alimentador: string;
  libro: string;
  hojas: string[];
  fecha: string | null;
  kw: number | null;
  kvar: number | null;
  kva: number | null;
  fp: number | null;
  kva_calculado: boolean;
  fp_calculado: boolean;
  registros: number;
  columnas: Record<string, string>;
  avisos: string[];
  error: string | null;
  /** Registros sin fecha o sin kW, que no entran en la curva (spec 006, RF-37). */
  fuera_de_curva?: number;
}

/** Curva del registro de un medidor de cabecera, entera o un tramo (spec 006, RF-31 a RF-39). */
/** Central térmica en un tramo de un alimentador: sus tres medidores (spec 021, RF-25). */
export interface CentralTermica {
  generacion: string;
  llegada: string;
  salida: string;
  /** Barra del troncal en DIgSILENT; optativa al buscar la máxima. */
  nodo: string;
}

/** Medidores que no son de un alimentador de la red y las centrales del perfil (021:RF-26, RF-27). */
export interface MedidoresExternos {
  medidores: { alimentador: string; medidor: string }[];
  centrales_perfil: Record<string, CentralTermica>;
  aviso_perfil: string | null;
}

/** Máxima de demanda de un alimentador con central (spec 021, RF-28 a RF-34). */
export interface MaximaConCentral {
  alimentador: string;
  fecha: string | null;
  demanda_kw: number | null;
  arriba_kw: number | null;
  arriba_kvar: number | null;
  abajo_kw: number | null;
  abajo_kvar: number | null;
  generacion_kw: number | null;
  generacion_kvar: number | null;
  cabecera_kw: number | null;
  cabecera_kvar: number | null;
  signo_llegada: number;
  signo_salida: number;
  desbalance_mediana_kw: number | null;
  generacion_max_kw: number | null;
  descartados: number;
  registros_comunes: number;
  registros_cabecera: number;
  maxima_cabecera: { fecha: string; kw: number } | null;
  /** Spec 021, RF-50: el registro coincidente con los demás alimentadores, no la máxima. */
  coincidente: boolean;
  periodo: string | null;
  avisos: string[];
  error: string | null;
}

export interface CurvaCabecera {
  medidor: string;
  /** Primer y último registro de la curva entera, aunque se pida un tramo. */
  inicio: string;
  fin: string;
  maxima: { fecha: string; kw: number };
  /** `[fecha ISO sin zona, kW, kVAR]`, en orden; reducida a 2 000 como mucho. */
  puntos: [string, number, number | null][];
  /** Registros del tramo antes de reducir. */
  total: number;
  reducida: boolean;
  fuera_de_curva: number;
}

export interface ClienteImportante {
  codigo: string;
  fila: number;
  ea: number | null;
  eri: number | null;
  pot: number | null;
  cruzado_por: '' | 'actual' | 'anterior';
  suministro_actual: string;
  suministro_anterior: string;
  sed: string;
  radial: string;
  motivo: string;
  /** 004:RF-56: vacío si el libro no trae nombre. */
  nombre: string;
}

export interface ClientesCruce {
  alimentadores: string[];
  /** Spec 013, RF-16: libro y mes de donde salieron los clientes. */
  libro?: string;
  mes?: string | null;
  cruzados: ClienteImportante[];
  no_cruzados: ClienteImportante[];
  avisos: string[];
  totales: { clientes: number; cruzados: number; no_cruzados: number; por_actual: number; por_anterior: number; de_otros: number };
}

// ------------------------------------------------------------ informes (spec 017, paso 4.4)

/** Una carga nueva aplicada en el paso 3: la barra donde se conectó es su punto de diseño. */
export interface CargaAplicada {
  sed: string;
  alimentador: string;
  barra: string;
  variacion: string;
  distancia_m: number | null;
  kw: number | null;
  kvar: number | null;
  kva_instalado: number | null;
  /** Ingresada sola (formulario); las del libro van en bloque. */
  sola: boolean;
}

export interface InformeGenerado {
  tipo: 'estudio' | 'factibilidad';
  docx: string;
  json: string;
  alimentadores: string[];
  numero: string | null;
  fecha: string | null;
  huecos: string[];
  factible: boolean | null;
  creado: number;
}

export interface InformesContexto {
  /** Claves del perfil que faltan por tipo; vacío, se puede generar. */
  faltan: Record<'estudio' | 'factibilidad', string[]>;
  /** Banda y umbral que trae el perfil; los que falten se piden (RF-81). */
  limites: Partial<Limites>;
  estudios: Record<'sin' | 'con', { fichero: string; alimentadores: Record<string, boolean> } | null>;
  obras: Record<string, number>;
  cargas: CargaAplicada[];
  /** Por medidor de la última máxima buscada: factor de carga del mes de su máxima. */
  factor_carga: Record<string, { fc: number; mes: string }>;
  generados: InformeGenerado[];
  /** Lo escrito antes en los formularios de este proyecto (RF-82). */
  formularios: Partial<Record<'estudio' | 'factibilidad', Record<string, unknown>>>;
  /** Libro de pérdidas subido y lo que dice de cada alimentador marcado (RF-93, RF-94). */
  libro_perdidas: {
    name: string; origin: string; error: string | null;
    lecturas: Record<string, {
      sistema_electrico: string | null; codigo_sistema: string | null; reconocido_kw_pct: number | null;
      reconocido_kwh_pct: number | null; precio_compra: number | null; faltan: string[];
    }>;
  } | null;
}

export interface InformeEstudioForm {
  project: string;
  alimentador: string;
  fecha: string;
  lugar: string;
  numero: string;
  asunto: string;
  destinatario: string;
  antecedentes: string[];
  descripcion: string[];
  limites: Partial<Limites>;
  anio: number | null;
}

export interface InformeFactibilidadForm {
  project: string;
  alimentador: string;
  sed: string;
  fecha: string;
  lugar: string;
  numero: string;
  asunto: string;
  destinatario: string;
  limites: Partial<Limites>;
  factor_carga: number | null;
  codigo_punto: string;
  solicitud: {
    cliente: string; ubicacion: string; tipo_solicitud: string; potencia_kw: number | null;
    fecha_solicitud: string; set_nombre: string; tension_kv: number | null; transformador: string;
    expediente: string; en_concesion: boolean | null;
  };
  perdidas_reconocidas: {
    sistema_electrico: string; codigo_sistema: string; reconocido_kw_pct: number | null;
    reconocido_kwh_pct: number | null; precio_compra: number | null;
  };
  transformador_set: { kv: number | null; sin_pct: number | null; con_pct: number | null; caso: string };
}

/** Spec 017, T10: cargas de barra del proyecto de transmisión y sus casos de estudio. */
export interface TrafoCargas {
  project: string;
  casos: string[];
  caso_activo: string | null;
  cargas: { nombre: string; barra: string; kv: number | null; trafos: string[] }[];
}

export interface TrafoResultado {
  project: string;
  caso: string;
  carga: string;
  transformador: string;
  delta_kw: number;
  delta_kvar: number;
  avisos: string[];
  devanado: { kv: number | null; sin_pct: number | null; con_pct: number | null };
}

export interface InformeResultado {
  informe: string;
  json: string;
  huecos: string[];
  estudios: string[];
  etapa?: string | null;
  factible?: boolean;
  excesos?: string[];
  punto_diseno?: Record<string, number | null> | null;
}

/** Spec 006: plan del ajuste a la máxima de cabecera. */
export interface ClientPeriodEvidence {
  status: 'CLIENT_PERIOD_VERIFIED' | 'CLIENT_PERIOD_UNKNOWN' | 'NO_CLIENT_BOOK';
  period: string | null;
  file: string | null;
  sheet: string | null;
  fingerprint: string | null;
  period_origin: string | null;
  warning: string | null;
}

export interface AjustePeriodo {
  status: 'CLIENT_PERIOD_MATCH' | 'NO_CLIENT_BOOK';
  maxima: string | null;
  clientes: string | null;
}

export interface AjusteResumenAlimentador {
  feeder: string;
  objetivo: AjustePlan['objetivo'];
  n_clientes: number;
  n_desconectados?: number;
  n_kva_entrada: number;
  n_sed_fijas: number;
  n_sed_escaladas_estimadas: number;
  periodo: AjustePeriodo;
  client_evidence: ClientPeriodEvidence;
}

export interface AjustePlan {
  token: string;
  project: string;
  feeder: string;
  objetivo: { kw: number; kvar: number; medidor: string; alimentador: string; fecha: string | null };
  tolerancia: number;
  n_clientes: number;
  n_kva_entrada: number;
  n_sed_fijas: number;
  n_sed_escaladas_estimadas: number;
  periodo: AjustePeriodo;
  client_evidence: ClientPeriodEvidence;
  source: { source_run_id: string; source_mode: InputMode; source_fingerprint: string };
  project_binding: PowerFactoryProjectBinding;
  /** Spec 008: alimentadores que se ajustan, en orden, con su objetivo. */
  feeders?: string[];
  ajustes?: AjusteResumenAlimentador[];
  avisos: string[];
  /** Spec 025, RF-24: año de la medición y caso en que se graba la calibración. */
  anio_medicion?: number | null;
  anio_casos?: number | null;
  caso?: string;
}

export interface AjusteSed {
  sed: string;
  /** Spec 015, RF-44: 'escala'; 'kva' en informes de antes de la 015. */
  origen: 'cliente' | 'escala' | 'kva';
  kva: number | null;
  kva_de: 'pf' | 'entrada' | null;
  clientes: string[];
  antes: { kw: number; kvar: number };
  despues: { kw: number; kvar: number; fp: number };
  derivaciones?: {
    cliente: string; p_kw: number; q_kvar: number; fp: number;
    metodo: 'ERI/EA' | 'FP_CABECERA_FALLBACK'; ea: number | null; eri: number | null;
  }[];
  avisos?: string[];
}

/** Spec 015, RF-50: balance de la cabecera con lo que consumen las cargas en el flujo. */
export interface BalanceCabecera {
  cabecera_kw: number;
  fijas_consumida_kw: number | null;
  fijas_escrita_kw: number | null;
  escaladas_consumida_kw: number | null;
  escaladas_escrita_kw: number | null;
  escrita_kw: number;
  perdidas_kw: number | null;
  ajustes_del_flujo: Record<string, number>;
  causa_probable: string | null;
}

/** Spec 015, RF-49: una carga que no consume en el flujo lo que tiene escrito. */
export interface ConsumoDistinto {
  sed: string;
  clase: 'FIJA' | 'ESCALABLE';
  p_escrita_kw: number;
  p_consumida_kw: number;
  q_escrita_kvar: number;
  q_consumida_kvar: number | null;
  u_pu: number | null;
}

export interface ValidacionNativa {
  status: 'VALIDO' | 'REQUIERE_DISTRIBUCION';
  correcta: boolean;
  fallos: ({ tipo: string; cargas?: ConsumoDistinto[]; causa_probable?: string | null } &
    Record<string, unknown>)[];
  balance?: BalanceCabecera | null;
}

/** Spec 020: una SED fija por encima de su potencia instalada, con su propuesta. */
export interface SedSobrecargada {
  sed: string; clientes: string[]; p_kw: number; kva_carga: number; kva: number; carga_pct: number;
  transformadores?: { transformador: string; tipo: string | null; kva: number; unidades: number;
    kv_at: number | null; v_bt: number | null; grupo: string | null }[];
  propuesta?: { kva: number | null; motivo?: string; unidades?: number; po_w?: number; pc_w?: number;
    io_pct?: number; uk_pct?: number; norma?: string; codigo?: string; carga_pct_prevista?: number;
    tipo_nuevo?: string };
}

export interface AjusteInforme {
  project: string;
  feeder: string;
  status?: 'OK' | 'AVISO_KVAR' | 'VIOLACION_FISICA' | 'NO_CONVERGE' | 'FALLO_VALIDACION_NATIVA';
  criterio_cuadre?: 'KW_ONLY';
  /** Spec 015, RF-56: fijas con su EA/ERI; escaladas con el factor del perfil o del archivo. */
  factor_potencia_cargas?: {
    fijas: string; escaladas: number | null; escaladas_origen: string;
    /** Spec 015, RF-44: las escaladas, por la potencia instalada de su SED. */
    escaladas_reparto?: string;
  };
  /** Spec 015, RF-60: bancos ya instalados en el proyecto, tal como están. */
  bancos?: {
    banco: string; barra: string | null; kv: number | null; q_nominal_kvar: number | null;
    q_flujo_kvar: number | null; u_pu: number | null; en_servicio: boolean;
    /** Spec 015, RF-66: escalones conectados de los que tiene, «3 de 3». */
    escalones?: string;
  }[];
  /** Spec 015, RF-66: bancos puestos a su máxima capacidad al calibrar. */
  bancos_puestos_a_maxima?: { banco: string }[];
  /** Spec 015, RF-62, RF-63: clientes fijos compensados por su banco propio. */
  fijas_compensadas?: {
    sed: string; cliente: string; p_kw: number; fp_ea_eri: number; fp_escrito: number;
    q_ea_eri_kvar: number; q_escrita_kvar: number;
  }[];
  /** Spec 015, RF-59: fijas que piden más que la potencia instalada de su SED. */
  fijas_sobre_su_transformador?: SedSobrecargada[];
  /** Spec 020, RF-10: las tablas de fichas del perfil, o por qué no hay. */
  fichas_transformador_sed?: { umbral_carga_pct?: number; normas?: string[]; avisos?: string[]; falta?: string };
  /** Spec 020, RF-4: la sobrecarga es la causa probable de que la calibración no salga. */
  sobrecarga_causa_probable?: boolean;
  /** Spec 020, RF-24: los transformadores cambiados en «Sin proyecto». */
  transformadores_implementados?: {
    cambios: { sed: string; transformador: string;
      antes: { tipo: string | null; kva: number; unidades: number };
      despues: { tipo: string; kva: number; unidades: number; norma?: string } }[];
    omitidas: { sed: string; motivo: string }[];
  };
  /** Spec 020, RF-60, RF-61: cada elemento cambiado, lo original existente y lo nuevo. */
  cambios_en_la_red?: CambioEnLaRed[];
  /** Spec 020, RF-26, RF-32: lo que dejaron en la recalibración. */
  resultado_transformadores?: {
    status: 'VALIDO' | 'FALLO'; calibracion_valida: boolean; sobrecargadas: string[];
    sobre_umbral: { sed: string; carga_pct: number; kva: number }[]; motivos: string[]; aviso: string | null;
  };
  /** Spec 015, RF-49: la validación no pasó y las cargas volvieron a como estaban. */
  calibracion_revertida?: boolean;
  /** Spec 015, RF-47 a RF-52: lo que consumen las cargas en el flujo, después de calibrar. */
  validacion_posterior_nativa?: ValidacionNativa;
  modo?: 'simular' | 'aplicar';
  /** Spec 008: el ajuste de este alimentador falló; los demás siguieron. */
  error?: string;
  /** Spec 008: cancelado antes de empezar este alimentador. */
  no_empezado?: boolean;
  variacion?: string;
  /** Spec 015: el escenario de «Sin proyecto» donde quedó la calibración. */
  escenario?: string;
  objetivo?: { kw: number; kvar: number; medidor: string; fecha: string | null };
  tolerancia?: number;
  cuadrado?: boolean;
  motivo?: string | null;
  cancelado?: boolean;
  flujos?: number;
  cabecera?: { kw: number; kvar: number } | null;
  /** RF-29: la cabecera con el escenario de operación restaurado, que manda sobre la variación. */
  cabecera_con_escenario?: { kw: number; kvar: number } | null;
  /** Spec 015, RF-46: ajustes del flujo que se quedan en «Sin proyecto» porque cuadró con ellos. */
  ajustes_del_flujo_conservados?: Record<string, number>;
  /** RF-27, RF-28: escenarios en que se grabó también el resultado. */
  escenarios?: { escenario: string; cargas: number; fallos: { sed: string; error: string }[] }[];
  perdidas?: { kw: number | null; kvar: number | null };
  /** Error relativo en la cabecera (medido − objetivo); «error» queda para los fallos. */
  desvio?: { kw: number | null; kvar: number | null };
  solo_kw?: boolean;
  reparto_solo_kw?: boolean;
  /** RF-14: diferencia informativa cuando el kVAR no participa en la aceptación. */
  kvar_no_bloqueante?: {
    status: 'OK' | 'AVISO_KVAR';
    objetivo_kvar: number;
    red_nativa_kvar: number | null;
    diferencia_kvar: number | null;
    diferencia_relativa: number | null;
    tolerancia: number;
    supera_tolerancia: boolean;
    bloquea: false;
  };
  relectura_cargas_nativas?: {
    status: 'VERIFICADO_PERSISTENCIA' | 'AVISO_RELECTURA';
    cantidad: number;
    antes: NativeLoadReread[];
    despues: NativeLoadReread[];
    poblacion: Record<string, string | number>;
  };
  relectura_proyecto_vinculado?: Record<string, unknown>;
  relectura_bancos?: Record<string, unknown>;
  todo_escala?: boolean;
  totales_sin_perdidas?: { kw: number; kvar: number };
  /** Cada flujo del cuadre; ``a`` es el factor de escala (scale0) de las escaladas. */
  historial?: { flujo: number; a?: number; converge: boolean; kw?: number | null }[];
  remedios?: { remedio: string; cambios: string[] }[];
  diagnostico?: {
    barras_sin_tension: string[];
    n_barras_sin_tension: number;
    sobrecargados: { elemento: string; clase: string; carga_pct: number }[];
    tension_minima?: { barra: string; u_pu: number };
    sed_por_encima_de_su_transformador?: { sed: string; kva: number; carga_kva: number }[];
  };
  avisos: string[];
  omitidas?: { sed: string; motivo: string; clientes?: string }[];
  // Spec 006, RF-26: SED fuera de servicio porque se desmarcaron todos sus clientes.
  desconectadas?: { sed: string; clientes: string[] }[];
  ambiguas?: { sed: string; motivo: string }[];
  /** Escritura que DIgSILENT no aceptó; con ``detalle``, un fallo de la validación nativa. */
  fallos?: { sed?: string | null; error: string; detalle?: Record<string, unknown> }[];
  sed?: AjusteSed[];
}

export interface NativeLoadReread {
  sed: string;
  full_name: string;
  p_kw: number;
  q_kvar: number;
  fp: number;
  outserv: number;
  i_scale: number;
  mode_inp: string;
}

export interface AjusteResultado {
  returncode: number;
  modo: string;
  report: string;
  project: string;
  informe: AjusteInforme;
  /** Spec 008: uno por alimentador, en el orden del ajuste. */
  informes?: AjusteInforme[];
  reports?: string[];
  /** Spec 020: el plan del ajuste, para implementar transformadores desde su resultado. */
  token?: string;
}

/** Spec 008: verificación de la convergencia del proyecto con lo que tenga activo. */
export interface VerificarInforme {
  project: string;
  modo: 'verificar';
  avisos: string[];
  variaciones_activas?: string[];
  escenario?: string | null;
  flujo?: {
    converged: boolean;
    vm_min?: number;
    vm_min_bus?: string;
    vm_max?: number;
    vm_max_bus?: string;
  };
  feeders: { feeder: string; cabecera: { kw: number; kvar: number } | null; motivo: string | null }[];
}

/** Spec 015: el «Caso base» de un alimentador en el vínculo del proyecto. */
export interface CasoBaseEstado {
  status: 'VERIFICADO' | 'NO_VERIFICADO';
  comprobaciones: Record<string, boolean>;
  fallos: string[];
  recorded_at?: number;
}

/** Resultado de «Verificar el Caso base» (spec 015, RF-9). */
export interface CasoBaseResultado {
  project: string;
  feeders: {
    feeder: string;
    status: 'VERIFICADO' | 'NO_VERIFICADO';
    motivo?: string;
    comprobaciones?: Record<string, { pass: boolean; fallos: unknown[] }>;
    avisos?: string[];
    report?: string;
  }[];
}

export interface VerificarResultado {
  returncode: number;
  report: string;
  project: string;
  informe: VerificarInforme;
}

// ---------------------------------------------------------------------------
// Spec 011: obras de mejora, estudios y transferencia sobre la red calibrada
// ---------------------------------------------------------------------------

export type ClaseObra = 'condensador' | 'reconectador' | 'regulador' | 'seccion' | 'terna' | 'tension'
  | 'enlace' | 'migracion' | 'consigna';
export type ClaseTipo = 'TypLne' | 'TypTr2' | 'TypVoltreg' | 'TypRecl';
export type OrigenTipo = 'proyecto' | 'global' | 'otro';

export interface TipoRef {
  nombre: string;
  clase: ClaseTipo;
  origen?: OrigenTipo;
  proyecto?: string;
}

/** Una obra como la define el formulario; el servidor la valida (obras_pf.validar_obra). */
export interface Obra {
  clase: ClaseObra;
  alimentador: string;
  casos: string[];
  barra?: string;
  tramo?: string;
  tramos?: string[];
  q_kvar?: number;
  escalones?: number;
  consigna_pu?: number;
  rango_pct?: number;
  pasos?: number;
  tipo?: TipoRef;
  kv_destino?: number;
  /** Spec 016: sección de toda la troncal del camino más largo, y el tipo de sus cables. */
  toda_troncal?: boolean;
  tipo_cable?: TipoRef;
  /** Enlace: el alimentador que cede (``alimentador`` es el que recibe). */
  cede?: string;
  minima_m?: number;
  /** Barra, o «latitud, longitud», que indica el operador para el enlace. */
  origen?: string;
  destino?: string;
  /** Migración: el nodo desde el que se pasa a la tensión de destino. */
  nodo?: string;
}

export interface ObraGuardada extends Obra {
  id: string;
}

/** Un tipo de una biblioteca, con los datos que deciden la elección (RF-94). */
export interface TipoFicha {
  nombre: string;
  clase: ClaseTipo;
  origen: OrigenTipo;
  proyecto: string;
  datos: Record<string, number | string>;
  resumen: string;
}

export interface AlimentadorLeido {
  kv: number | null;
  barras: { nombre: string; kv: number | null }[];
  tramos: { nombre: string; tipo: string | null; nlnum: number }[];
}

export interface ObrasBibliotecas {
  project?: string;
  alimentadores?: Record<string, AlimentadorLeido>;
  tipos?: TipoFicha[];
  avisos?: string[];
}

export interface ObraFila {
  obra: number;
  clase: ClaseObra;
  alimentador: string;
  casos: string[];
  variacion: string;
  elementos: { elemento: string; clase: string; cambio: string }[];
  tipos: { nombre: string; clase: string; desde: string; origen: string; reutiliza: boolean }[];
  avisos: string[];
  error: string;
  casos_activos?: string[];
  flujo?: Record<string, { converge: boolean }>;
}

export interface ObrasResultado {
  report: string;
  project: string;
  aplicadas: string[];
  informe: {
    modo: 'simular' | 'aplicar';
    obras: ObraFila[];
    avisos: string[];
    comprobacion?: { alimentadores: string[]; diferencias: { alimentador: string; medida: string }[] } | null;
    error?: string;
  };
}

export interface Limites {
  tension_min_pu: number;
  tension_max_pu: number;
  cargabilidad_max_pct: number;
  origen?: string;
}

export interface EstudiosCatalogo {
  ofrecidos: { clave: string; nombre: string }[];
  no_ofrecidos: { clave: string; nombre: string; falta: string[]; motivo: string }[];
  limites: Limites | null;
  error_limites: string | null;
  limite_s: number;
}

export interface EstudiosPlan {
  token: string;
  project: string;
  feeders: string[];
  estudios: string[];
  excluidos: { feeder: string; motivo: string }[];
  avisos: string[];
  limites: Limites;
  limite_s: number;
}

export interface EstudiosResultado {
  project: string;
  feeders: string[];
  estudios: {
    caso: string; estudio: string; error: string | null; no_terminado: boolean; avisos: string[];
    obras_activas: string[];
  }[];
  ficheros: string[];
  cancelado: boolean;
  casos: { avisos?: string[]; excluidos?: { feeder: string; motivo: string }[] };
}

export interface MaximoTransferencia {
  punto: string;
  carga_kw: number;
  carga_kva: number;
}

export interface SentidoTransferencia {
  caso: string;
  cede: string;
  recibe: string;
  enlace: string;
  admite?: boolean;
  maximo_seccionador?: MaximoTransferencia | null;
  maximo_nodo?: MaximoTransferencia | null;
  limita?: { paso: number; punto: string; motivo: string; elemento: string | null; valor: number | null } | null;
  capacidad?: { metodo: string; capacidad_kw: number | null; margen_kw: number | null } | null;
  avisos?: string[];
}

export interface TransferenciaResultado {
  report: string;
  fichero: string | null;
  informe: { resultados: SentidoTransferencia[]; avisos: string[]; error?: string };
}

/** Un guion DPL o Python del operador (spec 011, RF-27). */
export interface GuionOperador {
  nombre: string;
  clase: 'ComDpl' | 'ComPython';
  origen: 'caso' | 'proyecto';
  /** Roles de los casos que lo tienen: «sin», «con». */
  casos: string[];
  parametros: { nombre: string; tipo: string; valor: string; unidad: string; descripcion: string }[];
  objetos: string[];
}

export interface GuionResultado {
  project: string;
  guion: string;
  cancelado: boolean;
  resultados: { caso: string; codigo_guion: number | null; salida: string[]; error: string | null; no_terminado: boolean }[];
}


/** Spec 020, RF-60: un elemento de la red que cambió la calibración. */
export interface CambioEnLaRed {
  sed: string;
  elemento: string;
  clase: 'transformador' | 'banco' | 'fuente';
  original: { descripcion: string; potencia: number | null; unidad: 'kVA' | 'kvar' | 'pu' };
  nuevo: { descripcion: string; potencia: number | null; unidad: 'kVA' | 'kvar' | 'pu' };
  motivo: string;
}

/** Spec 022, RF-39 a RF-44: una barra de SET con medidor, su máxima y sus alimentadores. */
export interface BarraDeSet {
  clave: string;
  set: string;
  kv: number;
  suelta: boolean;
  medidores: string[];
  centrales: { medidor: string; kw: number | null; kvar: number | null }[];
  alimentadores: string[];
  fecha: string;
  kw: number;
  kvar: number;
  registros: number;
}

/** Spec 022, RF-48: los zonales de la estructura con sus alimentadores en la entrega. */
export interface EstructuraResumen {
  origen: 'perfil' | 'excel' | null;
  sin_set?: string[];
  /** 022:RF-78: los de la entrega que la tabla no traía, con la regla que los colocó. */
  deducidos?: { alimentador: string; set: string; zonal: string; regla: string }[];
  zonales: { nombre: string; sets: string[]; alimentadores: string[] }[];
}

/** 022:RF-52 a RF-54: el sistema eléctrico de un proyecto convertido por sistema. */
export interface SistemaDelProyecto {
  grupo: string;
  alimentadores: string[];
  medidores?: Record<string, string[]>;
  calibrados?: string[];
  sin_medidor?: string[];
}

/** Spec 024: una obra propuesta por el PIDE, con su evaluación y su estado. */
export interface ObraPIDE {
  codigo: string;
  anio: number;
  alternativa: string;
  rubro: string;
  caracter: string;
  alimentador: string | null;
  elemento: string;
  causa: string;
  denominacion: string | null;
  ci: number;
  prioridad: number;
  sobredimensionada: boolean;
  descartada: string | null;
  motivo_sin_obra: string | null;
  variacion_autonoma?: string;
  regulada: { anualidad?: number; costo_anual?: number } | null;
  privada: { van: number; tir: number | null } | null;
}

export interface PideResultado {
  project: string;
  feeders: string[];
  formatos: string;
  anios: { anio: number; factor: number; converge: boolean; vm_min?: number | null; problemas: number }[];
  obras: ObraPIDE[];
  implementadas: { codigo: string; alternativa: string; variacion: string; aviso: string }[];
  avisos: string[];
}

export interface EpisodioResumen {
  episode_id: string;
  clase: string;
  caso: string;
  creado: string;
  project: string;
  feeders: string[];
  accion: string | null;
  bloqueos: string[];
  violaciones: string[];
}
