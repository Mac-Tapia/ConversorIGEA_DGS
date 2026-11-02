import { useEffect, useMemo, useState } from 'react';
import { api } from '../api';
import { useApp } from '../context';
import type { MonitorAgenteEstado } from '../types';

const estados: Record<string, string> = {
  queued: 'En cola', running: 'Ejecutando', done: 'Ejecución terminada',
  failed: 'Falló', cancelled: 'Cancelado', hecha: 'Hecha', omitida: 'Omitida', pendiente: 'Pendiente',
};

/** 061: supervisión de las operaciones existentes; suscripción mediante jobs/WebSocket. */
export function MonitorAgente() {
  const { ws, jobs, run } = useApp();
  const [vista, setVista] = useState<MonitorAgenteEstado | null>(null);
  const [aviso, setAviso] = useState('');
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    let vigente = true;
    // Agrupa ráfagas de avances recibidas por WebSocket; no sondea con intervalos.
    const timer = window.setTimeout(() => {
      void api.asistenteMonitor(ws.id).then((r) => {
        if (vigente) { setVista(r); setAviso(''); }
      }).catch((e: unknown) => {
        if (vigente) setAviso(`Historial persistente no disponible: ${e instanceof Error ? e.message : String(e)}. `
          + 'Los trabajos de esta sesión siguen visibles. Compruebe que el servidor haya recargado el código.');
      });
    }, 150);
    return () => { vigente = false; window.clearTimeout(timer); };
  }, [ws.id, ws.active_run_id, jobs, revision]);

  const operaciones = useMemo(() => {
    const filas = new Map((vista?.workspace_id === ws.id ? vista.trabajos : []).map((j) => [j.id, j]));
    for (const j of Object.values(jobs)) {
      if (j.workspace_id === ws.id) filas.set(j.id, { ...filas.get(j.id), ...j, seguimiento: 'en_sesion', aceptacion_nativa: null });
    }
    return [...filas.values()].sort((a, b) => b.created_at - a.created_at).slice(0, 50);
  }, [vista, jobs, ws.id]);
  const actual = operaciones.find((j) => j.kind === 'agente_proyecto' && j.status === 'running' && j.seguimiento === 'en_sesion');

  return <section className="card stack" aria-label="Monitor de operación del asistente">
    <div className="row"><h3>Monitor del conversor</h3><span className="spacer" />
      <button className="btn btn-sm" onClick={() => setRevision((v) => v + 1)}>Actualizar evidencia</button></div>
    <p className="small">Operación supervisada · Espacio <code>{ws.id}</code> · Fuente: {ws.source_mode ?? 'sin cargar'}
      {ws.source_fingerprint && <> · Huella <code title={ws.source_fingerprint}>{ws.source_fingerprint.slice(0, 12)}</code></>}</p>
    <p className="muted small">Ejecute las órdenes y el flujo del proyecto desde este asistente. Aquí se observa su avance.
      {' '}Terminar un trabajo no acredita su aceptación eléctrica. La autonomía integral sigue pendiente de validación conjunta.</p>
    {aviso && <p className="alert alert-warn" role="status">{aviso}</p>}
    {vista?.retencion && <details className="small">
      <summary>Limpieza automática · cada {vista.retencion.intervalo_horas} horas · antigüedad mayor de {vista.retencion.retencion_dias} días</summary>
      <p>{vista.retencion.alcance} Se aplaza mientras haya trabajos en curso.</p>
      <p>Última revisión: {vista.retencion.ultima_revision
        ? `${new Date(vista.retencion.ultima_revision.terminada * 1000).toLocaleString()} · ${vista.retencion.ultima_revision.estado}`
        : 'Pendiente de la primera revisión'}.</p>
      <p>Próxima revisión: {vista.retencion.proxima_revision
        ? new Date(vista.retencion.proxima_revision * 1000).toLocaleString() : 'Al quedar libre el conversor'}.</p>
      {vista.retencion.error && <p className="alert alert-warn">{vista.retencion.error}</p>}
      {vista.retencion.ultima_revision && <details><summary>Detalle de la última revisión</summary>
        <pre>{JSON.stringify(vista.retencion.ultima_revision, null, 2)}</pre></details>}
      <p className="muted">Funciona con la web abierta; al volver a arrancar recupera las revisiones vencidas. Actualizar evidencia muestra el último resumen.</p>
    </details>}
    {vista?.workspace_id === ws.id && vista.errores_observacion.map((e) => <p key={e} className="alert alert-warn">Observación incompleta: {e}</p>)}
    {vista?.workspace_id === ws.id && <details open={Boolean(actual)}>
      <summary>Etapas del proyecto {actual?.progress?.label ? `· ${actual.progress.label}` : ''}</summary>
      <ol className="small">{vista.proyecto.etapas.map((e) => <li key={e.nombre}>
        <b>{e.nombre.replaceAll('_', ' ')}</b>: {actual?.progress?.label === e.nombre ? 'En ejecución' : estados[e.estado] ?? e.estado}
        {e.opcional ? ' (según los datos solicitados)' : ''}
        {e.resultado !== undefined && <details><summary>Evidencia de la etapa</summary><pre>{JSON.stringify(e.resultado, null, 2)}</pre></details>}
      </li>)}</ol>
    </details>}
    <details open={operaciones.some((j) => j.seguimiento === 'en_sesion' && ['queued', 'running'].includes(j.status))}>
      <summary>Últimas 50 operaciones del espacio</summary>
      {!operaciones.length ? <p className="small">Aún no hay operaciones observadas en este espacio.</p> :
        <table className="small"><thead><tr><th>Operación</th><th>Estado y avance</th><th>Control y evidencia</th></tr></thead>
          <tbody>{operaciones.map((j) => <tr key={j.id}>
            <td>{j.title}<br /><span className="muted">{j.lane === 'powerfactory' ? 'DIgSILENT' : j.lane === 'asistente' ? 'Asistente' : 'Motor'}</span></td>
            <td>{j.seguimiento === 'interrumpido' ? 'Proceso no observado: verificar antes de retomar' : estados[j.status] ?? j.status}
              {j.progress && <p>{j.progress.index}/{j.progress.total} · {j.progress.label}</p>}
              {j.error && <p className="alert alert-error">{j.error}</p>}</td>
            <td>{j.seguimiento === 'en_sesion' && ['queued', 'running'].includes(j.status) && jobs[j.id] &&
              <button className="btn btn-sm btn-danger" disabled={j.cancel_requested}
                onClick={() => void run(() => api.cancelJob(j.id))}>{j.cancel_requested ? 'Cancelación solicitada' : 'Cancelar'}</button>}
              <details><summary>Ver registro de la operación</summary><pre>{JSON.stringify(j, null, 2)}</pre></details>
              <span className="muted">La aceptación nativa se comprueba en el informe de la operación.</span></td>
          </tr>)}</tbody></table>}
    </details>
    {vista?.workspace_id === ws.id && <details>
      <summary>Aprendizaje y evidencias de los modelos ({vista.evidencias.length})</summary>
      <p className="muted small">{vista.alcance_modelos}. Un informe incorporado no activa sus pesos.</p>
      {!vista.evidencias.length && <p className="small">No hay informes incorporados; el estado de evaluación se consulta en el panel de modelos.</p>}
      {vista.evidencias.map((e) => <article key={e.id} className="stack small">
        <p><b>{e.etiqueta}</b> · {e.familia} · {String(e.informe.status ?? 'informe custodiado')}</p>
        <p>Incorporado: {e.registrado}<br />Hash: <code>{e.sha256}</code></p>
        <details><summary>Resultado y ajustes registrados</summary><pre>{JSON.stringify(e.informe, null, 2)}</pre></details>
      </article>)}
    </details>}
  </section>;
}
