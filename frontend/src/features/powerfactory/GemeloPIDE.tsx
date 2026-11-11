import { fmtNum } from '../../shared/formato';
import { useEffect, useState } from 'react';
import { api } from '../../api/client';
import { useApp } from '../../shared/context';
import { esProducto } from '../../shared/edicion';
import { AvisoBeta } from '../../shared/MarcaBeta';
import type { ClaveTipoAnalisis, EpisodioResumen, ObraPIDE, PideResultado, PideAnualResultado, PideFuentes, PideSolicitud,
  TiposAnalisis } from '../../api/types';

const RUBRO: Record<string, string> = {
  ampliacion_reforzamiento: 'Ampliación y reforzamiento', mejoramiento: 'Mejoramiento',
  remodelacion: 'Remodelación', innovacion_eficiencia: 'Innovación y eficiencia', seguridad: 'Seguridad',
};

/**
 * 5 · Planificación PIDE y gemelo digital (spec 024).
 *
 * Con el proyecto y los alimentadores de los pasos 1 y 2: diagnostica cada año del
 * horizonte en DIgSILENT, propone y prioriza las obras (art. 14 y 15 de la norma del PIDE)
 * y aplica solas en «Con proyecto» las que se construyen sin diseño, tras simularlas. El
 * gemelo aprende de cada acción y de los escenarios que simula en una copia del proyecto.
 */
