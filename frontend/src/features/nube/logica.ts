/** 109: lo que deciden las pantallas de la nube, sin React, para probarlo aparte. */
import { NOMBRE_PROVEEDOR, SIN_CUENTA } from '../../api/nube';
import type { AlcanceNube, CompartirPreviaRespuesta, CuentaNube, ImportarPeticion, LibroNube, ProveedorNube, ReciboNube,
  VinculoNube } from '../../api/nube';

export { SIN_CUENTA };

/** El mensaje con que la página del selector devuelve los ids (`web/nube_selector.py`, `MENSAJE`). */
export const MENSAJE_SELECCION = 'csg-nube-seleccion';

export const VISIBLE = NOMBRE_PROVEEDOR;

export const LIBROS: { clave: LibroNube; etiqueta: string }[] = [
  { clave: 'cabecera', etiqueta: 'Libros de cabecera' },
  { clave: 'suministros', etiqueta: 'Suministros' },
  { clave: 'clientes', etiqueta: 'Libro de clientes' },
  { clave: 'perdidas', etiqueta: 'Pérdidas' },
  { clave: 'coincidente', etiqueta: 'Máxima coincidente' },
];

export type Tono = 'ok' | 'warn' | 'error' | 'muted' | 'info';

/** Ninguna cuenta registrada en este equipo, o la API no respondió: la tarjeta dice `SIN_CUENTA`. */
export function sinRegistro(cuentas: CuentaNube[] | null): boolean {
  return !cuentas || !cuentas.some((c) => c.registrado);
}

export const conectadas = (cuentas: CuentaNube[] | null) => (cuentas ?? []).filter((c) => c.conectada && c.cuenta);

/** La vuelta del proveedor: `/?nube=conectada&proveedor=…`, `cancelada` o `error` (`nube_api.py`, `nube_retorno`). */
export function leerRetorno(search: string): { tono: Tono; texto: string } | null {
  const q = new URLSearchParams(search);
  const r = q.get('nube');
  if (r === 'conectada') {
    const p = q.get('proveedor');
    const nombre = p === 'google' || p === 'microsoft' ? VISIBLE[p] : null;
    return { tono: 'ok', texto: nombre ? `${nombre} conectado.` : 'Cuenta conectada.' };
  }
  if (r === 'cancelada') return { tono: 'warn', texto: 'Conexión cancelada.' };
  if (r === 'error') return { tono: 'error', texto: 'No se pudo conectar la cuenta. Vuelva a intentarlo.' };
  return null;
}

/** Los ids de un mensaje del selector, o `null` si no es del propio origen, de ese proveedor y de ese modo. */
export function seleccionDelSelector(ev: { origin: string; data: unknown }, origen: string, proveedor: ProveedorNube,
  modo: 'ficheros' | 'carpeta'): string[] | null {
  if (ev.origin !== origen || !ev.data || typeof ev.data !== 'object') return null;
  const d = ev.data as Record<string, unknown>;
  if (d.tipo !== MENSAJE_SELECCION || d.proveedor !== proveedor || d.modo !== modo) return null;
  if (!Array.isArray(d.ids) || !d.ids.every((x) => typeof x === 'string' && x.length > 0)) return null;
  return d.ids as string[];
}

/** El cuerpo de `POST …/nube/importar`: `destino` es «casilla:<slot>» o «libro:<tipo>». */
export function peticionImportar(proveedor: ProveedorNube, ids: string[], destino: string): ImportarPeticion {
  const [tipo, clave] = destino.split(':', 2);
  if (!clave || (tipo !== 'casilla' && tipo !== 'libro')) throw new Error('Elija dónde entra el fichero.');
  if (ids.length === 0) throw new Error('Elija al menos un fichero.');
  if (tipo === 'casilla') {
    if (ids.length !== 1) throw new Error('Una casilla admite un solo fichero.');
    return { proveedor, ids, casilla: clave };
  }
  const libro = LIBROS.find((l) => l.clave === clave)?.clave;
  if (!libro) throw new Error('Elija dónde entra el fichero.');
  return { proveedor, ids, libro };
}

/** 109:RF-10, RF-11, RF-20: sin bloqueo, con la confirmación de la previa y, si es público, con su autorización. */
export function puedeConfirmarCompartir(previa: CompartirPreviaRespuesta | null, autorizo: boolean): boolean {
  if (!previa || !previa.confirmacion || previa.bloqueo.length > 0) return false;
  return !previa.publico || autorizo;
}

