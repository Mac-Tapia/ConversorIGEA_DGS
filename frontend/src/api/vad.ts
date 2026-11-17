/**
 * 108 T29: la API del estudio de costos del VAD (`web/vad_api.py`), con los tipos del contrato. El armado de la empresa
 * modelo y el Informe Definitivo son trabajos del motor: la ruta devuelve el trabajo y se sigue en el Registro.
 */
import { request } from './client';
import type { components } from './esquema';
import type { Job } from './types';

export type CrearEstudioVad = components['schemas']['CrearEstudioVad'];
export type ObservacionVad = components['schemas']['ObservacionVad'];
export type RespuestaVad = components['schemas']['RespuestaVad'];

export interface EstudioVadFila {
  id: string; empresa: string; grupo: number; periodo: string; version_tdr: string; estado: string;
  armado?: { terminado?: boolean; cancelado?: boolean; sistemas?: Record<string, string> } | null;
}
export interface DestinoVad { tipo: string; id: string }
export interface ObservacionVadDetalle {
  numero: string; fecha: string; texto: string; estado: 'pendiente' | 'respondida'; afecta: DestinoVad[];
  respuesta: string; sustento: string; cambios: Record<string, string>;
}
export interface SistemaArmado {
  estado: string; motivo?: string; paso?: string; error?: string; sin_entrada?: string[];
  pasos?: Record<string, { completo?: boolean; huecos?: string[]; avisos?: string[] }>;
}
export interface DocumentoDefinitivo {
  documento: string; ruta: string | null; ruta_relativa: string | null; motivo: string; huecos?: string[];
  pdf_relativa?: string | null; motivo_pdf?: string;
}
export interface DetalleVad {
  estudio: EstudioVadFila;
  armado: { terminado?: boolean; cancelado?: boolean; error?: string; sistemas: Record<string, SistemaArmado> } | null;
  observaciones: ObservacionVadDetalle[];
  pendientes: string[];
  destinos: DestinoVad[];
  aviso_destinos: string;
  informe_definitivo: { documentos: DocumentoDefinitivo[]; huecos: string[] } | null;
  salidas: string[];
  /** 108 T30: el estado de cada paso de la línea del VAD tras la empresa modelo. */
  linea: { terminada?: boolean; pasos: Record<string, { estado: string; motivo?: string; error?: string }> } | null;
}

const base = (wid: string) => `/api/workspaces/${encodeURIComponent(wid)}/vad`;
const json = (body: unknown): RequestInit => ({
  method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
});

export const vad = {
  estudios: (wid: string) => request<{ estudios: EstudioVadFila[] }>(`${base(wid)}/estudios`),
  crear: (wid: string, p: CrearEstudioVad) => request<EstudioVadFila>(`${base(wid)}/estudios`, json(p)),
  detalle: (wid: string, estudio: string) => request<DetalleVad>(`${base(wid)}/${encodeURIComponent(estudio)}`),
  /**
   * El caso: un .zip con `sistemas.json` y las tablas que nombra, o la fuente `vad_caso` de la empresa por su id
   * (109:RF-25); sin ninguno, el servidor usa la vigente de la empresa.
   */
  armar: (wid: string, estudio: string, caso: File | { id: string } | null) => {
    const fd = new FormData();
    if (caso instanceof File) fd.append('files', caso, caso.name);
    else if (caso) fd.append('fuente_vad_caso', caso.id);
    return request<Job>(`${base(wid)}/${encodeURIComponent(estudio)}/armar`, { method: 'POST', body: fd });
  },
  observar: (wid: string, estudio: string, o: ObservacionVad) =>
    request<{ numero: string; estado: string }>(`${base(wid)}/${encodeURIComponent(estudio)}/observaciones`, json(o)),
  responder: (wid: string, estudio: string, numero: string, r: RespuestaVad) =>
    request<{ numero: string; estado: string }>(
      `${base(wid)}/${encodeURIComponent(estudio)}/observaciones/${encodeURIComponent(numero)}/respuesta`, json(r)),
  informeDefinitivo: (wid: string, estudio: string) =>
    request<Job>(`${base(wid)}/${encodeURIComponent(estudio)}/informe-definitivo`, { method: 'POST' }),
};
