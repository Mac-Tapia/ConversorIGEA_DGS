/** 109: la API de la nube (Google Drive y OneDrive) desde la web.
 *
 * Los tipos son los del contrato generado (`esquema.ts`, con `tools/generar_contrato_api.py` desde el OpenAPI real de
 * `web/nube_api.py`). Aquí no se escribe ninguna forma a mano: si el servidor cambia, `tsc` lo dice.
 *
 * Lo que el contrato declara como objeto libre (el destino, la copia vigente, la candidata y los recibos) se lee en
 * `features/nube/logica.ts` campo a campo, comprobando su tipo. La salida a la nube no se enciende desde aquí: la
 * decide el servidor y, apagada, responde 403 con su motivo.
 */
import type { components } from './esquema';
import { descargarBlob, json, request } from './client';
import type { Job } from './types';

type S = components['schemas'];

export type CuentaNube = S['NubeCuentaRespuesta'];
export type ProveedorRegistrado = S['NubeProveedorRespuesta'];
export type ProveedorNube = CuentaNube['nombre'];
export type Desconexion = S['NubeDesconectarRespuesta'];
export type Conexion = S['NubeConectarRespuesta'];
export type AlcanceNube = NonNullable<S['ConectarPeticion']['alcance']>;
export type VinculoNube = S['NubeVinculoRespuesta'];
export type ImportarPeticion = S['ImportarPeticion'];
export type LibroNube = NonNullable<ImportarPeticion['libro']>;
export type PublicarPrevia = S['PublicarPrevia'];
export type PublicarPreviaRespuesta = S['NubePublicarPreviaRespuesta'];
export type CompartirPrevia = S['CompartirPrevia'];
export type CompartirPreviaRespuesta = S['NubeCompartirPreviaRespuesta'];
export type ReciboNube = S['NubeRecibosRespuesta']['recibos'][number];

/** Decisión del usuario (OAuth en modo de prueba): sin cliente registrado en el equipo, la web dice esto y nada más.
 * Lo usan la nube (109:RF-19) y el correo (110:RF-1), que no pueden importarse entre sí. */
export const SIN_CUENTA = 'Sin cuenta conectada: configure config/nube.json';

export const NOMBRE_PROVEEDOR: Record<ProveedorNube, string> = { google: 'Google Drive', microsoft: 'OneDrive' };

const ws = (id: string) => `/api/workspaces/${encodeURIComponent(id)}/nube`;
const enc = encodeURIComponent;

export const nube = {
  proveedores: () => request<S['NubeProveedoresRespuesta']>('/api/nube/proveedores'),
  cuentas: (id: string) => request<S['NubeCuentasRespuesta']>(`${ws(id)}/cuentas`),
  /** Devuelve la dirección del proveedor; la web navega a ella y vuelve por `/nube/retorno`. */
  conectar: (id: string, proveedor: ProveedorNube, alcance?: AlcanceNube) =>
    request<Conexion>(`${ws(id)}/${enc(proveedor)}/conectar`,
      json('POST', (alcance ? { alcance } : {}) satisfies S['ConectarPeticion'])),
  desconectar: (id: string, proveedor: ProveedorNube) =>
    request<Desconexion>(`${ws(id)}/${enc(proveedor)}`, { method: 'DELETE' }),
  /** La página del selector del proveedor (fuera del OpenAPI); devuelve los ids por `postMessage`. */
  urlSelector: (id: string, proveedor: ProveedorNube, modo: 'ficheros' | 'carpeta') =>
    `/nube/selector/${enc(proveedor)}?espacio=${enc(id)}&modo=${modo}`,
  importar: (id: string, body: ImportarPeticion) => request<Job>(`${ws(id)}/importar`, json('POST', body)),
  /** 109:RF-22: la copia fija ya importada, para cargarla por la subida propia de su entrada. */
  copia: (id: string, sha256: string) => descargarBlob(`${ws(id)}/copias/${enc(sha256)}`),
  trabajo: (jobId: string) => request<Job>(`/api/jobs/${enc(jobId)}`),
  vinculos: (id: string) => request<S['NubeVinculosRespuesta']>(`${ws(id)}/vinculos`),
  versiones: (id: string) => request<Job>(`${ws(id)}/versiones`, { method: 'POST' }),
  traer: (id: string, vid: string) => request<Job>(`${ws(id)}/vinculos/${enc(vid)}/traer`, { method: 'POST' }),
  aceptar: (id: string, vid: string) =>
    request<VinculoNube>(`${ws(id)}/vinculos/${enc(vid)}/aceptar`,
      json('POST', { confirmar: true } satisfies S['AceptarPeticion'])),
  publicarPrevia: (id: string, body: PublicarPrevia) =>
    request<PublicarPreviaRespuesta>(`${ws(id)}/publicar/previa`, json('POST', body)),
  publicar: (id: string, body: PublicarPrevia, confirmacion: string) =>
    request<Job>(`${ws(id)}/publicar`, json('POST', { ...body, confirmacion } satisfies S['PublicarPeticion'])),
  compartirPrevia: (id: string, body: CompartirPrevia) =>
    request<CompartirPreviaRespuesta>(`${ws(id)}/compartir/previa`, json('POST', body)),
  compartir: (id: string, body: CompartirPrevia, autorizo_enlace_publico: boolean, confirmacion: string) =>
    request<Job>(`${ws(id)}/compartir`, json('POST',
      { ...body, autorizo_enlace_publico, confirmacion } satisfies S['CompartirPeticion'])),
  recibos: (id: string) => request<S['NubeRecibosRespuesta']>(`${ws(id)}/recibos`),
};
