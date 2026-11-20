import type { CeldaMatriz, MatrizEstudios } from '../api/matrizEstudios';

/** El motor con el que trabaja un botón de estudio de la web. */
export type MotorMatriz = 'digsilent' | 'abierto' | 'pinn' | 'conversor';
export interface RefMatriz { estudio: string; motor: MotorMatriz }

/** Lo que se pinta junto a un estudio: nada si está validado o si el servidor no dio la matriz. */
export interface Marca { texto: string; tono: 'warn' | 'muted'; titulo: string; deshabilitado: boolean }

/** 100:RF-12: las pestañas de los módulos y el estudio y el motor que usan sus botones. */
const PESTANAS: Record<string, RefMatriz> = {
  vnr: { estudio: 'vnr', motor: 'conversor' },
  pit: { estudio: 'pit', motor: 'abierto' },
  vad: { estudio: 'vad', motor: 'conversor' },
  pide: { estudio: 'pide', motor: 'digsilent' },
  largo: { estudio: 'largo_plazo', motor: 'digsilent' },
};

export const refDePestana = (id: string): RefMatriz | null => PESTANAS[id] ?? null;

export function celdaDe(matriz: MatrizEstudios | null, { estudio, motor }: RefMatriz): CeldaMatriz | null {
  return matriz?.estudios.find((e) => e.clave === estudio)?.celdas.find((c) => c.motor === motor) ?? null;
}

const nombreMotor = (matriz: MatrizEstudios | null, motor: string) =>
  matriz?.motores.find((m) => m.clave === motor)?.nombre ?? motor;

/** 100:RF-12: «Sin validar» avisa y deja usarlo; «No disponible» lo apaga con su motivo; validado no dice nada. */
export function marcaDe(matriz: MatrizEstudios | null, ref: RefMatriz): Marca | null {
  const celda = celdaDe(matriz, ref);
  if (!celda || celda.estado === 'validado') return null;
  const motor = nombreMotor(matriz, ref.motor);
  if (celda.estado === 'no_disponible') {
    return { texto: 'No disponible', tono: 'muted', titulo: `No disponible con ${motor}: ${celda.motivo}`, deshabilitado: true };
  }
  return { texto: 'Sin validar', tono: 'warn', titulo: `Sin validar con ${motor}: revise el resultado antes de entregarlo.`,
    deshabilitado: false };
}
