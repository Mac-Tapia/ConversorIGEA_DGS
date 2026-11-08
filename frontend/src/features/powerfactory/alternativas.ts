import type { Alternativa } from '../../api/types';

/** Lo que la web lee de las alternativas de cada alimentador (042:RF-58, RF-77). */
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
  const v = a.vuelve_a_fallar;
  if (v?.anio) {
    const donde = v.barra && v.u != null ? ` (${v.barra} a ${v.u.toFixed(3)} p.u.)` : '';
    return `${p}, vuelve a tener problemas en el año ${v.anio}${donde}; la alternativa de ese año se plantea en el PIDE partiendo de esta`;
  }
  if (v?.horizonte) return `${p}, cumple hasta el horizonte de ${v.horizonte} años`;
  const entre = a.hace_falta_entre;
  if (entre) {
    const [desde, hasta] = entre;
    if (!desde) return hasta ? `${p}, cumple hoy y hace falta antes del año ${hasta}` : `${p}, hace falta ya`;
    return hasta ? `${p}, hace falta entre el año ${desde} y el ${hasta}` : `${p}, hace falta tras el año ${desde}`;
  }
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
