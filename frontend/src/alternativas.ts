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
  elegida: boolean;
}

/** Las mismas palabras que el informe (`informes.filas_alternativas_escalera`). */
export function alcanceDe(a: Alternativa): string {
  if (a.definitiva == null) return 'sin medir';
  if (a.definitiva) return `definitiva, ${a.aguanta_anios} años`;
  return a.aguanta_anios ? `temporal, aguanta ${a.aguanta_anios} años` : 'temporal';
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
