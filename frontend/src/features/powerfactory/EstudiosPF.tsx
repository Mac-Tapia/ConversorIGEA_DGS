import { useCallback, useEffect, useState } from 'react';
import { api } from '../../api/client';
import { useApp } from '../../shared/context';
import type { DiagnosticoCargas, EstadoDiagnostico, EstudiosCatalogo, EstudiosPlan, EstudiosResultado, EstudiosResumen,
  FallaProteccion, Limites, OpcionesEstudios, PropuestaRed, ProteccionesEstado, ProteccionesEvaluacion } from '../../api/types';
import { DatosEmpresaPF } from './DatosEmpresaPF';
import { EntradasEstudios } from './EntradasEstudios';
import { betaActiva } from '../../shared/edicion';
import { GuionesPF } from './GuionesPF';
import { Ayuda, FileDrop, Modal } from '../../shared/ui';

const LIMITES: [keyof Limites, string][] = [
  ['tension_min_pu', 'Tensión mínima (p.u.)'],
  ['tension_max_pu', 'Tensión máxima (p.u.)'],
  ['cargabilidad_max_pct', 'Cargabilidad máxima (%)'],
];

/** Los casos del conversor, con o sin el año de su calibración (025, 037:RF-3). */
const CASO_DEL_CONVERSOR = /^(Sin proyecto|Cargas nuevas|Con proyecto)( \d{4})?$/;

/** 011:RF-135: por defecto, los casos del conversor que tenga el proyecto; si no tiene ninguno, ninguno marcado. */
export function casosPorDefecto(casos: string[]): string[] {
  return casos.filter((c) => CASO_DEL_CONVERSOR.test(c));
}

/** 011:RF-131, RF-135: sin calibración se puede estudiar igual; solo hacen falta estudios y alimentadores. */
export function puedePrepararEstudios({ pfBusy, estudios, alimentadores }: {
  pfBusy: boolean; estudios: number; alimentadores: number;
}): boolean {
  return !pfBusy && estudios > 0 && alimentadores > 0;
}

/** 011:RF-135: los casos de estudio del proyecto, varios a la vez, para elegir en cuáles se estudia. */
export function SelectorCasos({ casos, elegidos, onCambio }: {
  casos: string[]; elegidos: string[]; onCambio: (casos: string[]) => void;
}) {
  if (!casos.length) {
    return <p className="small muted">La lectura de los proyectos (paso 1) no trae sus casos de estudio: vuelva a leerlos
      para elegir otros. Sin elegir ninguno se estudian los del conversor que tenga el proyecto.</p>;
  }
  const alternar = (c: string) => onCambio(elegidos.includes(c)
    ? elegidos.filter((x) => x !== c) : casos.filter((x) => x === c || elegidos.includes(x)));
  return (
    <div>
      <p className="small"><strong>Casos de estudio</strong> ({elegidos.length} de {casos.length}): cualquier caso del
        proyecto de DIgSILENT, tal como está. Sin elegir ninguno se estudian los del conversor.</p>
      <div className="chips" role="group" aria-label="Casos de estudio">
        {casos.map((c) => (
          <button key={c} type="button" className={`chip ${elegidos.includes(c) ? 'on' : ''}`}
            aria-pressed={elegidos.includes(c)} onClick={() => alternar(c)}>{c}</button>
        ))}
      </div>
    </div>
  );
}

/**
 * 4.2 · Estudios (spec 011, RF-17 a RF-41, RF-130 a RF-135).
 *
 * En cualquier caso de estudio del proyecto de DIgSILENT (RF-130): por defecto, los del conversor
 * («Sin proyecto», «Cargas nuevas» y «Con proyecto», 037:RF-3) sobre el último ajuste aplicado (RF-12).
 * Sin calibración se estudia el caso tal como está y se avisa, sin bloquear (RF-131). Cada estudio con su
 * límite de tiempo (RF-39); los que no tienen datos se listan con lo que les falta (RF-24).
 */
