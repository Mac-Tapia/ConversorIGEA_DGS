/** 110: lo que decide la ventana «Enviar por correo», sin React, para probarlo aparte. */
import type { Adjuntable, CorreoPeticion, EstadoEnvio } from '../../api/correo';
import { SIN_CUENTA, type CuentaNube, type ProveedorNube } from '../../api/nube';
import { separarDirecciones } from '../../shared/direcciones';

export { SIN_CUENTA };

export interface CamposCorreo {
  /** «proveedor|correo» de la cuenta que envía. */
  cuenta: string;
  para: string;
  cc: string;
  cco: string;
  asunto: string;
  cuerpo: string;
  adjuntar: Adjuntable[];
}

type Tono = 'ok' | 'warn' | 'error' | 'muted' | 'info';

/** Por qué no se puede abrir la ventana, o `null` si hay una cuenta conectada (110:RF-1). */
export function motivoSinCuenta(cuentas: CuentaNube[] | null, error: string | null): string | null {
  if (!cuentas) return error ? `${SIN_CUENTA} (${error})` : SIN_CUENTA;
  if (!cuentas.some((c) => c.registrado)) return SIN_CUENTA;
  if (!cuentas.some((c) => c.conectada && c.cuenta)) return 'Conecte una cuenta en «Cuentas en la nube».';
  return null;
}

export interface CuentaDeCorreo { proveedor: ProveedorNube; cuenta: string; etiqueta: string;
  /** `puede_enviar` del servidor: `false` o `null` (sin saberlo) ofrecen pedir el permiso de envío. */
  puedeEnviar: boolean }

export function cuentasDeCorreo(cuentas: CuentaNube[] | null): CuentaDeCorreo[] {
  const salida: CuentaDeCorreo[] = [];
  for (const c of cuentas ?? []) {
    if (!c.conectada || !c.cuenta) continue;
    salida.push({ proveedor: c.nombre, cuenta: c.cuenta, puedeEnviar: c.puede_enviar === true,
      etiqueta: `${c.cuenta} (${c.nombre === 'google' ? 'Google' : 'Microsoft'})` });
  }
  return salida;
}

/** La cuenta elegida en la ventana («proveedor|correo»), si sigue conectada. */
export const cuentaElegida = (opciones: CuentaDeCorreo[], valor: string) =>
  opciones.find((o) => `${o.proveedor}|${o.cuenta}` === valor);

function lista(texto: string): string[] {
  const d = separarDirecciones(texto);
  if (d.invalidas.length) throw new Error(`Revise: ${d.invalidas.join(', ')}`);
  return d.validas;
}

/** El cuerpo de la vista previa con lo que hay en la ventana; un error dice qué falta en una frase. */
export function peticionVistaPrevia(c: CamposCorreo, ctx: { informe: string; proyecto?: string | null;
  escenario?: string | null }): CorreoPeticion {
  const [proveedor, cuenta] = c.cuenta.split('|', 2);
  if (!cuenta || (proveedor !== 'google' && proveedor !== 'microsoft')) throw new Error('Elija la cuenta que envía.');
  const para = lista(c.para);
  if (para.length === 0) throw new Error('Escriba al menos un destinatario.');
  return { informe: ctx.informe, proyecto: ctx.proyecto ?? null, escenario: ctx.escenario ?? null, proveedor, cuenta,
    para, cc: lista(c.cc), cco: lista(c.cco), asunto: c.asunto.trim(), cuerpo: c.cuerpo, adjuntar: c.adjuntar,
    origen: 'web' };
}

/** 110:RF-4: la vista previa solo vale para lo que se previsualizó; cualquier cambio en la ventana la anula. */
export const mismaPeticion = (a: CorreoPeticion | null, b: CorreoPeticion | null) =>
  Boolean(a && b) && JSON.stringify(a) === JSON.stringify(b);

const ESTADOS: Record<EstadoEnvio, { tono: Tono; texto: string }> = {
  reservado: { tono: 'info', texto: 'En cola' },
  enviando: { tono: 'info', texto: 'Enviando…' },
  aceptado: { tono: 'ok', texto: 'Enviado' },
  rechazado: { tono: 'error', texto: 'No salió' },
  desconocido: { tono: 'warn', texto: 'Sin confirmar: mírelo en «Enviados» de su cuenta' },
  cancelado: { tono: 'muted', texto: 'Cancelado' },
};

export const textoEstado = (estado: EstadoEnvio) => ESTADOS[estado] ?? { tono: 'muted' as Tono, texto: estado };
