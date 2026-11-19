import type { Job } from './types';

const SIN_TERMINAR = ['queued', 'running'];

/**
 * Los trabajos de la pestaña tras volver a conectar con el servidor (086:RF-9).
 *
 * Lo que el servidor sabe manda. Lo que la pestaña veía en marcha y el servidor no conoce murió con el proceso
 * anterior: sin esto quedaba «en cola» para siempre y bloqueaba su carril hasta recargar la página.
 */
export function fusionarTrabajos(previos: Record<string, Job>, delServidor: Job[], espacio: string,
  ahora: number): Record<string, Job> {
  const fusion = { ...previos };
  for (const j of delServidor) fusion[j.id] = j;
  const conocidos = new Set(delServidor.map((j) => j.id));
  for (const j of Object.values(previos)) {
    if (j.workspace_id === espacio && SIN_TERMINAR.includes(j.status) && !conocidos.has(j.id)) {
      fusion[j.id] = {
        ...j, status: 'interrumpido', finished_at: ahora,
        error: 'El servidor se reinició con este trabajo a medias: no terminó y su resultado no vale.',
      };
    }
  }
  return fusion;
}

/** La línea del Registro cuando el servidor ya no tiene parte de lo pedido (086:RF-115). */
export function lineaDeTruncado(datos: { perdidos?: number }): string {
  const n = Number(datos?.perdidos);
  const cuantos = Number.isFinite(n) && n > 0 ? `${n} ${n === 1 ? 'evento antiguo' : 'eventos antiguos'}` : 'eventos antiguos';
  return `Registro incompleto: faltan ${cuantos} que el servidor ya no guarda. Se relee el estado del espacio.`;
}

/** Los trabajos interrumpidos que el operador aún no dio por vistos, el más reciente primero. */
export function interrumpidosPendientes(jobs: Record<string, Job>, espacio: string, vistos: string[]): Job[] {
  return Object.values(jobs)
    .filter((j) => j.workspace_id === espacio && j.status === 'interrumpido' && !vistos.includes(j.id))
    .sort((a, b) => (b.finished_at ?? 0) - (a.finished_at ?? 0));
}