export function EstudiosPF({ project, feeders, ajusteJobId, faltaRecalibrar = [], casos = [] }: {
  project: string; feeders: string[]; ajusteJobId: string | null;
  /** 091:RF-21: el orden es calibración, recalibración y estudio; se avisa, sin apagar el botón. */
  faltaRecalibrar?: string[];
  /** 011:RF-134: los casos de estudio del proyecto, de la lectura de proyectos. */
  casos?: string[];
}) {
  const { ws, run, startJob, active, jobs, health } = useApp();
  const [catalogo, setCatalogo] = useState<EstudiosCatalogo | null>(null);
  const [elegidos, setElegidos] = useState<string[]>(['flujo']);
  // Al cambiar de proyecto, o al releerlo, se vuelve a los del conversor que tenga.
  const claveCasos = casos.join('\n');
  const [casosElegidos, setCasosElegidos] = useState<string[]>(() => casosPorDefecto(casos));
  useEffect(() => setCasosElegidos(casosPorDefecto(claveCasos ? claveCasos.split('\n') : [])), [project, claveCasos]);
  const [limites, setLimites] = useState<Record<string, string>>({});
  const [minutos, setMinutos] = useState('');
  const [plan, setPlan] = useState<EstudiosPlan | null>(null);
  // Spec 012: objetivo y máximos de reconectadores, crecimiento conjunto y contingencias PV.
  const [opciones, setOpciones] = useState<OpcionesEstudios>({ objetivo: 'ens', max_total: 3, max_por_alimentador: 1 });
  const pfBusy = Boolean(active.powerfactory);

  // 012:RF-19, RF-4: el catálogo depende del libro del proyecto y de la licencia.
  const cargar = useCallback(() => {
    void run(() => api.estudiosCatalogo(ws.id, project)).then((c) => {
      if (!c) return;
      setCatalogo(c);
      const ofrecidas = new Set(c.ofrecidos.map((e) => e.clave));
      setElegidos((xs) => xs.filter((x) => ofrecidas.has(x)));
      // RF-35: los del perfil de empresa, que el operador puede cambiar.
      if (c.limites) setLimites(Object.fromEntries(LIMITES.map(([k]) => [k, String(c.limites![k])])));
      setMinutos(String(Math.round(c.limite_s / 60)));
    });
  }, [run, ws.id, project]);
  useEffect(cargar, [cargar]);

  const ultima = Object.values(jobs).filter((j) => j.kind === 'estudios' && j.result
    && (j.result as { project?: string }).project === project).pop();   // 091:RF-23
  const resultado = (ultima?.result ?? null) as EstudiosResultado | null;

  const preparar = async () => {
    const cambiados: Partial<Limites> = {};
    for (const [k] of LIMITES) {
      const n = Number((limites[k] ?? '').trim().replace(',', '.'));
      if (catalogo?.limites && limites[k] !== String(catalogo.limites[k]) && !Number.isNaN(n)) {
        (cambiados as Record<string, number>)[k] = n;
      }
    }
    const m = Number(minutos.trim().replace(',', '.'));
    const p = await run(() => api.estudiosPlan(ws.id, {
      project, feeders, estudios: elegidos, ajuste_job_id: ajusteJobId, limites: cambiados,
      limite_s: Number.isFinite(m) && m > 0 ? m * 60 : null, opciones, casos: casosElegidos,
    }));
    if (p) setPlan(p);
  };
  const ejecutar = async () => {
    if (!plan) return;
    const job = await startJob(() => api.estudiosEjecutar(ws.id, plan.token));
    if (job) setPlan(null);
  };

  if (!catalogo) return <p className="muted">Cargando el catálogo de estudios…</p>;
  return (
    <div>
      <p className="muted">Se estudia cualquier caso del proyecto de DIgSILENT. Por defecto, los del conversor:</p>
      <ul className="small">
        <li><strong>«Sin proyecto»</strong>: la red calibrada y las demandas existentes.</li>
        <li><strong>«Cargas nuevas»</strong>: la misma red con las cargas nuevas que permiten converger,
          sin las obras exclusivas de «Con proyecto». Se informan las cargas excluidas.</li>
        <li><strong>«Con proyecto»</strong>: las cargas nuevas y las obras de mejora activas.</li>
      </ul>
      <Ayuda>Sin cargas nuevas se omite el diagnóstico; sin cargas ni obras se estudia solo «Sin proyecto». Un caso que no
        existe se informa y se sigue con los demás. Lo que proponen los optimizadores se informa, no se aplica.</Ayuda>
      <SelectorCasos casos={casos} elegidos={casosElegidos} onCambio={setCasosElegidos} />
      {!ajusteJobId && <p className="alert alert-warn">No hay ningún ajuste a la máxima aplicado en este proyecto: se estudia
        cada caso tal como está en DIgSILENT, sin comparar la cabecera con los objetivos de una calibración. Puede
        calibrar antes en el paso 2.</p>}
      {ajusteJobId && faltaRecalibrar.length > 0 && <p className="alert alert-warn">{faltaRecalibrar.join(', ')}: solo
        tiene la calibración. El orden es calibración, recalibración y estudio: recalibre en el paso 2.4. Puede preparar
        los estudios igual; el plan lo anota.</p>}
      <div className="chips">
        {catalogo.ofrecidos.map((e) => (
          <button key={e.clave} type="button" className={`chip ${elegidos.includes(e.clave) ? 'on' : ''}`}
            onClick={() => setElegidos((xs) => (xs.includes(e.clave) ? xs.filter((x) => x !== e.clave) : [...xs, e.clave]))}>
            {e.nombre}
          </button>
        ))}
      </div>
      {betaActiva(health, 'confiabilidad') && <DatosEmpresaPF project={project} feeders={feeders} libro={catalogo.datos_empresa} onCambio={cargar} />}
      <OpcionesRed elegidos={elegidos} opciones={opciones} setOpciones={setOpciones} />
      {catalogo.no_ofrecidos.length > 0 && (
        <details><summary className="muted">No disponibles todavía ({catalogo.no_ofrecidos.length})</summary>
          <ul className="small">{catalogo.no_ofrecidos.map((e) => <li key={e.clave}><strong>{e.nombre}</strong>: {e.motivo}</li>)}</ul>
        </details>
      )}
      {/* 012:RF-73 a RF-82: lo que falta a cada estudio se carga aquí, en TXT, PDF o imagen. */}
      <EntradasEstudios project={project} noOfrecidos={catalogo.no_ofrecidos} onCambio={cargar} />
      {catalogo.error_limites && <p className="alert alert-error">{catalogo.error_limites}</p>}
      <div className="form-grid">
        {LIMITES.map(([k, label]) => (
          <label key={k} className="field">
            <span>{label}</span>
            <input value={limites[k] ?? ''} inputMode="decimal"
              onChange={(e) => setLimites((x) => ({ ...x, [k]: e.target.value }))} />
          </label>
        ))}
        <label className="field">
          <span>Límite de tiempo por estudio y caso (min)</span>
          <input value={minutos} inputMode="decimal" onChange={(e) => setMinutos(e.target.value)} />
          <small className="muted">Un estudio que lo pasa se detiene y se sigue con el siguiente.</small>
        </label>
      </div>
      {catalogo.limites && <small className="muted">Límites de partida: {catalogo.limites.origen === 'perfil'
        ? 'los del perfil de empresa' : 'los de por defecto (sin perfil de empresa)'}.</small>}
      <div className="row">
        <button className="btn btn-primary"
          disabled={!puedePrepararEstudios({ pfBusy, estudios: elegidos.length, alimentadores: feeders.length })}
          onClick={preparar}>Preparar los estudios ({elegidos.length})</button>
      </div>
      {resultado && <ResultadoEstudios r={resultado} cancelado={ultima?.status === 'cancelled'} />}
      {/* RF-27 a RF-30: los guiones del operador, en la misma parte de los estudios. */}
      <GuionesPF project={project} />
      {/* Spec 049: las protecciones, con lo que les falta; nunca se juzgan por el flujo (RF-10). */}
      <DiagnosticoDeCargas project={project} feeders={feeders} />
      <ProteccionesPF project={project} feeders={feeders} />

      {plan && (
        <Modal title={`Estudios en ${plan.project}`} onClose={() => setPlan(null)} actions={<>
          <button className="btn" onClick={() => setPlan(null)}>Cerrar</button>
          <button className="btn btn-pf" disabled={pfBusy} onClick={ejecutar}>Ejecutar en DIgSILENT</button>
        </>}>
          <p>Alimentadores: {plan.feeders.join(', ')} · {plan.estudios.length} estudio(s).
            Orden de casos: {plan.casos.join(' → ')}. Hasta {Math.round(plan.limite_s / 60)} min por estudio y caso.</p>
          <Ayuda>«Cargas nuevas» se ejecuta si hay cargas nuevas; «Con proyecto», si hay cargas u obras.
            El diagnóstico se renueva con la calibración actual y muestra las cargas que no permiten converger.</Ayuda>
          {plan.avisos.map((a) => <p key={a} className="alert alert-warn">{a}</p>)}
          {plan.excluidos.length > 0 && (
            <div className="alert alert-warn"><strong>Fuera de los estudios:</strong>
              <ul>{plan.excluidos.map((x) => <li key={x.feeder}>{x.feeder}: {x.motivo}</li>)}</ul></div>
          )}
        </Modal>
      )}
    </div>
  );
}

