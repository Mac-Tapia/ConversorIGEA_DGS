import type { AccionSet, CuerpoSet } from '../../api/types';
/** Formulario de la operación de una SET existente y el cuerpo que manda al servidor (063:RF-36). */

export interface FormularioSet {
  accion: AccionSet;
  verificarFlujos: boolean;
  sincronizarCargas: boolean;
  conciliarFases: boolean;
  reabrir: boolean;
  desactivar: string;
  cambios: string;
  salidas: string;
  ajustes: string;
}

export const FORMULARIO_SET: FormularioSet = {
  accion: 'diagnostico', verificarFlujos: false, sincronizarCargas: false, conciliarFases: false, reabrir: true,
  desactivar: '', cambios: '', salidas: '', ajustes: '',
};


function lista(texto: string, campo: string): { valor: Record<string, unknown>[]; error?: string } {
  if (!texto.trim()) return { valor: [] };
  try {
    const valor = JSON.parse(texto);
    if (Array.isArray(valor) && valor.every((x) => x && typeof x === 'object' && !Array.isArray(x))) return { valor };
  } catch {
    // El mensaje es el mismo: el operador corrige el texto del campo.
  }
  return { valor: [], error: `${campo} tiene que ser una lista JSON de objetos.` };
}

/**
 * El cuerpo de la orden, o por qué no se puede mandar. El servidor vuelve a validarlo; aquí se evita
 * un trabajo de DIgSILENT que fallaría por un JSON mal escrito o sin alimentadores.
 */
export function cuerpoOperacionSet(
  project: string, feeders: string[], f: FormularioSet,
): { cuerpo?: CuerpoSet; error?: string } {
  if (!project || !feeders.length) return { error: 'Elija el proyecto y sus alimentadores.' };
  if (f.verificarFlujos && f.accion !== 'diagnostico') return { error: 'Verificar los flujos solo es parte del diagnóstico.' };
  const cambios = lista(f.cambios, 'Cambios');
  if (cambios.error) return { error: cambios.error };
  const salidas = lista(f.salidas, 'Salidas');
  if (salidas.error) return { error: salidas.error };
  let ajustes: Record<string, number> = {};
  if (f.ajustes.trim()) {
    try {
      ajustes = JSON.parse(f.ajustes);
    } catch {
      return { error: 'Los ajustes del flujo tienen que ser un objeto JSON, como {"iopt_at": 1}.' };
    }
    if (!ajustes || typeof ajustes !== 'object' || Array.isArray(ajustes)
      || !Object.values(ajustes).every((v) => Number.isInteger(v))) {
      return { error: 'Los ajustes del flujo tienen que ser un objeto JSON, como {"iopt_at": 1}.' };
    }
  }
  if (f.accion !== 'diagnostico' && !cambios.valor.length && !salidas.valor.length && !f.desactivar.trim()
    && !f.sincronizarCargas && !f.conciliarFases && !Object.keys(ajustes).length) {
    return { error: 'Evaluar o aplicar necesita al menos un cambio, una salida o un ajuste.' };
  }
  return {
    cuerpo: {
      project, feeders, accion: f.accion, verificar_flujos: f.verificarFlujos,
      sincronizar_cargas: f.sincronizarCargas, conciliar_fases: f.conciliarFases, reabrir: f.reabrir,
      desactivar_variaciones: f.desactivar.split(',').map((x) => x.trim()).filter(Boolean),
      cambios: cambios.valor, salidas: salidas.valor, ajustes_flujo: ajustes,
    },
  };
}
