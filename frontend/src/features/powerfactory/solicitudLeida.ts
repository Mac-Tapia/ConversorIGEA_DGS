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


/** Lo que la web ya sabe de la carga elegida (017:RF-91). */
export interface DatosDeCarga {
  kw?: number | null;
  cliente?: string | null;
  utm_x?: number | null;
  utm_y?: number | null;
  set_nombre?: string | null;
  tension_kv?: number | null;
}

/**
 * 017:RF-91: la solicitud y el punto con lo que ya se escribió de la carga en «Una carga nueva» y lo
 * que se sabe de su alimentador; solo en los campos vacíos: lo escrito o leído de la carta no se pisa.
 * Con CA101 (2026-11-13) el operador había escrito TierraLarga, sus UTM y CA101 en 3.2, y el informe
 * le volvía a pedir cliente, ubicación, SET y tensión.
 */
export function propuestaDeCarga<S extends Record<string, string>, P extends Record<string, string>>(
  sol: S, punto: P, carga: DatosDeCarga | null | undefined,
): { sol: S; punto: P; cambia: boolean } {
  if (!carga) return { sol, punto, cambia: false };
  const texto = (v: string | number | null | undefined) => (v == null || v === '' ? '' : String(v));
  const utm = carga.utm_x != null && carga.utm_y != null
    ? `UTM ${Math.round(carga.utm_x)} E, ${Math.round(carga.utm_y)} N` : '';
  const deSol: Record<string, string> = {
    cliente: texto(carga.cliente), ubicacion: utm, potencia_kw: texto(carga.kw),
    set_nombre: texto(carga.set_nombre), tension_kv: texto(carga.tension_kv),
  };
  const dePunto: Record<string, string> = { utm_x: texto(carga.utm_x), utm_y: texto(carga.utm_y) };
  let cambia = false;
  const llenar = <T extends Record<string, string>>(base: T, de: Record<string, string>): T => {
    const out: Record<string, string> = { ...base };
    for (const [k, v] of Object.entries(de)) {
      if (k in out && v && !String(out[k] ?? '').trim()) { out[k] = v; cambia = true; }
    }
    return out as T;
  };
  return { sol: llenar(sol, deSol), punto: llenar(punto, dePunto), cambia };
}