function ResultadoEstudios({ r, cancelado }: { r: EstudiosResultado; cancelado: boolean }) {
  const { ws, run } = useApp();
  const [resumen, setResumen] = useState<EstudiosResumen | null>(null);
  // Sin calibración no se preparan los casos del conversor: «casos» llega vacío y sin diagnóstico (011:RF-131).
  const diagnostico = r.casos.cargas_nuevas;
  // 017:RF-142: con lo que la corrida guardó; no se vuelve a DIgSILENT.
  const token = r.token;
  const pedirResumen = async () => {
    if (!token) return;
    const hecho = await run(() => api.estudiosResumen(ws.id, token));
    if (hecho) setResumen(hecho);
  };
  return (
    <div className="alert">
      <p><strong>Estudios en {r.project}</strong> · {r.feeders.join(', ')}</p>
      {(r.cancelado || cancelado) && <p className="alert alert-warn">Cancelado: se conservan los estudios terminados.</p>}
      {(r.casos.avisos ?? []).map((a) => <p key={a} className="alert alert-warn">{a}</p>)}
      {diagnostico && <div className="small">
        <p><strong>«{diagnostico.caso}»</strong>: {diagnostico.activas.length} carga(s) activa(s).</p>
        {diagnostico.no_convergen.length > 0 && <div className="alert alert-warn">
          <strong>Cargas excluidas del diagnóstico:</strong>
          <ul>{diagnostico.no_convergen.map((c) => <li key={c.variacion}>{c.texto || c.variacion}</li>)}</ul>
        </div>}
      </div>}
      <div className="table-wrap table-short">
        <table className="table">
          <thead><tr><th>Caso</th><th>Estudio</th><th>Obras activas</th><th>Estado</th></tr></thead>
          <tbody>{r.estudios.map((e) => (
            <tr key={`${e.caso}-${e.estudio}`}><td>{e.nombre_caso || e.caso}</td><td className="strong">{e.estudio}</td>
              <td className="mono small">{e.obras_activas.length ? e.obras_activas.join(', ') : 'ninguna'}</td>
              <td className="small">{e.no_terminado ? <span className="badge err">no terminó en su límite</span>
                : e.error ? <span className="badge err">{e.error}</span> : 'hecho'}
                {e.avisos.map((a) => <div key={a} className="muted">{a}</div>)}</td></tr>
          ))}</tbody>
        </table>
      </div>
      {r.libro && <p className="muted small">Con el libro {r.libro.nombre}, cargado el {(r.libro.cargado ?? '').replace('T', ' ')}.</p>}
      {r.red && r.red.length > 0 && <TablaRed r={r} />}
      {r.propuestas && r.propuestas.length > 0 && <Propuestas propuestas={r.propuestas} />}
      {r.ficheros.length > 0 && (
        <p>Ficheros: {r.ficheros.map((f) => (
          <a key={f} className="btn btn-sm btn-ghost" href={api.fileUrl(ws.id, f, true)}>{f}</a>))}</p>
      )}
      <ResumenEjecutivo token={token} resumen={resumen} onPedir={pedirResumen}
        enlace={(f) => api.fileUrl(ws.id, f, true)} />
    </div>
  );
}

