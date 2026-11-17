/** 109:RF-25 y RF-26: las fuentes de la empresa del espacio y su red convertida, con los tipos del contrato. */
import { request } from './client';
import type { components } from './esquema';

export type Fuente = components['schemas']['FuenteRespuesta'];
export type Fuentes = components['schemas']['FuentesRespuesta'];
export type RedDelEspacio = components['schemas']['RedDelEspacioRespuesta'];

const ruta = (id: string) => `/api/workspaces/${encodeURIComponent(id)}/fuentes`;

export const fuentes = {
  listar: (id: string, clase?: string) =>
    request<Fuentes>(clase ? `${ruta(id)}?clase=${encodeURIComponent(clase)}` : ruta(id)),
  subir: (id: string, clase: string, fichero: File, periodo = '') => {
    const fd = new FormData();
    fd.append('clase', clase);
    fd.append('periodo', periodo);
    fd.append('file', fichero, fichero.name);
    return request<Fuente>(ruta(id), { method: 'POST', body: fd });
  },
  red: (id: string) => request<RedDelEspacio>(`${ruta(id)}/red`),
};
