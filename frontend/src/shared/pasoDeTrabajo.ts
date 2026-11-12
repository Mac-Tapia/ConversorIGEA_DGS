import type { Job } from '../api/types';

/**
 * Dónde sale el aviso de cada trabajo (086:RF-70 a RF-75).
 *
 * Usuario, 2026-11-12: arriba de la web se apilaban «Trabajo interrumpido: Cargar / listar alimentadores» dos veces,
 * con la copia de datos, y «estos mensajes deberían aparecer en el numeral que corresponde de la web». Además, las dos
 * interrupciones ya no valían: después el mismo «Cargar / listar» terminó bien. Cada aviso va ahora al paso cuyo botón
 * lanza el trabajo, y uno resuelto por un trabajo posterior del mismo ámbito deja de mostrarse.
 */
export const PASOS = {
  entradas: { titulo: '1 · Entrada de datos', pestana: null },
  alimentadores: { titulo: '2 · Alimentadores', pestana: null },
  catalogo: { titulo: 'Catálogo de parámetros', pestana: 'catalog' },
  sistema: { titulo: 'Sistema completo', pestana: 'system' },
  'pf-proyecto': { titulo: 'Cargas en DIgSILENT → 1 · Proyecto', pestana: 'cargas' },
  'pf-calibracion': { titulo: 'Cargas en DIgSILENT → 2 · Alimentadores y calibración', pestana: 'cargas' },
  'pf-nuevas': { titulo: 'Cargas en DIgSILENT → 3 · Integración de nuevas', pestana: 'cargas' },
  'pf-obras': { titulo: 'Cargas en DIgSILENT → 4.1 · Obras de mejora', pestana: 'cargas' },
  'pf-estudios': { titulo: 'Cargas en DIgSILENT → 4.2 · Estudios', pestana: 'cargas' },
  'pf-transferencia': { titulo: 'Cargas en DIgSILENT → 4.3 · Transferencia de carga', pestana: 'cargas' },
  'pf-informes': { titulo: 'Cargas en DIgSILENT → 4.4 · Informes', pestana: 'cargas' },
  'pf-planificacion': { titulo: 'Cargas en DIgSILENT → 5 · Planificación', pestana: 'cargas' },
  asistente: { titulo: 'Asistente', pestana: 'asistente' },
  // 105: el tablero de la evolución de los clientes fijos, en su propia pestaña.
  'clientes-fijos': { titulo: 'Evolución de clientes fijos', pestana: 'clientes_fijos' },
} as const;

export type PasoId = keyof typeof PASOS;

/**
 * 086:RF-70, RF-71: cada `kind` del servidor con el paso que lo lanza; `null`, la zona general de arriba. La prueba
 * `frontend/test/avisosEnSuPaso.test.mjs` lee los `submit` del servidor y falla si falta alguno.
 */
export const PASO_DE_TRABAJO: Record<string, PasoId | null> = {
  // 1 · Entrada de datos: las publicaciones oficiales de VNR-GIS.
  vnr_publications: 'entradas', vnr_download: 'entradas',
  // 2 · Alimentadores: cargar, reconstruir, convertir, descargar e importar con su flujo.
  load: 'alimentadores', diagnose: 'alimentadores', reconstruct: 'alimentadores', convert: 'alimentadores',
  convert_group: 'alimentadores', archive: 'alimentadores', powerfactory: 'alimentadores',
  catalog: 'catalogo',
  clientes_fijos_evolucion: 'clientes-fijos',
  system: 'sistema',
  // Cargas en DIgSILENT.
  pf_projects: 'pf-proyecto', pf_adoptar_fuente: 'pf-proyecto', pf_verificar_base: 'pf-proyecto',
  recalibrar: 'pf-calibracion', pf_escaneo: 'pf-calibracion', demanda_cabecera: 'pf-calibracion',
  demanda_comparar_fijas: 'pf-calibracion', demanda_clientes_index: 'pf-calibracion',
  demanda_cabecera_index: 'pf-calibracion', ajuste_simular: 'pf-calibracion', ajuste_aplicar: 'pf-calibracion',
  ajuste_transformadores: 'pf-calibracion',
  pf_verificar: 'pf-nuevas', cargas_simular: 'pf-nuevas', cargas_aplicar: 'pf-nuevas', cargas_deshacer: 'pf-nuevas',
  obras_escalera: 'pf-nuevas', obras_con_proyecto: 'pf-nuevas', set_nueva_operacion: 'pf-nuevas',
  obras_bibliotecas: 'pf-obras', obras_simular: 'pf-obras', obras_aplicar: 'pf-obras',
  estudios: 'pf-estudios', estudio: 'pf-estudios', sesion: 'pf-estudios', guiones_listar: 'pf-estudios',
  guion_ejecutar: 'pf-estudios', protecciones_capacidades: 'pf-estudios', protecciones_fallas: 'pf-estudios',
  datos_confiabilidad: 'pf-estudios',
  transferencia: 'pf-transferencia',
  informe_estudio: 'pf-informes', informe_factibilidad: 'pf-informes', informe_documentos: 'pf-informes',
  informe_trafo: 'pf-informes', informe_trafo_cargas: 'pf-informes',
  pide: 'pf-planificacion', gemelo_aprender: 'pf-planificacion', gemelo_deriva: 'pf-planificacion',
  gemelo_pronostico: 'pf-planificacion', gemelo_temporal: 'pf-planificacion', gemelo_entrenar: 'pf-planificacion',
  gemelo_evaluar: 'pf-planificacion',
  asistente: 'asistente', asistente_control: 'asistente', asistente_interpretar: 'asistente',
  asistente_entrenar: 'asistente', asistente_mejora: 'asistente', asistente_indice: 'asistente', asistente_revision: 'asistente',
  agente_proyecto: 'asistente',
  // Sin botón propio en un paso: los lanza el servidor solo, o van al espacio aparte de VNR-GIS (`_vnr`).
  libros_nuevos: null, aprendizaje: null, download: null, vnr_export_cymdist: null, vnr_export_dgs: null,
};

