import { useState } from 'react';
import { api } from '../api';
import { useApp } from '../context';
import type { AsistentePlan, AsistenteRespuesta } from '../types';

/** Spec 026: la consola del asistente. La orden se escribe en español; lo que escribe en
 * DIgSILENT o en disco espera la confirmación (RF-8) y se ejecuta como cualquier trabajo. */
interface Intercambio {
  texto: string;
  r: AsistenteRespuesta;
  trabajo?: string;
}

function Plan({ plan }: { plan: AsistentePlan }) {
  const datos = Object.entries(plan.datos);
  return (
    <div className="stack">
      {plan.tarea
        ? <p><b>{plan.descripcion}</b> <span className="muted small">({plan.interpretado_por}, {Math.round(plan.confianza * 100)} %)</span></p>
        : <p className="alert alert-warn">No entendí la orden.</p>}
      {datos.length > 0 && (
        <ul className="small">{datos.map(([k, v]) => <li key={k}><b>{k}</b>: {Array.isArray(v) ? v.join(', ') : String(v)}</li>)}</ul>
      )}
      {plan.pasos && plan.pasos.length > 0 && <p className="small">Pasos: {plan.pasos.join(' → ')}</p>}
      {plan.faltan.map((f) => <p key={f} className="alert alert-warn">Falta {f}</p>)}
      {plan.dudas.map((d) => <p key={d} className="alert alert-warn">{d}</p>)}
      <details>
        <summary className="small">Razonamiento</summary>
        <ul className="small">{plan.razonamiento.map((x) => <li key={x}>{x}</li>)}</ul>
      </details>
    </div>
  );
}

/** RF-28, RF-31: lo que el asistente hizo, decidió y consultó en internet, para auditarlo. */
function Registro() {
  const { run } = useApp();
  const [registro, setRegistro] = useState<Record<string, unknown[]> | null>(null);
  const filas = (k: string) => (registro?.[k] ?? []) as Record<string, unknown>[];
  return (
    <details onToggle={(e) => { if ((e.target as HTMLDetailsElement).open) void run(api.asistenteRegistro).then((r) => r && setRegistro(r)); }}>
      <summary className="small">Registro del asistente (órdenes, decisiones, mejoras, internet, avisos)</summary>
      {registro && (
        <div className="stack small">
          <p>{Object.entries(registro).map(([k, v]) => `${k}: ${v.length}`).join(' · ')}</p>
          {filas('conjunto_real').map((c, i) => (
            <p key={i}>Órdenes reales del operador: {String(c.ordenes)} de las {String(c.hacen_falta)} que hacen falta
              {c.confirmacion_obligatoria ? '; mientras tanto, todo lo que escribe pide confirmación' : ''}.</p>))}
          {filas('senales').length > 0 && (
            <table className="small">
              <thead><tr><th>Tarea</th><th>Recompensas</th><th>Penalizaciones</th><th>Confirmadas</th>
                <th>Corregidas</th><th>Rechazadas</th><th>Fallidas</th></tr></thead>
              <tbody>{filas('senales').map((s) => (
                <tr key={String(s.tarea)}><td>{String(s.tarea)}</td><td>{String(s.recompensas)}</td>
                  <td>{String(s.penalizaciones)}</td><td>{String(s.confirmada)}</td><td>{String(s.corregida)}</td>
                  <td>{String(s.rechazada)}</td><td>{String(s.fallida)}</td></tr>))}</tbody>
            </table>
          )}
          <ul>{filas('ordenes').slice(-10).reverse().map((o, i) => (
            <li key={i}>{String(o.fecha)} · «{String(o.texto)}» → {String(o.tarea ?? 'sin entender')}</li>))}</ul>
          <ul>{filas('internet').slice(-5).reverse().map((o, i) => (
            <li key={i}>{String(o.destino)}: {String(o.consulta)}{o.bloqueada ? ` (bloqueada: ${String(o.bloqueada)})` : ''}</li>))}</ul>
          <ul>{filas('avisos').slice(-5).reverse().map((o, i) => <li key={i}>{String(o.texto)}</li>)}</ul>
        </div>
      )}
    </details>
  );
}

