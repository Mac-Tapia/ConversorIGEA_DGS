/**
 * 086:RF-126: el ámbito de la máxima, con su variante no coincidente en el mismo desplegable.
 *
 * El 2026-11-24 el usuario no encontró la «Máxima de cada alimentador (no coincidente)» que pidió el 19-11: estaba solo
 * en «Instante de la calibración», que aparece después de buscar la máxima coincidente. Aquí se elige antes de buscar,
 * con dos o más alimentadores, por SET y por sistema eléctrico. El valor por defecto de cada ámbito no cambia.
 */
export type TipoAnalisis = 'alimentadores' | 'set' | 'sistema';

export interface Ambito {
  tipo: TipoAnalisis;
  /** Cada alimentador en su propia máxima: los instantes no ocurren juntos. */
  noCoincidente: boolean;
}

export const OPCIONES_AMBITO: { valor: string; rotulo: string }[] = [
  { valor: 'alimentadores', rotulo: 'Alimentadores (1 a 3 juntos): su máxima coincidente' },
  { valor: 'alimentadores:propia', rotulo: 'Alimentadores: la máxima de cada uno (no coincidente)' },
  { valor: 'set', rotulo: 'Por SET: máxima de barra de SET (alta tensión → media tensión)' },
  { valor: 'set:propia', rotulo: 'Por SET: la máxima de cada alimentador (no coincidente)' },
  { valor: 'sistema', rotulo: 'Sistema eléctrico: máxima coincidente de sus barras de alta tensión' },
  { valor: 'sistema:propia', rotulo: 'Sistema eléctrico: la máxima de cada alimentador (no coincidente)' },
];

export function valorDelAmbito(a: Ambito): string {
  return a.noCoincidente ? `${a.tipo}:propia` : a.tipo;
}

export function leerAmbito(valor: string): Ambito {
  const [tipo, variante] = valor.split(':');
  if (tipo !== 'alimentadores' && tipo !== 'set' && tipo !== 'sistema') {
    throw new Error(`ámbito de la máxima desconocido: ${valor}`);
  }
  return { tipo, noCoincidente: variante === 'propia' };
}

/** Con más de 3 alimentadores la coincidente pide SET o sistema; la no coincidente toma cada uno por su cuenta. */
export function demasiadosParaLaCoincidente(a: Ambito, alimentadores: number): boolean {
  return a.tipo === 'alimentadores' && !a.noCoincidente && alimentadores > 3;
}
