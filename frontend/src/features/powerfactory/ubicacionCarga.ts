/**
 * 004:RF-72 a RF-80: lo que la web dice de la ubicación de una carga nueva, sin React, para probarlo solo.
 *
 * SE0001 (PA217, 2026-11-12) se escribió con Y = 476 517, un dígito de menos, y se conectó desde cerca del Polo Sur.
 * El servidor mide cada punto contra la zona de su alimentador y propone la corrección; la web la muestra junto a la
 * fila y solo la copia en el formulario si el operador la elige: nunca se corrige sola.
 */
import type { CargasPlan, ConexionDeLaCarga, PropuestaUbicacion, UbicacionCarga, UbicacionRechazada } from '../../api/types';
import { fmtNum } from '../../shared/formato';

/** La hoja con que el servidor lee la carga de «3.2 · Una carga nueva». */
export const HOJA_FORMULARIO = 'formulario';

/** El rechazo o el nodo más cercano de la carga del formulario en un plan (004:RF-80). */
export function medidaDelFormulario(p: Pick<CargasPlan, 'nuevas' | 'ubicaciones_rechazadas'>): {
  rechazo: UbicacionRechazada | null; ubicacion: UbicacionCarga | null;
} {
  const rechazo = (p.ubicaciones_rechazadas ?? []).find((x) => x.hoja === HOJA_FORMULARIO) ?? null;
  const fila = p.nuevas.find((x) => (x as { hoja?: string }).hoja === HOJA_FORMULARIO);
  return { rechazo, ubicacion: rechazo ? null : fila?.ubicacion ?? null };
}

/** Los campos del formulario que cambia una propuesta, como texto (004:RF-74). */
export function camposDePropuesta(pr: PropuestaUbicacion): Record<string, string> {
  return Object.fromEntries(Object.entries(pr.cambios).map(([k, x]) => [k, String(x)]));
}

/** «a 12 m del nodo 18943»: la distancia que midió el servidor (004:RF-72). */
export function aDelNodo(u: Pick<UbicacionCarga, 'distancia_m' | 'nodo'>): string {
  return `a ${fmtNum(u.distancia_m)} m del nodo ${u.nodo}`;
}

/** El nodo más cercano, la línea de conexión y la carga que reemplaza, tras simular o aplicar (004:RF-76, RF-78). */
export function textoDeLaConexion(c: ConexionDeLaCarga): string {
  return [
    c.ubicacion ? aDelNodo(c.ubicacion) : '',
    c.longitud_linea_m != null ? `línea de conexión de ${fmtNum(c.longitud_linea_m)} m` : '',
    c.reemplaza ? `reemplaza la carga anterior (cambió ${c.reemplaza.cambios.join(', ')})` : '',
  ].filter(Boolean).join(' · ');
}
