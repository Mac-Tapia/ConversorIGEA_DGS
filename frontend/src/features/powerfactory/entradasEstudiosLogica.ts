/**
 * Lógica de «Datos que faltan a los estudios» (spec 012, RF-75, RF-77, RF-80), sin React para
 * poder probarla con `node --test`.
 *
 * Usuario, 2026-11-13: «lo que falta se ingresará en TXT o en imagen» y «todo tiene que ser
 * cargado desde la web». El catálogo dice, por estudio no disponible, el nombre de cada entrada
 * que le falta; aquí se cruza con los esquemas del servidor para que cada entrada salga una sola
 * vez aunque la pidan varios estudios (la Pcc la piden el cortocircuito y las protecciones).
 */
import type { EntradaEsquema, EntradasEstado, FilaEntrada } from '../../api/entradasEstudios';

export interface EstudioNoOfrecido {
  clave: string;
  nombre: string;
  falta: string[];
  motivo: string;
}

export interface EntradaQueFalta {
  esquema: EntradaEsquema;
  /** Los estudios no disponibles que la piden, por su nombre. */
  estudios: string[];
  guardada: boolean;
}

/** Ficheros que se pueden soltar (usuario: «TXT o en imagen, JPG o similares»). */
export const ACEPTA = '.txt,.csv,.tsv,.dat,.pdf,.png,.jpg,.jpeg,.bmp,.tif,.tiff,.webp';

/** Filas que se muestran por página: un perfil de 15 minutos de un año tiene 35 040. */
export const POR_PAGINA = 100;

/**
 * Las entradas que piden los estudios no disponibles, una vez cada una y en el orden de los
 * esquemas; también las ya guardadas, para poder reemplazarlas (RF-80).
 */
export function entradasQueFaltan(noOfrecidos: EstudioNoOfrecido[], estado: EntradasEstado): EntradaQueFalta[] {
  const out: EntradaQueFalta[] = [];
  for (const esquema of estado.esquemas) {
    const estudios = noOfrecidos.filter((e) => e.falta.includes(esquema.nombre)).map((e) => e.nombre);
    const guardada = Boolean(estado.guardadas[esquema.clave]);
    if (estudios.length || guardada || estado.borradores[esquema.clave]) out.push({ esquema, estudios, guardada });
  }
  return out;
}

/** Los estudios que ya tienen sus datos pero cuya ejecución en DIgSILENT no está (RF-80). */
export function conDatosSinEjecucion(noOfrecidos: EstudioNoOfrecido[]): EstudioNoOfrecido[] {
  return noOfrecidos.filter((e) => !e.falta.length && e.motivo.startsWith('datos cargados'));
}

/** Una fila vacía con las columnas del esquema, para escribir a mano sin fichero. */
export function filaVacia(esquema: EntradaEsquema): FilaEntrada {
  return Object.fromEntries(esquema.columnas.map((c) => [c.clave, null]));
}

/** Las filas con una celda cambiada; la tabla no se muta (React compara por referencia). */
export function editarCelda(filas: FilaEntrada[], fila: number, columna: string, valor: string): FilaEntrada[] {
  return filas.map((f, i) => (i === fila ? { ...f, [columna]: valor.trim() === '' ? null : valor } : f));
}

/** Las filas sin la de índice `fila`. */
export function quitarFila(filas: FilaEntrada[], fila: number): FilaEntrada[] {
  return filas.filter((_f, i) => i !== fila);
}

/** El tramo de filas de la página `numero` (desde 0) y cuántas páginas hay. */
export function pagina(filas: FilaEntrada[], numero: number, tam = POR_PAGINA): { desde: number; filas: FilaEntrada[]; paginas: number } {
  const paginas = Math.max(1, Math.ceil(filas.length / tam));
  const n = Math.min(Math.max(0, numero), paginas - 1);
  return { desde: n * tam, filas: filas.slice(n * tam, (n + 1) * tam), paginas };
}

/** El texto de una celda: los números como los escribió el servidor, lo vacío en blanco. */
export function textoCelda(v: unknown): string {
  return v === null || v === undefined ? '' : String(v);
}

/** Errores de una fila concreta (los del servidor empiezan por «Fila n»), para marcarla. */
export function filasConError(errores: string[]): Set<number> {
  const out = new Set<number>();
  for (const e of errores) {
    const m = /^Fila (\d+)/.exec(e);
    if (m) out.add(Number(m[1]) - 1);
  }
  return out;
}
