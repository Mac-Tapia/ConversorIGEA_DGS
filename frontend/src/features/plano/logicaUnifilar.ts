import type { CapasPlano, VistaPlano } from '../../api/plano';

/**
 * 111:RF-23: la disposición del unifilar en el navegador, sin reglas eléctricas. El servidor da a cada barra su nivel
 * y su orden desde la cabecera (la misma regla que el unifilar del PIT); aquí solo se pasan a coordenadas del dibujo y
 * se cuelgan de ellas los tramos, las SED y las maniobras de la vista, por su código. Nada cambia vértices ni datos.
 */
export const PASO_X = 96;
export const PASO_Y = 40;
const MARGEN = 24;

export type PuntoUnifilar = { x: number; y: number };
export type TramoUnifilar = { codigo: string; desde: string; hasta: string; x1: number; y1: number; x2: number; y2: number };
export type DisposicionUnifilar = {
  ancho: number;
  alto: number;
  barras: Array<{ codigo: string } & PuntoUnifilar>;
  tramos: TramoUnifilar[];
  /** Tramos de la vista cuyos extremos no están en el unifilar: se cuentan, no se inventan. */
  sinDibujar: string[];
  sinAlcanzar: string[];
  fuente: string | null;
};

export function disposicionUnifilar(vista: VistaPlano): DisposicionUnifilar {
  const u = vista.unifilar;
  const pos = new Map<string, PuntoUnifilar>();
  for (const b of u.barras) pos.set(b.codigo, { x: MARGEN + b.nivel * PASO_X, y: MARGEN + b.orden * PASO_Y });
  const tramos: TramoUnifilar[] = [];
  const sinDibujar: string[] = [];
  for (const t of vista.tramos) {
    const a = pos.get(t.desde);
    const z = pos.get(t.hasta);
    if (!a || !z) { sinDibujar.push(t.codigo); continue; }
    tramos.push({ codigo: t.codigo, desde: t.desde, hasta: t.hasta, x1: a.x, y1: a.y, x2: z.x, y2: z.y });
  }
  return {
    ancho: MARGEN * 2 + Math.max(u.niveles - 1, 0) * PASO_X,
    alto: MARGEN * 2 + Math.max(u.ancho - 1, 0) * PASO_Y,
    barras: u.barras.map((b) => ({ codigo: b.codigo, ...(pos.get(b.codigo) as PuntoUnifilar) })),
    tramos,
    sinDibujar,
    sinAlcanzar: u.sin_alcanzar,
    fuente: u.fuente,
  };
}

/** El punto donde va una SED o una maniobra: su barra, o el centro de su tramo. */
export function puntoDe(d: DisposicionUnifilar, barra: string | null | undefined, tramo: string | null | undefined): PuntoUnifilar | null {
  const b = barra ? d.barras.find((x) => x.codigo === barra) : undefined;
  if (b) return { x: b.x, y: b.y };
  const t = tramo ? d.tramos.find((x) => x.codigo === tramo) : undefined;
  return t ? { x: (t.x1 + t.x2) / 2, y: (t.y1 + t.y2) / 2 } : null;
}

/**
 * 111:RF-10, RF-23: los mismos resultados que el plano, por código. «alerta» si alguna capa marca un incumplimiento,
 * «normal» si tiene valor dentro de la banda; sin resultado, el elemento no lleva banda. Las bandas las da el servidor.
 */
export function bandasPorCodigo(capas: CapasPlano | null): Map<string, 'alerta' | 'normal'> {
  const salida = new Map<string, 'alerta' | 'normal'>();
  if (!capas?.pintable) return salida;
  for (const capa of Object.values(capas.capas)) {
    for (const e of capa.elementos) {
      if (e.incumple) salida.set(e.codigo, 'alerta');
      else if (e.banda === 'normal' && !salida.has(e.codigo)) salida.set(e.codigo, 'normal');
    }
  }
  return salida;
}
