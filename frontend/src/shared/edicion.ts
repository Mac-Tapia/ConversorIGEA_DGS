import type { Health } from '../api/types';

export type ClaveBeta = 'asistente' | 'set_nueva' | 'pide' | 'confiabilidad';
type Edicion = Pick<Health, 'edicion'>;

/** 086:RF-16: qué se enseña lo decide el servidor (`/api/health`); aquí solo se pregunta. */
export const esProducto = (h: Edicion): boolean => h.edicion.producto;

/** Una función en beta apagada no se ofrece. En desarrollo no hay betas: todo sigue visible. */
export const betaActiva = (h: Edicion, clave: ClaveBeta): boolean =>
  h.edicion.beta.find((b) => b.clave === clave)?.activa ?? true;

/** Lo que se dice en pantalla de una función en beta; nada en desarrollo. */
export const avisoBeta = (h: Edicion, clave: ClaveBeta): string | null =>
  h.edicion.beta.find((b) => b.clave === clave)?.aviso ?? null;