/** 017:RF-142, RF-143: el botón del resumen ejecutivo de la corrida y sus ficheros, cuando están. */
export function ResumenEjecutivo({ token, resumen, onPedir, enlace }: {
  token?: string; resumen: EstudiosResumen | null; onPedir: () => void; enlace: (fichero: string) => string;
}) {
  return (
    <div>
      <div className="row">
        <button className="btn" disabled={!token} onClick={onPedir}
          title={token ? undefined : 'Esta corrida es anterior al resumen: vuelva a ejecutar los estudios.'}>
          Resumen ejecutivo</button>
        {resumen && <a className="btn btn-sm btn-ghost" href={enlace(resumen.docx)}>{resumen.docx}</a>}
        {resumen?.xlsx && <a className="btn btn-sm btn-ghost" href={enlace(resumen.xlsx)}>{resumen.xlsx}</a>}
      </div>
      {resumen && <ul className="small">{resumen.conclusiones.map((c) => <li key={c}>{c}</li>)}</ul>}
    </div>
  );
}

/** Opciones de los estudios de la spec 012, solo las de los elegidos (RF-37, RF-45, RF-53). */
function OpcionesRed({ elegidos, opciones, setOpciones }: {
  elegidos: string[]; opciones: OpcionesEstudios; setOpciones: (o: OpcionesEstudios) => void;
}) {
  const poner = (cambio: Partial<OpcionesEstudios>) => setOpciones({ ...opciones, ...cambio });
  const entero = (v: string) => Math.max(1, Math.round(Number(v) || 1));
  return (
    <div className="form-grid">
      {elegidos.includes('reconectadores') && <>
        <label className="field"><span>Reconectadores: minimizar</span>
          <select value={opciones.objetivo} onChange={(e) => poner({ objetivo: e.target.value as 'ens' | 'saidi' })}>
            <option value="ens">ENS (energía no suministrada)</option><option value="saidi">SAIDI</option>
          </select></label>
        <label className="field"><span>Reconectadores en total (máx.)</span>
          <input inputMode="numeric" value={opciones.max_total ?? ''} onChange={(e) => poner({ max_total: entero(e.target.value) })} /></label>
        <label className="field"><span>Por alimentador (máx.)</span>
          <input inputMode="numeric" value={opciones.max_por_alimentador ?? ''}
            onChange={(e) => poner({ max_por_alimentador: entero(e.target.value) })} /></label>
      </>}
      {elegidos.includes('alojamiento') && (
        <label className="field"><span>Capacidad de alojamiento</span>
          <span><input type="checkbox" checked={Boolean(opciones.conjunto)} onChange={(e) => poner({ conjunto: e.target.checked })} />{' '}
            también el crecimiento conjunto de las cargas escalables</span></label>)}
      {elegidos.includes('curvas_pv') && (
        <label className="field"><span>Curvas PV</span>
          <span><input type="checkbox" checked={Boolean(opciones.contingencias)}
            onChange={(e) => poner({ contingencias: e.target.checked })} /> con las N-1 de la troncal</span></label>)}
    </div>
  );
}

const fmt = (v: unknown) => (typeof v === 'number' ? v.toLocaleString('es', { maximumFractionDigits: 3 }) : v == null ? '—' : String(v));

