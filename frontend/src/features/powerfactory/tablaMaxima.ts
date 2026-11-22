import type { AmbitoMaxima, MaximaCabecera } from '../../api/types';
import { fmtNum } from '../../shared/formato';

/**
 * 004:RF-112 a RF-116 y 028:RF-43, RF-44: cómo se lee la tabla «Buscar la máxima».
 *
 * Las columnas principales (fecha y hora, kW, kVAR, kVA, FP y V) son lo que se carga en DIgSILENT: en el modo
 * coincidente, el valor de cada alimentador en el instante común; en el no coincidente, la máxima sostenida de cada
 * uno. La máxima propia (en el coincidente) y el pico de 15 minutos son referencias en columnas aparte.
 */
export type TipoAnalisis = 'alimentadores' | 'set' | 'sistema';

/**
 * 086:RF-135: si el servidor tiene en memoria las curvas de esta máxima. Solo guarda las de la última búsqueda y las
 * pierde al reiniciarse; pedir las de otra daba 404 y errores en la consola al abrir la web.
 */
export function curvasEnMemoria(enMemoria: readonly string[] | null | undefined, jobId: string | null | undefined): boolean {
  return Boolean(jobId) && (enMemoria ?? []).includes(jobId as string);
}

export interface ResultadoMaxima {
  resultados?: MaximaCabecera[];
  ambito?: AmbitoMaxima;
  instante?: string | null;
  coincidente?: { fecha?: string | null; total_kw?: number | null } | null;
  sistema_60kv?: { fecha?: string | null; total_kw?: number | null } | null;
  por_barra?: boolean;
}

export interface ModoDeLaTabla {
  /** El criterio con que salió la tabla. */
  ambito: AmbitoMaxima;
  /** El instante común a todos los alimentadores, si lo hay. */
  instanteComun: string | null;
  totalComunKw: number | null;
  /** La tabla es de otro ámbito que el elegido: hay que volver a buscar. */
  deOtroAmbito: boolean;
  /** Título de la columna de la fecha y hora de lo que se carga. */
  tituloFecha: string;
}

/** El ámbito de un resultado; los guardados antes de 028:RF-43 se deducen de sus campos. */
export function ambitoDe(r: ResultadoMaxima | null | undefined): AmbitoMaxima | null {
  if (!r) return null;
  if (r.ambito) return r.ambito;
  if (r.por_barra) return r.sistema_60kv ? 'sistema' : 'set';
  if (r.coincidente) return 'coincidente';
  if (r.instante) return 'instante';
  const alims = new Set((r.resultados ?? []).map((x) => x.alimentador).filter(Boolean));
  return alims.size > 1 ? 'propia' : 'alimentador';
}

export function modoDeLaTabla(r: ResultadoMaxima | null | undefined, tipo: TipoAnalisis): ModoDeLaTabla | null {
  const ambito = ambitoDe(r);
  if (!r || !ambito) return null;
  const instanteComun = ambito === 'sistema' ? r.sistema_60kv?.fecha ?? null
    : ambito === 'coincidente' ? r.coincidente?.fecha ?? r.instante ?? null
    : ambito === 'instante' ? r.instante ?? null : null;
  const totalComunKw = ambito === 'sistema' ? r.sistema_60kv?.total_kw ?? null
    : ambito === 'coincidente' ? r.coincidente?.total_kw ?? null : null;
  // «propia» e «instante» se eligen en «Instante de la calibración» con cualquier ámbito; los demás, con el suyo.
  const deOtroAmbito = (ambito === 'set' && tipo !== 'set') || (ambito === 'sistema' && tipo !== 'sistema')
    || ((ambito === 'coincidente' || ambito === 'alimentador') && tipo !== 'alimentadores');
  const tituloFecha = instanteComun ? 'Fecha y hora (instante común)'
    : ambito === 'set' ? 'Fecha y hora (máx. de su barra)' : 'Fecha y hora (máx. 1 h)';
  return { ambito, instanteComun, totalComunKw, deOtroAmbito, tituloFecha };
}

/** La fila no está en el instante común (028:RF-38: sin medida en él, su máxima del mes). */
export function fueraDelInstante(fila: MaximaCabecera, modo: ModoDeLaTabla | null): boolean {
  return Boolean(modo?.instanteComun && fila.fecha && !fila.error && fila.fecha !== modo.instanteComun);
}

/** La máxima propia como referencia: solo cuando lo que se carga no es ella (modo coincidente o de barra). */
export function conPropiaDeReferencia(modo: ModoDeLaTabla | null): boolean {
  return Boolean(modo && modo.ambito !== 'propia' && modo.ambito !== 'alimentador');
}

/** Lo que se carga en DIgSILENT de una fila: exactamente sus columnas principales (028:RF-44). */
export function cargaDeLaFila(fila: MaximaCabecera): { fecha: string | null; kw: number | null; kvar: number | null } {
  return { fecha: fila.fecha, kw: fila.kw, kvar: fila.kvar };
}

/** La hora de la ventana: «18:15–19:00» si es de una hora, o nada si es un registro. */
export function horaDeLaVentana(fila: MaximaCabecera): string {
  const v = fila.ventana;
  if (!v || v.registros <= 1) return '';
  return `${v.inicio.slice(11, 16)}–${v.fin.slice(11, 16)}`;
}

/** El factor de carga con tres decimales, o una raya. */
export function fmtFactor(x: number | null | undefined): string {
  return x == null || !Number.isFinite(x) ? '—' : fmtNum(x, 3);
}
