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

// ------------------------------------------------------------------ 111:RF-20 a RF-22: el espacio de ingeniería

/** De dónde viene una selección: la misma regla vale para todas (111:RF-20). */
export type OrigenSeleccion = 'plano' | 'tabla' | 'buscador' | 'inspector' | 'resultados' | 'hallazgo';

export type Seleccion = {
  elegido: string | null;
  /** Lo que se manda a la página del plano: seleccionar (resalta y encuadra) o deseleccionar; `null`, nada. */
  alPlano: { tipo: 'seleccionar'; codigo: string } | { tipo: 'deseleccionar' } | null;
  anuncio: string;
};

/**
 * 111:RF-20: la selección hecha en cualquier vista, para todas. Un código del plano se selecciona en todas, también
 * en el plano (que lo resalta y lo encuadra aunque la selección viniera de él); `null` la quita en todas. Un código
 * que no está en las vistas no cambia la selección y se dice.
 */
export function seleccionEnlazada(codigo: string | null, elementos: Elemento[]): Seleccion {
  if (codigo === null) return { elegido: null, alPlano: { tipo: 'deseleccionar' }, anuncio: 'Selección quitada.' };
  if (!elementos.some((e) => e.codigo === codigo)) {
    return { elegido: null, alPlano: null, anuncio: `${codigo} no está en el plano de este alimentador.` };
  }
  return { elegido: codigo, alPlano: { tipo: 'seleccionar', codigo }, anuncio: `${codigo} seleccionado.` };
}

export type NormaHallazgo = { clave?: string | null; acto?: string | null; articulo?: string | null; pagina?: string | null;
  cita?: string | null; estado?: string | null; obligatoria?: boolean | null; criterio_empresa?: string | null;
  origen?: string | null; falta?: string | null };

export type Hallazgo = {
  codigo: string; capa: string; magnitud: string; texto: string; valor: number; umbral: number; unidad: string;
  norma: NormaHallazgo | null; caso: string; motor: string;
};

type CapasLike = {
  pintable: boolean; caso?: string | null;
  capas: Record<string, { leyenda: { magnitud: string; unidad: string; caso?: string | null; motor_texto?: string | null };
    elementos: { codigo: string; incumple?: { texto: string; valor: number; umbral: number; norma?: NormaHallazgo | null } | null }[] }>;
};

/** 111:RF-21: cada hallazgo de los resultados, con lo que el inspector enseña: valor, umbral, norma, caso y motor. */
export function hallazgosDe(capas: CapasLike | null): Hallazgo[] {
  if (!capas || !capas.pintable) return [];
  const salida: Hallazgo[] = [];
  for (const [clave, capa] of Object.entries(capas.capas)) {
    for (const e of capa.elementos) {
      if (!e.incumple) continue;
      salida.push({ codigo: e.codigo, capa: clave, magnitud: capa.leyenda.magnitud, texto: e.incumple.texto,
        valor: e.incumple.valor, umbral: e.incumple.umbral, unidad: capa.leyenda.unidad, norma: e.incumple.norma ?? null,
        caso: capa.leyenda.caso ?? capas.caso ?? '', motor: capa.leyenda.motor_texto ?? '' });
    }
  }
  return salida;
}

/** 111:RF-22: el reparto de la pantalla de ingeniería, en %: el ancho del plano y el alto de la tabla en su columna. */
export type Paneles = { plano: number; tabla: number };
export const PANELES_POR_DEFECTO: Paneles = { plano: 60, tabla: 55 };
export const LIMITES_PANEL = { min: 25, max: 80, paso: 5 } as const;
const CLAVE_PANELES = 'convertersmartgrid.plano.paneles';

const acotar = (x: number) => Math.max(LIMITES_PANEL.min, Math.min(LIMITES_PANEL.max, Math.round(x)));

/** Los paneles que este navegador recordaba en ese espacio; si no hay, o no se entienden, los de por defecto. */
export function panelesRecordados(almacen: Almacen | null, ws: string): Paneles {
  try {
    const crudo = almacen?.getItem(`${CLAVE_PANELES}.${ws}`);
    if (!crudo) return { ...PANELES_POR_DEFECTO };
    const p = JSON.parse(crudo) as Partial<Paneles>;
    if (!Number.isFinite(p.plano) || !Number.isFinite(p.tabla)) return { ...PANELES_POR_DEFECTO };
    return { plano: acotar(p.plano as number), tabla: acotar(p.tabla as number) };
  } catch {
    return { ...PANELES_POR_DEFECTO };
  }
}

/** Recuerda el reparto en ese espacio; sin almacenamiento, la pantalla sigue con el que tiene. */
export function recordarPaneles(almacen: Almacen | null, ws: string, p: Paneles): void {
  try {
    almacen?.setItem(`${CLAVE_PANELES}.${ws}`, JSON.stringify({ plano: acotar(p.plano), tabla: acotar(p.tabla) }));
  } catch {
    /* sin almacenamiento */
  }
}

/**
 * El nuevo tamaño de un panel al pulsar una tecla en su separador (patrón «window splitter» de WAI-ARIA): flechas,
 * Inicio y Fin; `null` si la tecla no lo mueve. `crece` son las teclas que lo agrandan (derecha o abajo).
 */
export function ajustarPanel(actual: number, tecla: string, orientacion: 'vertical' | 'horizontal'): number | null {
  const [crece, mengua] = orientacion === 'vertical' ? ['ArrowRight', 'ArrowLeft'] : ['ArrowDown', 'ArrowUp'];
  if (tecla === crece) return acotar(actual + LIMITES_PANEL.paso);
  if (tecla === mengua) return acotar(actual - LIMITES_PANEL.paso);
  if (tecla === 'Home') return LIMITES_PANEL.min;
  if (tecla === 'End') return LIMITES_PANEL.max;
  return null;
}

// ------------------------------------------------------------------ 111:RF-24, RF-25: varios alimentadores a la vez

/** Los alimentadores del plano: el principal (el de la variación y el unifilar) y los añadidos, sin repetir y en el
 * orden de la lista; un añadido que ya no está en la lista se olvida. */
export function alimentadoresDelPlano(principal: string, extra: string[], opciones: string[]): string[] {
  if (!principal) return [];
  const vistos = new Set([principal]);
  const salida = [principal];
  for (const o of opciones) if (extra.includes(o) && !vistos.has(o)) { vistos.add(o); salida.push(o); }
  return salida;
}

/** Pone o quita un alimentador de los añadidos. */
export function alternarAlimentador(extra: string[], alimentador: string): string[] {
  return extra.includes(alimentador) ? extra.filter((x) => x !== alimentador) : [...extra, alimentador];
}

/** Los alimentadores que se pueden añadir, filtrados por el texto (sin distinguir mayúsculas), sin el principal. */
export function alimentadoresAnadibles(opciones: string[], principal: string, texto: string): string[] {
  const q = texto.trim().toLocaleLowerCase('es');
  return opciones.filter((o) => o !== principal && (!q || o.toLocaleLowerCase('es').includes(q)));
}
