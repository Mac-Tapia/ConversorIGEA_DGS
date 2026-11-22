/**
 * 112:RF-21 (T19) — lo que el guion del dibujo de escala (`escala_dibujo.mjs`) calcula sin navegador, para probarlo
 * solo: los percentiles (la misma interpolación lineal que `tools/benchmark_escala_web.py`), el nombre del JSON de cada
 * tamaño y los puertos que la medición nunca usa (los de la web del operador).
 */

/** Las webs del operador: la medición arranca la suya en otro puerto libre. */
export const PUERTOS_PROHIBIDOS = Object.freeze([8765, 8766]);

export function puertoPermitido(puerto) {
  return Number.isInteger(puerto) && puerto > 0 && !PUERTOS_PROHIBIDOS.includes(puerto);
}

/** El JSON de un tamaño; `tools/benchmark_escala_web.py --dibujo` lo busca con el mismo nombre. */
export function nombreDibujo(alimentadores) {
  return `dibujo_${alimentadores}.json`;
}

/** Percentil `p` (0-100) con interpolación lineal entre los valores ordenados (el método por defecto de numpy). */
export function percentil(valores, p) {
  if (!valores.length) throw new Error('sin valores');
  const orden = [...valores].sort((a, b) => a - b);
  const pos = ((orden.length - 1) * p) / 100;
  const i = Math.floor(pos);
  if (i + 1 >= orden.length) return orden[orden.length - 1];
  return orden[i] + (pos - i) * (orden[i + 1] - orden[i]);
}

const r3 = (x) => Math.round(x * 1000) / 1000;

/** p50, p95, máximo y media de una magnitud; nunca un cero inventado: sin valores, o con uno que no es un tiempo
 * positivo, es un error que dice cuál. */
export function resumen(valores) {
  const malos = valores.filter((v) => !(typeof v === 'number' && Number.isFinite(v) && v > 0));
  if (!valores.length || malos.length) throw new Error(`tiempos no válidos: ${JSON.stringify(malos)}`);
  const media = valores.reduce((a, b) => a + b, 0) / valores.length;
  return { n: valores.length, p50_ms: r3(percentil(valores, 50)), p95_ms: r3(percentil(valores, 95)),
    max_ms: r3(Math.max(...valores)), media_ms: r3(media), valores_ms: valores.map(r3) };
}
