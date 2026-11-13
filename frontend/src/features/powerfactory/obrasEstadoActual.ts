// 086:RF-77: las obras del estado actual, sin cargas nuevas. Electro Oriente NJA202 (T32, 2026-11-12): calibrado a
// 0,568 p.u. en la fase A y con 14 % de pérdidas, la web solo ofrecía la escalera dentro del informe de cargas nuevas,
// y sin cargas no había informe: «Con proyecto» quedaba sin obras aunque la red violaba límites.

export interface EstadoParaObras {
  /** Hay un proyecto de DIgSILENT elegido. */
  proyecto: string | null;
  /** Los alimentadores marcados en el paso 2. */
  alimentadores: string[];
  /** El «Sin proyecto» de ese proyecto está calibrado. */
  calibrado: boolean;
  /** El proyecto del último informe de cargas nuevas, si lo hay. */
  proyectoDeCargas: string | null;
}

/** Se ofrece con el proyecto calibrado y alimentadores marcados, mientras no haya cargas nuevas integradas en él. */
export function ofrecerObrasEstadoActual(e: EstadoParaObras): boolean {
  return Boolean(e.proyecto) && e.alimentadores.length > 0 && e.calibrado && e.proyectoDeCargas !== e.proyecto;
}

/** El resultado de «Con proyecto» sin cargas nuevas: lo medido es el estado actual. */
export const RESUMEN_SIN_CARGAS = 'Sin cargas nuevas: obras para el estado actual, solo en los alimentadores que violan límites.';