export function GemeloPIDE({ project, feeders, plazo = null, anio: anioExterno, onAnio, tipos = null }: {
  project: string; feeders: string[];
  /** 072:RF-29: el tipo de análisis elegido arriba; con él, el año de presentación es el mismo campo. */
  plazo?: ClaveTipoAnalisis | null; anio?: string; onAnio?: (a: string) => void; tipos?: TiposAnalisis | null;
}) {
  const { ws, startJob, active, jobs, run, health } = useApp();
  // 086:RF-16: el gemelo (PINN, aprendizaje) no se entrega; su ruta también se niega, y aquí ni se pregunta.
  const producto = esProducto(health);
  const [capex, setCapex] = useState('');
  const [anioPropio, setAnioPropio] = useState('');
  const anio = anioExterno ?? anioPropio;
  const setAnio = onAnio ?? setAnioPropio;
  const [formato01, setFormato01] = useState('');
  const [implementar, setImplementar] = useState(true);
  // 072:RF-34, RF-35: el largo plazo plantea las obras; el corto plazo no se planifica aquí (pasos 2 a 4).
  const plazoPeticion = planificacionDe(plazo);
  const aplicar = implementar && plazoPeticion !== 'largo_plazo';
  const [n, setN] = useState(20);
  const [episodios, setEpisodios] = useState<EpisodioResumen[]>([]);
  const pfBusy = Boolean(active.powerfactory);
  const ultima = Object.values(jobs).filter((j) => j.kind === 'pide' && j.result &&
    (j.result as { project?: string }).project === project).pop();
  const r = (ultima?.result ?? null) as PideResultado | PideAnualResultado | null;
  const [modo, setModo] = useState<'historico' | 'anual'>('historico');
  const aprendido = Object.values(jobs).filter((j) => j.kind === 'gemelo_aprender' && j.result).pop();

  const cargarEpisodios = async () => {
    const e = await run(() => api.gemeloEpisodios(ws.id, { proyecto: project }));
    if (e) setEpisodios(e);
  };
  useEffect(() => { if (project && !producto) void cargarEpisodios(); }, [project, ultima?.id, aprendido?.id]);  // eslint-disable-line react-hooks/exhaustive-deps

  const decidir = async (o: ObraPIDE, decision: 'aceptada' | 'rechazada' | 'modificada') => {
    await run(() => api.pideDecision(ws.id, { project, codigo: o.codigo, decision }));
  };

  if (!feeders.length) return <p className="muted">Marque al menos un alimentador en el paso 2.</p>;
  return (
    <div>
      <AvisoBeta clave="pide" />
      <h4>{producto ? 'Plan de inversiones (PIDE)' : '5.1 · Plan de inversiones (PIDE)'}</h4>
      <label className="field"><span>Flujo de planeamiento</span>
        <select value={modo} disabled={pfBusy} onChange={(e) => setModo(e.target.value as typeof modo)}>
          <option value="historico">Diagnóstico y propuesta del horizonte</option>
          <option value="anual">Continuación anual desde corto plazo aceptado</option>
        </select></label>
      {modo === 'anual' ? <FormularioPideAnual key={`${ws.id}:${project}:${feeders.join('|')}`} ws={ws.id}
        project={project} feeders={feeders} busy={pfBusy} planificar={(body) => startJob(() => api.pide(ws.id, body))} /> : <>
      <p className="muted">Diagnóstico de «Sin proyecto» en DIgSILENT para cada año del horizonte, obras por rubro con su
        costo, evaluación (art. 14) y prioridad (art. 15). Los bancos y las ternas se simulan y, si funcionan, se aplican
        solos en «Con proyecto», cada uno en su variación para poder deshacerlo.</p>
      <div className="row">
        <label className="field grow"><span>Libro CAPEX (ruta en el servidor, opcional)</span>
          <input className="search" value={capex} placeholder="p. ej. D:\…\capex.xlsx"
            onChange={(e) => setCapex(e.target.value)} /></label>
        <label className="field"><span>Año de presentación (se presenta cada 4 años)</span>
          <input type="number" min={2000} max={2100} value={anio} placeholder="sin él, sin módulos"
            onChange={(e) => setAnio(e.target.value)} /></label>
        <label className="field grow"><span>Formato 01 de la empresa (ruta en el servidor, opcional)</span>
          <input className="search" value={formato01} placeholder="p. ej. D:\…\formato01.xlsx"
            onChange={(e) => setFormato01(e.target.value)} /></label>
        <label className="check" title={plazoPeticion === 'largo_plazo' ? 'El plan de largo plazo plantea las obras; no las aplica.' : undefined}>
          <input type="checkbox" checked={aplicar} disabled={plazoPeticion === 'largo_plazo'}
            onChange={(e) => setImplementar(e.target.checked)} /> Aplicar solas las obras que funcionan</label>
        <button className="btn btn-pf" disabled={pfBusy || !project}
          onClick={() => startJob(() => api.pide(ws.id, cuerpoPlanificar(project, feeders, plazo, {
            capex, anio, formato01, implementar })))}>
          {plazoPeticion === 'largo_plazo' ? 'Planificar el largo plazo' : plazoPeticion === 'pide' ? 'Planificar como PIDE' : 'Planificar'}
        </button>
      </div>
      {plazo === 'corto_plazo' && <p className="small muted">Tipo elegido: corto plazo. Se resuelve en los pasos 2 a 4
        («Con proyecto» y sus informes); aquí se planifican el PIDE y el largo plazo, que escriben los dos entregables
        si no elige uno de ellos arriba.</p>}
      {plazoPeticion && <p className="small muted">{plazoPeticion === 'largo_plazo'
        ? 'Tipo elegido: planeamiento de largo plazo. Se escriben solo sus módulos (F01 a F07) y las obras se plantean, sin aplicarlas.'
        : 'Tipo elegido: PIDE. Se escriben sus módulos (F08 a F15) y los del plan de largo plazo que consume (F01 a F07).'}</p>}
      </>}
      {r && ('modo' in r && r.modo === 'anual'
        ? <VistaPideAnual r={r} ws={ws.id} /> : <ResultadoPIDE r={r as PideResultado} ws={ws.id} decidir={decidir} tipos={tipos} />)}

      {!producto && <>
      <h4>5.2 · Gemelo digital</h4>
      <p className="muted">Aprende de cada acción en DIgSILENT. Aquí simula escenarios (demanda y tramos fuera de servicio)
        en una copia del proyecto, que se borra al terminar, y reentrena el modelo si toca.</p>
      <div className="row">
        <label className="field"><span>Escenarios</span>
          <input type="number" min={1} max={200} value={n} onChange={(e) => setN(Number(e.target.value) || 1)} /></label>
        <button className="btn btn-pf" disabled={pfBusy || !project}
          onClick={() => startJob(() => api.gemeloAprender(ws.id, { project, feeders, n }))}>Aprender</button>
        <button className="btn btn-ghost btn-sm" onClick={() => void cargarEpisodios()}>Actualizar</button>
        <button className="btn btn-ghost btn-sm"
          title="Episodios nuevos y fuera del dominio del modelo por familia, y si conviene reentrenar"
          onClick={() => startJob(() => api.gemeloDeriva(ws.id))}>Revisar deriva</button>
        <button className="btn btn-ghost btn-sm" title="Deja en uso el modelo del gemelo promovido antes del actual"
          onClick={() => void run(() => api.volverModelo('gemelo'))}>Volver al modelo anterior</button>
      </div>
      {episodios.length > 0 && (
        <div className="table-wrap table-short">
          <table className="table">
            <thead><tr><th>Fecha</th><th>Caso</th><th>Clase</th><th>Acción</th><th>Avisos</th></tr></thead>
            <tbody>{episodios.slice(-50).reverse().map((e) => (
              <tr key={e.episode_id}>
                <td className="small">{e.creado}</td><td>{e.caso}</td>
                <td><span className={`badge ${e.clase === 'accepted' || e.clase === 'counterfactual' ? 'ok'
                  : e.clase === 'quarantine' ? 'warn' : 'err'}`}>{e.clase}</span></td>
                <td className="small">{e.accion}</td>
                <td className="small">{[...e.bloqueos, ...e.violaciones].slice(0, 2).join(' · ')}</td>
              </tr>))}</tbody>
          </table>
        </div>
      )}
      </>}
    </div>
  );
}

