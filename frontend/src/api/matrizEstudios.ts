/** 100:RF-8, RF-10: la matriz estudio × motor del servidor (`GET /api/estudios/matriz`).
 * Los tipos repiten `MatrizEstudiosRespuesta` del contrato hasta que `esquema.ts` se regenere con ella. */
import { request } from './client';

export type EstadoMatriz = 'validado' | 'sin_validar' | 'no_disponible';
export interface CeldaMatriz {
  motor: string; estado: EstadoMatriz; motivo: string;
  evidencia: { spec: string; estado: string | null }[];
}
export interface EstudioMatriz { clave: string; nombre: string; celdas: CeldaMatriz[] }
export interface MatrizEstudios {
  /** De dónde salen los estados: specs/ del repositorio, el recurso del programa instalado o ninguno (100:RF-13). */
  origen: 'specs' | 'recurso' | 'ninguno';
  motores: { clave: string; nombre: string }[]; estudios: EstudioMatriz[];
}

export const matrizEstudios = {
  leer: () => request<MatrizEstudios>('/api/estudios/matriz'),
};
