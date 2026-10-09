import type {
  CargasPlan, ClientesCruce, DemandaMedidores, Economia, FeederRow, Health, Job, MaximaCabecera,
  Options, OutputFile, PowerFactoryStatus, ReconstructionReport, WorkspaceState,
} from './types';

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

/** Convierte una respuesta fallida en `ApiError` con el `detail` del servidor.
 *
 * Un 422 de FastAPI trae `detail` como lista de objetos; `download()` lo copiaba como
 * venía y el aviso mostraba «[object Object]» (spec 001, RF-12). Las dos vías pasan
 * por aquí. */
async function apiError(res: Response): Promise<ApiError> {
  let detail = `${res.status} ${res.statusText}`;
  try {
    const body = await res.json();
    if (typeof body.detail === 'string') detail = body.detail;
    else if (Array.isArray(body.detail)) detail = body.detail.map((d: { msg: string }) => d.msg).join('; ');
  } catch {
    /* respuesta sin JSON: se queda el estado HTTP */
  }
  return new ApiError(res.status, detail);
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, init);
  if (!res.ok) throw await apiError(res);
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

const json = (method: string, body: unknown): RequestInit => ({
  method,
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(body),
});

function form(file: File, field = 'file'): RequestInit {
  const fd = new FormData();
  fd.append(field, file, file.name);
  return { method: 'POST', body: fd };
}

const ws = (id: string) => `/api/workspaces/${encodeURIComponent(id)}`;
const enc = encodeURIComponent;

export type DemandaTipo = 'medidores' | 'cabecera' | 'suministros' | 'clientes';

