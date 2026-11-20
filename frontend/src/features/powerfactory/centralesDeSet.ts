/** 086:RF-122 (amplía 022:RF-88): la SET de cada central térmica (CT…) del libro, elegida entre todas las de la
 * estructura. Primero las SET de los alimentadores analizados; una central cuya SET no tiene ninguno de ellos no entra
 * en la máxima por barra y se dice por qué. La regla de qué entra la aplica también el servidor. */
import type { CentralDeBarra, SetDeCentral } from '../../api/types';

const mayus = (x: string) => x.trim().toUpperCase();

/** Las SET con algún alimentador analizado y las demás, cada grupo en el orden del servidor. */
export function setsPorAnalisis(sets: SetDeCentral[], analizados: string[]): { analizadas: SetDeCentral[]; otras: SetDeCentral[] } {
  const elegidos = new Set(analizados.map(mayus));
  const analizadas: SetDeCentral[] = [];
  const otras: SetDeCentral[] = [];
  for (const s of sets) (s.alimentadores.some((a) => elegidos.has(mayus(a))) ? analizadas : otras).push(s);
  return { analizadas, otras };
}

/** La SET de la central: la que eligió el operador o, si no, la del libro. */
export function setDeLaCentral(c: CentralDeBarra, elegida: Record<string, string>): string {
  return elegida[c.medidor] ?? c.set;
}

/** Los alimentadores de esa SET (para «En un tramo de…»); sin la lista de SET, los que trajo la central. */
export function alimentadoresDeSet(codigo: string, sets: SetDeCentral[], c: CentralDeBarra): string[] {
  const s = sets.find((x) => x.codigo === codigo);
  return s ? s.alimentadores : codigo === c.set ? c.alimentadores : [];
}

/** Por qué la central no entra en la máxima por barra, o `null` si entra. */
export function motivoNoEntra(codigo: string, sets: SetDeCentral[], analizados: string[]): string | null {
  if (!codigo) return 'Sin SET: no entra. Elija la SET a la que se conecta.';
  const s = sets.find((x) => x.codigo === codigo);
  if (!s) return null;
  const elegidos = new Set(analizados.map(mayus));
  return s.alimentadores.some((a) => elegidos.has(mayus(a)))
    ? null : `${s.rotulo} no tiene ninguno de los alimentadores analizados: no entra.`;
}
