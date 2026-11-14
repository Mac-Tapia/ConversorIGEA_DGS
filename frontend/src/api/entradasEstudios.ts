/** 012:RF-73 a RF-82: la API de las entradas que faltan a los estudios, cargadas desde la web. */
import { json, request } from './client';
import type { Job } from './types';

export type FilaEntrada = Record<string, string | number | null>;

export interface ColumnaEntrada {
  clave: string;
  titulo: string;
  unidad: string;
  obligatoria: boolean;
  numero: boolean;
}

export interface EntradaEsquema {
  clave: string;
  /** El nombre de la entrada en el catálogo de estudios: el que sale en «falta». */
  nombre: string;
  titulo: string;
  ayuda: string;
  columnas: ColumnaEntrada[];
  /** Claves de los estudios que la piden. */
  estudios: string[];
}

export interface EntradaGuardada {
  fichero: string | null;
  confirmado: string | null;
  faltan: string[];
  completa: boolean;
  filas: FilaEntrada[];
}

export interface EntradaBorrador {
  clave: string;
  filas: FilaEntrada[];
  columnas?: string[];
  errores: string[];
  avisos: string[];
  faltan: string[];
  ficheros: string[];
  metodos: string[];
  leido: string;
}

export interface EntradasEstado {
  project: string;
  esquemas: EntradaEsquema[];
  guardadas: Record<string, EntradaGuardada>;
  borradores: Record<string, EntradaBorrador>;
  /** Nombres del catálogo que lo guardado ya cumple (RF-79). */
  cumplidas: string[];
}

const ruta = (id: string) => `/api/workspaces/${encodeURIComponent(id)}/pf/entradas-estudios`;

export const entradasEstudios = {
  estado: (id: string, project: string) =>
    request<EntradasEstado>(`${ruta(id)}?project=${encodeURIComponent(project)}`),
  /** Lee los ficheros en un trabajo del motor (con OCR si hace falta) y deja el borrador (RF-74). */
  leer: (id: string, project: string, clave: string, files: File[]) => {
    const fd = new FormData();
    fd.append('project', project);
    for (const f of files) fd.append('files', f, f.name);
    return request<Job>(`${ruta(id)}/${encodeURIComponent(clave)}/leer`, { method: 'POST', body: fd });
  },
  /** Guarda lo confirmado en la tabla; un 400 trae cada fila y columna que no vale (RF-77). */
  guardar: (id: string, project: string, clave: string, filas: FilaEntrada[]) =>
    request<EntradasEstado>(`${ruta(id)}/${encodeURIComponent(clave)}`, json('PUT', { project, filas })),
  descartar: (id: string, project: string, clave: string) =>
    request<EntradasEstado>(`${ruta(id)}/${encodeURIComponent(clave)}/borrador?project=${encodeURIComponent(project)}`,
      { method: 'DELETE' }),
};
