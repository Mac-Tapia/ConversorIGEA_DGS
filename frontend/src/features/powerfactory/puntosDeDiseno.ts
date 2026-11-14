/** 017:RF-109, RF-124: la lógica del mapa de las cargas nuevas, sin React, para probarla con node --test.
 *
 * Usuario, 2026-11-13: «debe haber un botón para actualizar la imagen de la ubicación y el punto de fijación de
 * diseño cuando el usuario verificó en DIgSILENT, corrigió o asignó otro punto». Lo que decide aquí: qué lectura
 * de DIgSILENT es la de este proyecto, qué filas se pueden usar y cómo se dice cada diferencia. */

/** Lo mínimo de un trabajo que hace falta aquí: el de `api/types.ts` lo cumple. */
export interface TrabajoMin {
  kind: string;
  status: string;
  created_at: number;
  result?: unknown;
}

export const KIND_LECTURA = 'mapa_cargas_digsilent';

interface DiferenciaMin {
  sed: string;
  alimentador: string | null;
  estado: string;
  cambios: string[];
  error: string | null;
  guardado: { barra: string | null } | null;
  leido: { barra: string | null; enlace?: { nombre: string; km: number } | null } | null;
}

interface LecturaMin {
  project: string;
  lectura: string;
  diferencias: DiferenciaMin[];
}

/** La última lectura terminada de DIgSILENT de este proyecto; la de otro proyecto no vale (017:RF-124). */
export function ultimaLectura<L extends LecturaMin>(trabajos: TrabajoMin[], project: string): L | null {
  const propios = trabajos
    .filter((j) => j.kind === KIND_LECTURA && j.status === 'done' && j.result
      && (j.result as LecturaMin).project === project.trim())
    .sort((a, b) => a.created_at - b.created_at);
  const ultimo = propios.pop();
  return ultimo ? (ultimo.result as L) : null;
}

/** «Usar este punto» solo donde hay algo que usar: un nodo leído y un cambio, o una carga que la web no tenía. */
export function sePuedeUsar(d: DiferenciaMin): boolean {
  return Boolean(d.leido?.barra) && (d.estado === 'cambiada' || d.estado === 'solo_en_digsilent');
}

const ETIQUETAS: Record<string, string> = {
  igual: 'Igual que en DIgSILENT',
  cambiada: 'Cambiada en DIgSILENT',
  solo_en_digsilent: 'Solo en DIgSILENT',
  no_leida: 'No se pudo leer',
};

/** La frase de la fila: qué cambió, o por qué no se leyó. */
export function textoDiferencia(d: DiferenciaMin): string {
  const base = ETIQUETAS[d.estado] ?? d.estado;
  if (d.estado === 'no_leida') return `${base}: ${d.error || 'sin lectura'}`;
  if (!d.cambios.length) return base;
  return `${base}: ${d.cambios.join('; ')}`;
}

/** Las filas de la tabla: primero las que piden decisión, después las iguales; dentro, por alimentador y SED. */
export function filasOrdenadas<D extends DiferenciaMin>(diferencias: D[]): D[] {
  const peso = (d: DiferenciaMin) => (sePuedeUsar(d) ? 0 : d.estado === 'no_leida' ? 1 : 2);
  return [...diferencias].sort((a, b) => peso(a) - peso(b)
    || String(a.alimentador ?? '').localeCompare(String(b.alimentador ?? ''))
    || a.sed.localeCompare(b.sed));
}

/** El rótulo de una carga en la lista: SED, kW y si va sola o en bloque, como en el mapa. */
export function rotuloCarga(c: { sed: string; kw: number | null; sola: boolean }): string {
  const kw = c.kw == null ? '' : ` · ${c.kw.toLocaleString('es-PE', { maximumFractionDigits: 1 })} kW`;
  return `${c.sed}${kw}${c.sola ? '' : ' · en bloque'}`;
}

/** Coordenadas para la cuadrilla: UTM si el perfil da su CRS, si no el GPS (constitución P13: no se supone). */
export function textoCoordenadas(p: { lat: number | null; lon: number | null; utm: number[] | null } | null): string {
  if (!p || p.lat == null || p.lon == null) return '—';
  if (p.utm && p.utm.length >= 2) {
    const f = (x: number) => x.toLocaleString('es-PE', { maximumFractionDigits: 1 });
    return `E ${f(p.utm[0])} · N ${f(p.utm[1])}`;
  }
  return `${p.lat.toFixed(6)}, ${p.lon.toFixed(6)}`;
}
