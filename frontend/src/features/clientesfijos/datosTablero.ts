/** 105: lo que el tablero calcula para dibujar, sin React: se prueba con node --test. */
import type { AvisoEvolucion, EvolucionResultado } from '../../api/evolucionFijas';

export type Magnitud = 'p_max' | 'q_max' | 'energia_p';

export const MAGNITUDES: { clave: Magnitud; titulo: string; unidad: string }[] = [
  { clave: 'p_max', titulo: 'P máxima por mes', unidad: 'kW' },
  { clave: 'q_max', titulo: 'Q máxima por mes', unidad: 'kVAR' },
  { clave: 'energia_p', titulo: 'Energía activa por mes', unidad: 'MWh' },
];

const NOMBRES = ['ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic'];

/** «2026-04» → «abr 2026». */
export function nombreMes(mes: string | null | undefined): string {
  if (!mes) return '—';
  const [a, m] = mes.split('-');
  return `${NOMBRES[Number(m) - 1] ?? m} ${a}`;
}

/** Un porcentaje con su signo: «+12,3 %», «−4,0 %». */
export function fmtPct(v: number | null | undefined, digitos = 1): string {
  if (v == null || !Number.isFinite(v)) return '—';
  const texto = Math.abs(v).toLocaleString('es-PE', { minimumFractionDigits: digitos, maximumFractionDigits: digitos });
  return `${v > 0 ? '+' : v < 0 ? '−' : ''}${texto} %`;
}

/** «2026-03-25T14:45» → «25/03/2026 14:45», sin pasar por la zona horaria del navegador. */
export function fmtInstante(iso: string | null | undefined): string {
  if (!iso) return '—';
  const [d, h] = iso.split('T');
  const [a, m, dd] = d.split('-');
  return `${dd}/${m}/${a}${h ? ` ${h.slice(0, 5)}` : ''}`;
}

/** Sube, baja o igual: el color de la tabla de variaciones (105:RF-24). */
export function claseVariacion(pct: number | null | undefined): '' | 'var-sube' | 'var-baja' | 'var-igual' {
  if (pct == null || !Number.isFinite(pct)) return '';
  return pct > 0.05 ? 'var-sube' : pct < -0.05 ? 'var-baja' : 'var-igual';
}

export interface SerieMensual { clave: string; etiqueta: string; total: boolean; valores: (number | null)[] }

/** Las líneas de un gráfico mensual: una por cliente y una por total, sin los meses copiados (105:RF-23). */
export function seriesMensuales(r: EvolucionResultado, magnitud: Magnitud): { meses: string[]; series: SerieMensual[] } {
  const copias = new Set(r.copias.map((c) => c.mes));
  const meses = r.meses.filter((m) => !copias.has(m));
  const fila = (filas: { mes: string; [k: string]: unknown }[]) => {
    const por = new Map(filas.map((d) => [d.mes, d[magnitud] as number | null | undefined]));
    return meses.map((m) => por.get(m) ?? null);
  };
  return {
    meses,
    series: [
      ...r.clientes.map((c) => ({ clave: c.codigo, etiqueta: `${c.codigo} (${c.sed})`, total: false, valores: fila(c.meses) })),
      ...r.totales.map((t) => ({ clave: `TOTAL ${t.alimentador}`, etiqueta: `Total ${t.alimentador}`, total: true,
        valores: fila(t.meses) })),
    ],
  };
}

export interface FilaVariacion { clave: string; etiqueta: string; total: boolean; celdas: (number | null)[] }

/** La tabla de variaciones mes a mes de una magnitud (105:RF-24). */
export function tablaVariaciones(r: EvolucionResultado, magnitud: 'p_max' | 'energia_p'): { meses: string[]; filas: FilaVariacion[] } {
  const copias = new Set(r.copias.map((c) => c.mes));
  const meses = r.meses.filter((m) => !copias.has(m));
  const celdas = (v: Record<string, { pct: number | null }> | undefined) => meses.map((m) => v?.[m]?.pct ?? null);
  return {
    meses,
    filas: [
      ...r.clientes.map((c) => ({ clave: c.codigo, etiqueta: c.codigo, total: false, celdas: celdas(c.resumen.variacion[magnitud]) })),
      ...r.totales.map((t) => ({ clave: `TOTAL ${t.alimentador}`, etiqueta: `Total ${t.alimentador}`, total: true,
        celdas: celdas(t.resumen.variacion[magnitud]) })),
    ],
  };
}

export const TIPOS_AVISO: Record<AvisoEvolucion['tipo'], string> = {
  copia: 'Mes copiado', fijos_sobre_cabecera: 'Fijos por encima de la cabecera', discrepancia: 'Fuentes que discrepan',
  posible_renumeracion: 'Posible renumeración (no aplicada)', incompleto: 'Mes incompleto', sin_suministro: 'Cliente sin suministro',
  sin_medicion: 'Cliente sin medición', sin_clientes: 'Alimentador sin clientes fijos', sin_libro: 'Mes sin libro',
  contradiccion: 'Valores distintos entre libros', cabecera: 'Cabecera', lectura: 'Lectura de los libros',
};

/** Los avisos por tipo, los que cambian las cifras primero (105:RF-26). */
export function avisosPorTipo(avisos: AvisoEvolucion[]): { tipo: AvisoEvolucion['tipo']; titulo: string; textos: string[] }[] {
  const orden = Object.keys(TIPOS_AVISO) as AvisoEvolucion['tipo'][];
  return orden
    .map((tipo) => ({ tipo, titulo: TIPOS_AVISO[tipo], textos: avisos.filter((a) => a.tipo === tipo).map((a) => a.texto) }))
    .filter((g) => g.textos.length);
}