/**
 * 086:RF-72: los que se repiten con sus mismos datos: no llevan más parámetro que el espacio. Uno con proyecto o
 * alimentadores elegidos se repite desde su botón, con lo que el operador tenga marcado.
 */
export const REPETIBLES = ['load', 'pf_projects', 'demanda_clientes_index', 'demanda_cabecera_index',
  'vnr_publications'] as const;

const CON_AVISO = ['interrumpido', 'failed', 'cancelled'];

/** El paso de un trabajo; `aprendizaje:<huella>` es el tipo `aprendizaje`. Uno sin paso, `null`. */
export function pasoDeTrabajo(kind: string): PasoId | null {
  return PASO_DE_TRABAJO[kind.split(':')[0]] ?? null;
}

/**
 * 086:RF-73: el ámbito de un trabajo. El servidor escribe en el título el proyecto y los alimentadores
 * («Recalibrar · PROYECTO · AL209»); el reintento del vigilante añade « (reintento)» al mismo título.
 */
export function ambitoDe(j: Job): string {
  return `${j.workspace_id}\u0000${j.kind}\u0000${j.title.replace(/ \(reintento\)$/, '')}`;
}

/** 086:RF-73: después terminó bien otro del mismo tipo y ámbito. */
export function resuelto(j: Job, todos: Job[]): boolean {
  const ambito = ambitoDe(j);
  return todos.some((o) => o.id !== j.id && o.status === 'done' && (o.created_at ?? 0) > (j.created_at ?? 0)
    && ambitoDe(o) === ambito);
}

export interface Aviso {
  job: Job;
  /** Los anteriores del mismo ámbito, también sin resolver ni ver: un solo aviso, no uno por intento. */
  anteriores: Job[];
  paso: PasoId | null;
}

const cuando = (j: Job) => j.finished_at ?? j.created_at ?? 0;

/** 086:RF-70, RF-73: los avisos sin ver ni resolver del espacio, uno por ámbito, el más reciente primero. */
export function avisosDeTrabajos(jobs: Record<string, Job>, espacio: string, vistos: readonly string[]): Aviso[] {
  const todos = Object.values(jobs).filter((j) => j.workspace_id === espacio);
  const grupos = new Map<string, Job[]>();
  for (const j of todos) {
    if (!CON_AVISO.includes(j.status) || vistos.includes(j.id) || resuelto(j, todos)) continue;
    const clave = ambitoDe(j);
    grupos.set(clave, [...(grupos.get(clave) ?? []), j]);
  }
  return [...grupos.values()]
    .map((g) => g.sort((a, b) => cuando(b) - cuando(a)))
    .map((g) => ({ job: g[0], anteriores: g.slice(1), paso: pasoDeTrabajo(g[0].kind) }))
    .sort((a, b) => cuando(b.job) - cuando(a.job));
}

/** 086:RF-71, RF-75: van arriba los que no tienen paso o cuyo paso está en una pestaña que hoy no se ofrece. */
export function esGeneral(a: Aviso, pestanas: readonly string[]): boolean {
  if (a.paso === null) return true;
  const pestana = PASOS[a.paso].pestana;
  return pestana !== null && !pestanas.includes(pestana);
}

/** 086:RF-75: cuántos avisos esperan en cada pestaña, para decirlo en su nombre. */
export function avisosPorPestana(avisos: Aviso[], pestanas: readonly string[]): Record<string, number> {
  const cuenta: Record<string, number> = {};
  for (const a of avisos) {
    const pestana = a.paso ? PASOS[a.paso].pestana : null;
    if (pestana && pestanas.includes(pestana)) cuenta[pestana] = (cuenta[pestana] ?? 0) + 1;
  }
  return cuenta;
}