export function estadoVinculo(v: VinculoNube): { tono: Tono; texto: string } {
  if (v.estado === 'nueva') return { tono: 'warn', texto: 'Versión nueva' };
  if (v.estado === 'sin_comprobar') return { tono: 'muted', texto: 'No se pudo comprobar' };
  return { tono: 'ok', texto: 'Al día' };
}

// El contrato declara como objeto libre el destino, la candidata y los recibos: se leen campo a campo, y lo que no
// tenga el tipo esperado no se pinta.
type Libre = { [clave: string]: unknown };
const objeto = (x: unknown): Libre | null => (x && typeof x === 'object' && !Array.isArray(x) ? x as Libre : null);
const texto = (x: unknown): string | null => (typeof x === 'string' && x ? x : null);
const numero = (x: unknown): number | null => (typeof x === 'number' && Number.isFinite(x) ? x : null);

/** La casilla o el libro al que entra el vínculo (`destino` de `registrar_vinculo`). */
export function destinoDe(v: VinculoNube): { casilla: string | null; libro: string | null } {
  const d = objeto(v.destino);
  return { casilla: texto(d?.casilla), libro: texto(d?.libro) };
}

export function nombreDestino(v: VinculoNube, etiquetas: Record<string, string> = {}): string {
  const { casilla, libro } = destinoDe(v);
  if (casilla) return etiquetas[casilla] ?? casilla;
  return LIBROS.find((l) => l.clave === libro)?.etiqueta ?? libro ?? '';
}

export interface Comparacion { iguales: boolean; tamanoAnterior: number | null; tamanoNuevo: number | null;
  lineas: { anadidas: number; quitadas: number } | null }

/** 109:RF-8: lo que cambia entre la copia en uso y la traída (`comparar()` de `web/nube.py`), o `null` sin candidata. */
export function comparacionDe(v: VinculoNube): Comparacion | null {
  const c = objeto(objeto(v.candidata)?.comparacion);
  if (!c || typeof c.iguales !== 'boolean') return null;
  const l = objeto(c.lineas);
  const anadidas = numero(l?.anadidas);
  const quitadas = numero(l?.quitadas);
  return { iguales: c.iguales, tamanoAnterior: numero(objeto(c.anterior)?.tamano),
    tamanoNuevo: numero(objeto(c.nueva)?.tamano),
    lineas: anadidas !== null && quitadas !== null ? { anadidas, quitadas } : null };
}

/** Las publicaciones que se pueden compartir: los recibos de tipo «publicacion» con su clave. */
export function publicacionesDe(recibos: ReciboNube[]): { clave: string; etiqueta: string }[] {
  const salida: { clave: string; etiqueta: string }[] = [];
  for (const r of recibos) {
    const clave = texto(r.clave);
    if (r.tipo !== 'publicacion' || !clave) continue;
    const nombre = texto(r.nombre_remoto) ?? texto(r.paquete) ?? 'Expediente';
    const hora = texto(r.hora);
    salida.push({ clave, etiqueta: hora ? `${nombre} · ${hora.replace('T', ' ').slice(0, 16)}` : nombre });
  }
  return salida;
}

/** 109:RF-1, 110:RF-1: lo que permite hoy una cuenta conectada (la misma da los archivos y el correo). */
export function permisosDeCuenta(c: CuentaNube): string {
  if (!c.conectada || (c.puede_publicar === null && c.puede_enviar === null)) return '';
  const archivos = c.puede_publicar === true ? 'Archivos: leer y publicar' : 'Archivos: leer';
  if (c.puede_enviar === null) return archivos;
  return `${archivos} · Correo: ${c.puede_enviar ? 'enviar' : 'no'}`;
}

/** 109:RF-9, 110:RF-1: si la cuenta conectada aún no concedió publicar o enviar. Sin saberlo (`null`), se ofrece. */
export function faltaPermiso(c: CuentaNube | undefined, alcance: Exclude<AlcanceNube, 'leer'>): boolean {
  if (!c || !c.conectada) return false;
  return (alcance === 'publicar' ? c.puede_publicar : c.puede_enviar) !== true;
}
