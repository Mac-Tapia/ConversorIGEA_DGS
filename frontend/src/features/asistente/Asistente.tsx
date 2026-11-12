import { useEffect, useState } from 'react';
import { api } from '../../api/client';
import { useApp } from '../../shared/context';
import { AvisosTrabajo } from '../../shared/AvisosTrabajo';
import type { AsistentePlan, AsistenteRespuesta, EstadoModelos, ListaProyecto } from '../../api/types';
import type { EstadoAceptacionAgente } from '../../api/asistenteAceptacion';
import { esProducto } from '../../shared/edicion';
import { AvisoBeta } from '../../shared/MarcaBeta';
import { MonitorAgente } from './MonitorAgente';
import { EquipoAsistente } from './EquipoAsistente';
import { Aprendizaje } from './Aprendizaje';

/** Spec 026: la consola del asistente. La orden se escribe en español; lo que escribe en
 * DIgSILENT o en disco espera la confirmación (RF-8) y se ejecuta como cualquier trabajo. */
interface Intercambio {
  texto: string;
  r?: AsistenteRespuesta;
  interpretacion?: string;
  trabajo?: string;
}

/** 086:RF-23, RF-24: lo que el operador autoriza al confirmar, dicho antes de pulsar. */
const QUE_HACE: Record<string, string> = {
  usa_licencia: 'Ocupa la licencia de DIgSILENT mientras corre.',
  sale_a_la_red: 'Sale a internet.',
  escribe: 'Escribe en DIgSILENT o en disco.',
};

