/** Piezas comunes de las gráficas SVG de la web: sin librería de gráficos, con los tokens de styles.css. */
import { useCallback, useEffect, useRef, useState, type CSSProperties } from 'react';

/** 006:RF-45: letra del mismo tamaño en pantalla, sea cual sea el ancho de la gráfica.
 *
 *  Las gráficas son un SVG con `viewBox` que se escala al ancho de su caja: un texto de 12 unidades medía unos 26 px en una
 *  pantalla ancha, el doble que el título (usuario, 2026-11-12: «disminuir el tamaño de las letras y números de las
 *  etiquetas de los ejes al mismo tamaño del título»). Se mide el ancho real y se pasa en `--escala` (unidades del dibujo por
 *  píxel); `.curva-texto` multiplica su tamaño en px por ella. Devuelve la referencia que hay que poner en el `<svg>` y su
 *  estilo. */
export function useLetraFija(ancho: number): [(el: SVGSVGElement | null) => void, CSSProperties] {
  const [escala, setEscala] = useState(1);
  const observador = useRef<ResizeObserver | null>(null);
  const ref = useCallback((el: SVGSVGElement | null) => {
    observador.current?.disconnect();
    observador.current = null;
    if (!el) return;
    const medir = () => {
      const w = el.getBoundingClientRect().width;
      if (w > 0) setEscala(ancho / w);
    };
    medir();
    if (typeof ResizeObserver !== 'undefined') {
      observador.current = new ResizeObserver(medir);
      observador.current.observe(el);
    }
  }, [ancho]);
  useEffect(() => () => observador.current?.disconnect(), []);
  return [ref, { ['--escala' as string]: String(escala) } as CSSProperties];
}

/** Valores «redondos» para las marcas de un eje. */
export function marcas(min: number, max: number, n = 5): number[] {
  const paso0 = (max - min) / n || 1;
  const mag = 10 ** Math.floor(Math.log10(paso0));
  const paso = [1, 2, 2.5, 5, 10].map((k) => k * mag).find((k) => k >= paso0) ?? paso0;
  const out = [];
  for (let v = Math.ceil(min / paso) * paso; v <= max + 1e-9; v += paso) out.push(Number(v.toFixed(6)));
  return out;
}

/** Tramos de puntos seguidos con valor: un valor vacío corta la línea, no la lleva a cero. */
export function tramos(xs: [number, number | null][]): string[] {
  const out: string[] = [];
  let actual: string[] = [];
  for (const [x, y] of xs) {
    if (y == null) {
      if (actual.length) out.push(actual.join(' '));
      actual = [];
    } else actual.push(`${x.toFixed(1)},${y.toFixed(1)}`);
  }
  if (actual.length) out.push(actual.join(' '));
  return out;
}

/** Colores de las series: tokens de styles.css, con su versión oscura. */
export const COLORES_SERIE = 8;
export const colorSerie = (i: number) => `var(--serie-${i % COLORES_SERIE})`;

/**
 * 086:RF-123: las etiquetas de varios puntos sin taparse. Recibe la altura de cada punto (en px del viewBox) y devuelve
 * la de su etiqueta: en orden de altura, cada una al menos `separacion` por debajo de la anterior y dentro de
 * [`arriba`, `abajo`]; si no caben, se reparten por igual. Mismo orden que la entrada.
 */
export function separarEtiquetas(ys: number[], arriba: number, abajo: number, separacion: number): number[] {
  const orden = ys.map((y, i) => ({ y, i })).sort((a, b) => a.y - b.y || a.i - b.i);
  const salida = new Array<number>(ys.length);
  if (!orden.length) return salida;
  if ((orden.length - 1) * separacion > abajo - arriba) {
    const paso = orden.length > 1 ? (abajo - arriba) / (orden.length - 1) : 0;
    orden.forEach((o, k) => { salida[o.i] = arriba + k * paso; });
    return salida;
  }
  let previa = -Infinity;
  const puestas = orden.map((o) => { previa = Math.max(o.y, arriba, previa + separacion); return previa; });
  // Si la última se sale por abajo, se suben las de abajo lo justo (caben: se comprobó arriba).
  for (let k = puestas.length - 1; k >= 0; k--) {
    puestas[k] = Math.min(puestas[k], k === puestas.length - 1 ? abajo : puestas[k + 1] - separacion);
  }
  orden.forEach((o, k) => { salida[o.i] = puestas[k]; });
  return salida;
}
