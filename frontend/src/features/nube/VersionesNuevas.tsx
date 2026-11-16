import { useCallback, useEffect, useRef, useState } from 'react';
import { nube, type VinculoNube } from '../../api/nube';
import { useApp } from '../../shared/context';
import { fmtBytes } from '../../shared/formato';
import { Modal, Pill, useConfirm } from '../../shared/ui';
import { comparacionDe, estadoVinculo, nombreDestino } from './logica';

const TERMINADO = new Set(['done', 'failed', 'cancelled', 'parcial', 'interrumpido', 'no_converge']);
const DE_LA_NUBE = new Set(['nube_importar', 'nube_versiones', 'nube_traer']);

/** 109:RF-7, RF-8, RF-17: los ficheros vinculados, su estado y, si hay versión nueva, la comparación. */
export function ListaVinculos({ vinculos, ocupado, onTraer, onAceptar, etiquetas = {} }: {
  vinculos: VinculoNube[];
  ocupado: boolean;
  onTraer: (vid: string) => void;
  onAceptar: (vid: string) => void;
  etiquetas?: Record<string, string>;
}) {
  if (vinculos.length === 0) return <p className="muted">Aún no hay ficheros importados de la nube.</p>;
  return (
    <ul className="stack">
      {vinculos.map((v) => {
        const e = estadoVinculo(v);
        const c = comparacionDe(v);
        return (
          <li key={v.id} className="stack">
            <div className="row">
              <strong>{v.nombre_remoto}</strong>
              <span className="muted small">{`→ ${nombreDestino(v, etiquetas)}`}</span>
              <Pill tone={e.tono}>{e.texto}</Pill>
            </div>
            {v.estado === 'sin_comprobar' && v.motivo && <small className="muted">{v.motivo}</small>}
            {v.estado === 'nueva' && !v.candidata && (
              <div><button className="btn btn-sm" disabled={ocupado} onClick={() => onTraer(v.id)}>Traer y comparar</button></div>
            )}
            {v.candidata && c && (
              <div className="stack">
                <small>{c.iguales ? 'Mismo contenido que la copia en uso.'
                  : c.tamanoAnterior !== null && c.tamanoNuevo !== null
                    ? `Tamaño: ${fmtBytes(c.tamanoAnterior)} → ${fmtBytes(c.tamanoNuevo)}` : 'Contenido distinto.'}</small>
                {c.lineas && <small>{`Líneas: +${c.lineas.anadidas} / −${c.lineas.quitadas}`}</small>}
                <small className="muted">Lo ya calculado con la copia anterior no cambia.</small>
                <div><button className="btn btn-sm btn-primary" disabled={ocupado} onClick={() => onAceptar(v.id)}>
                  Usar la versión nueva</button></div>
              </div>
            )}
          </li>
        );
      })}
    </ul>
  );
}

/** El botón «Versiones» (con cuántas nuevas hay) y su ventana. */
export function VersionesNuevas() {
  const { ws, health, jobs, active, startJob, refresh } = useApp();
  const confirmar = useConfirmar();
  const [vinculos, setVinculos] = useState<VinculoNube[]>([]);
  const [abierto, setAbierto] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const vistos = useRef(new Set<string>());
  const leer = useCallback(async () => {
    try {
      setVinculos((await nube.vinculos(ws.id)).vinculos);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, [ws.id]);
  useEffect(() => { void leer(); }, [leer]);
  // Al terminar una importación, una comprobación o una descarga de la nube, se vuelve a leer (sin sondeo).
  useEffect(() => {
    for (const j of Object.values(jobs)) {
      if (j.workspace_id === ws.id && DE_LA_NUBE.has(j.kind) && TERMINADO.has(j.status) && !vistos.current.has(j.id)) {
        vistos.current.add(j.id);
        void leer();
      }
    }
  }, [jobs, ws.id, leer]);

  const ocupado = Boolean(active.engine);
  const nuevas = vinculos.filter((v) => v.estado === 'nueva').length;
  const etiquetas = Object.fromEntries(Object.entries(health.slots).map(([k, s]) => [k, s.etiqueta.split(' —')[0]]));
  const aceptar = async (vid: string) => {
    if (!await confirmar()) return;
    try {
      await nube.aceptar(ws.id, vid);
      await Promise.all([leer(), refresh()]);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  return (
    <>
      <button className="btn btn-sm" onClick={() => setAbierto(true)}>
        {nuevas > 0 ? `Versiones (${nuevas} nueva${nuevas > 1 ? 's' : ''})` : 'Versiones'}</button>
      {abierto && (
        <Modal title="Versiones en la nube" onClose={() => setAbierto(false)} actions={
          <button className="btn" disabled={ocupado || vinculos.length === 0}
            onClick={() => void startJob(() => nube.versiones(ws.id))}>Comprobar ahora</button>}>
          <ListaVinculos vinculos={vinculos} ocupado={ocupado} etiquetas={etiquetas}
            onTraer={(vid) => void startJob(() => nube.traer(ws.id, vid))} onAceptar={(vid) => void aceptar(vid)} />
          <div aria-live="polite">{error && <p className="alert alert-error" role="alert">{error}</p>}</div>
        </Modal>
      )}
    </>
  );
}

function useConfirmar() {
  const confirm = useConfirm();
  return () => confirm('Usar la versión nueva', <p>Las entradas pasan a la versión nueva. La anterior se conserva.</p>, 'Usar');
}