function Plan({ plan }: { plan: AsistentePlan }) {
  const datos = Object.entries(plan.datos);
  const efectos = (plan.efectos ?? []).filter((e) => QUE_HACE[e]);
  return (
    <div className="stack">
      {plan.tarea
        ? <p><b>{plan.descripcion}</b> <span className="muted small">({plan.interpretado_por}, {Math.round(plan.confianza * 100)} %)</span></p>
        : plan.dudas.length === 0 && <p className="alert alert-warn">No entendí la orden.</p>}
      {efectos.length > 0 && <p className="small">{efectos.map((e) => QUE_HACE[e]).join(' ')}</p>}
      {(plan.avisos ?? []).map((a) => <p key={a} className="alert alert-warn">{a}</p>)}
      {plan.guardado && (
        <p className={plan.guardado.vigente ? 'small' : 'alert alert-warn'}>
          {plan.guardado.estado === 'interrumpido'
            ? 'Este plan estaba ejecutándose cuando se cortó la web: pudo quedar a medias y no se reanuda solo. '
            : 'Plan guardado, a la espera de su confirmación. '}
          {plan.guardado.ultimo_error && `Último intento: ${plan.guardado.ultimo_error}. `}
          {!plan.guardado.vigente && `No se puede confirmar: ${plan.guardado.motivo}.`}
        </p>
      )}
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
function Modelos() {
  const { run } = useApp();
  const [modelos, setModelos] = useState<EstadoModelos | null>(null);
  return (
    <details onToggle={(e) => {
      if ((e.target as HTMLDetailsElement).open)
        void run(api.asistenteModelos).then((r) => r && setModelos(r));
    }}>
      <summary className="small">Estado de los modelos y evidencia de evaluación</summary>
      {modelos && <table className="small">
        <thead><tr><th>Familia</th><th>Algoritmo</th><th>Estado</th><th>En uso</th><th>Evidencia</th><th>Observaciones</th></tr></thead>
        <tbody>{modelos.familias.map((f) => <tr key={f.familia}>
          <td>{f.familia}</td><td>{f.algorithm ?? '—'}</td>
          <td>{f.estado ?? 'Pendiente de evidencia'}</td><td>{f.en_uso ?? '—'}</td>
          {/* 043:RF-8: el estado con lo que lo respalda; sin candidato, solo hay informe o nada. */}
          <td>{f.candidate_id ? `Candidato ${f.candidate_id.slice(0, 12)} · ` : ''}
            {f.gates.approved === true ? 'puertas aprobadas · ' : f.candidate_id ? 'puertas no aprobadas · ' : ''}
            {f.estado ? f.report_path : '—'}</td>
          <td>{f.bloqueos.join('; ') || '—'}</td>
        </tr>)}</tbody>
      </table>}
    </details>
  );
}

/** 085:RF-30: un modelo que no pasa las puertas no se usa en silencio; y volver al anterior está a un clic. */
function ModeloProvisional() {
  const { run } = useApp();
  const [aviso, setAviso] = useState<string | null>(null);
  const leer = () => run(api.asistenteModelos).then((r) => {
    if (r) setAviso(r.familias.find((f) => f.provisional)?.provisional?.aviso ?? null);
  });
  useEffect(() => { void leer(); }, [run]);
  if (!aviso) return null;
  return (
    <div className="alert alert-warn stack">
      <p>{aviso}</p>
      <div className="row">
        <button className="btn btn-ghost" onClick={() => void run(() => api.volverModelo('asistente')).then(leer)}>
          Volver al modelo anterior</button>
      </div>
    </div>
  );
}

function Aceptacion() {
  const { run } = useApp();
  const [estado, setEstado] = useState<EstadoAceptacionAgente | null>(null);
  return <details onToggle={(e) => {
    if ((e.target as HTMLDetailsElement).open)
      void run(api.asistenteAceptacion).then((r) => r && setEstado(r));
  }}>
    <summary className="small">200 propuestas y aceptación del agente</summary>
    {estado && <div className="stack small">
      <p><b>Propuestas del maestro:</b> {estado.propuestas.materializadas} materializadas,
        {' '}{estado.propuestas.unicas} únicas, de {estado.propuestas.definidas} previstas.</p>
      <p><b>Órdenes reales del operador:</b> {estado.humanas.unicas} únicas
        {' '}en {estado.humanas.eventos} registros. Las propuestas del maestro se contabilizan aparte.</p>
      <p>Los nombres y las rutas de las propuestas son ejemplos de prueba.</p>
      {estado.evaluacion ? <>
        <p>Evaluadas: {estado.evaluacion.ejemplos}. Acierto de tarea:
          {' '}{(estado.evaluacion.acierto_tarea * 100).toFixed(1)} %.
          {' '}F1 de datos: {(estado.evaluacion.f1_datos * 100).toFixed(1)} %.</p>
        <p>{estado.evaluacion.aceptacion.asistida.aprobada
          ? 'Cumple la evaluación de uso asistido. Las escrituras siguen pidiendo confirmación.'
          : 'No cumple todavía la evaluación de uso asistido.'}</p>
        {estado.evaluacion.aceptacion.asistida.fallos.map((f) => <p key={f} className="alert alert-warn">{f}</p>)}
      </> : <p>Evaluación de las 200 propuestas pendiente.</p>}
      {!estado.integral && <p>Aceptación integral y validación eléctrica pendientes.</p>}
      {estado.bloqueos.map((b) => <p key={b} className="alert alert-warn">{b}</p>)}
      <details><summary>Revisar las propuestas del maestro</summary>
        <ol>{estado.propuestas.filas.map((r, i) => <li key={i}>{r.texto} <span className="muted">({r.tarea})</span></li>)}</ol>
      </details>
    </div>}
  </details>;
}

function Registro() {
  const { run, health } = useApp();
  const [registro, setRegistro] = useState<Record<string, unknown[]> | null>(null);
  const filas = (k: string) => (registro?.[k] ?? []) as Record<string, unknown>[];
  return (
    <details onToggle={(e) => { if ((e.target as HTMLDetailsElement).open) void run(api.asistenteRegistro).then((r) => r && setRegistro(r)); }}>
      <summary className="small">Registro del asistente (órdenes, decisiones, mejoras, internet, avisos)</summary>
      {registro && (
        <div className="stack small">
          <p>{Object.entries(registro).map(([k, v]) => `${k}: ${v.length}`).join(' · ')}</p>
          {!esProducto(health) && filas('conjunto_real').map((c, i) => (
            <p key={i}>Órdenes reales únicas del operador: {String(c.ordenes)}.
              {' '}Referencia de muestra humana: {String(c.hacen_falta)}.
              {c.confirmacion_obligatoria ? ' Las escrituras requieren confirmación.' : ''}</p>))}
          {!esProducto(health) && filas('senales').length > 0 && (
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

/** 027:RF-43, RF-44: el agente hace el proyecto entero; si se corta, retoma donde quedó. */
function ProyectoDesdeCero() {
  const { ws, run, startJob, active } = useApp();
  const [lista, setLista] = useState<ListaProyecto | null>(null);
  const [sistema, setSistema] = useState('');
  const [periodo, setPeriodo] = useState('');
  const [ruta, setRuta] = useState('');
  const [cargas, setCargas] = useState('');
  const [reiniciar, setReiniciar] = useState(false);
  const listo = sistema.trim() && /^\d{4}(-\d{2})?$/.test(periodo.trim());
  const solicitud = { sistema: sistema.trim(), periodo: periodo.trim(), ruta: ruta.trim() || undefined,
    ruta_cargas: cargas.trim() || undefined, reiniciar };
  // Cualquier cambio deja de ser lo que el operador revisó: el botón de confirmar desaparece.
  useEffect(() => { setLista(null); }, [ws.id, sistema, periodo, ruta, cargas, reiniciar]);
  const escrituras = lista?.etapas_escritura ?? [];
  const textoEtapa = { pendiente: 'se hará', hecha: 'ya hecha, no se repite', se_omitira: 'se omitirá', falta_dato: 'falta un dato' } as const;
  return (
    <details>
      <summary className="small">Proyecto desde cero (el agente hace todas las etapas)</summary>
      <div className="stack small">
        <p className="muted">Cargar la fuente, convertir, importar y calibrar el sistema, verificar el «Caso base»,
          cargas nuevas, obras, estudios, PIDE e informe. Cada etapa hecha queda guardada: si se corta, la siguiente
          vez retoma desde la que falta.</p>
        <div className="row">
          <label className="field"><span>Sistema eléctrico</span>
            <input value={sistema} placeholder="Nombre del sistema" onChange={(e) => setSistema(e.target.value)} /></label>
          <label className="field"><span>Periodo</span>
            <input value={periodo} placeholder="2026-07" onChange={(e) => setPeriodo(e.target.value)} /></label>
          <label className="field"><span>Carpeta de la demanda</span>
            <input value={ruta} placeholder="referencia" onChange={(e) => setRuta(e.target.value)} /></label>
          <label className="field"><span>Libro de cargas nuevas (opcional)</span>
            <input value={cargas} onChange={(e) => setCargas(e.target.value)} /></label>
          <label className="row"><input type="checkbox" checked={reiniciar} onChange={(e) => setReiniciar(e.target.checked)} />
            Empezar de nuevo</label>
          <button className="btn" disabled={!listo} onClick={() => void run(() => api.agenteProyectoLista(ws.id, solicitud)).then((r) => r && setLista(r))}>
            Ver las etapas</button>
        </div>
        {lista && <div className="stack">
          <p>Un solo clic confirma las {escrituras.length} etapas que escriben en DIgSILENT o en disco:</p>
          <ol>{lista.etapas.map((e) => <li key={e.nombre}>
            <b>{e.nombre}</b>: {e.descripcion} <span className="muted">({textoEtapa[e.estado]}{e.falta.length > 0 && `: ${e.falta.join(', ')}`})</span>
          </li>)}</ol>
          {lista.bloqueo && <p className="alert alert-warn">{lista.bloqueo}</p>}
          <button className="btn btn-primary" disabled={Boolean(active.asistente) || Boolean(lista.bloqueo) || escrituras.length === 0
              || lista.etapas.some((e) => e.estado === 'falta_dato')}
            onClick={() => startJob(() => api.agenteProyecto(ws.id, { ...solicitud, confirmacion: lista.confirmacion }))}>
            Confirmar estas {escrituras.length} etapas y hacer el proyecto</button>
        </div>}
      </div>
    </details>
  );
}

export function Asistente() {
  const { ws, run, startJob, jobs, active, health } = useApp();
  // 086:RF-16: entrenar y la revisión por roles no se entregan; el servidor también niega sus rutas.
  const desarrollo = !esProducto(health);
  const [texto, setTexto] = useState('');
  const [historial, setHistorial] = useState<Intercambio[]>([]);
  const [enviando, setEnviando] = useState(false);
  const [correccion, setCorreccion] = useState<Record<string, string>>({});

  useEffect(() => {
    let vigente = true;
    setHistorial([]);
    setCorreccion({});
    // 067:RF-19: lo que quedó por confirmar antes de reiniciar la web o recargar la página.
    void run(() => api.asistentePlanes(ws.id)).then((r) => {
      if (vigente && r) setHistorial((h) => [...r.planes.filter((p) => !h.some((x) => x.r?.plan.id === p.id))
        .map((plan) => ({ texto: plan.texto, r: { plan } })), ...h]);
    });
    return () => { vigente = false; };
  }, [ws.id, run]);

  useEffect(() => {
    setHistorial((rows) => {
      let changed = false;
      const next = rows.map((row) => {
        const job = row.interpretacion ? jobs[row.interpretacion] : undefined;
        if (!row.r && job?.status === 'done' && job.result?.plan) {
          changed = true;
          const response = job.result as AsistenteRespuesta;
          return { ...row, r: response, trabajo: response.trabajo?.id };
        }
        return row;
      });
      return changed ? next : rows;
    });
  }, [jobs]);

  const enviar = async () => {
    const orden = texto.trim();
    if (!orden || enviando) return;
    setEnviando(true);
    const job = await startJob(() => api.asistenteOrden(ws.id, orden));
    setEnviando(false);
    if (!job) return;
    setTexto('');
    setHistorial((h) => [...h, { texto: orden, interpretacion: job.id }]);
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
      <AvisoBeta clave="asistente" />
      {/* 086:RF-70: las órdenes y los entrenamientos del asistente que no terminaron bien. */}
      <AvisosTrabajo paso="asistente" />
      <ModeloProvisional />
      <MonitorAgente />
      {desarrollo && <EquipoAsistente />}
      {desarrollo && <Modelos />}
      {desarrollo && <Aprendizaje />}
      {desarrollo && <Aceptacion />}
      <p className="muted small">
        Escriba lo que quiere hacer, por ejemplo «calibra el sistema X con julio de 2026» o «¿cómo se calibra una
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
        {desarrollo && <button className="btn btn-ghost" disabled={Boolean(active.engine)}
          title="Reentrena el Transformer de órdenes y, si hay informes reales, el clasificador. Solo pasa a uso lo que aprueben sus puertas; si no, sigue el modelo actual"
          onClick={() => startJob(() => api.asistenteEntrenar(ws.id))}>Reentrenar</button>}
      </div>
      <Registro />
      <ProyectoDesdeCero />
      {[...historial].reverse().map((x, rev) => {
        const i = historial.length - 1 - rev;
        if (!x.r) {
          const pending = x.interpretacion ? jobs[x.interpretacion] : undefined;
          return <article key={x.interpretacion} className="card stack">
            <p><b>›</b> {x.texto}</p>
            <p className={pending?.status === 'failed' ? 'alert alert-error' : 'small'}>
              {pending?.error ?? (pending?.status === 'cancelled' ? 'Orden cancelada.' : 'Interpretando la orden…')}
            </p>
          </article>;
        }
        const plan = x.r.plan;
        const job = x.trabajo ? jobs[x.trabajo] : undefined;
        const entregables: string[] = [...(x.r.respuesta?.entregables ?? []), ...(job?.result?.entregables ?? [])];
        return (
          <article key={plan.id} className="card stack">
            <p><b>›</b> {x.texto}</p>
            <Plan plan={plan} />
            {desarrollo && <EquipoAsistente planId={plan.id} />}
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
                {typeof job.result?.texto === 'string' && ` — ${job.result.texto}`}
                {/* 042:RF-84: el texto dice «bájelo del enlace»: el enlace tiene que estar. */}
                {typeof job.result?.enlace === 'string' && <> <a href={job.result.enlace}>Descargar</a></>}
              </p>
            )}
            {entregables.length > 0 && (
              <p className="small">Entregables: {entregables.map((e) => (
                <a key={e} href={api.fileUrl(ws.id, e, true)}>{e} </a>
              ))}</p>
            )}
            {plan.listo && (plan.espera_confirmacion ?? plan.escribe) && !x.trabajo && (
              <div className="row">
                <button className="btn btn-primary" disabled={plan.guardado?.vigente === false} onClick={() => void confirmar(i, plan.id)}>Confirmar y ejecutar</button>
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
