/**
 * 042:RF-113: lo que dice la casilla «Libro CAPEX» cuando se deja en blanco.
 *
 * El 2026-11-27 el operador no podía proponer las obras de LL202 sin escribir la ruta de un libro CAPEX que ya estaba
 * entre sus referencias. En blanco, el servidor usa el vigente (el del perfil o el de las referencias del espacio), y la
 * casilla lo nombra para que se sepa con qué se costea.
 */
export interface CapexVigente {
  ruta: string;
  nombre: string;
  origen: 'perfil' | 'referencias';
}

export function textoCapexVigente(v: CapexVigente | null | undefined): string {
  if (!v) return 'ruta del .xlsx (no hay uno en las referencias)';
  return `en blanco: ${v.nombre} (${v.origen === 'perfil' ? 'del perfil' : 'de las referencias'})`;
}
