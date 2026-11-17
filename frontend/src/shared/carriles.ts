/** Los carriles de trabajo del servidor (`web/jobs.LANES`) con el nombre que ve el operador.
 *
 * Uno por carril: la búsqueda de publicaciones va en «Red» justamente para no ocupar el «Motor», y la barra de trabajos
 * tiene que decirlo así. Un carril nuevo del servidor sin nombre aquí hace fallar `test/carriles.test.mjs`. */
export const NOMBRE_CARRIL: Record<string, string> = {
  engine: 'Motor',
  powerfactory: 'DIgSILENT',
  asistente: 'Asistente',
  control: 'Control',
  correo: 'Correo',
  red: 'Red',
};

/** El nombre de un carril; uno desconocido se enseña tal cual, nunca como otro carril. */
export function nombreCarril(lane: string): string {
  return NOMBRE_CARRIL[lane] ?? lane;
}