/** Una fila por caso, alimentador y estudio de la spec 012, con la diferencia (RF-30, RF-31, RF-47, RF-52, RF-56). */
function TablaRed({ r }: { r: EstudiosResultado }) {
  const columnas: [string, string][] = [['saifi', 'SAIFI'], ['saidi', 'SAIDI'], ['caidi', 'CAIDI'], ['ens_kwh', 'ENS (kWh/a)'],
    ['reconectadores', 'Reconect.'], ['capacidad_gd_min_kw', 'GD mín. (kW)'], ['capacidad_carga_min_kw', 'Carga mín. (kW)'],
    ['margen_kw', 'Margen PV (kW)'], ['barra_critica', 'Barra crítica'], ['kvar_propuestos', 'kvar propuestos'],
    ['ahorro_anual', 'Ahorro anual'], ['coste_anual', 'Coste anual']];
  const usadas = columnas.filter(([k]) => r.red!.some((f) => f[k] != null));
  const c = r.comparacion_ens;
  return (
    <>
      {c && c.ens_total_diferencia_kwh != null && <p className="small">ENS total de los marcados: {fmt(c.ens_total_kwh['Sin proyecto'])} →{' '}
        {fmt(c.ens_total_kwh['Con proyecto'])} kWh/a ({c.ens_total_diferencia_kwh >= 0 ? '+' : ''}{fmt(c.ens_total_diferencia_kwh)} kWh/a
        {c.ens_total_diferencia_pct != null && `, ${c.ens_total_diferencia_pct >= 0 ? '+' : ''}${fmt(c.ens_total_diferencia_pct)} %`}).</p>}
      <div className="table-wrap table-short">
        <table className="table">
          <thead><tr><th>Caso</th><th>Alimentador</th><th>Estudio</th>{usadas.map(([, t]) => <th key={t}>{t}</th>)}<th>Nota</th></tr></thead>
          <tbody>{r.red!.map((f) => (
            <tr key={`${f.caso}-${f.alimentador}-${f.estudio}`}><td>{f.caso}</td><td>{f.alimentador}</td><td>{f.estudio}</td>
              {usadas.map(([k]) => <td key={k} className="num">{fmt(f[k])}</td>)}
              <td className="small">{f.fiable === false ? <span className="badge err">no fiable</span> : null} {f.motivo ? String(f.motivo) : ''}</td></tr>
          ))}</tbody>
        </table>
      </div>
    </>
  );
}

/** Reconectadores y bancos propuestos; aceptar uno lo deja como obra de 4.1 (RF-40, RF-58). */
function Propuestas({ propuestas }: { propuestas: PropuestaRed[] }) {
  const { ws, run, refresh } = useApp();
  const [aceptadas, setAceptadas] = useState<Set<number>>(new Set());
  const aceptar = async (p: PropuestaRed, i: number) => {
    const obra = p.tipo === 'reconectador'
      ? { clase: 'reconectador' as const, alimentador: p.alimentador, casos: ['Con proyecto'], tramo: p.tramo ?? '' }
      : { clase: 'condensador' as const, alimentador: p.alimentador, casos: ['Con proyecto'], barra: p.nodo ?? '',
          q_kvar: p.kvar ?? 0, escalones: p.pasos ?? 1 };
    if (await run(() => api.obraAnadir(ws.id, obra))) {
      setAceptadas((s) => new Set(s).add(i));
      await refresh();                     // 4.1 la muestra junto a las demás obras
    }
  };
  return (
    <div className="table-wrap table-short">
      <table className="table">
        <thead><tr><th>Propuesta</th><th>Caso</th><th>Alimentador</th><th>Dónde</th><th>Detalle</th><th /></tr></thead>
        <tbody>{propuestas.map((p, i) => (
          <tr key={`${p.tipo}-${p.caso}-${p.alimentador}-${p.elemento ?? p.nodo}`}>
            <td>{p.tipo === 'reconectador' ? 'Reconectador' : 'Banco de condensadores'}</td><td>{p.caso}</td><td>{p.alimentador}</td>
            <td className="mono small">{p.tipo === 'reconectador' ? `${p.elemento} (tramo ${p.tramo ?? '—'})` : p.nodo}</td>
            <td className="small">{p.tipo === 'reconectador'
              ? `mejora del conjunto: ${fmt(p.mejora_kwh)} kWh/a` : `${fmt(p.kvar)} kvar en ${p.pasos} paso(s) · coste anual ${fmt(p.coste_anual)}`}</td>
            <td>{aceptadas.has(i) ? <span className="badge ok">en 4.1</span>
              : <button className="btn btn-sm" disabled={p.tipo === 'reconectador' && !p.tramo}
                  onClick={() => aceptar(p, i)}>Aceptar como obra</button>}</td>
          </tr>
        ))}</tbody>
      </table>
    </div>
  );
}

const ESTADO_PROTECCIONES: Record<ProteccionesEvaluacion['estado'], [string, string]> = {
  cumple: ['ok', 'cumple los criterios del perfil'],
  no_cumple: ['err', 'no cumple'],
  parcial: ['warn', 'parcial: hay fallas o criterios sin evaluar'],
  bloqueado: ['err', 'bloqueado: ninguna falla evaluada'],
};
const TIPOS_FALLA: [FallaProteccion['tipo'], string][] = [
  ['trifasica', 'Trifásica'], ['bifasica', 'Bifásica'], ['monofasica', 'Monofásica'], ['bifasica_tierra', 'Bifásica a tierra'],
];

/**
 * Protecciones (spec 049): disponibilidad con la lista concreta de lo que falta (RF-2), las
 * capacidades de la versión conectada (RF-1) y, si todo está, las fallas y su coordinación
 * (RF-5 a RF-7). Un flujo convergente no es selectividad: se dice siempre (RF-10).
 */
