/**
 * 006:RF-48: las marcas del eje de tiempo de las curvas, del primer registro al último.
 *
 * Hasta el 2026-11-27 las marcas iban cada N días desde el primer registro y la última caía donde caía: con la medición
 * del 01/01/26 al 27/10/26 el eje terminaba en «09/09/26» y octubre, recién cargado, no tenía rótulo. Ahora, en tramos de
 * más de dos meses, hay una marca el día 1 de cada mes (o de cada pocos meses en tramos de años) y siempre una en el
 * último día con registros: cada histórico nuevo que se carga mueve el final del eje con él.
 */
export interface MarcaDeTiempo {
  t: number;
  texto: string;
}

const DIA_MS = 24 * 3600 * 1000;
const dos = (n: number) => String(n).padStart(2, '0');

/** «27/10/26»: el día, como el resto de la web (sin depender del idioma del navegador). */
export const textoDia = (d: Date) => `${dos(d.getDate())}/${dos(d.getMonth() + 1)}/${dos(d.getFullYear() % 100)}`;

/**
 * Las marcas de días (o de meses) entre ``t0`` y ``t1``: como mucho ``maximo`` marcas de paso, la del primer día si no
 * queda pegada a la primera de ellas (a menos de medio paso) y siempre la del último día.
 */
export function marcasDeDias(t0: number, t1: number, maximo = 10): MarcaDeTiempo[] {
  if (!(t1 > t0)) return [{ t: t0, texto: textoDia(new Date(t0)) }];
  const dias = (t1 - t0) / DIA_MS;
  const pasos: number[] = [];
  let pasoMs: number;
  if (dias > 62) {
    const a = new Date(t0);
    const b = new Date(t1);
    const meses = (b.getFullYear() - a.getFullYear()) * 12 + b.getMonth() - a.getMonth();
    const k = Math.max(1, Math.ceil(meses / maximo));
    const d = new Date(a.getFullYear(), a.getMonth(), 1);
    if (d.getTime() < t0) d.setMonth(d.getMonth() + 1);
    for (; d.getTime() <= t1; d.setMonth(d.getMonth() + k)) pasos.push(d.getTime());
    pasoMs = k * 30 * DIA_MS;
  } else {
    // Días: a medianoche cada N días enteros (repartidas a tiempo igual caían a media jornada).
    const paso = Math.max(1, Math.ceil(dias / 6));
    const d = new Date(t0);
    d.setHours(0, 0, 0, 0);
    if (d.getTime() < t0) d.setDate(d.getDate() + 1);
    for (; d.getTime() <= t1; d.setDate(d.getDate() + paso)) pasos.push(d.getTime());
    pasoMs = paso * DIA_MS;
  }
  const ts = [...pasos];
  if (!ts.length || ts[0] - t0 >= pasoMs / 2) ts.unshift(t0);
  // El último día siempre se rotula: es lo que se acaba de cargar. Si queda pegado a la marca anterior, la sustituye.
  if (ts.length > 1 && t1 - ts[ts.length - 1] < pasoMs / 2) ts.pop();
  if (textoDia(new Date(ts[ts.length - 1])) !== textoDia(new Date(t1))) ts.push(t1);
  return ts.map((t) => ({ t, texto: textoDia(new Date(t)) }));
}
