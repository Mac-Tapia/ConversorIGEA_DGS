/** 105: la API de la evolución de los clientes fijos y de la carpeta de archivo, con los tipos del contrato. */
import { json, request } from './client';
import type { components } from './esquema';
import type { Job } from './types';

type S = components['schemas'];
export type EvolucionEstado = S['EvolucionFijasRespuesta'];
export type EvolucionResultado = S['EvolucionResultadoRespuesta'];
export type ClienteEvolucion = S['ClienteEvolucionRespuesta'];
export type TotalEvolucion = S['TotalEvolucionRespuesta'];
export type MesClienteFijo = S['MesClienteFijoRespuesta'];
export type AvisoEvolucion = S['AvisoEvolucionRespuesta'];
export type CurvaClienteFijo = S['CurvaClienteFijoRespuesta'];
export type PeticionEvolucion = S['EvolucionFijasPeticion'];

/** Evento de la ventana al cambiar la carpeta de archivo (105:RF-29). */
export const EVENTO_ARCHIVO = 'csg-archivo';

const ruta = (id: string) => `/api/workspaces/${encodeURIComponent(id)}/clientes-fijos/evolucion`;

export const evolucionFijas = {
  estado: (id: string) => request<EvolucionEstado>(ruta(id)),
  lanzar: (id: string, body: PeticionEvolucion) => request<Job>(ruta(id), json('POST', body)),
  curva: (id: string, cliente: string) =>
    request<CurvaClienteFijo>(`${ruta(id)}/curva?cliente=${encodeURIComponent(cliente)}`),
  archivo: () => request<S['ArchivoInformesRespuesta']>('/api/archivo'),
  ponerArchivo: (carpeta: string | null) =>
    request<S['ArchivoInformesRespuesta']>('/api/archivo', json('PUT', { ruta: carpeta })),
};