function ProteccionesPF({ project, feeders }: { project: string; feeders: string[] }) {
  const { ws, run, startJob, active, jobs } = useApp();
  const [estado, setEstado] = useState<ProteccionesEstado | null>(null);
  const [licencia, setLicencia] = useState(false);
  const [barras, setBarras] = useState('');
  const [tipo, setTipo] = useState<FallaProteccion['tipo']>('trifasica');
  const [periodo, setPeriodo] = useState('');
  const pfBusy = Boolean(active.powerfactory);
  // Se vuelve a leer al terminar cada trabajo de protecciones del espacio.
  const hechos = Object.values(jobs).filter((j) => j.kind.startsWith('protecciones_') && j.status === 'done').length;

  useEffect(() => {
    if (!project) return;
    void run(() => api.protecciones(ws.id, project)).then((e) => { if (e) setEstado(e); });
  }, [run, ws.id, project, hechos]);

  if (!project || !estado) return null;
  const d = estado.disponibilidad;
  const comprobar = () => startJob(() => api.proteccionesCapacidades(ws.id, { project, feeders, ejecutar_ordenes: licencia }));
  const fallas: FallaProteccion[] = barras.split(/[,;\s]+/).map((b) => b.trim()).filter(Boolean)
    .map((b) => ({ id: `${b}_${tipo}`, tipo, ubicacion: b, fase: tipo === 'monofasica' ? 'a' : null, r_ohm: 0, x_ohm: 0 }));
  const ejecutar = () => startJob(() => api.proteccionesEjecutar(ws.id, {
    project, feeders, caso: estado.capacidades?.caso ?? '', periodo, fallas }));
  return (
    <details className="card" open={!d.disponible}>
      <summary><strong>Protecciones</strong>{' '}
        {/* 049:RF-2: lo que falta se carga aquí mismo; no es un bloqueo (usuario, 2026-11-13). */}
        <span className={`badge ${d.disponible ? 'ok' : 'warn'}`}>{d.disponible ? 'disponible' : 'faltan datos'}</span></summary>
      <p className="alert alert-warn">{estado.aviso}</p>
      {!d.disponible && <>
        {d.faltan.length > 0 && <><p className="small"><strong>Faltan datos:</strong></p>
          <ul className="small">{d.faltan.map((f) => <li key={f}>{f}</li>)}</ul></>}
        {d.bloqueos.length > 0 && <><p className="small"><strong>DIgSILENT no lo ha comprobado:</strong></p>
          <ul className="small">{d.bloqueos.map((b) => <li key={b}>{b}</li>)}</ul></>}
      </>}
      <AjustesProtecciones project={project} onGuardado={setEstado} />
      {estado.capacidades
        ? <p className="small muted">Comprobado en DIgSILENT {estado.capacidades.version ?? '(versión desconocida)'},
          caso «{estado.capacidades.caso}»{estado.capacidades.comprobado ? `, ${estado.capacidades.comprobado}` : ''}:{' '}
          {Object.entries(estado.capacidades.dispositivos).map(([c, n]) => `${n} ${c}`).join(', ')}.</p>
        : <p className="small muted">Las capacidades de la versión conectada aún no se han comprobado.</p>}
      <div className="row">
        <label className="check"><input type="checkbox" checked={licencia} onChange={(e) => setLicencia(e.target.checked)} />
          {' '}Ejecutar el cortocircuito para comprobar la licencia</label>
        <button className="btn" disabled={pfBusy} onClick={comprobar}>Comprobar capacidades</button>
      </div>
      {d.disponible && <div className="form-grid">
        <label className="field"><span>Barras con falla</span>
          <input value={barras} onChange={(e) => setBarras(e.target.value)} placeholder="separadas por comas" /></label>
        <label className="field"><span>Tipo de falla</span>
          <select value={tipo} onChange={(e) => setTipo(e.target.value as FallaProteccion['tipo'])}>
            {TIPOS_FALLA.map(([k, t]) => <option key={k} value={k}>{t}</option>)}</select></label>
        <label className="field"><span>Mes de análisis (AAAA-MM)</span>
          <input value={periodo} onChange={(e) => setPeriodo(e.target.value)} /></label>
        <button className="btn btn-primary" disabled={pfBusy || !fallas.length || !/^\d{4}-\d{2}$/.test(periodo)}
          onClick={ejecutar}>Estudiar {fallas.length} falla(s)</button>
      </div>}
      {Object.entries(estado.evaluaciones).map(([rol, e]) => <EvaluacionProtecciones key={rol} rol={rol} e={e} />)}
      {estado.comparacion?.error && <p className="small muted">Sin comparación entre casos: {estado.comparacion.error}.</p>}
    </details>
  );
}

/** Los campos de un dispositivo que el operador confirma, con su tipo (049:RF-3). */
const CAMPOS_AJUSTE: [string, string, 'texto' | 'numero' | string[]][] = [
  ['id', 'Equipo', 'texto'], ['clase', 'Clase', ['rele', 'reconectador', 'fusible']], ['cubiculo', 'Cubículo', 'texto'],
  ['fabricante', 'Fabricante', 'texto'], ['modelo', 'Modelo', 'texto'], ['curva', 'Curva', 'texto'],
  ['arranque', 'Arranque', 'numero'], ['unidad_arranque', 'Unidad', ['A', 'A sec', 'pu']], ['dial', 'Dial', 'numero'],
  ['unidad_dial', 'Unidad del dial', ['dial', 's']], ['ct_primario_a', 'TC primario (A)', 'numero'],
  ['ct_secundario_a', 'TC secundario (A)', 'numero'], ['poder_corte_ka', 'Poder de corte (kA)', 'numero'],
];

