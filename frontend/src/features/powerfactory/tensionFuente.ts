import { fmtNum } from '../../shared/formato';
import type { TensionFuente } from '../../api/types';

/**
 * La tensión medida en la fuente de cada alimentador, en el campo «Tensión en la fuente» de 2.4
 * (spec 021, RF-79 a RF-82). La regla de qué medida va a cada fuente es del servidor (la de su
 * barra de SET o la de su cabecera, RF-85); aquí solo se rellena el campo y se dice de dónde sale.
 */

/** 021:RF-82: la banda en que la tensión medida va sola a la fuente; la misma que admite la API. */
export const BANDA_FUENTE_PU = [0.9, 1.1] as const;

/** 021:RF-79: el valor con que se rellena el campo: la medida en pu, si está en la banda; si no, vacío. */
export function tensionInicial(medida: TensionFuente | null | undefined): string {
  const pu = medida?.pu;
  return pu != null && pu >= BANDA_FUENTE_PU[0] && pu <= BANDA_FUENTE_PU[1] ? pu.toFixed(4) : '';
}

/** 021:RF-79, RF-82, RF-76: lo que dice el campo bajo su valor: de dónde sale, o por qué no se rellena. */
export function notaDeLaMedida(medida: TensionFuente | null | undefined): string {
  if (!medida) return '';
  const donde = medida.barra || medida.medidor || '—';
  const kv = medida.kv != null ? ` (${fmtNum(medida.kv, 3)} kV)` : '';
  const base = `medida a las ${medida.fecha ?? '—'} en ${donde}${kv}`;
  if (medida.pu == null) {
    return `${base}; sin la nominal en la conversión, DIgSILENT la pasa a pu con la de la barra de su fuente`;
  }
  if (medida.pu < BANDA_FUENTE_PU[0] || medida.pu > BANDA_FUENTE_PU[1]) {
    return `${base}: ${fmtNum(medida.pu, 4)} pu, fuera de 0,90 a 1,10; no se aplica sola: escríbala si la confirma`;
  }
  return base;
}

/** 021:RF-80: el número que escribió el operador, o ``null`` si dejó el campo vacío. */
export function puEscrito(texto: string): number | null {
  return texto.trim() ? Number(texto.replace(',', '.')) : null;
}

/** 021:RF-80: lo que va a la API: solo los alimentadores cuyo campo tocó el operador; los demás, el servidor. */
export function tensionesTocadas(escritas: Record<string, string>): Record<string, number | null> {
  return Object.fromEntries(Object.entries(escritas).map(([a, texto]) => [a, puEscrito(texto)]));
}

/** 021:RF-82: lo escrito vale si está vacío o entre 0,90 y 1,10 pu. */
export function tensionValida(texto: string): boolean {
  const pu = puEscrito(texto);
  return pu === null || (Number.isFinite(pu) && pu >= BANDA_FUENTE_PU[0] && pu <= BANDA_FUENTE_PU[1]);
}
