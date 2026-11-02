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

/** Palabras que nombran un trámite o una forma de sociedad, no a un cliente. */
const GENERICAS = new Set(['AMPC', 'AMPLIACION', 'CARGA', 'NUEVA', 'SUMINISTRO', 'EMPRESA', 'SOCIEDAD', 'SERVICIO']);

function palabras(nombre: string): Set<string> {
  const limpio = nombre.normalize('NFD').replace(/[̀-ͯ]/g, '').toUpperCase();
  return new Set(limpio.split(/[^A-Z0-9]+/).filter((p) => p.length >= 4 && !GENERICAS.has(p)));
}

/**
 * 063:RF-49: el cliente de la solicitud no comparte ningún nombre con la carga elegida. T7 en SM218:
 * «AMPC INKA'S BERRIES S.A.C.» salió con el cliente, el NIS y la potencia de Minera Santa María. Una
 * carga con solo un código («SN1») no dice de quién es, y entonces no se afirma nada.
 */
export function clienteAjeno(carga: string, cliente: string): boolean {
  const deLaCarga = palabras(carga);
  const delCliente = palabras(cliente);
  if (!deLaCarga.size || !delCliente.size) return false;
  return ![...deLaCarga].some((p) => delCliente.has(p));
}

/** 063:RF-48: el formulario guardado es de una carga: elegir otra, o ninguna, no hereda su solicitud. */
export function esOtraCarga(previa: string, nueva: string): boolean {
  return previa !== '' && previa !== nueva;
}

/**
 * 063:RF-51: la potencia del campo es solo la propuesta de la carga, y lo que dice la carta manda. T7 en
 * SM218: la carga vale 1100 kW (el incremento) y la carta dice 900 a 2000 kW; quedaba «incremento de 200 kW».
 */
export function esPotenciaPropuesta(valor: string, kwCarga: number | null | undefined): boolean {
  return kwCarga != null && Number(valor) === kwCarga;
}

/** 063:RF-52: el incremento de la solicitud no es la potencia de la carga del modelo (tolerancia de 1 kW). */
export function incrementoNoCuadra(incremento: number | null, kwCarga: number | null | undefined): boolean {
  return incremento != null && kwCarga != null && Math.abs(incremento - kwCarga) > 1;
}

