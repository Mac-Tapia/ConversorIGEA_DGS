/** 108 T28: la API del estudio VNR (Guía del VNR, RCD 232-2017-OS/CD), con los tipos del contrato. */
import { request } from './client';
import type { components } from './esquema';
import type { Job } from './types';

export type VnrEstudio = components['schemas']['VnrEstudioRespuesta'];

export interface PeticionVnr {
  sector: string;
  sector_sicodi: string;
  resolucion: string;
  anio: number;
  moneda: string;
  /** Sin él, la red VNR-GIS que dejó la carga del espacio (109:RF-26). */
  canonical?: File | null;
  /** El libro subido, o el id de la fuente de la empresa (109:RF-25); sin ninguno, el vigente. */
  sicodi?: File | string | null;
}

const ruta = (id: string) => `/api/workspaces/${encodeURIComponent(id)}/vnr/estudio`;

export const vnr = {
  estado: (id: string) => request<VnrEstudio>(ruta(id)),
  lanzar: (id: string, p: PeticionVnr) => {
    const fd = new FormData();
    fd.append('sector', p.sector);
    fd.append('sector_sicodi', p.sector_sicodi);
    fd.append('resolucion', p.resolucion);
    fd.append('anio', String(p.anio));
    fd.append('moneda', p.moneda);
    if (p.canonical) fd.append('canonical', p.canonical, p.canonical.name);
    if (p.sicodi instanceof File) fd.append('sicodi', p.sicodi, p.sicodi.name);
    else if (p.sicodi) fd.append('fuente_sicodi', p.sicodi);
    return request<Job>(ruta(id), { method: 'POST', body: fd });
  },
};