/** 072:RF-29: qué tipo va en la petición: el corto plazo no se planifica aquí, así que no lo lleva. */
export function planificacionDe(plazo: ClaveTipoAnalisis | null): 'pide' | 'largo_plazo' | null {
  return plazo === 'pide' || plazo === 'largo_plazo' ? plazo : null;
}

/** 072:RF-34, RF-35: el cuerpo de «Planificar»; en largo plazo nunca pide aplicar obras. */
export function cuerpoPlanificar(project: string, feeders: string[], plazo: ClaveTipoAnalisis | null,
  f: { capex: string; anio: string; formato01: string; implementar: boolean }): PideSolicitud {
  const tipo = planificacionDe(plazo);
  return { project, feeders, capex: f.capex.trim() || null, anio_presentacion: f.anio.trim() ? Number(f.anio) : null,
    formato_01: f.formato01.trim() || null, implementar: f.implementar && tipo !== 'largo_plazo',
    ...(tipo ? { plazo: tipo } : {}) };
}

/** 072:RF-32: los documentos del estudio agrupados por su entregable, con las claves de módulo del servidor. */
export function porEntregable(ficheros: string[], tipos: TiposAnalisis | null): { titulo: string; ficheros: string[] }[] {
  const grupos = (tipos?.tipos ?? []).filter((t) => t.clave !== 'corto_plazo').map((t) => ({
    titulo: t.titulo, claves: t.entregables.map((e) => e.clave), ficheros: [] as string[] }));
  const otros: string[] = [];
  for (const f of ficheros) {
    // «3_formulacion_pide_<token>.docx»: el número y la clave del módulo, como los escribe el servidor.
    const clave = f.replace(/^\d+_/, '');
    const g = grupos.find((x) => x.claves.some((c) => clave.startsWith(`${c}_`)));
    (g ? g.ficheros : otros).push(f);
  }
  return [...grupos.filter((g) => g.ficheros.length).map(({ titulo, ficheros: fs }) => ({ titulo, ficheros: fs })),
    ...(otros.length ? [{ titulo: 'Documentos del estudio', ficheros: otros }] : [])];
}

