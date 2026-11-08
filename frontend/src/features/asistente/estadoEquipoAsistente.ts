/** 065:RF-22/23: el cliente consulta permisos; no concede roles ni adjunta rutas. */
import type { Job } from '../../api/types';

export interface PermisoEquipo {
  plan: string;
  responsable: string;
  herramienta: string | null;
  alcance: { espacio: string; fuente: string | null; proyecto: string | null };
  confirmada: boolean;
  permiso_efectivo: boolean;
  motivo: string;
  carril: string;
}
export interface RevisionEquipo {
  plan: string;
  tipo: string;
  aprobada?: boolean;
  motivo?: string;
  rol?: string;
  decision?: string;
}
export interface EstadoEquipo {
  espacio: string;
  autonomia_habilitada: boolean;
  roles: { rol: string; puede_ejecutar: boolean }[];
  herramientas: { herramienta: string; modo: string; escribe: boolean; carril: string }[];
  permisos: PermisoEquipo[];
  acciones: { plan: string; estado: string; herramienta: string; responsable: string }[];
  revisiones: RevisionEquipo[];
  /** 067:RF-7: informes y estudios custodiados del espacio, sin su contenido. */
  evidencias: { id: string; etiqueta: string; proyecto: string | null; titulo: string | null; registrado: string }[];
  error_evidencias: string;
}

async function pedir<T>(ruta: string, init?: RequestInit): Promise<T> {
  const r = await fetch(ruta, init);
  if (!r.ok) {
    let mensaje = `${r.status} ${r.statusText}`;
    try {
      const cuerpo = await r.json() as { detail?: string | { msg: string }[] };
      if (typeof cuerpo.detail === 'string') mensaje = cuerpo.detail;
      else if (Array.isArray(cuerpo.detail)) mensaje = cuerpo.detail.map(d => d.msg).join('; ');
    } catch { /* Se conserva el error HTTP si el servidor no envía JSON. */ }
    throw new Error(mensaje);
  }
  return r.json() as Promise<T>;
}
const base = (espacio: string) => `/api/workspaces/${encodeURIComponent(espacio)}/asistente`;
export const equipoApi = {
  estado: (espacio: string) => pedir<EstadoEquipo>(`${base(espacio)}/equipo`),
  revisar: (espacio: string, plan: string) => pedir<Job>(`${base(espacio)}/${encodeURIComponent(plan)}/revision`,
    { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' }),
};
