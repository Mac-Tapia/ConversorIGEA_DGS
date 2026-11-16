/**
 * 109:RF-21 a RF-24 (T19, SELECTOR-UNICO): un solo campo «Elegir archivo» por entrada, con su origen (el equipo siempre;
 * Google Drive u OneDrive si hay cuenta conectada), el filtro de tipo de esa entrada y guardar una salida en la carpeta
 * del equipo que elija el operador. Lógica pura: se prueba en node, sin navegador.
 */

export type Origen = 'equipo' | 'google' | 'microsoft';

export const NOMBRE_ORIGEN: Record<Origen, string> = { equipo: 'Equipo', google: 'Google Drive', microsoft: 'OneDrive' };

interface CuentaMinima { nombre: string; conectada?: boolean | null; cuenta?: string | null }

/** 109:RF-21: el equipo siempre; cada nube solo con su cuenta conectada (las nubes vienen apagadas). */
export function origenesDe(cuentas: CuentaMinima[] | null | undefined): Origen[] {
  const nubes = (cuentas ?? [])
    .filter((c) => c.conectada && c.cuenta && (c.nombre === 'google' || c.nombre === 'microsoft'))
    .map((c) => c.nombre as Origen);
  return ['equipo', ...(['google', 'microsoft'] as Origen[]).filter((o) => nubes.includes(o))];
}

const piezas = (accept?: string) => (accept ?? '').split(',').map((t) => t.trim().toLowerCase()).filter(Boolean);

/** 109:RF-23: ¿admite la entrada este fichero? Por extensión («.xlsx») o por tipo MIME («application/pdf», «image/*»). */
export function admite(nombre: string, tipo: string, accept?: string): boolean {
  const lista = piezas(accept);
  if (lista.length === 0) return true;
  const bajo = nombre.toLowerCase();
  const mime = (tipo || '').toLowerCase();
  return lista.some((t) => {
    if (t.startsWith('.')) return bajo.endsWith(t);
    if (t.endsWith('/*')) return Boolean(mime) && mime.startsWith(t.slice(0, -1));
    return Boolean(mime) && mime === t;
  });
}

/** Los tipos que admite la entrada, en palabras: «.xlsx o .csv». */
export function tiposEnPalabras(accept?: string): string {
  const ext = [...new Set(piezas(accept).filter((t) => t.startsWith('.')))];
  if (ext.length === 0) return piezas(accept).join(', ');
  return ext.length === 1 ? ext[0] : `${ext.slice(0, -1).join(', ')} o ${ext[ext.length - 1]}`;
}

/** 109:RF-23: separa lo que vale de lo que no, con el aviso que dice qué ficheros y qué tipos admite la entrada. */
export function separarPorTipo<F extends { name: string; type: string }>(ficheros: F[], accept?: string):
  { validos: F[]; aviso: string | null } {
  const validos = ficheros.filter((f) => admite(f.name, f.type, accept));
  const malos = ficheros.filter((f) => !validos.includes(f)).map((f) => `«${f.name}»`);
  if (malos.length === 0) return { validos, aviso: null };
  const verbo = malos.length === 1 ? 'no vale' : 'no valen';
  return { validos, aviso: `${malos.join(', ')} ${verbo} aquí: admite ${tiposEnPalabras(accept)}.` };
}

/** Lo que la ventana del navegador ofrece para guardar; en las pruebas se pasa uno simulado. */
export interface VentanaGuardar {
  showSaveFilePicker?: (opciones: { suggestedName: string }) => Promise<{
    createWritable: () => Promise<{ write: (d: Blob) => Promise<void>; close: () => Promise<void> }>;
  }>;
  document: { createElement: (tag: 'a') => { href: string; download: string; click: () => void; remove?: () => void };
    body: { appendChild: (n: unknown) => unknown } };
  URL: { createObjectURL: (b: Blob) => string; revokeObjectURL: (u: string) => void };
}

/**
 * 109:RF-24: guarda una salida en la carpeta del equipo que elija el operador. Con el diálogo de guardar del navegador
 * (Chromium) se elige carpeta y nombre; sin él, va a la descarga del navegador, que pregunta dónde si así está puesto.
 */
export async function guardarEnEquipo(datos: Blob, nombre: string, w: VentanaGuardar):
  Promise<'guardado' | 'descargado' | 'cancelado'> {
  if (typeof w.showSaveFilePicker === 'function') {
    try {
      const destino = await w.showSaveFilePicker({ suggestedName: nombre });
      const escritura = await destino.createWritable();
      await escritura.write(datos);
      await escritura.close();
      return 'guardado';
    } catch (e) {
      if (e instanceof Error && e.name === 'AbortError') return 'cancelado';
      throw e;
    }
  }
  const url = w.URL.createObjectURL(datos);
  try {
    const a = w.document.createElement('a');
    a.href = url;
    a.download = nombre;
    w.document.body.appendChild(a);
    a.click();
    a.remove?.();
  } finally {
    w.URL.revokeObjectURL(url);
  }
  return 'descargado';
}
