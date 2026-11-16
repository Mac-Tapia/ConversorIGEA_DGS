/** 111:RF-14: el protocolo con la página del plano, que vive en un `<iframe sandbox>` sin origen propio.
 *
 * La pestaña solo acepta mensajes de `iframe.contentWindow`, con el origen del marco y con un tipo de `SALIDA` y sus
 * campos; manda solo los de `ENTRADA`. Las dos listas son las de `pagina_plano.py` (la prueba las compara).
 *
 * El marco va con `sandbox="allow-scripts"`, sin `allow-same-origin`: su origen es opaco y el navegador lo da como
 * «null» en `event.origin`. La página envía a `window.location.origin` (la web), así que nadie más los recibe. Hacia la
 * página, un origen opaco solo admite `'*'` como destino: lo que se manda (códigos y capas) no es secreto, y la página
 * comprueba que viene del padre y con el origen de la web. */

/** Lo que la pestaña puede pedir a la página. */
export const ENTRADA = ['seleccionar', 'resaltar', 'capa', 'propuesta'] as const;
/** Lo que la página manda a la pestaña. */
export const SALIDA = ['listo', 'seleccionado'] as const;

export type TipoEntrada = (typeof ENTRADA)[number];
export type MensajeDelPlano =
  | { tipo: 'listo' }
  | { tipo: 'seleccionado'; clase: 'tramo' | 'barra' | 'sed' | 'maniobra'; codigo: string; alimentador?: string };

const CLASES = ['tramo', 'barra', 'sed', 'maniobra'] as const;
/** El origen con que llegan los mensajes de un marco con `sandbox` sin `allow-same-origin`. */
export const ORIGEN_DEL_MARCO = 'null';

/** El mensaje de la página, o `null` si viene de otra ventana o no cumple el esquema. */
export function leerMensaje(evento: { source: unknown; origin?: string; data: unknown }, marco: unknown): MensajeDelPlano | null {
  if (!marco || evento.source !== marco || evento.origin !== ORIGEN_DEL_MARCO) return null;
  const d = evento.data;
  if (!d || typeof d !== 'object') return null;
  const m = d as Record<string, unknown>;
  if (m.tipo === 'listo') return { tipo: 'listo' };
  if (m.tipo !== 'seleccionado' || typeof m.codigo !== 'string' || !m.codigo) return null;
  if (!CLASES.includes(m.clase as (typeof CLASES)[number])) return null;
  if (m.alimentador !== undefined && typeof m.alimentador !== 'string') return null;
  const salida: MensajeDelPlano = { tipo: 'seleccionado', clase: m.clase as (typeof CLASES)[number], codigo: m.codigo };
  if (typeof m.alimentador === 'string') salida.alimentador = m.alimentador;
  return salida;
}

/** Un mensaje para la página; un tipo fuera de `ENTRADA` es un error de programación. */
export function mensajeAlPlano(tipo: TipoEntrada, campos: Record<string, unknown>): Record<string, unknown> {
  if (!ENTRADA.includes(tipo)) throw new Error(`Mensaje no admitido por el plano: ${String(tipo)}`);
  return { tipo, ...campos };
}
