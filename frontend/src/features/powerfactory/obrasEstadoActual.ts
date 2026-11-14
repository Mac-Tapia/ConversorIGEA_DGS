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

/** Una carga nueva aplicada en los alimentadores marcados, leída del disco (072:RF-33). */
export interface CargaAplicadaEnDisco { sed: string; alimentador: string; sola: boolean }

/**
 * 086:RF-77: lo que dice el bloque de obras. Tras reiniciar la web el informe de cargas nuevas ya no está en la sesión y el
 * bloque decía «Sin cargas nuevas» con SECA001 aplicada en CA101 (2026-11-13): el operador no encontraba dónde proponer las
 * obras de la escalera. El servidor ya las evalúa con las cargas aplicadas en disco; aquí se dice y se nombran.
 */
export function textosObras(cargas: CargaAplicadaEnDisco[], feeders: string[]): {
  titulo: string; ayuda: string; boton: string;
} {
  const suyas = cargas.filter((c) => feeders.includes(c.alimentador));
  if (!suyas.length) {
    return {
      titulo: 'Obras para el estado actual',
      ayuda: 'Sin cargas nuevas, «Con proyecto» lleva obras solo si el estado calibrado viola límites: bancos, regulador, '
        + 'sección, terna o transferencia, de menor a mayor costo. El que cumple queda sin obras.',
      boton: 'Corregir el estado actual en «Con proyecto»',
    };
  }
  const nombres = suyas.map((c) => `${c.sed} (${c.alimentador}${c.sola ? '' : ', en bloque'})`).join(', ');
  return {
    titulo: 'Obras en «Con proyecto» con las cargas nuevas',
    ayuda: `Con las cargas nuevas ya aplicadas (${nombres}), la escalera prueba bancos, regulador, sección, terna y `
      + 'transferencia de menor a mayor costo, con hasta 3 alternativas por alimentador, y se queda con la más barata que '
      + 'cumple. Un alimentador que ya cumple queda sin obras.',
    boton: 'Proponer obras automáticamente',
  };
}

/**
 * 018:RF-19 ampliada: el proyecto y los alimentadores con que trabajan 4 y 5. Usuario (2026-11-13): en 4.2 un desplegable con
 * todos los proyectos de DIgSILENT; el elegido ya pasó por calibración y ajustes manuales, y se estudia, se planifica como
 * PIDE o a largo plazo tal cual, sin calibrarlo aquí. Sin elección, el del paso 1 con sus alimentadores marcados.
 */
export function proyectoDeEstudio(elegido: string, feedersElegidos: string[], paso1: string, marcados: string[]): {
  proyecto: string; feeders: string[]; propio: boolean;
} {
  if (elegido && elegido !== paso1) return { proyecto: elegido, feeders: feedersElegidos, propio: true };
  return { proyecto: paso1, feeders: marcados, propio: false };
}