export const api = {
  health: () => request<Health>('/api/health'),
  powerfactory: (refresh = false) =>
    request<PowerFactoryStatus>(`/api/powerfactory${refresh ? '?refresh=true' : ''}`),

  createWorkspace: () => request<WorkspaceState>('/api/workspaces', { method: 'POST' }),
  workspace: (id: string) => request<WorkspaceState>(ws(id)),
  setOptions: (id: string, opts: Partial<Options>) =>
    request<WorkspaceState>(`${ws(id)}/options`, json('PUT', opts)),
  sourceScope: (id: string) => request<import('./types').SourceScope>(`${ws(id)}/source-scope`),
  setSourceScope: (id: string, company: string | null, period: string | null) =>
    request<import('./types').SourceScope>(
      `${ws(id)}/source-scope`, json('PUT', { company, period }),
    ),

  uploadInput: (id: string, slot: string, file: File) =>
    request<{ warning: string; workspace: WorkspaceState }>(`${ws(id)}/inputs/${slot}`, form(file)),
  serverPathInput: (id: string, slot: string, path: string) =>
    request<{ warning: string; workspace: WorkspaceState }>(`${ws(id)}/inputs/${slot}/path`, json('POST', { path })),
  clearInput: (id: string, slot: string) =>
    request<WorkspaceState>(`${ws(id)}/inputs/${slot}`, { method: 'DELETE' }),
  autoInputs: (id: string, files: File[]) => {
    const fd = new FormData();
    files.forEach((f) => fd.append('files', f, f.name));
    return request<{
      assigned: { slot: string; name: string }[];
      unassigned: { name: string; reason: string }[];
      workspace: WorkspaceState;
    }>(`${ws(id)}/inputs-auto`, { method: 'POST', body: fd });
  },
  vnrPublications: (refresh = false) =>
    request<import('./types').VnrPublications>(`/api/vnr/publications${refresh ? '?refresh=true' : ''}`),
  vnrDownload: (id: string, publicationId: string) =>
    request<{ workspace: WorkspaceState; manifest: Record<string, unknown> }>(
      `${ws(id)}/vnr/download`, json('POST', { publication_id: publicationId }),
    ),

  load: (id: string) => request<Job>(`${ws(id)}/load`, { method: 'POST' }),
  feeders: (id: string) => request<{ loaded: boolean; feeders: FeederRow[] }>(`${ws(id)}/feeders`),
  diagnose: (id: string, feeders: string[], all: boolean) =>
    request<Job>(`${ws(id)}/diagnose`, json('POST', { feeders, all })),
  reconstruct: (id: string, feeders: string[], all: boolean) =>
    request<Job>(`${ws(id)}/reconstruct`, json('POST', { feeders, all })),
  reconstructionReport: (id: string) =>
    request<ReconstructionReport>(`${ws(id)}/files/reconstruction_report.json`),
  convert: (id: string, feeders: string[], all: boolean) =>
    request<Job>(`${ws(id)}/convert`, json('POST', { feeders, all })),
  convertGroup: (id: string, feeders: string[], nombre: string) =>
    request<Job>(`${ws(id)}/convert`, json('POST', { feeders, all: false, unir: true, nombre })),

  cancelJob: (jobId: string) => request<Job>(`/api/jobs/${jobId}/cancel`, { method: 'POST' }),

  outputs: (id: string) => request<OutputFile[]>(`${ws(id)}/outputs`),
  fileUrl: (id: string, rel: string, download = false) =>
    `${ws(id)}/files/${rel.split('/').map(enc).join('/')}${download ? '?download=1' : ''}`,
  zipUrl: (id: string, feeders: string[] = []) =>
    `${ws(id)}/outputs.zip${feeders.length ? '?' + feeders.map((f) => `feeder=${enc(f)}`).join('&') : ''}`,

  powerfactoryFlow: (id: string, feeders: string[]) =>
    request<Job>(`${ws(id)}/powerfactory/flow`, json('POST', { feeders })),

  // Spec 004: cargas en un proyecto que ya existe en DIgSILENT, sin entradas cargadas.
  cargasPlantillaUrl: (id: string, tipo: 'demandas' | 'nuevas', format: 'xlsx' | 'csv') =>
    `${ws(id)}/cargas/plantilla/${tipo}?format=${format}`,
  pfProjects: (id: string) => request<Job>(`${ws(id)}/powerfactory/projects`, { method: 'POST' }),
  cargasPlan: (id: string, project: string, feeders: string[], demandas?: File | null,
    nuevas?: File | null, nueva?: Record<string, string> | null, economia?: Economia | null) => {
    const fd = new FormData();
    fd.append('project', project);
    feeders.forEach((f) => fd.append('feeders', f));
    if (demandas) fd.append('update_file', demandas, demandas.name);
    if (nuevas) fd.append('create_file', nuevas, nuevas.name);
    if (nueva) fd.append('nueva', JSON.stringify(nueva));
    if (economia) fd.append('economia', JSON.stringify(economia));
    return request<CargasPlan>(`${ws(id)}/lote/plan`, { method: 'POST', body: fd });
  },
  cargasSimular: (id: string, token: string) =>
    request<Job>(`${ws(id)}/lote/${token}/simular`, { method: 'POST' }),
  cargasAplicar: (id: string, token: string) =>
    request<Job>(`${ws(id)}/lote/${token}/apply`, { method: 'POST' }),

  catalogBuild: (id: string, feeders: string[]) =>
    request<Job>(`${ws(id)}/catalog/build`, json('POST', { feeders })),
  catalogApply: (id: string, file: File, previewFeeder?: string) =>
    request<{
      codes: string[];
      count: number;
      preview_feeder: string | null;
      changes: { line: string; variation_pct: number | null }[];
      workspace: WorkspaceState;
    }>(`${ws(id)}/catalog/apply${previewFeeder ? `?preview_feeder=${enc(previewFeeder)}` : ''}`, form(file)),
  catalogClear: (id: string) => request<WorkspaceState>(`${ws(id)}/catalog`, { method: 'DELETE' }),

  // Demanda medida (spec 004, RF-22 a RF-39): misma pestaña que las cargas.
  demandaSubir: (id: string, tipo: DemandaTipo, files: File[]) => {
    const fd = new FormData();
    files.forEach((f) => fd.append('files', f, f.name));
    return request<WorkspaceState>(`${ws(id)}/demanda/${tipo}`, { method: 'POST', body: fd });
  },
  demandaRuta: (id: string, tipo: DemandaTipo, path: string) =>
    request<WorkspaceState>(`${ws(id)}/demanda/${tipo}/path`, json('POST', { path })),
  demandaQuitar: (id: string, tipo: DemandaTipo) =>
    request<WorkspaceState>(`${ws(id)}/demanda/${tipo}`, { method: 'DELETE' }),
  demandaMedidores: (id: string, alimentador: string) =>
    request<DemandaMedidores>(`${ws(id)}/demanda/medidores?alimentador=${enc(alimentador)}`),
  demandaCabecera: (id: string, medidores: { alimentador: string; medidor: string }[]) =>
    request<Job>(`${ws(id)}/demanda/cabecera/buscar`, json('POST', { medidores })),
  demandaClientes: (id: string) =>
    request<ClientesCruce>(`${ws(id)}/demanda/clientes/cruzar`, { method: 'POST' }),
  demandaExcel: (id: string, datos: { cabecera: MaximaCabecera[]; clientes: unknown[]; no_cruzados: unknown[] }) =>
    download(`${ws(id)}/demanda/excel`, json('POST', datos)),

  system: (id: string, action: 'grid' | 'base' | 'missing-data') =>
    request<Job>(`${ws(id)}/system/${action}`, { method: 'POST' }),
};

/** Descarga una URL de la API mostrando el error del servidor si lo hay. `init` para un POST. */
export async function download(url: string, init?: RequestInit): Promise<void> {
  const res = await fetch(url, init);
  if (!res.ok) throw await apiError(res);
  const blob = await res.blob();
  const cd = res.headers.get('content-disposition') ?? '';
  const match = /filename\*?=(?:UTF-8'')?"?([^";]+)"?/i.exec(cd);
  const name = match ? decodeURIComponent(match[1]) : url.split('/').pop()!.split('?')[0];
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = name;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(a.href), 10_000);
}

export const fmtBytes = (n: number) =>
  n < 1024 ? `${n} B` : n < 1024 ** 2 ? `${(n / 1024).toFixed(1)} KB` : `${(n / 1024 ** 2).toFixed(1)} MB`;

export const fmtNum = (n: number | null | undefined, digits = 0) =>
  n == null ? '—' : n.toLocaleString('es-PE', { maximumFractionDigits: digits, minimumFractionDigits: digits });