function ResultadoPIDE({ r, ws, decidir, tipos }: { r: PideResultado; ws: string;
  decidir: (o: ObraPIDE, d: 'aceptada' | 'rechazada' | 'modificada') => void; tipos: TiposAnalisis | null }) {
  return (
    <div className="alert">
      {r.avisos.map((x) => <p key={x} className="alert alert-warn">{x}</p>)}
      <p className="small">Años: {r.anios.map((a) => `${String(a.anio).padStart(2, '0')} (${a.problemas} problema(s), mín. ${fmtNum(a.vm_min ?? null, 3)} p.u.)`).join(' · ')}</p>
      {r.implementadas.map((x) => <p key={x.codigo} className="alert alert-ok">{x.codigo} {x.alternativa}: {x.aviso}</p>)}
      <div className="table-wrap table-short">
        <table className="table">
          <thead><tr><th>Prioridad</th><th>Año</th><th>Rubro</th><th>Obra</th><th>Dónde</th><th>Inversión</th>
            <th>Costo anual</th><th>Estado</th><th>Decisión</th></tr></thead>
          <tbody>{r.obras.map((o) => (
            <tr key={o.codigo}>
              <td>{o.prioridad}</td><td>{String(o.anio).padStart(2, '0')}</td><td className="small">{RUBRO[o.rubro] ?? o.rubro}</td>
              <td className="strong">{o.codigo} · {o.denominacion ?? o.alternativa}</td>
              <td className="small">{o.alimentador} · {o.elemento}</td>
              <td>{fmtNum(o.ci, 0)}</td><td>{fmtNum(o.regulada?.costo_anual ?? null, 0)}</td>
              <td className="small">{o.variacion_autonoma ? `aplicada (${o.variacion_autonoma})`
                : o.descartada ?? (o.sobredimensionada ? 'sobredimensionada' : o.motivo_sin_obra ?? 'propuesta')}</td>
              <td><div className="chips">
                {(['aceptada', 'rechazada', 'modificada'] as const).map((d) => (
                  <button key={d} className="chip" onClick={() => decidir(o, d)}>{d}</button>))}
              </div></td>
            </tr>))}</tbody>
        </table>
      </div>
      <a className="btn btn-sm btn-ghost" href={api.fileUrl(ws, r.formatos, true)}>Formatos 01 a 15 · {r.formatos}</a>
      {porEntregable(r.informes_planeamiento ?? [], tipos).map((g) => (
        <div key={g.titulo} className="row"><span className="small strong">{g.titulo}:</span>
          {g.ficheros.map((f) => <a key={f} className="btn btn-sm btn-ghost" href={api.fileUrl(ws, f, true)}>{f}</a>)}</div>))}
      {r.con_y_sin && (
        <p className="small">Con y sin proyecto: {r.con_y_sin.hueco
          ?? `VAN ${fmtNum(r.con_y_sin.van ?? null, 0)}, TIR ${r.con_y_sin.tir != null ? `${fmtNum(r.con_y_sin.tir * 100, 2)} %` : 'no tiene'}; solo mide el ahorro de pérdidas`}</p>)}
      {r.huecos && r.huecos.length > 0 && (
        <details><summary className="small">Datos que faltan en los formatos ({r.huecos.length})</summary>
          <ul className="small">{r.huecos.map((h) => (
            <li key={`${h.formato}-${h.campo}-${h.motivo}`}>{h.formato}{h.campo ? ` · ${h.campo}` : ''}: {h.motivo}</li>))}</ul>
        </details>)}
    </div>
  );
}

/** 072:RF-25, 072:RF-28: obras físicas explícitas, ninguna inferida por su nombre. */
export function cuerpoPideAnual(project: string, feeders: string[], fuentes: PideFuentes,
  estudio: string, fin: number, texto: string): PideSolicitud {
  if (!project || !feeders.length) throw new Error('Elija proyecto y alimentadores.');
  if (!/^[A-Za-z0-9][A-Za-z0-9_.-]{0,79}$/.test(estudio)) throw new Error('Indique un identificador de estudio nuevo.');
  if (!Number.isInteger(fin) || fin <= fuentes.corto_plazo.anio) throw new Error('El año final debe continuar el corto plazo.');
  const obras = texto.split(/\r?\n/).filter((x) => x.trim()).map((linea) => {
    const partes = linea.split('|');
    const anio = Number(partes[0]?.trim()); const variacion = partes[1]?.trim() ?? '';
    if (partes.length !== 2 || !Number.isInteger(anio) || anio <= fuentes.corto_plazo.anio || anio > fin ||
      !/[\\/]/.test(variacion) || !variacion.endsWith('.IntScheme')) {
      throw new Error('Cada obra requiere año relativo e identidad completa de variación física, separados por |.');
    }
    return { anio, variacion };
  });
  if (new Set(obras.map((o) => o.variacion)).size !== obras.length) throw new Error('Una obra física no puede repetirse.');
  return { project, feeders, modo: 'anual', anual: { estudio_id: estudio, anio_fin: fin,
    corto_plazo: fuentes.corto_plazo, proyeccion_anual: fuentes.proyeccion_anual, obras_por_anio: obras } };
}