interface LecturaAjuste { fichero: string; dispositivo: Record<string, unknown>; faltan: string[]; errores: string[]; avisos: string[] }

/**
 * 049:RF-2: los ficheros de ajustes del relé y el reconectador del alimentador se cargan aquí, se leen en un trabajo y el
 * operador confirma o completa cada dato antes de guardarlo. Antes solo cabía la hoja «Protecciones» del libro de la
 * empresa, en otra pestaña, y esta sección decía «bloqueado» (usuario, 2026-11-13).
 */
function AjustesProtecciones({ project, onGuardado }: { project: string; onGuardado: (e: ProteccionesEstado) => void }) {
  const { ws, run, startJob, jobs } = useApp();
  const ultimo = Object.values(jobs).filter((j) => j.kind === 'protecciones_ajustes').pop();
  const [filas, setFilas] = useState<LecturaAjuste[]>([]);
  const leido = ultimo?.status === 'done' ? (ultimo.result as { lecturas?: LecturaAjuste[] } | null) : null;
  useEffect(() => { if (leido?.lecturas) setFilas(leido.lecturas); }, [ultimo?.id, ultimo?.status]);  // eslint-disable-line react-hooks/exhaustive-deps
  const cambiar = (i: number, campo: string, valor: string, tipo: CampoTipo) => setFilas((fs) => fs.map((f, k) => k !== i ? f
    : { ...f, dispositivo: { ...f.dispositivo, [campo]: tipo === 'numero' ? (valor.trim() === '' ? null : Number(valor.replace(',', '.'))) : valor } }));
  const guardar = async () => {
    const r = await run(() => api.proteccionesDispositivos(ws.id, project, filas.map((f) => f.dispositivo)));
    if (r) { onGuardado(r); setFilas([]); }
  };
  return (
    <div className="stack">
      <p className="small"><strong>Ajustes de los equipos del alimentador</strong> — los ficheros del relé o del
        reconectador (TXT, PDF, foto o escaneo en JPG o PNG, o los de su programa); se leen y usted confirma cada dato antes de guardarlo.</p>
      <FileDrop compact accept=".txt,.pdf,.csv,.set,.rdb,.jpg,.jpeg,.png,.tif,.tiff,.bmp,.webp" multiple
        onFiles={(files) => void startJob(() => api.proteccionesAjustes(ws.id, project, files))}>
        <span>Soltar o <u>elegir</u> los ficheros de ajustes</span>
      </FileDrop>
      {filas.length > 0 && <>
        <div className="table-wrap">
          <table className="table">
            <thead><tr><th>Fichero</th>{CAMPOS_AJUSTE.map(([, t]) => <th key={t}>{t}</th>)}<th>Falta</th></tr></thead>
            <tbody>{filas.map((f, i) => (
              <tr key={f.fichero + i}>
                <td className="small">{f.fichero}</td>
                {CAMPOS_AJUSTE.map(([campo, , tipo]) => (
                  <td key={campo}>{Array.isArray(tipo)
                    ? <select value={String(f.dispositivo[campo] ?? '')} onChange={(e) => cambiar(i, campo, e.target.value, 'texto')}>
                        <option value="">—</option>{tipo.map((o) => <option key={o} value={o}>{o}</option>)}</select>
                    : <input size={tipo === 'numero' ? 6 : 12} inputMode={tipo === 'numero' ? 'decimal' : undefined}
                        value={f.dispositivo[campo] == null ? '' : String(f.dispositivo[campo])}
                        onChange={(e) => cambiar(i, campo, e.target.value, tipo)} />}</td>))}
                <td className="small">{[...f.errores, ...f.faltan].join('; ') || 'completo'}</td>
              </tr>))}</tbody>
          </table>
        </div>
        <div className="row">
          <button className="btn btn-primary btn-sm" onClick={() => void guardar()}>Guardar {filas.length} equipo(s)</button>
          <small className="muted">Lo que siga faltando se dice en «Faltan datos»; el estudio usa solo los equipos completos.</small>
        </div>
      </>}
    </div>
  );
}

type CampoTipo = 'texto' | 'numero' | string[];

const ESTADO_DIAG: Record<string, [string, string]> = { corregido: ['ok', 'corregido'], sigue: ['err', 'sigue'] };
const pu = (v: number | null | undefined) => (v == null ? '—' : v.toFixed(3).replace('.', ','));
const pct = (v: number | null | undefined) => (v == null ? '—' : v.toFixed(1).replace('.', ','));

function EstadoDiag({ e }: { e: EstadoDiagnostico }) {
  if (e == null) return <span className="muted small">sin «Con proyecto»</span>;
  const [tono, texto] = ESTADO_DIAG[e];
  return <span className={`badge ${tono}`}>{texto}</span>;
}

/**
 * 017:RF-106 ampliada: lo que ocasionan las cargas nuevas, comparado con «Sin proyecto», y si las obras de «Con proyecto»
 * lo corrigen. Usuario (2026-11-13): tras conectar la carga, un resumen de sobrecargas de nodo a nodo y de barras con
 * caída de tensión, para ver al proponer obras si de verdad se corrigió. Sale de los flujos guardados de esta sección.
 */
