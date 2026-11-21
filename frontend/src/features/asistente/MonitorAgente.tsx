import { Fragment, useEffect, useMemo, useState } from 'react';
import { api } from '../../api/client';
import { useApp } from '../../shared/context';
import { nombreCarril } from '../../shared/carriles';
import { fmtBytes } from '../../shared/formato';
import type { MonitorAgenteEstado } from '../../api/types';

const estados: Record<string, string> = {
  parcial: 'Parcial',
  no_converge: 'No converge',
  queued: 'En cola', running: 'Ejecutando', done: 'Ejecución terminada',
  failed: 'Falló', cancelled: 'Cancelado', interrumpido: 'Interrumpido', hecha: 'Hecha', omitida: 'Omitida', pendiente: 'Pendiente',
};

/** 111 T17 (M1): nombre en español de cada clave que el servidor guarda en el registro de una operación. */
const ETIQUETAS: Record<string, string> = {
  id: 'Identificador', kind: 'Tipo', title: 'Operación', status: 'Estado', estado: 'Estado', lane: 'Carril',
  created_at: 'Creado', started_at: 'Iniciado', finished_at: 'Terminado', updated_at: 'Actualizado',
  terminada: 'Terminada', cancel_requested: 'Cancelación solicitada', error: 'Error', errores: 'Errores',
  progress: 'Avance', index: 'Paso', total: 'Total', label: 'Etapa', result: 'Resultado', resultado: 'Resultado',
  workspace_id: 'Espacio', seguimiento: 'Seguimiento', contexto: 'Contexto', aceptacion_nativa: 'Aceptación nativa',
  eliminados: 'Eliminados', conservados: 'Conservados', ruta: 'Fichero', motivo: 'Motivo',
  bytes_logicos_retirados: 'Espacio liberado', message: 'Mensaje', summary: 'Resumen', warnings: 'Avisos',
  path: 'Fichero', file: 'Fichero', files: 'Ficheros', output: 'Salida', outputs: 'Salidas', reason: 'Motivo',
  name: 'Nombre', version: 'Versión',
};
const SEGUIMIENTO: Record<string, string> = { en_sesion: 'En esta sesión', interrumpido: 'Interrumpido', historico: 'Histórico' };
const ES_RUTA = /^(?:[A-Za-z]:[\\/]|\\\\|\/)/;
const ES_FECHA = /(?:_at|^terminada|^inicio|^fin)$/;

/** Una ruta absoluta del equipo se queda en el nombre del fichero; el resto, tal cual. */
export function sinRutas(valor: unknown): unknown {
  if (typeof valor === 'string') return ES_RUTA.test(valor) ? (valor.split(/[\\/]/).filter(Boolean).pop() ?? valor) : valor;
  if (Array.isArray(valor)) return valor.map(sinRutas);
  if (valor && typeof valor === 'object') {
    return Object.fromEntries(Object.entries(valor as Record<string, unknown>).map(([k, v]) => [k, sinRutas(v)]));
  }
  return valor;
}

const etiqueta = (k: string) => ETIQUETAS[k] ?? (k.charAt(0).toUpperCase() + k.slice(1)).replaceAll('_', ' ');

function legible(clave: string, v: unknown, nivel: number): string | null {
  if (v === null || v === undefined || v === '' || (Array.isArray(v) && !v.length)) return null;
  if (typeof v === 'boolean') return v ? 'Sí' : 'No';
  if (typeof v === 'number') {
    if (ES_FECHA.test(clave) && v > 1e9) return new Date(v * 1000).toLocaleString();
    if (clave === 'bytes_logicos_retirados') return fmtBytes(v);
    return v.toLocaleString('es-PE');
  }
  if (typeof v === 'string') {
    if (clave === 'status' || clave === 'estado') return estados[v] ?? v;
    if (clave === 'lane') return nombreCarril(v);
    if (clave === 'seguimiento') return SEGUIMIENTO[v] ?? v;
    return String(sinRutas(v));
  }
  if (Array.isArray(v)) {
    if (v.every((x) => typeof x !== 'object' || x === null)) {
      const vistos = v.slice(0, 5).map((x) => String(sinRutas(x)));
      return v.length > 5 ? `${vistos.join(', ')} y ${v.length - 5} más` : vistos.join(', ');
    }
    return `${v.length} ${v.length === 1 ? 'elemento' : 'elementos'}`;
  }
  if (typeof v === 'object') {
    const partes = nivel < 1 ? filasLegibles(v, nivel + 1).map((f) => `${f.etiqueta}: ${f.valor}`) : [];
    return partes.length ? partes.join(' · ') : null;
  }
  return String(v);
}

