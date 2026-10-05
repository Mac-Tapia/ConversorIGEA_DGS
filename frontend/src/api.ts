import type {
  CreatePlan, EventItem, FeederRow, Health, Job, LoadPlan, Options, OutputFile,
  PowerFactoryStatus, WorkspaceState,
} from './types';

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, init);
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    try {
      const body = await res.json();
      if (typeof body.detail === 'string') detail = body.detail;
      else if (Array.isArray(body.detail)) detail = body.detail.map((d: { msg: string }) => d.msg).join('; ');
    } catch {
      /* respuesta sin JSON: se queda el estado HTTP */
    }
    throw new ApiError(res.status, detail);
  }
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

export const api = {
  health: () => request<Health>('/api/health'),
  powerfactory: (refresh = false) =>
    request<PowerFactoryStatus>(`/api/powerfactory${refresh ? '?refresh=true' : ''}`),

  createWorkspace: () => request<WorkspaceState>('/api/workspaces', { method: 'POST' }),
  workspace: (id: string) => request<WorkspaceState>(ws(id)),
  setOptions: (id: string, opts: Partial<Options>) =>
    request<WorkspaceState>(`${ws(id)}/options`, json('PUT', opts)),
  sourceRuns: (id: string) => request<import('./types').SourceRun[]>(`${ws(id)}/runs`),

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
  convert: (id: string, feeders: string[], all: boolean) =>
    request<Job>(`${ws(id)}/convert`, json('POST', { feeders, all })),
  convertGroup: (id: string, feeders: string[], nombre: string) =>
    request<Job>(`${ws(id)}/convert`, json('POST', { feeders, all: false, unir: true, nombre })),

  job: (jobId: string) => request<Job>(`/api/jobs/${jobId}`),
  cancelJob: (jobId: string) => request<Job>(`/api/jobs/${jobId}/cancel`, { method: 'POST' }),
  events: (id: string, since: number) => request<EventItem[]>(`${ws(id)}/events?since=${since}`),

  outputs: (id: string) => request<OutputFile[]>(`${ws(id)}/outputs`),
  fileUrl: (id: string, rel: string, download = false) =>
    `${ws(id)}/files/${rel.split('/').map(enc).join('/')}${download ? '?download=1' : ''}`,
  zipUrl: (id: string, feeders: string[] = []) =>
    `${ws(id)}/outputs.zip${feeders.length ? '?' + feeders.map((f) => `feeder=${enc(f)}`).join('&') : ''}`,

  powerfactoryFlow: (id: string, feeders: string[]) =>
    request<Job>(`${ws(id)}/powerfactory/flow`, json('POST', { feeders })),

  loadTemplateUrl: (id: string, feeder: string, format: 'xlsx' | 'csv') =>
    `${ws(id)}/feeders/${enc(feeder)}/load-template?format=${format}`,
  loadPlan: (id: string, feeder: string, file: File) =>
    request<LoadPlan>(`${ws(id)}/feeders/${enc(feeder)}/load-plan`, form(file)),
  createTemplateUrl: (id: string, feeder: string, format: 'xlsx' | 'csv') =>
    `${ws(id)}/feeders/${enc(feeder)}/create-template?format=${format}`,
  createPlan: (id: string, feeder: string, file: File) =>
    request<CreatePlan>(`${ws(id)}/feeders/${enc(feeder)}/create-plan`, form(file)),
  createPlanSingle: (id: string, feeder: string, body: Record<string, unknown>) =>
    request<CreatePlan>(`${ws(id)}/feeders/${enc(feeder)}/create-plan/single`, json('POST', body)),
  applyPlan: (id: string, token: string) =>
    request<Job>(`${ws(id)}/plans/${token}/apply`, { method: 'POST' }),

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

  system: (id: string, action: 'grid' | 'base' | 'missing-data') =>
    request<Job>(`${ws(id)}/system/${action}`, { method: 'POST' }),
};

/** Descarga una URL de la API mostrando el error del servidor si lo hay. */
export async function download(url: string): Promise<void> {
  const res = await fetch(url);
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    try {
      detail = (await res.json()).detail ?? detail;
    } catch {
      /* sin JSON */
    }
    throw new ApiError(res.status, detail);
  }
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
