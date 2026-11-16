/** Direcciones de correo escritas por el operador: la nube (109:RF-10) y el correo (110:RF-1) las leen igual.
 *
 * Solo separa y limpia lo que se escribió; quien decide si una dirección vale es el servidor, que la vuelve a comprobar.
 */
const FORMA = /^[^\s@<>,;]+@[^\s@<>,;]+\.[^\s@<>,;]+$/;

export function separarDirecciones(texto: string): { validas: string[]; invalidas: string[] } {
  const vistas = new Set<string>();
  const validas: string[] = [];
  const invalidas: string[] = [];
  for (const trozo of texto.split(/[\s,;]+/)) {
    const d = trozo.trim();
    if (!d) continue;
    if (!FORMA.test(d)) { invalidas.push(d); continue; }
    if (vistas.has(d.toLowerCase())) continue;
    vistas.add(d.toLowerCase());
    validas.push(d);
  }
  return { validas, invalidas };
}