/** 111 T17 (M1): los datos de una operación como filas «etiqueta: valor» en español, sin vacíos ni rutas. */
export function filasLegibles(datos: unknown, nivel = 0): { etiqueta: string; valor: string }[] {
  if (!datos || typeof datos !== 'object' || Array.isArray(datos)) {
    const v = legible('', datos, nivel);
    return v === null ? [] : [{ etiqueta: 'Valor', valor: v }];
  }
  return Object.entries(datos as Record<string, unknown>).flatMap(([k, v]) => {
    const valor = legible(k, v, nivel);
    return valor === null ? [] : [{ etiqueta: etiqueta(k), valor }];
  });
}

/** La lista legible y, plegado, el detalle técnico (el JSON, sin rutas absolutas) para quien lo necesite. */
export function DatosLegibles({ datos }: { datos: unknown }) {
  const filas = filasLegibles(datos);
  return <div className="small">
    {filas.length ? <dl className="datos">{filas.map((f, i) => <Fragment key={i}>
      <dt>{f.etiqueta}</dt><dd>{f.valor}</dd></Fragment>)}</dl> : <p className="muted">Sin datos.</p>}
    <details><summary>Detalle técnico</summary><pre>{JSON.stringify(sinRutas(datos), null, 2)}</pre></details>
  </div>;
}

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
        <DatosLegibles datos={vista.retencion.ultima_revision} /></details>}
      <p className="muted">Funciona con la web abierta; al volver a arrancar recupera las revisiones vencidas. Actualizar evidencia muestra el último resumen.</p>
    </details>}
    {vista?.workspace_id === ws.id && vista.errores_observacion.map((e) => <p key={e} className="alert alert-warn">Observación incompleta: {e}</p>)}
    {vista?.workspace_id === ws.id && <details open={Boolean(actual)}>
      <summary>Etapas del proyecto {actual?.progress?.label ? `· ${actual.progress.label}` : ''}</summary>
      <ol className="small">{vista.proyecto.etapas.map((e) => <li key={e.nombre}>
        <b>{e.nombre.replaceAll('_', ' ')}</b>: {actual?.progress?.label === e.nombre ? 'En ejecución' : estados[e.estado] ?? e.estado}
        {e.opcional ? ' (según los datos solicitados)' : ''}
        {e.resultado !== undefined && <details><summary>Evidencia de la etapa</summary><DatosLegibles datos={e.resultado} /></details>}
      </li>)}</ol>
    </details>}
    <details open={operaciones.some((j) => j.seguimiento === 'en_sesion' && ['queued', 'running'].includes(j.status))}>
      <summary>Últimas 50 operaciones del espacio</summary>
      {!operaciones.length ? <p className="small">Aún no hay operaciones observadas en este espacio.</p> :
        <table className="small"><thead><tr><th>Operación</th><th>Estado y avance</th><th>Control y evidencia</th></tr></thead>
          <tbody>{operaciones.map((j) => <tr key={j.id}>
            <td>{j.title}<br /><span className="muted">{nombreCarril(j.lane)}</span></td>
            <td>{j.seguimiento === 'interrumpido' ? 'Proceso no observado: verificar antes de retomar' : estados[j.status] ?? j.status}
              {j.progress && <p>{j.progress.index}/{j.progress.total} · {j.progress.label}</p>}
              {j.error && <p className="alert alert-error">{j.error}</p>}</td>
            <td>{j.seguimiento === 'en_sesion' && ['queued', 'running'].includes(j.status) && jobs[j.id] &&
              <button className="btn btn-sm btn-danger" disabled={j.cancel_requested}
                onClick={() => void run(() => api.cancelJob(j.id))}>{j.cancel_requested ? 'Cancelación solicitada' : 'Cancelar'}</button>}
              <details><summary>Ver registro de la operación</summary><DatosLegibles datos={j} /></details>
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
        <details><summary>Resultado y ajustes registrados</summary><DatosLegibles datos={e.informe} /></details>
      </article>)}
    </details>}
  </section>;
}
