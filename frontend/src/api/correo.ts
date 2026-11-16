/** 110: la API del envío de informes por correo.
 *
 * Los tipos son los del contrato generado (`esquema.ts`, desde el OpenAPI real de `web/correo_api.py`). La ventana pide
 * la vista previa (no envía nada), y «Confirmar y enviar» manda la firma que vio el operador: si el informe o un
 * adjunto cambió, el servidor responde 409 y pide revisarlo otra vez. El doble clic devuelve el recibo que ya había,
 * sin otro envío. Un envío cuyo resultado se desconoce lo resuelve el operador con «Llegó» o «No llegó».
 */
import type { components } from './esquema';
import { json, request } from './client';

type S = components['schemas'];

export type CorreoPeticion = S['CorreoVistaPreviaPeticion'];
export type CorreoVistaPrevia = S['CorreoVistaPrevia'];
export type CorreoEnvio = S['CorreoEnvio'];
export type CorreoConfirmacion = S['CorreoConfirmacion'];
export type CorreoHistorial = S['CorreoHistorial'];
export type Adjuntable = NonNullable<CorreoPeticion['adjuntar']>[number];
export type EstadoEnvio = CorreoEnvio['estado'];

const ruta = (id: string) => `/api/workspaces/${encodeURIComponent(id)}/correo`;
const hex = (texto: string, largo: number) => new RegExp(`^[0-9a-f]{${largo}}$`).test(texto);

/** Un identificador que no tiene la forma del servidor no llega a la red: se dice aquí, con su motivo. */
function comprobar(texto: string, largo: number, que: string): string {
  if (!hex(texto, largo)) throw new Error(`${que} no válido.`);
  return texto;
}

export const correo = {
  vistaPrevia: (id: string, body: CorreoPeticion) =>
    request<CorreoVistaPrevia>(`${ruta(id)}/vista-previa`, json('POST', body)),
  confirmar: (id: string, borrador: string, firma: string) =>
    request<CorreoConfirmacion>(`${ruta(id)}/${comprobar(borrador, 32, 'Borrador')}/confirmar`,
      json('POST', { firma: comprobar(firma, 64, 'Firma') } satisfies S['CorreoConfirmacionPeticion'])),
  envio: (id: string, clave: string) =>
    request<CorreoEnvio>(`${ruta(id)}/envios/${comprobar(clave, 64, 'Envío')}`),
  historial: (id: string, informe: string) =>
    request<CorreoHistorial>(`${ruta(id)}/historial?informe=${encodeURIComponent(informe)}`),
  resolver: (id: string, clave: string, llego: boolean) =>
    request<CorreoEnvio>(`${ruta(id)}/envios/${comprobar(clave, 64, 'Envío')}/resolver`,
      json('POST', { llego } satisfies S['CorreoResolucionPeticion'])),
};
