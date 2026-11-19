/**
 * 072:RF-45 (revisión de 1d, 18-11): el proyecto y los alimentadores elegidos se guardan en el espacio con PUT /options,
 * al momento en pantalla (optimista) y después con la respuesta del servidor. Cada respuesta se aplicaba aunque hubiera
 * otro envío más nuevo en vuelo: clic A, clic B, llega A y la pantalla vuelve a [A]; el clic C partía de [A] y B se
 * perdía aunque se había visto marcado. Y un fallo restauraba un estado viejo, también de otro espacio.
 *
 * Aquí solo la respuesta (o el fallo) del ÚLTIMO envío toca la pantalla, y solo si el espacio sigue siendo el mismo.
 * El servidor aplica los cambios en orden, así que la respuesta del último ya trae los anteriores.
 */
export interface ConOpciones {
  id: string;
  options?: object | null;
}

export function crearGuardado<W extends ConOpciones>(
  leer: () => W,
  fijar: (w: W) => void,
  enviar: (id: string, cambio: Record<string, unknown>) => Promise<W>,
  secuencia: { current: number },
): (cambio: Record<string, unknown>) => Promise<void> {
  return (cambio) => {
    const actual = leer();
    fijar({ ...actual, options: { ...(actual.options ?? {}), ...cambio } });
    const mio = ++secuencia.current;
    const vigente = () => mio === secuencia.current && leer().id === actual.id;
    return enviar(actual.id, cambio).then(
      (respuesta) => { if (vigente()) fijar(respuesta); },
      () => { if (vigente()) fijar(actual); },
    );
  };
}
