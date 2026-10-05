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
  hoja: { formato: string; orientacion: string; escala_1_a: number; cuadricula_mm: number } | null;
  ties: number | null;
  completitud: { fallos: string[] } | null;
}

export interface SlotSpec {
  grupo: 'txt' | 'mdb' | 'vnr' | 'comun';
  tipo: string | null;
  etiqueta: string;
  obligatorio: boolean;
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

export interface LoadPlan {
  token: string;
  kind: 'cargas';
  feeder: string;
  plan_file: string;
  summary: Record<string, number | boolean | string>;
  report: string;
  row_errors: string[];
  unknown: string[];
  updates: { sed: string; kw_before: number; kvar_before: number; kw_after: number; kvar_after: number }[];
  applicable: boolean;
}

export interface CreatePlan {
  token: string;
  kind: 'sed_nuevas';
  feeder: string;
  plan_file: string;
  summary: Record<string, number | boolean | string>;
  report: string;
  row_errors: string[];
  already_exists: string[];
  create: {
    sed: string;
    installed_kva: number;
    node_id: string;
    distance_m: number;
    conductor: string;
    binding: string;
    voltage_drop_pct: number;
    kw: number;
    kvar: number;
  }[];
  applicable: boolean;
}

export interface PfProject {
  name: string;
  feeders: string[];
}

export interface LotePlan {
  token: string;
  kind: 'lote';
  plan_file: string;
  project: string;
  /** Orden en que se aplicarán en PowerFactory: el de la selección. */
  order: string[];
  feeders_summary: {
    feeder: string;
    updates: number;
    unknown: string[];
    create: number;
    already_exists: string[];
    errors: number;
    routing_basis: ('sed_identity' | 'sheet_node_coordinates')[];
    scenario: string | null;
    variation: string | null;
    changes: {
      sed: string;
      before: { kw: number; kvar: number; fp: number };
      after: { kw: number; kvar: number; fp: number };
    }[];
    /** Inversión de la etapa de SED nuevas, en miles de US$ (si se dieron costes). */
    inversion_kusd?: number;
  }[];
  without_changes: string[];
  tec: EconomiaTec | null;
  row_errors: string[];
  applicable: boolean;
}

export type LoteFeederStatus = 'APPLIED' | 'ROLLED_BACK' | 'ROLLBACK_FAILED';

export interface LoteFeederResult {
  feeder: string;
  status: LoteFeederStatus;
  before: Record<string, Record<string, unknown>>;
  after: Record<string, Record<string, unknown>>;
  created: string[];
  comldf: { converged?: boolean; return_code?: number; ldf_valid?: boolean };
  rollback: {
    status: 'NOT_REQUIRED' | 'RESTORED' | 'PARTIAL';
    attempted: boolean;
    containers_deleted: string[];
    errors: string[];
  };
  actualizacion?: { escenario?: string } | null;
  creacion?: { variacion?: string } | null;
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
