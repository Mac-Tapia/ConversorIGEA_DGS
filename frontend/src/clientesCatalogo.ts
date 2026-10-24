import type { DemandaLibro } from './types';

export interface MesClientes {
  mes: string;
  libro: string;
}

export interface EstadoCatalogoClientes {
  esCatalogo: boolean;
  activos: number;
  /** Spec 013, RF-7: un libro por mes (el ganador de RF-5), en orden de calendario. */
  meses: MesClientes[];
  listoParaCruzar: boolean;
  motivo: string;
}

/**
 * Estado operacional del libro heredado o de la carpeta mensual. Con varios meses el
 * operador elige uno (spec 013, RF-8 a RF-12): nunca se toma uno por su cuenta.
 */
export function estadoCatalogoClientes(meta?: DemandaLibro, periodo = '', anio = ''): EstadoCatalogoClientes {
  const esCatalogo = meta?.source_kind === 'folder' && Array.isArray(meta.catalogo);
  if (!esCatalogo) return { esCatalogo: false, activos: 1, meses: [], listoParaCruzar: true, motivo: '' };
  // Spec 025, RF-23: con un año elegido, solo sus meses; los de otro año no se mezclan.
  const activos = meta.catalogo?.filter((libro) => libro.activo
    && (!anio || (libro.mes ?? '').startsWith(`${anio}-`))) ?? [];
  const meses = activos.filter((libro) => libro.mes)
    .map((libro) => ({ mes: libro.mes as string, libro: libro.nombre }))
    .sort((a, b) => a.mes.localeCompare(b.mes));
  const base = { esCatalogo: true, activos: activos.length, meses };
  if (!meta.vigente) {
    return { ...base, listoParaCruzar: false, motivo: 'Actualice el índice antes de cruzar.' };
  }
  if (activos.length === 0) {
    return { ...base, listoParaCruzar: false,
      motivo: 'Ningún libro de la carpeta tiene mes: actualice el índice o revise sus nombres.' };
  }
  if (/^\d{4}$/.test(periodo)) {
    // Spec 025, RF-10: con el año entero, el ajuste cruza cada alimentador con el libro del
    // mes de su propia máxima; aquí no hay un solo mes que cruzar.
    return { ...base, listoParaCruzar: false,
      motivo: `Con todo ${periodo}, el ajuste (2.4) cruza cada alimentador con los clientes del mes de su máxima; para ver aquí un cruce, elija un mes.` };
  }
  if (activos.length === 1) return { ...base, listoParaCruzar: true, motivo: '' };
  if (!meses.some((m) => m.mes === periodo)) {
    return { ...base, listoParaCruzar: false,
      motivo: `Hay ${activos.length} meses en la carpeta; elija el mes de los clientes antes de cruzar.` };
  }
  return { ...base, listoParaCruzar: true, motivo: '' };
}