/** 072:RF-18, 072:RF-24: archivos del operador; subir no es aceptar el modelo. */
export function FormularioPideAnual({ ws, project, feeders, busy, planificar }: {
  ws: string; project: string; feeders: string[]; busy: boolean;
  planificar: (body: PideSolicitud) => Promise<unknown> }) {
  const [perfil, setPerfil] = useState<File | null>(null);
  const [evaluacion, setEvaluacion] = useState<File | null>(null);
  const [corto, setCorto] = useState<File | null>(null);
  const [fuentes, setFuentes] = useState<PideFuentes | null>(null);
  const [estudio, setEstudio] = useState(''); const [fin, setFin] = useState('');
  const [obras, setObras] = useState(''); const [error, setError] = useState('');
  const [subiendo, setSubiendo] = useState(false);
  const subir = async () => {
    if (!perfil || !evaluacion || !corto) { setError('Seleccione los tres archivos JSON.'); return; }
    setError(''); setSubiendo(true); setFuentes(null);
    try { setFuentes(await api.pideFuentes(ws, perfil, evaluacion, corto)); }
    catch (e) { setError(e instanceof Error ? e.message : String(e)); }
    finally { setSubiendo(false); }
  };
  const iniciar = async () => {
    try {
      if (!fuentes) throw new Error('Cargue las tres fuentes del estudio.');
      const body = cuerpoPideAnual(project, feeders, fuentes, estudio.trim(), Number(fin), obras);
      setError(''); await planificar(body);
    } catch (e) { setError(e instanceof Error ? e.message : String(e)); }
  };
  return <section>
    <p className="muted">Continúa copias del corto plazo con demanda P/Q anual aceptada por carga y, cuando corresponde,
      por fase. Cada obra se conserva en los años siguientes. Sin evaluación anual aceptada, datos físicos completos
      u obra suficiente, el estudio se bloquea. No se extrapola el pronóstico de 28 días.</p>
    <fieldset disabled={busy || subiendo}>
      <legend>Fuentes del estudio anual</legend>
      <div className="row">
        <label className="field grow"><span>Perfil anual (JSON)</span><input type="file" accept=".json,application/json"
          onChange={(e) => { setPerfil(e.target.files?.[0] ?? null); setFuentes(null); }} /></label>
        <label className="field grow"><span>Evaluación del modelo (JSON)</span><input type="file" accept=".json,application/json"
          onChange={(e) => { setEvaluacion(e.target.files?.[0] ?? null); setFuentes(null); }} /></label>
        <label className="field grow"><span>Evidencia del corto plazo (JSON)</span><input type="file" accept=".json,application/json"
          onChange={(e) => { setCorto(e.target.files?.[0] ?? null); setFuentes(null); }} /></label>
        <button className="btn btn-ghost" disabled={!perfil || !evaluacion || !corto} onClick={() => void subir()}>Cargar fuentes</button>
      </div>
      <p className="small muted">La evaluación debe identificar modelo, dataset, año base y horizonte anual aceptado.
        Subir estos archivos conserva su procedencia; no concede aceptación científica.</p>
      {fuentes && <div className="alert"><p>Corto plazo: año {fuentes.corto_plazo.anio}, base {fuentes.corto_plazo.anio_base}.</p>
        <p className="small">Caso: {fuentes.corto_plazo.caso}<br />Escenario: {fuentes.corto_plazo.escenario}</p>
        <p className="small">Obras iniciales: {fuentes.corto_plazo.variaciones.join(' · ') || 'ninguna declarada'}</p>
        <FuentesPide fuentes={fuentes.fuentes} /></div>}
      <div className="row">
        <label className="field grow"><span>Identificador del estudio (nuevo)</span><input value={estudio}
          onChange={(e) => setEstudio(e.target.value)} placeholder="Identificador único, sin sobrescribir estudios" /></label>
        <label className="field"><span>Año relativo final</span><input type="number" min={(fuentes?.corto_plazo.anio ?? 4) + 1}
          value={fin} onChange={(e) => setFin(e.target.value)} /></label>
      </div>
      <label className="field"><span>Obras físicas por año</span><textarea value={obras} rows={4}
        onChange={(e) => setObras(e.target.value)} placeholder="Una línea por obra: año relativo | identidad completa de variación física" /></label>
      <p className="small muted">Use las variaciones físicas ya preparadas en el proyecto. Puede dejar la lista vacía para
        diagnosticar; ante el primer incumplimiento sin obra suficiente, el estudio se detiene y lo informa.</p>
      <button className="btn btn-pf" disabled={!project || !fuentes} onClick={() => void iniciar()}>Continuar año a año</button>
      <p className="small muted">Cancelar en el Registro termina la etapa en curso y restituye el estado original;
        conserva el informe y las copias parciales. La restitución se confirma por relectura.</p>
    </fieldset>
    {error && <p role="alert" className="alert alert-err">{error}</p>}
  </section>;
}