export function Asistente() {
  const { ws, run, startJob, jobs, active } = useApp();
  const [texto, setTexto] = useState('');
  const [historial, setHistorial] = useState<Intercambio[]>([]);
  const [enviando, setEnviando] = useState(false);
  const [correccion, setCorreccion] = useState<Record<string, string>>({});

  const enviar = async () => {
    const orden = texto.trim();
    if (!orden || enviando) return;
    setEnviando(true);
    const r = await run(() => api.asistenteOrden(ws.id, orden));
    setEnviando(false);
    if (!r) return;
    setTexto('');
    setHistorial((h) => [...h, { texto: orden, r, trabajo: r.trabajo?.id }]);
  };

  const confirmar = async (i: number, planId: string) => {
    const job = await startJob(() => api.asistenteConfirmar(ws.id, planId));
    if (job) setHistorial((h) => h.map((x, k) => (k === i ? { ...x, trabajo: job.id } : x)));
  };

  const rechazar = async (i: number, planId: string) => {
    const r = await run(() => api.asistenteRechazar(ws.id, planId));
    if (r) setHistorial((h) => h.map((x, k) => (k === i ? { ...x, trabajo: 'rechazado' } : x)));
  };

  const corregir = async (i: number, planId: string) => {
    const tarea = (correccion[planId] ?? '').trim();
    if (!tarea) return;
    const r = await run(() => api.asistenteCorregir(ws.id, planId, { tarea }));
    if (r) setHistorial((h) => h.map((x, k) => (k === i ? { ...x, r } : x)));
  };

  return (
    <div className="stack">
      <p className="muted small">
        Escriba lo que quiere hacer, por ejemplo «calibra el sistema Pisco con julio de 2026» o «¿cómo se calibra una
        barra sin medidor?». Las consultas se responden al momento; lo que escribe en DIgSILENT o en disco espera su
        confirmación. Todo se interpreta en esta máquina.
      </p>
      <div className="row">
        <label htmlFor="asistente-orden" className="sr-only">Orden</label>
        <textarea id="asistente-orden" rows={2} value={texto} placeholder="Escriba la orden…" disabled={enviando}
          onChange={(e) => setTexto(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) void enviar(); }} />
        <button className="btn btn-primary" disabled={enviando || !texto.trim()} onClick={() => void enviar()}>
          {enviando ? 'Interpretando…' : 'Enviar'}
        </button>
        <button className="btn btn-ghost" disabled={Boolean(active.engine)}
          title="Reentrena el Transformer de órdenes y el clasificador de informes con lo confirmado y corregido"
          onClick={() => startJob(() => api.asistenteEntrenar(ws.id))}>Reentrenar</button>
      </div>
      <Registro />
      {[...historial].reverse().map((x, rev) => {
        const i = historial.length - 1 - rev;
        const plan = x.r.plan;
        const job = x.trabajo ? jobs[x.trabajo] : undefined;
        const entregables: string[] = [...(x.r.respuesta?.entregables ?? []), ...(job?.result?.entregables ?? [])];
        return (
          <article key={plan.id} className="card stack">
            <p><b>›</b> {x.texto}</p>
            <Plan plan={plan} />
            {x.r.respuesta && (
              <div className="stack">
                <p>{x.r.respuesta.texto}</p>
                {(x.r.respuesta.citas ?? []).length > 0 && (
                  <ol className="small">{x.r.respuesta.citas!.map((c) => <li key={c.n}><code>{c.fuente}</code> {c.texto.slice(0, 240)}</li>)}</ol>
                )}
              </div>
            )}
            {job && (
              <p className={job.status === 'failed' ? 'alert alert-error' : 'small'}>
                Trabajo «{job.title}»: {job.status}{job.error ? ` — ${job.error}` : ''}
              </p>
            )}
            {entregables.length > 0 && (
              <p className="small">Entregables: {entregables.map((e) => (
                <a key={e} href={api.fileUrl(ws.id, e, true)}>{e} </a>
              ))}</p>
            )}
            {plan.listo && plan.escribe && !x.trabajo && (
              <div className="row">
                <button className="btn btn-primary" onClick={() => void confirmar(i, plan.id)}>Confirmar y ejecutar</button>
                <button className="btn btn-ghost" title="El plan no es lo que pidió: cuenta como penalización para el modelo"
                  onClick={() => void rechazar(i, plan.id)}>Rechazar</button>
              </div>
            )}
            {!x.trabajo && (
              <div className="row small">
                <label htmlFor={`corregir-${plan.id}`}>¿Otra tarea?</label>
                <input id={`corregir-${plan.id}`} placeholder={plan.alternativas[0]?.[0] ?? 'nombre de la tarea'}
                  value={correccion[plan.id] ?? ''} onChange={(e) => setCorreccion((c) => ({ ...c, [plan.id]: e.target.value }))} />
                <button className="btn btn-sm" disabled={!(correccion[plan.id] ?? '').trim()}
                  onClick={() => void corregir(i, plan.id)}>Corregir</button>
              </div>
            )}
          </article>
        );
      })}
    </div>
  );
}
