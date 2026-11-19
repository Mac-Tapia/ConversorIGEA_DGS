/** 107:RF-21: la biblioteca normativa general, con los tipos del contrato. */
import { request } from './client';
import type { components } from './esquema';

export type Biblioteca = components['schemas']['BibliotecaRespuesta'];
export type NormaResumen = components['schemas']['NormaResumen'];
export type Reglas = components['schemas']['ReglasRespuesta'];
export type Agregada = components['schemas']['AgregadaRespuesta'];

export const normativa = {
  listar: (fecha?: string) =>
    request<Biblioteca>(fecha ? `/api/normativa?fecha=${encodeURIComponent(fecha)}` : '/api/normativa'),
  reglas: (acto: string) => request<Reglas>(`/api/normativa/reglas?acto=${encodeURIComponent(acto)}`),
  agregar: (fichero: File) => {
    const fd = new FormData();
    fd.append('file', fichero, fichero.name);
    return request<Agregada>('/api/normativa', { method: 'POST', body: fd });
  },
  // 107:RF-22 (026:RF-46): comprobar las fuentes oficiales (solo lee), la vista previa de una regeneración y aplicarla.
  fuentes: (fecha?: string) => request<Record<string, unknown>>(
    fecha ? `/api/normativa/fuentes?fecha=${encodeURIComponent(fecha)}` : '/api/normativa/fuentes'),
  regenerar: (generador: string) => request<Record<string, unknown>>('/api/normativa/regenerar', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ generador }) }),
  aplicarRegeneracion: (token: string) =>
    request<Record<string, unknown>>(`/api/normativa/regenerar/${encodeURIComponent(token)}/aplicar`, { method: 'POST' }),
};

/** Las normas que contienen el texto buscado en su acto o su título, sin distinguir mayúsculas ni tildes. */
export function filtrarNormas(normas: NormaResumen[], texto: string): NormaResumen[] {
  const plano = (s: string) => s.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();
  const q = plano(texto.trim());
  return q ? normas.filter((n) => plano(`${n.acto} ${n.titulo}`).includes(q)) : normas;
}
