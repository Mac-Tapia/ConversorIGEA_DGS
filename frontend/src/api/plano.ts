/** 111: la API del plano de la red, con los tipos del contrato generado (`esquema.ts`); ninguno escrito a mano.
 *
 * Toda regla eléctrica la decide el servidor (RF-15): aquí solo se piden la vista, las ediciones con su versión, el
 * estudio (un trabajo en su carril), las capas y la comparación. */
import { json, request } from './client';
import type { components } from './esquema';
import type { Job } from './types';

type S = components['schemas'];
export type Plano = S['PlanoRespuesta'];
export type VistaPlano = S['VistaPlanoRespuesta'];
export type TramoPlano = S['TramoPlanoRespuesta'];
export type BarraPlano = S['BarraPlanoRespuesta'];
export type SedPlano = S['SedPlanoRespuesta'];
export type ManiobraPlano = S['ManiobraPlanoRespuesta'];
export type DeducidoPlano = S['DeducidoPlanoRespuesta'];
export type VariacionPlano = S['VariacionPlanoRespuesta'];
export type VariacionesPlano = S['VariacionesPlanoRespuesta'];
export type EdicionPlano = S['EditarVariacionPeticion']['edicion'];
export type PropuestaAjuste = S['PropuestaAjusteRespuesta'];
export type CapasPlano = S['CapasPlanoRespuesta'];
export type CapaPlano = S['CapaPlanoRespuesta'];
export type ElementoCapa = S['ElementoCapaRespuesta'];
export type ComparacionPlano = S['ComparacionPlanoRespuesta'];
export type ElementoComparado = S['ElementoComparadoRespuesta'];
/** 111:RF-29: el motor que pide el operador al estudiar una variación. */
export type MotorPedido = NonNullable<S['EstudiarPlanoPeticion']['motor']>;

const ruta = (id: string) => `/api/workspaces/${encodeURIComponent(id)}/plano`;
const variacion = (id: string, vid: string) => `${ruta(id)}/variaciones/${encodeURIComponent(vid)}`;

function consulta(alimentadores: string[], extra: Record<string, string | null | undefined> = {}): string {
  const q = new URLSearchParams();
  for (const a of alimentadores) if (a) q.append('alimentador', a);
  for (const [k, v] of Object.entries(extra)) if (v) q.set(k, v);
  return q.toString();
}

export const plano = {
  datos: (id: string, alimentadores: string[] = [], project: string | null = null) =>
    request<Plano>(`${ruta(id)}?${consulta(alimentadores, { project })}`),
  /** La página con Leaflet dentro, para un `<iframe sandbox>`: aislada, sin alcance a la API. */
  paginaUrl: (id: string, alimentadores: string[] = [], vid: string | null = null) =>
    `${ruta(id)}/pagina?${consulta(alimentadores, { variacion: vid })}`,
  abrir: (id: string, body: S['AbrirVariacionPeticion']) =>
    request<VariacionPlano>(`${ruta(id)}/variaciones`, json('POST', body)),
  /** Lo guardado de verdad: las variaciones del alimentador en el servidor y cuáles tienen estudio. */
  variaciones: (id: string, alimentador: string) =>
    request<VariacionesPlano>(`${ruta(id)}/variaciones?${new URLSearchParams({ alimentador })}`),
  leer: (id: string, vid: string) => request<VariacionPlano>(variacion(id, vid)),
  editar: (id: string, vid: string, version: number, edicion: EdicionPlano) =>
    request<VariacionPlano>(variacion(id, vid), json('PATCH', { version, edicion })),
  deshacer: (id: string, vid: string, version: number) =>
    request<VariacionPlano>(`${variacion(id, vid)}/deshacer`, json('POST', { version })),
  rehacer: (id: string, vid: string, version: number) =>
    request<VariacionPlano>(`${variacion(id, vid)}/rehacer`, json('POST', { version })),
  confirmar: (id: string, vid: string, version: number) =>
    request<VariacionPlano>(`${variacion(id, vid)}/confirmar`, json('POST', { version })),
  ajuste: (id: string, vid: string, punto: [number, number]) =>
    request<PropuestaAjuste>(`${variacion(id, vid)}/ajuste`, json('POST', { punto })),
  /** 111:RF-29: el operador elige el motor; «automatico» es la elección de siempre. */
  estudiar: (id: string, vid: string, project: string | null, motor: MotorPedido = 'automatico') =>
    request<Job>(`${variacion(id, vid)}/estudiar`, json('POST', { project: project || null, motor })),
  resultados: (id: string, vid: string) =>
    request<CapasPlano>(`${ruta(id)}/resultados?${new URLSearchParams({ variacion: vid })}`),
  comparar: (id: string, a: string, b: string) =>
    request<ComparacionPlano>(`${ruta(id)}/comparar?${new URLSearchParams({ a, b })}`),
};
