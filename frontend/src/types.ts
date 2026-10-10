// Tipos de la API (src/igea_dgs/web). Se mantienen a mano: son pocos y cambian poco.

export type InputMode = 'txt' | 'mdb' | 'vnr';

export interface Options {
  input_mode: InputMode;
  source_company: string | null;
  source_period: string | null;
  source_crs: string;
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
  /** Libros de la demanda medida guardados en el espacio (spec 004, RF-39). */
  demanda?: Partial<Record<'medidores' | 'cabecera' | 'suministros' | 'clientes', DemandaLibro>>;
  last_seq: number;
  jobs?: Job[];
  warning?: string;
}

export interface Health {
  version: string;
  capabilities: { geography: boolean; xlsx: boolean; access: boolean; pandapower: boolean };
  crs_presets: { code: string; label: string }[];
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
  /** Solo la cabecera: los libros de la carpeta. */
  libros?: string[];
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
}

export interface ClientesCruce {
  alimentadores: string[];
  cruzados: ClienteImportante[];
  no_cruzados: ClienteImportante[];
  avisos: string[];
  totales: { clientes: number; cruzados: number; no_cruzados: number; por_actual: number; por_anterior: number; de_otros: number };
}

/** Spec 006: plan del ajuste a la máxima de cabecera. */
export interface AjustePlan {
  token: string;
  project: string;
  feeder: string;
  objetivo: { kw: number; kvar: number; medidor: string; alimentador: string; fecha: string | null };
  tolerancia: number;
  n_clientes: number;
  n_kva_entrada: number;
  avisos: string[];
}

export interface AjusteSed {
  sed: string;
  origen: 'cliente' | 'kva';
  kva: number | null;
  kva_de: 'pf' | 'entrada' | null;
  clientes: string[];
  antes: { kw: number; kvar: number };
  despues: { kw: number; kvar: number };
}

export interface AjusteInforme {
  project: string;
  feeder: string;
  modo: 'simular' | 'aplicar';
  variacion?: string;
  objetivo?: { kw: number; kvar: number; medidor: string; fecha: string | null };
  tolerancia?: number;
  cuadrado?: boolean;
  motivo?: string | null;
  cancelado?: boolean;
  flujos?: number;
  cabecera?: { kw: number; kvar: number } | null;
  perdidas?: { kw: number | null; kvar: number | null };
  /** Error relativo en la cabecera (medido − objetivo); «error» queda para los fallos. */
  desvio?: { kw: number | null; kvar: number | null };
  solo_kw?: boolean;
  todo_escala?: boolean;
  totales_sin_perdidas?: { kw: number; kvar: number };
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
  ambiguas?: { sed: string; motivo: string }[];
  fallos?: { sed: string; error: string }[];
  sed?: AjusteSed[];
}

export interface AjusteResultado {
  returncode: number;
  modo: string;
  report: string;
  project: string;
  informe: AjusteInforme;
}
