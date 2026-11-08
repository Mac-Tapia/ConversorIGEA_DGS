import { useEffect, useState } from 'react';
import { useApp } from '../../shared/context';
import { equipoApi } from './estadoEquipoAsistente';
import type { EstadoEquipo } from './estadoEquipoAsistente';

/** 065/047: roles, permisos y revisión supervisada; usa eventos de trabajos existentes. */
export function EquipoAsistente({ planId }: { planId?: string }) {
  const { ws, run, startJob, active, jobs } = useApp();
  const [abierto, setAbierto] = useState(false);
  const [estado, setEstado] = useState<EstadoEquipo | null>(null);
  const [iniciando, setIniciando] = useState(false);
  const cambios = Object.values(jobs).filter(j => j.workspace_id === ws.id &&
    (j.kind.startsWith('asistente') || j.kind === 'agente_proyecto'))
    .map(j => `${j.id}:${j.status}`).sort().join('|');
  useEffect(() => {
    if (!abierto) return;
    let vigente = true;
    void run(() => equipoApi.estado(ws.id)).then(r => { if (vigente && r) setEstado(r); });
    return () => { vigente = false; };
  }, [abierto, ws.id, planId, cambios, run]);
  const revisar = async () => {
    if (!planId || iniciando) return;
    setIniciando(true);
    try { await startJob(() => equipoApi.revisar(ws.id, planId)); }
    finally { setIniciando(false); }
  };
  return <details onToggle={e => setAbierto((e.target as HTMLDetailsElement).open)}>
    <summary className="small">Equipo del asistente y permisos efectivos</summary>
    <div className="stack small">
      <p>El operador confirma las escrituras. Fuentes, física, coste y riesgo revisan la propuesta;
        sus dictámenes conservan las citas y requieren evidencia del mismo proyecto y fuente.</p>
      {planId && <button className="btn" disabled={iniciando || Boolean(active.asistente)} onClick={() => void revisar()}>
        {iniciando ? 'Preparando revisión…' : 'Revisar esta propuesta por roles'}</button>}
      {estado && <>
        <p>{estado.roles.map(r => `${r.rol}: ${r.puede_ejecutar ? 'ejecuta con permiso del plan' : 'solo revisa'}`).join(' · ')}</p>
        {estado.error_evidencias && <p className="alert alert-warn">{estado.error_evidencias}</p>}
        <p>{estado.evidencias.length > 0
          ? `Evidencia custodiada: ${estado.evidencias.slice(0, 5).map(e => `${e.titulo ?? e.etiqueta} (${e.proyecto ?? 'sin proyecto'})`).join(' · ')}.`
          : 'Aún no hay evidencia en este espacio: los informes y estudios que terminan bien quedan custodiados solos.'}</p>
        {estado.permisos.length > 0 && <table className="small">
          <thead><tr><th>Herramienta</th><th>Responsable</th><th>Permiso</th><th>Proyecto</th></tr></thead>
          <tbody>{estado.permisos.filter(p => !planId || p.plan === planId).map(p => <tr key={p.plan}>
            <td>{p.herramienta || 'Sin tarea'}</td><td>{p.responsable}</td>
            <td>{p.permiso_efectivo ? 'Concedido para este plan' : p.motivo}</td>
            <td>{p.alcance.proyecto || 'Sin proyecto nativo'}</td>
          </tr>)}</tbody>
        </table>}
        {estado.revisiones.filter(r => r.tipo === 'resultado' && (!planId || r.plan === planId)).slice(-3).map((r, i) =>
          <p key={i} className={r.aprobada ? 'small' : 'alert alert-warn'}>{r.motivo}</p>)}
        <details><summary>Herramientas disponibles en el catálogo</summary>
          <ul>{estado.herramientas.map(h => <li key={h.herramienta}>{h.herramienta}: {h.escribe ? 'requiere confirmación' : 'lectura'}</li>)}</ul>
        </details>
      </>}
      <p className="muted">La revisión no autoriza la ejecución ni acredita aceptación eléctrica o calidad del modelo.</p>
    </div>
  </details>;
}
