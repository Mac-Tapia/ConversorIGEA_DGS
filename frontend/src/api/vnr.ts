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
  canonical: File;
  sicodi: File;
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
    fd.append('canonical', p.canonical, p.canonical.name);
    fd.append('sicodi', p.sicodi, p.sicodi.name);
    return request<Job>(ruta(id), { method: 'POST', body: fd });
  },
};