function DiagnosticoDeCargas({ project, feeders }: { project: string; feeders: string[] }) {
  const { ws, jobs } = useApp();
  const [diag, setDiag] = useState<Record<string, DiagnosticoCargas>>({});
  // Se vuelve a leer al terminar cada corrida de estudios.
  const hechos = Object.values(jobs).filter((j) => j.kind.startsWith('estudios') && j.status === 'done').length;
  useEffect(() => {
    if (!project || !feeders.length) return;
    let vivo = true;
    api.estudiosDiagnostico(ws.id, project, feeders).then((r) => { if (vivo) setDiag(r.diagnosticos); })
      .catch(() => { if (vivo) setDiag({}); });
    return () => { vivo = false; };
  }, [ws.id, project, feeders.join(','), hechos]);  // eslint-disable-line react-hooks/exhaustive-deps
  const filas = Object.entries(diag);
  if (!filas.length) return null;
  return (
    <div className="card stack">
      <strong>Diagnóstico de las cargas nuevas</strong>
      <p className="small muted">«Sin proyecto», con las cargas sin obras y «Con proyecto»: lo que solo aparece con las cargas lo
        ocasionaron ellas; lo que ya estaba va aparte. Corra de nuevo los estudios tras aplicar obras para ver si se corrigió.</p>
      {filas.map(([f, d]) => (
        <details key={f} open={d.provocados > 0}>
          <summary><strong>{f}</strong>{' — '}
            {d.provocados
              ? <>{d.tension.provocadas.length} barra(s) bajo {pu(d.limites.tension_min_pu)} p.u. y{' '}
                {d.sobrecargas.provocadas.length} tramo(s) sobre {pct(d.limites.cargabilidad_max_pct)} % por las cargas
                {d.con_proyecto ? `; con las obras se corrigen ${d.corregidos} de ${d.provocados}` : '; aún sin «Con proyecto»'}</>
              : 'las cargas no ocasionan barras bajas ni sobrecargas'}
            {' · '}tensión mínima {pu(d.tension_min.sin)} → {pu(d.tension_min.cargas)} → {pu(d.tension_min.con)} p.u.
          </summary>
          {d.trechos.length > 0 && <div className="table-wrap"><table className="table">
            <thead><tr><th>Trecho sobrecargado: desde</th><th>Hasta</th><th>km</th><th>Carga máx. (%)</th><th>Con las obras</th></tr></thead>
            <tbody>{d.trechos.map((t) => <tr key={`${t.desde}-${t.hasta}`}><td>{t.desde}</td><td>{t.hasta}</td>
              <td>{t.km.toFixed(3).replace('.', ',')}</td><td>{pct(t.carga_max)}</td><td><EstadoDiag e={t.estado} /></td></tr>)}</tbody>
          </table></div>}
          {d.tension.provocadas.length > 0 && <div className="table-wrap table-short"><table className="table">
            <thead><tr><th>Barra bajo el límite</th><th>Sin proyecto</th><th>Con las cargas</th><th>Con proyecto</th><th>Estado</th></tr></thead>
            <tbody>{d.tension.provocadas.map((b) => <tr key={b.barra}><td>{b.barra}</td><td>{pu(b.sin)}</td><td>{pu(b.cargas)}</td>
              <td>{pu(b.con)}</td><td><EstadoDiag e={b.estado} /></td></tr>)}</tbody>
          </table></div>}
          {(d.tension.previas.length + d.sobrecargas.previas.length) > 0 && <p className="small muted">
            Ya estaban sin las cargas: {d.tension.previas.length} barra(s) baja(s) y {d.sobrecargas.previas.length} sobrecarga(s).</p>}
        </details>))}
    </div>
  );
}

function EvaluacionProtecciones({ rol, e }: { rol: string; e: ProteccionesEvaluacion }) {
  const [clase, texto] = ESTADO_PROTECCIONES[e.estado];
  return (
    <div>
      <h4>{e.caso ?? rol} <span className={`badge ${clase}`}>{texto}</span></h4>
      <p className="small">{e.cobertura.evaluadas} de {e.cobertura.fallas} falla(s) evaluadas en DIgSILENT;
        {' '}{e.violaciones.length} criterio(s) incumplido(s); {e.no_evaluados.length} sin evaluar.</p>
      {e.violaciones.length > 0 && <ul className="small">{e.violaciones.map((v, i) => (
        <li key={i}><strong>{v.tipo}</strong> {v.dispositivo}{v.falla ? ` en ${v.falla}` : ''}
          {v.valor != null && v.limite != null ? `: ${v.valor.toFixed(3)} frente a ${v.limite.toFixed(3)}` : ''}
          {v.detalle ? ` (${v.detalle})` : ''}</li>))}</ul>}
      {e.no_evaluados.length > 0 && <details><summary className="small muted">Sin evaluar ({e.no_evaluados.length})</summary>
        <ul className="small">{e.no_evaluados.map((n, i) => <li key={i}>{n.que}: {n.razon}</li>)}</ul></details>}
    </div>
  );
}
