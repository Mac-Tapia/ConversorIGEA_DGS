// 114:RF-7, RF-11: los textos del bloque del agente MASAC en sombra, aparte para probarlos sin React.
import type { DecisionAgente, PropuestaAgente } from '../../api/types';
import { cuenta, fmtNum } from '../../shared/formato';

export const TITULO_AGENTE = 'Propuesta del agente (en sombra, no se aplica)';

/** El marcador frente a la regla actual (la escalera de obras), con todas las propuestas del proyecto. */
export function textoMarcador(a: { agente: number; regla: number; empate: number }): string {
  const total = a.agente + a.regla + a.empate;
  if (!total) return 'Aún no hay propuestas en este proyecto.';
  return `Frente a la regla actual: acierta el agente ${cuenta(a.agente, 'vez', 'veces')}, la regla `
    + `${cuenta(a.regla, 'vez', 'veces')}, ${cuenta(a.empate, 'empate', 'empates')} (${cuenta(total, 'propuesta', 'propuestas')}).`;
}

export function textoAcierta(acierta: PropuestaAgente['acierta']): string {
  return acierta === 'agente' ? 'Esta vez acierta el agente.'
    : acierta === 'regla' ? 'Esta vez acierta la regla actual.' : 'Esta vez empatan.';
}

/** Cómo queda la red con una propuesta: lo que se compara para decir quién acierta. */
export function textoResultado(r: PropuestaAgente['agente']): string {
  const norma = r.en_norma ? 'en norma' : 'fuera de norma';
  const obras = r.costo ? `obras ${fmtNum(r.costo)}` : 'sin obras';
  const maniobras = r.costo_maniobras ? `, maniobras ${fmtNum(r.costo_maniobras)}` : '';
  const minima = r.vm_min != null ? `, mínima ${fmtNum(r.vm_min, 3)} p.u.` : '';
  return `${norma}, ${obras}${maniobras}${minima}`;
}

/** Solo una propuesta sin decidir se confirma o se deshace: después queda como la dejó el operador. */
export const puedeDecidir = (d: DecisionAgente) => d.estado === 'propuesta';

export function textoEstado(d: DecisionAgente): string {
  return d.estado === 'confirmada' ? 'Confirmada' : d.estado === 'deshecha' ? 'Deshecha' : '';
}
