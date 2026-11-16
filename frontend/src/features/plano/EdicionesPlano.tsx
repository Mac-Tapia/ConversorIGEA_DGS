import type { VariacionPlano } from '../../api/plano';
import { TEXTOS } from './textosPlano';

function resumen(e: Record<string, unknown>): string {
  const codigo = String(e.codigo ?? e.tramo ?? '');
  switch (e.tipo) {
    case 'maniobra': return `${codigo}: ${String(e.antes ?? '')} → ${String(e.estado ?? '')}`;
    case 'tramo': return `${TEXTOS.tramoNuevo} ${codigo}: ${String(e.desde ?? '')} → ${String(e.hasta ?? '')}`;
    case 'ajuste': return `${codigo}: extremo a ${String(e.nodo ?? '')}`;
    case 'equipo': return `${String(e.clase ?? '')} ${codigo} en ${String(e.tramo ?? '')}`;
    default: return codigo;
  }
}

/** 111:RF-9: las ediciones de la variación, con deshacer y rehacer mientras no esté confirmada. */
export function EdicionesPlano({ variacion, ocupado, onDeshacer, onRehacer, onConfirmar }: {
  variacion: VariacionPlano;
  ocupado: boolean;
  onDeshacer: () => void;
  onRehacer: () => void;
  onConfirmar: () => void;
}) {
  const abierta = variacion.estado === 'abierta';
  return (
    <div>
      <h4>{TEXTOS.ediciones}</h4>
      {variacion.ediciones.length === 0
        ? <p className="muted">{TEXTOS.sinEdiciones}</p>
        : <ol className="lista-compacta">{variacion.ediciones.map((e, i) => <li key={i}>{resumen(e as Record<string, unknown>)}</li>)}</ol>}
      {!abierta && <p className="muted">{TEXTOS.confirmada}</p>}
      <div className="toolbar">
        <button type="button" onClick={onDeshacer} disabled={!abierta || ocupado || variacion.ediciones.length === 0}>{TEXTOS.deshacer}</button>
        <button type="button" onClick={onRehacer} disabled={!abierta || ocupado || variacion.deshechas.length === 0}>{TEXTOS.rehacer}</button>
        <button type="button" onClick={onConfirmar} disabled={!abierta || ocupado}>{TEXTOS.confirmar}</button>
      </div>
    </div>
  );
}
