/** Lógica de la pestaña del plano que no es una regla eléctrica: listar, buscar, navegar con teclado y la ventana de
 * filas de la tabla virtualizada. Las reglas de la edición y los umbrales los decide el servidor. */
import type { BarraPlano, ManiobraPlano, SedPlano, TramoPlano, VistaPlano } from '../../api/plano';

export type Elemento =
  | { clase: 'tramo'; codigo: string; alimentador: string; detalle: string; dato: TramoPlano }
  | { clase: 'barra'; codigo: string; alimentador: string; detalle: string; dato: BarraPlano }
  | { clase: 'sed'; codigo: string; alimentador: string; detalle: string; dato: SedPlano }
  | { clase: 'maniobra'; codigo: string; alimentador: string; detalle: string; dato: ManiobraPlano };

/** Todos los elementos de las vistas, con el mismo código que el plano, el inspector y los resultados. */
export function elementosDe(vistas: VistaPlano[]): Elemento[] {
  const salida: Elemento[] = [];
  for (const v of vistas) {
    const a = v.alimentador;
    for (const t of v.tramos) salida.push({ clase: 'tramo', codigo: t.codigo, alimentador: a, detalle: `${t.desde} → ${t.hasta}`, dato: t });
    for (const b of v.barras) salida.push({ clase: 'barra', codigo: b.codigo, alimentador: a, detalle: '', dato: b });
    for (const s of v.sed) salida.push({ clase: 'sed', codigo: s.codigo, alimentador: a, detalle: s.barra ?? '', dato: s });
    for (const m of v.maniobras) salida.push({ clase: 'maniobra', codigo: m.codigo, alimentador: a, detalle: m.estado, dato: m });
  }
  return salida;
}

/** Los elementos cuyo código contiene el texto (sin distinguir mayúsculas); el que coincide entero va primero. */
export function buscarPorCodigo(elementos: Elemento[], texto: string, tope = 50): Elemento[] {
  const q = texto.trim().toLocaleLowerCase('es');
  if (!q) return [];
  const hallados = elementos.filter((e) => e.codigo.toLocaleLowerCase('es').includes(q));
  hallados.sort((x, y) => Number(y.codigo.toLocaleLowerCase('es') === q) - Number(x.codigo.toLocaleLowerCase('es') === q));
  return hallados.slice(0, tope);
}

/** El índice al que lleva una tecla en una lista de `total` filas, o `null` si la tecla no navega. */
export function siguienteIndice(actual: number, tecla: string, total: number, pagina = 10): number | null {
  if (total <= 0) return null;
  const tope = (i: number) => Math.max(0, Math.min(total - 1, i));
  switch (tecla) {
    case 'ArrowDown': return tope(actual + 1);
    case 'ArrowUp': return tope(actual - 1);
    case 'Home': return 0;
    case 'End': return total - 1;
    case 'PageDown': return tope(actual + pagina);
    case 'PageUp': return tope(actual - pagina);
    default: return null;
  }
}

/** Las filas que caben en la ventana de la tabla, con un margen arriba y abajo. */
export function ventanaDeFilas(scrollTop: number, alto: number, altoFila: number, total: number, margen = 5) {
  const inicio = Math.max(0, Math.floor(scrollTop / altoFila) - margen);
  const fin = Math.min(total, Math.ceil((scrollTop + alto) / altoFila) + margen);
  return { inicio, fin, antes: inicio * altoFila, despues: Math.max(0, (total - fin) * altoFila) };
}

/** Lee los vértices escritos a mano, uno por línea («latitud, longitud»); `null` si alguno no se entiende. */
export function leerVertices(texto: string): number[][] | null {
  const lineas = texto.split(/\r?\n/).map((l) => l.trim()).filter(Boolean);
  const salida: number[][] = [];
  for (const l of lineas) {
    const partes = l.split(/[;,\s]+/).filter(Boolean).map(Number);
    if (partes.length !== 2 || partes.some((x) => !Number.isFinite(x))) return null;
    salida.push(partes);
  }
  return salida;
}

/** Un valor de una capa como se lee: número con coma decimal, o el texto tal cual. */
export function textoValor(valor: unknown, unidad = ''): string {
  if (valor === null || valor === undefined) return '—';
  if (typeof valor === 'number') return `${valor.toLocaleString('es-PE', { maximumFractionDigits: 4 })}${unidad ? ` ${unidad}` : ''}`;
  return String(valor);
}

type Almacen = Pick<Storage, 'getItem' | 'setItem'>;
const CLAVE_RECORDADA = 'convertersmartgrid.plano.variacion';
const ID_VARIACION = /^[0-9a-f]{16}$/;

/** El almacenamiento del navegador, o `null` si no lo hay o su acceso lanza (navegación privada, previsualización). */
export function almacenDelNavegador(): Almacen | null {
  try {
    return globalThis.localStorage ?? null;
  } catch {
    return null;
  }
}

/** La variación que este navegador miraba en ese espacio, solo como comodidad: lo guardado vive en el servidor. */
export function variacionRecordada(almacen: Almacen | null, ws: string): string | null {
  try {
    const v = almacen?.getItem(`${CLAVE_RECORDADA}.${ws}`) ?? null;
    return v && ID_VARIACION.test(v) ? v : null;
  } catch {
    return null;
  }
}

/** Recuerda la variación que se mira; si el almacenamiento no deja, no pasa nada. */
export function recordarVariacion(almacen: Almacen | null, ws: string, id: string): void {
  try {
    almacen?.setItem(`${CLAVE_RECORDADA}.${ws}`, id);
  } catch {
    /* sin almacenamiento: la pestaña sigue con la lista del servidor */
  }
}
