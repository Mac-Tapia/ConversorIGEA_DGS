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
