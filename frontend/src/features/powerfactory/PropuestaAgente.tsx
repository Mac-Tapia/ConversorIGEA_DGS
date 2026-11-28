import { useCallback, useEffect, useState } from 'react';
import { api } from '../../api/client';
import type { AgenteSombraEstado } from '../../api/types';
import { useApp } from '../../shared/context';
import { Ayuda } from '../../shared/ui';
import { TITULO_AGENTE, puedeDecidir, textoAcierta, textoEstado, textoMarcador, textoResultado } from './textosAgente';

/** 114:RF-7, RF-9, RF-11: lo que propone el agente MASAC junto a la regla actual, sin aplicar nada.
 *
 * Va junto a las obras automáticas porque compite con ellas: la regla actual es su escalera. Confirmar o deshacer
 * solo enseña al agente; las obras se aplican con los botones de siempre. */
export function PropuestaAgente({ project, feeders }: { project: string; feeders: string[] }) {
  const { ws, run, startJob, active, jobs } = useApp();
  const [estado, setEstado] = useState<AgenteSombraEstado | null>(null);
  const [decidiendo, setDecidiendo] = useState(false);
  // Cada propuesta terminada en esta sesión cambia lo registrado: se vuelve a leer.
  const hechas = Object.values(jobs).filter((j) => j.kind === 'agente_sombra' && j.status === 'done').length;
  const leer = useCallback(() => {
    if (!project) return;
    void run(() => api.agenteSombra(ws.id, project)).then((r) => { if (r) setEstado(r); });
  }, [run, ws.id, project]);
  useEffect(leer, [leer, hechas]);
  const ocupado = Boolean(active.asistente) || decidiendo;
  const decidir = async (id: string, accion: 'confirmar' | 'deshacer') => {
    setDecidiendo(true);
    try {
      if (await run(() => api.agenteSombraDecidir(ws.id, id, accion))) leer();
    } finally {
      setDecidiendo(false);
    }
  };
  const ultima = estado?.propuestas[0];
  return (
    <div className="card" aria-label={TITULO_AGENTE}>
      <h4>{TITULO_AGENTE}</h4>
      <Ayuda>Se calcula con la red guardada del proyecto, sin DIgSILENT. Confirmar o deshacer solo enseña al agente.</Ayuda>
      <div className="row">
        <button className="btn btn-sm" disabled={ocupado || !project}
          onClick={() => void startJob(() => api.agenteSombraPedir(ws.id, { project, feeders }))}>
          Pedir propuesta del agente</button>
        {estado && <span className="small muted">{textoMarcador(estado.aciertos)}</span>}
      </div>
      {ultima && (
        <>
          <p className="small"><strong>{textoAcierta(ultima.acierta)}</strong> Agente: {textoResultado(ultima.agente)} · Regla actual:{' '}
            {textoResultado(ultima.regla)}</p>
          {ultima.decisiones.length === 0 ? <p className="small muted">El agente no propone cambios.</p> : (
            <ul className="small">{ultima.decisiones.map((d) => (
              <li key={d.id}>{d.explicacion}{' '}
                {puedeDecidir(d) ? <>
                  <button type="button" className="btn btn-sm" disabled={ocupado}
                    onClick={() => void decidir(d.id, 'confirmar')}>Confirmar</button>{' '}
                  <button type="button" className="btn btn-sm" disabled={ocupado}
                    onClick={() => void decidir(d.id, 'deshacer')}>Deshacer</button>
                </> : <span className="muted">{textoEstado(d)}</span>}
              </li>))}</ul>)}
        </>
      )}
    </div>
  );
}
