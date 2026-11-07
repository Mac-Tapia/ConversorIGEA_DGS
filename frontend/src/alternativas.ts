/** Lo que la web lee de las alternativas de cada alimentador (042:RF-58, RF-77). */
export interface Alternativa {
  numero: number;
  nombre: string;
  inversion: number | null;
  costo_anual: number | null;
  fraccion: number | null;
  valle?: boolean | null;
  definitiva?: boolean | null;
  aguanta_anios?: number | null;
  factor?: number | null;
  /** 098:RF-35: el horizonte más corto que se midió; 0 años es que no llega ni a él. */
  mas_corto?: number | null;
  u_min_mt?: number | null;
  /** 098:RF-37: «corto plazo» se aplica; «largo plazo» se plantea, para el año en que hace falta. */
  plazo?: string | null;
  hace_falta_en_anio?: number | null;
  elegida: boolean;
}

/** Las mismas palabras que el informe (`informes.filas_alternativas_escalera`). */
export function alcanceDe(a: Alternativa): string {
  if (a.definitiva == null) return 'sin medir';
  if (a.definitiva) return `definitiva, ${a.aguanta_anios} años`;
  if (a.aguanta_anios) return `temporal, aguanta ${a.aguanta_anios} años`;
  return 'temporal, no llega al horizonte más corto' + (a.mas_corto ? ` (${a.mas_corto} años)` : '');
}

/** 098:RF-37: las mismas palabras que la columna «Plazo» del informe. */
export function plazoDe(a: Alternativa): string {
  const p = a.plazo ?? '';
  return a.hace_falta_en_anio == null ? p : `${p}, hace falta en el año ${a.hace_falta_en_anio}`;
}

export function tensionDe(a: Alternativa): string {
  return a.u_min_mt == null ? '' : a.u_min_mt.toFixed(3);
}

export function sorteosDe(a: Alternativa): string {
  return a.fraccion == null ? 'sin sortear' : `${Math.round(100 * a.fraccion)} %`;
}

export function valleDe(a: Alternativa): string {
  return a.valle === true ? 'cumple' : 'no comprobado';
}

/** De menor a mayor costo anual; la que no tiene costo («ninguna obra corrige») va al final. */
export function porCosto(lista: readonly Alternativa[]): Alternativa[] {
  return [...lista].sort((a, b) => (a.costo_anual ?? Infinity) - (b.costo_anual ?? Infinity));
}