/** Como mucho ``maximo`` puntos, con el mínimo y el máximo de cada intervalo: la punta no se pierde (105:RF-25). */
export function reducir<T extends [string, number, number | null]>(puntos: T[], maximo = 3000): T[] {
  if (puntos.length <= maximo) return puntos;
  const paso = Math.ceil(puntos.length / (maximo / 2));
  const out: T[] = [];
  for (let i = 0; i < puntos.length; i += paso) {
    const tramo = puntos.slice(i, i + paso);
    let lo = tramo[0];
    let hi = tramo[0];
    for (const p of tramo) {
      if (p[1] < lo[1]) lo = p;
      if (p[1] > hi[1]) hi = p;
    }
    out.push(...(lo[0] <= hi[0] ? [lo, hi] : [hi, lo]).filter((p, k, xs) => k === 0 || p !== xs[0]));
  }
  return out;
}

/** Texto comparable: sin tildes, sin mayúsculas y con los espacios juntos (105:RF-39). */
export function normalizarTexto(t: string | null | undefined): string {
  return (t ?? '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase().replace(/\s+/g, ' ').trim();
}

/** Un código comparable: sin espacios ni separadores, sin el «.0» de Excel ni ceros a la izquierda. */
export function normalizarCodigo(t: string | null | undefined): string {
  const s = normalizarTexto(t).replace(/^(\d+)\.0+$/, '$1').replace(/[\s_\-.]+/g, '');
  return /^\d+$/.test(s) ? s.replace(/^0+(?=\d)/, '') : s;
}

/** Distancia de edición (Levenshtein) con la transposición de dos letras como una sola errata. */
function distancia(a: string, b: string): number {
  const d = Array.from({ length: a.length + 1 }, (_v, i) => [i, ...Array(b.length).fill(0)]);
  for (let j = 1; j <= b.length; j++) d[0][j] = j;
  for (let i = 1; i <= a.length; i++) {
    for (let j = 1; j <= b.length; j++) {
      const c = a[i - 1] === b[j - 1] ? 0 : 1;
      d[i][j] = Math.min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + c);
      if (i > 1 && j > 1 && a[i - 1] === b[j - 2] && a[i - 2] === b[j - 1]) d[i][j] = Math.min(d[i][j], d[i - 2][j - 2] + 1);
    }
  }
  return d[a.length][b.length];
}

/** Parecido de 0 a 1 entre dos palabras. */
export function parecido(a: string, b: string): number {
  if (!a || !b) return 0;
  if (b.startsWith(a)) return Math.max(0.9, a.length / b.length);
  return 1 - distancia(a, b) / Math.max(a.length, b.length);
}

export interface Encontrado { codigo: string; puntaje: number; campo: string; valor: string }

interface Buscable { codigo: string; cl?: string; nombre?: string; sed: string; alimentador: string; anteriores: string[] }

/**
 * Buscador del tablero por NIS, CL, nombre, SED o alimentador, ordenado por relevancia (105:RF-39). Un código vale
 * entero (100), por su comienzo (90) o por un trozo (80); el nombre entero vale 95 y un trozo 85, y si no se busca
 * palabra a palabra, sin tildes y con erratas, con el parecido medio (hasta 79). Debajo de 60 no se da como encontrado.
 */
export function buscarClientes(clientes: Buscable[], consulta: string): Encontrado[] {
  const q = normalizarTexto(consulta);
  const qc = normalizarCodigo(consulta);
  if (!q) return [];
  const salida: Encontrado[] = [];
  for (const c of clientes) {
    let mejor: Encontrado | null = null;
    const proponer = (puntaje: number, campo: string, valor: string) => {
      if (!mejor || puntaje > mejor.puntaje) mejor = { codigo: c.codigo, puntaje, campo, valor };
    };
    const codigos: [string, string | undefined][] = [['NIS', c.codigo], ...c.anteriores.map((a) => ['NIS anterior', a] as [string, string]),
      ['CL', c.cl], ['SED', c.sed], ['alimentador', c.alimentador]];
    for (const [campo, valor] of codigos) {
      const v = normalizarCodigo(valor);
      if (!v || !qc) continue;
      if (v === qc) proponer(100, campo, valor!);
      else if (v.startsWith(qc)) proponer(90, campo, valor!);
      else if (qc.length >= 3 && v.includes(qc)) proponer(80, campo, valor!);
    }
    const nombre = normalizarTexto(c.nombre);
    if (nombre) {
      const palabras = nombre.split(/[^a-z0-9ñ]+/).filter(Boolean);
      const buscadas = q.split(/[^a-z0-9ñ]+/).filter(Boolean);
      if (palabras.length && buscadas.length) {
        const media = buscadas.reduce((s, b) => s + Math.max(...palabras.map((p) => parecido(b, p))), 0) / buscadas.length;
        // El nombre entero, o un trozo de tres letras o más, vale más que el parecido palabra a palabra.
        const puntaje = nombre === q ? 95 : q.length >= 3 && nombre.includes(q) ? 85 : Math.round(media * 79);
        if (puntaje >= 60) proponer(puntaje, 'nombre', c.nombre!);
      }
    }
    if (mejor) salida.push(mejor);
  }
  return salida.sort((a, b) => b.puntaje - a.puntaje || a.codigo.localeCompare(b.codigo));
}