function FuentesPide({ fuentes }: { fuentes: Record<string, unknown> }) {
  return <details><summary>Fuentes y huellas</summary><dl className="small">
    {Object.entries(fuentes).map(([k, v]) => <div key={k}><dt>{k.replaceAll('_', ' ')}</dt><dd>{String(v)}</dd></div>)}
  </dl></details>;
}

/** 072:RF-26, 072:RF-27: conserva resultado parcial y separa las aceptaciones. */
export function VistaPideAnual({ r, ws }: { r: PideAnualResultado; ws: string }) {
  const medida = (m?: PideAnualResultado['anios'][number]['antes']) => m
    ? `${m.converge ? 'Converge' : 'No converge'} · ${m.cumple ? 'Cumple' : 'Incumple'} · ${m.problemas.length} problema(s)`
    : 'Sin medir';
  return <section className="alert">
    <h4>Resultado anual: {r.estado.replaceAll('_', ' ')}</h4>
    <p className="small">Proyecto: {r.project} · Alimentadores: {r.feeders.join(' · ')}</p>
    {r.error && <p role="alert" className="alert alert-err">{r.error}</p>}
    {(r.avisos ?? []).map((a, i) => <p key={i} className="alert alert-warn">{a}</p>)}
    <p>Aceptación nativa pendiente. La ejecución y la convergencia no acreditan aceptación eléctrica o científica.</p>
    <p>Restitución: <strong>{r.restitucion?.ok ? 'Confirmada por relectura' : 'Sin confirmar'}</strong>
      {r.restitucion?.diferencias.length ? ` · ${r.restitucion.diferencias.join(' · ')}` : ''}</p>
    {r.primer_anio_incumplimiento != null && <p>Primer incumplimiento: año relativo {r.primer_anio_incumplimiento}.</p>}
    <div className="table-wrap"><table className="table"><thead><tr><th>Año</th><th>Antes de obras</th><th>Después</th><th>Obras y casos</th></tr></thead>
      <tbody>{r.anios.map((a) => <tr key={a.anio}><td>{a.anio_calendario} (año {a.anio})</td>
        <td>{medida(a.antes)}</td><td>{medida(a.despues)}</td><td className="small">
          <p>Aplicadas: {a.obras_aplicadas.join(' · ') || 'ninguna'}</p>
          <p>Acumuladas: {a.obras_acumuladas?.join(' · ') || 'sin relectura'}</p>
          {Object.entries(a.casos).map(([rol, caso]) => <p key={rol}>{rol}: {caso}</p>)}</td></tr>)}</tbody></table></div>
    <FuentesPide fuentes={r.fuentes} />
    {r.report && <a className="btn btn-ghost btn-sm" href={api.fileUrl(ws, r.report)} target="_blank" rel="noreferrer">Informe anual JSON</a>}
    <p className="small muted">Pendientes: revisión humana de entregables y costos de la fuente oficial exigida cuando no estén acreditados.</p>
  </section>;
}
