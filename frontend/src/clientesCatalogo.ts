import type { DemandaLibro } from './types';

export interface EstadoCatalogoClientes {
  esCatalogo: boolean;
  activos: number;
  listoParaCruzar: boolean;
  motivo: string;
}

/** Estado operacional del libro heredado o de la nueva carpeta mensual. */
export function estadoCatalogoClientes(meta?: DemandaLibro): EstadoCatalogoClientes {
  const esCatalogo = meta?.source_kind === 'folder' && Array.isArray(meta.catalogo);
  if (!esCatalogo) return { esCatalogo: false, activos: 1, listoParaCruzar: true, motivo: '' };
  const activos = meta.catalogo?.filter((libro) => libro.activo).length ?? 0;
  if (!meta.vigente) {
    return { esCatalogo: true, activos, listoParaCruzar: false,
      motivo: 'Actualice el índice antes de cruzar.' };
  }
  if (activos !== 1) {
    return { esCatalogo: true, activos, listoParaCruzar: false,
      motivo: `Hay ${activos} meses activos; elija un mes antes de cruzar.` };
  }
  return { esCatalogo: true, activos, listoParaCruzar: true, motivo: '' };
}
