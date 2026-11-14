import type { Health } from '../api/types';

export type ClaveBeta = 'asistente' | 'set_nueva' | 'pide' | 'confiabilidad';
type Edicion = Pick<Health, 'edicion'>;

/** 086:RF-16: qué edición es lo dice el servidor (`/api/health`). Desde el 2026-11-13 (usuario: «nada debería estar
 * apagado ni bloqueado») ninguna pantalla se oculta por la edición: solo se marcan las betas y se respeta la que se apague. */
export const esProducto = (h: Edicion): boolean => h.edicion.producto;

/** Una función en beta apagada no se ofrece. En desarrollo no hay betas: todo sigue visible. */
export const betaActiva = (h: Edicion, clave: ClaveBeta): boolean =>
  h.edicion.beta.find((b) => b.clave === clave)?.activa ?? true;

/** Lo que se dice en pantalla de una función en beta; nada en desarrollo. */
export const avisoBeta = (h: Edicion, clave: ClaveBeta): string | null =>
  h.edicion.beta.find((b) => b.clave === clave)?.aviso ?? null;
