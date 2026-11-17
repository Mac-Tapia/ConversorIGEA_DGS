import { createContext, useContext, type ComponentType } from 'react';
import type { CorreoVistaPrevia, EstadoEnvio } from '../api/correo';
import type { CuentaNube } from '../api/nube';

/**
 * Spec 070, RF-80 a RF-82 (002:RF-18, RF-19): lo que la tarjeta de operador del asistente usa de la nube y del correo.
 * Un feature no importa otro: la capa `app` compone y da aquí los componentes y la lógica de `features/nube` y de
 * `features/powerfactory`; el asistente solo conoce este contrato.
 */
export interface AccionesOperador {
  ElegirDeLaNube: ComponentType<{ cuentas: CuentaNube[] }>;
  PublicarExpediente: ComponentType<{ cuentas: CuentaNube[]; seleccion?: string[]; nombreInicial?: string;
    paraInicial?: string; boton?: string }>;
  VistaPrevia: ComponentType<{ previa: CorreoVistaPrevia; ocupado: boolean; onConfirmar: () => void }>;
  conectadas: (cuentas: CuentaNube[] | null) => CuentaNube[];
  textoEstado: (estado: EstadoEnvio) => { tono: 'ok' | 'warn' | 'error' | 'muted' | 'info'; texto: string };
}

export const AccionesOperadorCtx = createContext<AccionesOperador | null>(null);

export function useAccionesOperador(): AccionesOperador {
  const acciones = useContext(AccionesOperadorCtx);
  if (!acciones) throw new Error('la tarjeta de operador necesita sus acciones de la capa app (AccionesOperadorCtx)');
  return acciones;
}
