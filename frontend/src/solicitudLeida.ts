/** Lo que se lee de los PDF del solicitante, uno cada vez, con su documento (spec 063). */
export interface Leido {
  valor: string;
  fichero: string;
}

/**
 * 063:RF-19, RF-20: lo leído antes se conserva y lo de otro documento se añade. El bloque de 4.4
 * lee un PDF por vez: sustituir la lista dejaba siempre una sola fecha y un solo alimentador, y
 * releer un documento repetía sus filas.
 */
export function acumularLeidos(
  previos: Leido[], fichero: string,
  nuevos: { valor: string | number; fichero: string }[] | undefined,
): Leido[] {
  return [
    ...previos.filter((x) => x.fichero !== fichero),
    ...(nuevos ?? []).map((x) => ({ valor: String(x.valor), fichero: x.fichero })),
  ];
}

/** 063:RF-19: los alimentadores de los PDF que no son el de la carga elegida. */
export function alimentadoresDistintos(leidos: Leido[], alimentador: string | null | undefined): Leido[] {
  if (!alimentador) return [];
  const propio = alimentador.trim().toUpperCase();
  return leidos.filter((x) => x.valor.trim().toUpperCase() !== propio);
}
