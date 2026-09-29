// Tipos de la API (src/igea_dgs/web). Se mantienen a mano: son pocos y cambian poco.

export type InputMode = 'txt' | 'mdb';

export interface Options {
  input_mode: InputMode;
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
  grupo: 'txt' | 'mdb' | 'comun';
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
  totals: Totals | null;
  conversion: { expected_dgs_files: number } | null;
  integrity: { errors: number; warnings: number } | null;
  catalog_report: CatalogReport | null;
  catalog_applied: boolean;
  catalog_file: string | null;
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
  conversion: Conversion | null;
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
