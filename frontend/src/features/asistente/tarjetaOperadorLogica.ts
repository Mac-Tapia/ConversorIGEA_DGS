import type { CorreoVistaPrevia } from '../../api/correo';
import type { ProveedorNube, ProveedorRegistrado } from '../../api/nube';

/** Spec 070, RF-79 a RF-81: las cinco tarjetas que el asistente deja en su panel. El asistente lee y prepara; enviar,
 * publicar, compartir, importar y conectar los hace el clic del operador, que el navegador manda por la ruta de
 * siempre. Lo que no es una de estas cinco, con su forma, no se pinta: el resultado de un trabajo no elige rutas. */
export type TipoTarjeta = 'enviar_informe' | 'publicar_nube' | 'compartir_nube' | 'importar_nube' | 'conectar_nube';

export interface Tarjeta {
  tipo: TipoTarjeta;
  proveedor: ProveedorNube | null;
  para: string[];
  previa?: CorreoVistaPrevia;
  salida?: string;
  proveedores?: ProveedorRegistrado[];
}

const TIPOS: ReadonlySet<string> = new Set<TipoTarjeta>(
  ['enviar_informe', 'publicar_nube', 'compartir_nube', 'importar_nube', 'conectar_nube']);
const PROVEEDORES: ReadonlySet<string> = new Set(['google', 'microsoft']);
const BORRADOR = /^[0-9a-f]{32}$/;
const FIRMA = /^[0-9a-f]{64}$/;
const DIRECCION = /^[^\s@<>"]+@[^\s@<>"]+\.[^\s@<>"]+$/;

const esObjeto = (x: unknown): x is Record<string, unknown> => typeof x === 'object' && x !== null && !Array.isArray(x);

/** La tarjeta del resultado de un trabajo del asistente, solo si es de su misma tarea y tiene la forma esperada. */
export function tarjetaDe(tarea: string | null | undefined, resultado: unknown): Tarjeta | null {
  if (!tarea || !TIPOS.has(tarea) || !esObjeto(resultado) || !esObjeto(resultado.tarjeta)) return null;
  const t = resultado.tarjeta;
  if (t.tipo !== tarea) return null;
  const proveedor = typeof t.proveedor === 'string' && PROVEEDORES.has(t.proveedor) ? t.proveedor as ProveedorNube : null;
  const para = Array.isArray(t.para) ? t.para.filter((d): d is string => typeof d === 'string' && DIRECCION.test(d)) : [];
  const tarjeta: Tarjeta = { tipo: tarea as TipoTarjeta, proveedor, para };
  if (tarea === 'enviar_informe') {
    const p = t.previa;
    if (!esObjeto(p) || typeof p.borrador !== 'string' || !BORRADOR.test(p.borrador)
        || typeof p.firma !== 'string' || !FIRMA.test(p.firma)) return null;
    tarjeta.previa = p as unknown as CorreoVistaPrevia;
  } else if (tarea === 'publicar_nube') {
    tarjeta.salida = typeof t.salida === 'string' && !t.salida.includes('..') ? t.salida : '';
  } else if (tarea === 'conectar_nube') {
    tarjeta.proveedores = Array.isArray(t.proveedores)
      ? t.proveedores.filter((p): p is ProveedorRegistrado => esObjeto(p) && PROVEEDORES.has(String(p.nombre)))
      : [];
  }
  return tarjeta;
}

/** Los proveedores que se ofrecen para conectar: el que nombró la orden, o los registrados en este equipo. */
export function proveedoresParaConectar(t: Tarjeta): ProveedorRegistrado[] {
  const registrados = (t.proveedores ?? []).filter((p) => p.registrado);
  return t.proveedor ? registrados.filter((p) => p.nombre === t.proveedor) : registrados;
}
