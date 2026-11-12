import type { Diagnostico, Escaneo, AsistenteRespuesta, CentralDeBarra, SistemaDelProyecto, EstructuraResumen,
  AjustePlan, AjusteResultado, CargasPlan, CentralTermica, ClientesCruce, CriterioFijas, CurvaCabecera, DemandaMedidores,
  MaximaConCentral, MedidoresExternos, Economia, EstudiosCatalogo, EstudiosPlan, DatosEmpresa, OpcionesEstudios, ProteccionesEstado, FallaProteccion,
  FeederRow, Health, InformeEstudioForm, ResumenEspacio, InformeFactibilidadForm, InformesContexto, Job, Limites, MaximaCabecera, Obra,
  ObraGuardada, Options, OutputFile, PfInventario, PowerFactoryStatus, InstalacionesPowerFactory, ReconstructionReport, WorkspaceState, EpisodioResumen } from './types';

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

export async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, init);
  if (!res.ok) throw await apiError(res);
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export const json = (method: string, body: unknown): RequestInit => ({
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

export type DemandaTipo = 'medidores' | 'cabecera' | 'suministros' | 'clientes' | 'estructura';

/** 086:RF-56: el perfil activo, con lo que dice «validar-perfil». */
export interface PerfilEstado {
  ruta: string;
  existe: boolean;
  errores: string[];
  desconocidas: string[];
  faltan: { clave: string; funcion: string; si_falta: string; opcional: boolean }[];
}

export const api = {
  health: () => request<Health>('/api/health'),
  // 086:RF-40, RF-43: el doctor y la versión con sus notas.
  diagnostico: () => request<Diagnostico>('/api/sistema/diagnostico'),
  versionPrograma: () => request<{ version: string; notas: string }>('/api/sistema/version'),
  powerfactory: (refresh = false) =>
    request<PowerFactoryStatus>(`/api/powerfactory${refresh ? '?refresh=true' : ''}`),
  // 103:RF-3: las instalaciones encontradas y la elección del operador.
  pfInstalaciones: () => request<InstalacionesPowerFactory>('/api/powerfactory/instalaciones'),
  pfElegir: (carpeta_api: string | null) =>
    request<InstalacionesPowerFactory>('/api/powerfactory/instalaciones', json('POST', { carpeta_api })),

  createWorkspace: () => request<WorkspaceState>('/api/workspaces', { method: 'POST' }),
  // 086:RF-2, RF-3, RF-9: lo que le pasó a los datos, con lo que se puede hacer.
  espacios: () => request<ResumenEspacio[]>('/api/workspaces'),
  restaurarCopia: (id: string) => request<WorkspaceState>(`${ws(id)}/restaurar-copia`, { method: 'POST' }),
  descartarNoDisponible: (id: string, campo: string, clave: string) =>
    request<WorkspaceState>(`${ws(id)}/no-disponibles/descartar`, json('POST', { campo, clave })),
  registroTrabajo: (jobId: string) => request<{ job: string; lineas: string[] }>(`/api/jobs/${enc(jobId)}/registro`),
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
  vnrPublications: () => request<import('./types').VnrPublications>('/api/vnr/publications'),
  vnrRefresh: (id: string) => request<Job>(`${ws(id)}/vnr/publications/refresh`, { method: 'POST' }),
  vnrDownload: (id: string, publicationId: string) =>
    request<Job>(
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
  // Spec 022, RF-47 a RF-51: la conversión por sistema eléctrico, una opción propia.
  estructura: (id: string) => request<EstructuraResumen>(`${ws(id)}/estructura`),
  // 022:RF-82: con `sets`, solo esas SET, cada una con su red y sus barras.
  convertSistema: (id: string, zonales: string[], sets: string[] = []) =>
    request<Job>(`${ws(id)}/convert/sistema`, json('POST', { zonales, sets })),

  cancelJob: (jobId: string) => request<Job>(`/api/jobs/${jobId}/cancel`, { method: 'POST' }),

  outputs: (id: string) => request<OutputFile[]>(`${ws(id)}/outputs`),
  fileUrl: (id: string, rel: string, download = false) =>
    `${ws(id)}/files/${rel.split('/').map(enc).join('/')}${download ? '?download=1' : ''}`,
  zipArchive: (id: string, feeders: string[] = []) =>
    request<Job>(`${ws(id)}/outputs/archive`, json('POST', { feeders })),

  powerfactoryFlow: (id: string, feeders: string[]) =>
    request<Job>(`${ws(id)}/powerfactory/flow`, json('POST', { feeders })),

  // Spec 004: cargas en un proyecto que ya existe en DIgSILENT, sin entradas cargadas.
  cargasPlantillaUrl: (id: string, tipo: 'demandas' | 'nuevas', format: 'xlsx' | 'csv') =>
    `${ws(id)}/cargas/plantilla/${tipo}?format=${format}`,
  pfProjects: (id: string) => request<Job>(`${ws(id)}/powerfactory/projects`, { method: 'POST' }),
  // Spec 007, RF-40: el último ajuste aplicado guardado en disco (sobrevive a un reinicio).
  ajusteUltimo: (id: string, project: string) =>
    request<{ ajuste: (AjusteResultado & { id: string; finished_at: number }) | null }>(
      `${ws(id)}/demanda/ajuste/ultimo?project=${encodeURIComponent(project)}`),
  // Spec 018, RF-13: la última lista leída en el espacio, sin abrir DIgSILENT.
  // Spec 028, RF-21, RF-22: recalibrar el sistema del proyecto, aparte de la calibración inicial.
  recalibrarDatos: (id: string, project: string) =>
    request<{ zonal: string; demanda_dir: string; grupo?: string; alimentadores?: string[]; del_sistema?: string[] }>(`${ws(id)}/demanda/recalibrar?project=${encodeURIComponent(project)}`),
  // 028:RF-40: ``solo``, los alimentadores del sistema que se recalibran; vacío, todos.
  recalibrar: (id: string, body: { project: string; periodo: string; zonal?: string; demanda_dir?: string; transformadores?: boolean;
    criterio_fijas?: CriterioFijas; solo?: string[]; maximo_mes?: string[]; a_su_maxima?: string[] }) =>
    request<Job>(`${ws(id)}/demanda/recalibrar`, json('POST', body)),
  // Spec 028, RF-9: escanear alimentadores en DIgSILENT antes de recalibrar.
  pfEscanear: (id: string, project: string, feeders: string[], anio: number | null = null) =>
    request<Job>(`${ws(id)}/powerfactory/escanear`, json('POST', { project, feeders, anio })),
  // 028:RF-30: el último escaneo de cada proyecto, también el automático de una recalibración.
  pfEscaneoGuardado: (id: string) =>
    request<{ escaneo: Record<string, Escaneo> }>(`${ws(id)}/powerfactory/escaneo`),
  pfProjectsGuardados: (id: string) => request<PfInventario>(`${ws(id)}/powerfactory/projects`),
  // Spec 018, RF-10: usar la ejecución fuente con la que se aceptó el proyecto.
  pfAdoptarFuente: (id: string, project: string) =>
    request<Job>(`${ws(id)}/powerfactory/adoptar-fuente`, json('POST', { project })),
  pfVerificarBase: (id: string, project: string, feeders: string[]) =>
    request<Job>(`${ws(id)}/powerfactory/caso-base`, json('POST', { project, feeders })),
  pfVerificar: (id: string, project: string, feeders: string[]) =>
    request<Job>(`${ws(id)}/powerfactory/verificar`, json('POST', { project, feeders })),
  cargasPlan: (id: string, project: string, feeders: string[], demandas?: File | null,
    nuevas?: File | null, nueva?: Record<string, string> | null, economia?: Economia | null,
    ajusteJobId?: string | null, minimaM?: number | null) => {
    const fd = new FormData();
    fd.append('project', project);
    feeders.forEach((f) => fd.append('feeders', f));
    if (demandas) fd.append('update_file', demandas, demandas.name);
    if (nuevas) fd.append('create_file', nuevas, nuevas.name);
    if (nueva) fd.append('nueva', JSON.stringify(nueva));
    if (economia) fd.append('economia', JSON.stringify(economia));
    // Spec 007, RF-1: el ajuste aplicado que hace de base; sin él, sobre lo activo.
    if (ajusteJobId) fd.append('ajuste_job_id', ajusteJobId);
    // Spec 016, RF-73: la distancia mínima para enganchar en una barra sin partir el tramo.
    if (minimaM != null) fd.append('minima_m', String(minimaM));
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
      /** 081:RF-70: dónde entran las fichas; lo escribe el servidor, no la pantalla. */
      aviso: string;
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
  demandaClientesIndexar: (id: string) =>
    request<Job>(`${ws(id)}/demanda/clientes/indexar`, { method: 'POST' }),
  // Spec 025, RF-28 y RF-32: el índice por año de la medición de cabecera, como trabajo.
  demandaCabeceraIndexar: (id: string) =>
    request<Job>(`${ws(id)}/demanda/cabecera/indexar`, { method: 'POST' }),
  demandaQuitar: (id: string, tipo: DemandaTipo) =>
    request<WorkspaceState>(`${ws(id)}/demanda/${tipo}`, { method: 'DELETE' }),
  demandaMedidores: (id: string, alimentador: string) =>
    request<DemandaMedidores>(`${ws(id)}/demanda/medidores?alimentador=${enc(alimentador)}`),
  // Spec 013, RF-11: ``periodo``, la máxima de ese mes; spec 021, RF-50: ``instante``, el
  // registro de esa fecha y hora en todos los medidores (calibración coincidente).
  demandaCabecera: (id: string, medidores: { alimentador: string; medidor: string }[],
    criterio: { project?: string; periodo?: string; instante?: string; por_barra?: boolean;
      centrales_tramo?: Record<string, string>; coincidente?: boolean; sistema_60kv?: boolean;
      centrales?: Record<string, { generacion: string; llegada: string; salida: string }> } = {}) =>
    request<Job>(`${ws(id)}/demanda/cabecera/buscar`, json('POST', {
      medidores, project: criterio.project || null, periodo: criterio.periodo || null, instante: criterio.instante || null,
      por_barra: Boolean(criterio.por_barra), centrales_tramo: criterio.centrales_tramo ?? {},
      coincidente: Boolean(criterio.coincidente), centrales: criterio.centrales ?? {},
      sistema_60kv: Boolean(criterio.sistema_60kv),
    })),
  // 022:RF-88: las centrales térmicas (CT…) del libro, para decir si van en barra o en tramo.
  demandaCentrales: (id: string) =>
    request<{ centrales: CentralDeBarra[] }>(`${ws(id)}/demanda/centrales`),
  demandaCurva: (id: string, jobId: string, medidor: string, desde?: string, hasta?: string) => {
    const q = new URLSearchParams({ medidor });
    if (desde) q.set('desde', desde);
    if (hasta) q.set('hasta', hasta);
    return request<CurvaCabecera>(`${ws(id)}/demanda/cabecera/${enc(jobId)}/curva?${q}`);
  },
  demandaMedidoresExternos: (id: string, red: string[]) => {
    const q = new URLSearchParams();
    red.forEach((r) => q.append('red', r));
    return request<MedidoresExternos>(`${ws(id)}/demanda/medidores-externos?${q}`);
  },
  demandaCurvaCentral: (id: string, jobId: string, alimentador: string, cabecera: string, c: CentralTermica,
    desde?: string, hasta?: string) => {
    const q = new URLSearchParams({ alimentador, cabecera, generacion: c.generacion, llegada: c.llegada, salida: c.salida });
    if (desde) q.set('desde', desde);
    if (hasta) q.set('hasta', hasta);
    return request<CurvaCabecera>(`${ws(id)}/demanda/cabecera/${enc(jobId)}/central/curva?${q}`);
  },
  demandaCentral: (id: string, jobId: string, alimentador: string, cabecera: string, c: CentralTermica) =>
    request<MaximaConCentral>(`${ws(id)}/demanda/cabecera/${enc(jobId)}/central?${new URLSearchParams({
      alimentador, cabecera, generacion: c.generacion, llegada: c.llegada, salida: c.salida,
    })}`),
  demandaAlimentadores: (id: string) =>
    request<{ alimentadores: string[] }>(`${ws(id)}/demanda/alimentadores`),
  // 022:RF-54: el sistema eléctrico del proyecto, si se convirtió por sistema.
  demandaSistema: (id: string, project: string) =>
    request<{ sistema: SistemaDelProyecto | null }>(
      `${ws(id)}/demanda/sistema?project=${encodeURIComponent(project)}`),
  // Spec 017, paso 4.4: lo que la web ya guardó para los informes, y su generación.
  informesContexto: (id: string, project: string, feeders: string[], jobId?: string) => {
    const q = new URLSearchParams({ project });
    feeders.forEach((f) => q.append('feeder', f));
    if (jobId) q.set('job_id', jobId);
    return request<InformesContexto>(`${ws(id)}/informes?${q}`);
  },
  informesFormulario: (id: string, project: string, tipo: 'estudio' | 'factibilidad', datos: unknown) =>
    request<{ guardado: boolean }>(`${ws(id)}/informes/formulario`, json('PUT', { project, tipo, datos })),
  informesPerdidasSubir: (id: string, file: File) => {
    const fd = new FormData();
    fd.append('file', file, file.name);
    return request<{ name: string }>(`${ws(id)}/informes/perdidas`, { method: 'POST', body: fd });
  },
  // Spec 017, RF-124: vista previa de la ubicación del cliente nuevo; sin DIgSILENT, al momento.
  informesUbicacion: (id: string, body: { project: string; alimentador: string; sed: string; cliente: string;
    potencia_kw: number | null; codigo_punto: string }) =>
    request<{ fichero: string; rotulo: string }>(`${ws(id)}/informes/ubicacion`, json('POST', body)),
  // Spec 017, RF-136 y RF-137: los PDF del solicitante, leídos en un trabajo.
  informesDocumentos: (id: string, tipo: 'factibilidad' | 'estudio', files: File[]) => {
    const fd = new FormData();
    fd.append('tipo', tipo);
    files.forEach((f) => fd.append('files', f, f.name));
    return request<Job>(`${ws(id)}/informes/documentos`, { method: 'POST', body: fd });
  },
  informesPerdidasRuta: (id: string, path: string) =>
    request<{ name: string }>(`${ws(id)}/informes/perdidas/path`, json('POST', { path })),
  informesPerdidasQuitar: (id: string) =>
    request<{ quitado: boolean }>(`${ws(id)}/informes/perdidas`, { method: 'DELETE' }),
  informesTrafoCargas: (id: string, transmision = '') =>
    request<Job>(`${ws(id)}/informes/transformador/cargas`, json('POST', { transmision })),
  informesTrafo: (id: string, body: { project: string; alimentador: string; carga: string; caso: string; transmision?: string }) =>
    request<Job>(`${ws(id)}/informes/transformador`, json('POST', body)),
  informeEstudio: (id: string, body: InformeEstudioForm) =>
    request<Job>(`${ws(id)}/informes/estudio`, json('POST', body)),
  informeFactibilidad: (id: string, body: InformeFactibilidadForm) =>
    request<Job>(`${ws(id)}/informes/factibilidad`, json('POST', body)),
  // 035:RF-1: con la máxima de cada alimentador, el registro de su instante.
  // 039:RF-1: el criterio de todas las fijas; por defecto, coincidente.
  demandaClientes: (id: string, alimentadores: string[], periodo?: string,
    maximas?: Record<string, { fecha: string | null; kw: number | null; kvar: number | null; fp: number | null }>,
    criterio: CriterioFijas = 'coincidente', criterioPorAlimentador: Record<string, CriterioFijas> = {},
    aSuMaxima?: string[]) =>
    request<ClientesCruce>(`${ws(id)}/demanda/clientes/cruzar`,
      json('POST', { alimentadores, criterio, criterio_por_alimentador: criterioPorAlimentador,
        ...(periodo ? { periodo } : {}), ...(maximas ? { maximas } : {}),
        ...(aSuMaxima ? { a_su_maxima: aSuMaxima } : {}) })),
  // 039:RF-13, RF-15: la selección «a su máxima» de la tabla cruzada, guardada en el espacio.
  demandaASuMaxima: (id: string, codigos: string[]) =>
    request<{ a_su_maxima: string[] }>(`${ws(id)}/demanda/clientes/a-su-maxima`, json('PUT', { codigos })),
  // 039:RF-5: los dos criterios frente a la cabecera y a la red simulada, como trabajo.
  demandaCompararFijas: (id: string, body: { project: string; alimentadores: string[]; periodo?: string;
    maximas: Record<string, { fecha: string | null; kw: number | null; kvar: number | null; fp: number | null }> }) =>
    request<Job>(`${ws(id)}/demanda/clientes/comparar`, json('POST', body)),
  ajustePlan: (id: string, body: { project: string; job_id: string; medidor: string; medidores?: string[]; tolerancia: number; desconectados?: string[]; centrales?: Record<string, CentralTermica>; tension_fuente_pu?: number | null; completar_bancos?: boolean; criterio_fijas?: CriterioFijas; criterio_por_alimentador?: Record<string, CriterioFijas>; a_su_maxima?: string[] }) =>
    request<AjustePlan>(`${ws(id)}/demanda/ajuste/plan`, json('POST', body)),
  ajusteSimular: (id: string, token: string) =>
    request<Job>(`${ws(id)}/demanda/ajuste/${enc(token)}/simular`, { method: 'POST' }),
  ajusteAplicar: (id: string, token: string) =>
    request<Job>(`${ws(id)}/demanda/ajuste/${enc(token)}/aplicar`, { method: 'POST' }),
  // Spec 020, RF-13 a RF-15: transformadores nuevos de las SED marcadas y recalibración.
  ajusteTransformadores: (id: string, token: string, feeder: string, sed: string[]) =>
    request<Job>(`${ws(id)}/demanda/ajuste/${enc(token)}/transformadores`, json('POST', { feeder, sed })),
  demandaExcel: (id: string, datos: { cabecera: MaximaCabecera[]; clientes: unknown[]; no_cruzados: unknown[] }) =>
    download(`${ws(id)}/demanda/excel`, json('POST', datos)),

  // Spec 011: obras de mejora, estudios y transferencia sobre la red calibrada (paso 4).
  obraAnadir: (id: string, obra: Obra) => request<ObraGuardada>(`${ws(id)}/obras`, json('POST', obra)),
  obraQuitar: (id: string, obraId: string) =>
    request<void>(`${ws(id)}/obras/${enc(obraId)}`, { method: 'DELETE' }),
  obrasBibliotecas: (id: string, body: { project: string; feeders: string[]; otro_proyecto: string }) =>
    request<Job>(`${ws(id)}/pf/obras/bibliotecas`, json('POST', body)),
  obrasSimular: (id: string, body: { project: string; feeders: string[]; otro_proyecto: string }) =>
    request<Job>(`${ws(id)}/pf/obras/simular`, json('POST', body)),
  obrasAplicar: (id: string, body: { project: string; feeders: string[]; otro_proyecto: string }) =>
    request<Job>(`${ws(id)}/pf/obras/aplicar`, json('POST', body)),
  // Spec 025, RF-44: bancos, sección y terna hasta que «Con proyecto <año>» converja.
  obrasEscalera: (id: string, body: { project: string; feeders: string[]; anio_casos: number | null;
    tipo_cambio: number | null; capex: string }) =>
    request<Job>(`${ws(id)}/pf/obras/escalera`, json('POST', body)),
  // Spec 042, RF-13: escalera carga a carga y SET nueva para las que no caben.
  obrasConProyecto: (id: string, body: { project: string; feeders: string[]; anio_casos: number | null;
    tipo_cambio: number | null; capex: string; alimentadores_nuevos: number;
    set_nueva_nombre?: string; directo_set_nueva?: boolean;
    escalera_primero?: boolean; rehacer_obras?: boolean }) =>      // 042:RF-76
    request<Job>(`${ws(id)}/pf/obras/con-proyecto`, json('POST', body)),
  // 063:RF-36: diagnosticar o reforzar una SET existente, sin recrearla.
  setNuevaOperacion: (id: string, body: import('./types').CuerpoSet) =>
    request<Job>(`${ws(id)}/pf/obras/set-nueva/operacion`, json('POST', body)),
  // Spec 012: el catálogo según el libro de la empresa del proyecto y la licencia.
  estudiosCatalogo: (id: string, project: string) =>
    request<EstudiosCatalogo>(`${ws(id)}/pf/estudios?project=${enc(project)}`),
  estudiosPlan: (id: string, body: {
    project: string; feeders: string[]; estudios: string[]; ajuste_job_id: string | null;
    limites: Partial<Limites>; limite_s: number | null; opciones: OpcionesEstudios;
  }) => request<EstudiosPlan>(`${ws(id)}/pf/estudios/plan`, json('POST', body)),
  datosEmpresaSubir: (id: string, project: string, file: File) => {
    const fd = new FormData();
    fd.append('project', project);
    fd.append('file', file, file.name);
    return request<{ libro: DatosEmpresa }>(`${ws(id)}/pf/datos-empresa`, { method: 'POST', body: fd });
  },
  datosEmpresaPlantillaUrl: (id: string) => `${ws(id)}/pf/datos-empresa/plantilla`,
  datosEmpresaAplicar: (id: string, body: { project: string; feeders: string[] }) =>
    request<Job>(`${ws(id)}/pf/datos-empresa/aplicar`, json('POST', body)),
  // Spec 049: disponibilidad, capacidades de la versión conectada y fallas de las protecciones.
  protecciones: (id: string, project: string) =>
    request<ProteccionesEstado>(`${ws(id)}/pf/protecciones?project=${enc(project)}`),
  proteccionesCapacidades: (id: string, body: { project: string; feeders: string[]; ejecutar_ordenes: boolean }) =>
    request<Job>(`${ws(id)}/pf/protecciones/capacidades`, json('POST', body)),
  proteccionesEjecutar: (id: string, body: { project: string; feeders: string[]; caso: string; periodo: string;
    fallas: FallaProteccion[] }) => request<Job>(`${ws(id)}/pf/protecciones/ejecutar`, json('POST', body)),
  estudiosEjecutar: (id: string, token: string) =>
    request<Job>(`${ws(id)}/pf/estudios/${enc(token)}/ejecutar`, { method: 'POST' }),
  guiones: (id: string, project: string) => request<Job>(`${ws(id)}/pf/guiones`, json('POST', { project })),
  guionEjecutar: (id: string, body: {
    project: string; nombre: string; origen: 'caso' | 'proyecto'; parametros: Record<string, string>; casos: string[];
    confirmado: boolean;
  }) => request<Job>(`${ws(id)}/pf/guiones/ejecutar`, json('POST', body)),
  // Spec 024: PIDE, gemelo digital y decisiones del operador.
  pide: (id: string, body: import('./types').PideSolicitud) =>
    request<Job>(`${ws(id)}/pide`, json('POST', body)),
  // 086:RF-56: el perfil de la empresa, validado y cargado desde la web.
  perfilEstado: () => request<PerfilEstado>('/api/perfil'),
  perfilGuardar: (perfil: File, estructura?: File | null) => {
    const body = new FormData();
    body.append('perfil', perfil);
    if (estructura) body.append('estructura', estructura);
    return request<PerfilEstado>('/api/perfil', { method: 'POST', body });
  },
  pideFuentes: (id: string, perfil: File, evaluacion: File, corto: File) => {
    const body = new FormData();
    body.append('perfil', perfil); body.append('evaluacion', evaluacion); body.append('corto_plazo', corto);
    return request<import('./types').PideFuentes>(`${ws(id)}/pide/fuentes`, { method: 'POST', body });
  },
  /** 072:RF-29 a RF-32: corto plazo, PIDE y largo plazo, con el horizonte del año de presentación si lo hay. */
  planeamientoTipos: (anio?: number | null) =>
    request<import('./types').TiposAnalisis>(`/api/planeamiento/tipos${anio ? `?${new URLSearchParams({ anio_presentacion: String(anio) })}` : ''}`),
  pideDecision: (id: string, body: { project: string; codigo: string; decision: string; comentario?: string }) =>
    request<Record<string, unknown>>(`${ws(id)}/pide/decision`, json('POST', body)),
  gemeloAprender: (id: string, body: { project: string; feeders: string[]; n: number }) =>
    request<Job>(`${ws(id)}/digital-twin/aprender`, json('POST', body)),
  // 027:RF-22 a RF-24: deriva por familia y vuelta al modelo anterior.
  gemeloDeriva: (id: string) => request<Job>(`${ws(id)}/digital-twin/deriva`, { method: 'POST' }),
  volverModelo: (modelo: 'gemelo' | 'asistente') =>
    request<{ modelo: string; version: string }>(`/api/modelos/${modelo}/volver`, { method: 'POST' }),
  gemeloEpisodios: (id: string, filtros: { proyecto?: string; caso?: string; clase?: string }) =>
    request<EpisodioResumen[]>(`${ws(id)}/digital-twin/episodes?${new URLSearchParams(
      Object.entries(filtros).filter(([, v]) => v) as [string, string][])}`),
  transferencia: (id: string, body: { project: string; feeders: string[]; casos: string[];
    cabecera_job_id?: string | null }) =>
    request<Job>(`${ws(id)}/pf/transferencia`, json('POST', body)),

  // Spec 026: asistente de órdenes.
  asistenteOrden: (id: string, texto: string) =>
    request<Job>(`${ws(id)}/asistente/orden`, json('POST', { texto })),
  asistenteConfirmar: (id: string, planId: string) =>
    request<Job>(`${ws(id)}/asistente/${enc(planId)}/confirmar`, { method: 'POST' }),
  asistenteCorregir: (id: string, planId: string, body: { tarea?: string; datos?: Record<string, unknown>;
    tipo_informe?: 'estudio' | 'factibilidad'; subtipo?: string }) =>
    request<AsistenteRespuesta>(`${ws(id)}/asistente/${enc(planId)}/corregir`, json('POST', body)),
  asistenteEntrenar: (id: string) => request<Job>(`${ws(id)}/asistente/entrenar`, { method: 'POST' }),
  asistenteRegistro: () => request<Record<string, unknown[]>>('/api/asistente/registro'),
  asistenteModelos: () => request<import('./types').EstadoModelos>('/api/asistente/modelos'),
  asistenteAprendizaje: () => request<import('./types').EstadoAprendizaje>('/api/asistente/aprendizaje'),
  cancelarAprendizaje: (clave: string) => request<import('./types').CancelacionAprendizaje>(
    `/api/asistente/aprendizaje/${encodeURIComponent(clave)}/cancelar`, { method: 'POST' }),
  asistenteMonitor: (id: string) => request<import('./types').MonitorAgenteEstado>(`/api/workspaces/${id}/asistente/monitor`),
  asistenteAceptacion: () => request<import('./asistenteAceptacion').EstadoAceptacionAgente>('/api/asistente/aceptacion'),
  // 027:RF-43, RF-44: el proyecto entero desde el espacio, con puntos de control.
  agenteProyecto: (id: string, body: { sistema: string; periodo: string; ruta?: string; ruta_cargas?: string; reiniciar?: boolean; confirmacion: string }) =>
    request<Job>(`${ws(id)}/agente/proyecto`, json('POST', body)),
  // 067:RF-37: las etapas que el operador ve antes de confirmarlas de una vez.
  agenteProyectoLista: (id: string, body: { sistema: string; periodo: string; ruta?: string; ruta_cargas?: string; reiniciar?: boolean }) =>
    request<import('./types').ListaProyecto>(`${ws(id)}/agente/proyecto/lista`, json('POST', body)),
  // 067:RF-19: los planes que siguen por confirmar, también tras reiniciar la web.
  asistentePlanes: (id: string) =>
    request<{ planes: import('./types').AsistentePlan[]; ilegibles: number }>(`${ws(id)}/asistente/planes`),
  // 027:RF-35: rechazar un plan es una penalización para el modelo.
  asistenteRechazar: (id: string, planId: string) =>
    request<{ plan: string; rechazado: boolean }>(`${ws(id)}/asistente/${planId}/rechazar`, { method: 'POST' }),

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
