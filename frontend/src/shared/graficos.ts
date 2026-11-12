/** Piezas comunes de las gráficas SVG de la web: sin librería de gráficos, con los tokens de styles.css. */

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
