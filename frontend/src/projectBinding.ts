import type { PfProject } from './types';

export interface EstadoVinculoProyecto {
  bloqueado: boolean;
  advertencias: number;
  elementos: number;
}

/** Separa impedimentos reales de cambios deliberados que solo requieren trazabilidad. */
export function estadoVinculoProyecto(project: PfProject | null): EstadoVinculoProyecto {
  const warnings = project?.binding_warnings ?? [];
  return {
    bloqueado: Boolean(project && (!project.binding || project.binding_blocked_reason)),
    advertencias: warnings.length,
    elementos: warnings.reduce((total, warning) => total + warning.elements.length, 0),
  };
}
