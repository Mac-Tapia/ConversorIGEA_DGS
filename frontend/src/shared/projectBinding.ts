import type { PfProject } from '../api/types';

export interface EstadoVinculoProyecto {
  bloqueado: boolean;
  advertencias: number;
  elementos: number;
}

/** Separa impedimentos reales de cambios deliberados que solo requieren trazabilidad. */
export function estadoVinculoProyecto(project: PfProject | null): EstadoVinculoProyecto {
  const warnings = project?.binding_warnings ?? [];
  return {
    // 018:RF-19, regla del usuario (2026-11-13): se calibra cualquier proyecto de DIgSILENT, convertido o no por
    // el conversor. El vínculo con la conversión ya no bloquea nada: su falta es un aviso (textoCausaVinculo).
    bloqueado: false,
    advertencias: warnings.length,
    elementos: warnings.reduce((total, warning) => total + warning.elements.length, 0),
  };
}

/**
 * Spec 018, RF-11: cómo usar la ejecución fuente con la que se aceptó el proyecto.
 * Sin fuente activa se usa sola, porque el espacio no tiene nada que perder (CA101,
 * 2026-10-15: un espacio nuevo dejaba bloqueado un proyecto ya verificado); con otra
 * fuente activa lo decide el operador.
 */
export function usoDeLaFuente(project: PfProject | null): 'automatico' | 'boton' | null {
  if (!project?.binding_fuente_disponible) return null;
  if (project.binding_blocked_code === 'PROJECT_BINDING_NO_ACTIVE_SOURCE') return 'automatico';
  if (project.binding_blocked_code === 'PROJECT_BINDING_SOURCE_MISMATCH') return 'boton';
  return null;
}

/**
 * Texto para cada causa de PROJECT_BINDING_*: el código solo no dice qué hacer. El vínculo
 * se comparte entre espacios (spec 018), así que «sin vínculo» ya no es «aceptado en otro
 * espacio», sino «nunca aceptado desde esta web».
 */
const CAUSA_VINCULO: Record<string, string> = {
  PROJECT_BINDING_MISSING:
    'Este proyecto no tiene vínculo con una conversión de esta web: se calibra y se estudia con los datos del propio '
    + 'proyecto de DIgSILENT.',
  PROJECT_BINDING_NO_ACTIVE_SOURCE:
    'Este espacio no tiene fuente cargada: se usa el vínculo guardado del proyecto y los datos de DIgSILENT. Para '
    + 'comprobarlo contra la fuente, cargue y convierta la misma, con las mismas opciones.',
  PROJECT_BINDING_SOURCE_MISMATCH:
    'La fuente activa de este espacio no es la que se usó al aceptar el proyecto: se trabaja con el vínculo guardado y los datos de DIgSILENT.',
  PROJECT_BINDING_SOURCE_UNAVAILABLE:
    'La ejecución con la que se aceptó el proyecto no está en esta carpeta de datos: se trabaja con el vínculo guardado y los datos de DIgSILENT.',
  PROJECT_BINDING_FEEDER_MISMATCH:
    'Los alimentadores del proyecto en DIgSILENT ya no son los que se aceptaron. Vuelva a leer los proyectos; si siguen distintos, reimporte.',
  PROJECT_BINDING_PROJECT_MISMATCH:
    'El proyecto ya no aparece en la carpeta de DIgSILENT. Vuelva a leer los proyectos.',
  PROJECT_BINDING_NATIVE_UNREADABLE:
    'No se pudo leer el proyecto en DIgSILENT. Ciérrelo si está abierto en otra sesión y vuelva a leer los proyectos.',
  PROJECT_BINDING_FOLDER_MISMATCH:
    'El vínculo de este proyecto es de otra carpeta de DIgSILENT. Revise la carpeta del perfil de empresa.',
  PROJECT_BINDING_REGISTRY_UNREADABLE:
    'El registro de vínculos compartido (output/web/vinculos_pf.json) no se puede leer. No se bloquea en silencio: revise o restaure el fichero.',
  PROJECT_BINDING_RECORD_MISMATCH:
    'El vínculo guardado de este proyecto se modificó después de aceptarlo. Reimporte el proyecto para aceptarlo de nuevo.',
};

export function textoCausaVinculo(project: PfProject): string {
  return CAUSA_VINCULO[project.binding_blocked_code ?? ''] ?? project.binding_blocked_reason
    ?? 'No se puede usar este proyecto en este espacio de trabajo.';
}
