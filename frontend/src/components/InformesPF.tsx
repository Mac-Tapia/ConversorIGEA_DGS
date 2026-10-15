import { useEffect, useMemo, useState, type ReactNode } from 'react';
import { api, fmtNum } from '../api';
import { useApp } from '../context';
import type {
  InformeEstudioForm, InformeFactibilidadForm, InformeResultado, InformesContexto, Limites, MaximaCabecera,
} from '../types';

const LIMITES: [keyof Limites, string][] = [
  ['tension_min_pu', 'Tensión mínima (p.u.)'],
  ['tension_max_pu', 'Tensión máxima (p.u.)'],
  ['cargabilidad_max_pct', 'Cargabilidad máxima (%)'],
];

const hoy = () => new Date().toISOString().slice(0, 10);
/** Número escrito con coma o punto; en blanco o mal escrito, ``null``. */
const num = (s: string) => {
  const t = s.trim().replace(',', '.');
  const n = Number(t);
  return t && Number.isFinite(n) ? n : null;
};
/** Párrafos separados por una línea en blanco, como los escribe el operador. */
const parrafos = (s: string) => s.split(/\n\s*\n/).map((x) => x.trim()).filter(Boolean);

type Cabecera = { fecha: string; numero: string; lugar: string; asunto: string; destinatario: string };
const CABECERA: [keyof Cabecera, string, string][] = [
  ['fecha', 'Fecha', 'date'], ['numero', 'N.º de informe', 'text'], ['lugar', 'Lugar', 'text'],
  ['asunto', 'Asunto (referencia)', 'text'], ['destinatario', 'Destinatario', 'text'],
];

function Campos<T extends Record<string, string>>({ campos, valores, fijar }: {
  campos: [keyof T & string, string, string?][]; valores: T; fijar: (k: keyof T & string, v: string) => void;
}) {
  return <>{campos.map(([k, label, tipo]) => (
    <label key={k} className="field">
      <span>{label}</span>
      <input type={tipo ?? 'text'} value={valores[k]} onChange={(e) => fijar(k, e.target.value)}
        inputMode={tipo === 'decimal' ? 'decimal' : undefined} />
    </label>
  ))}</>;
}

/** Huecos, veredicto y descarga del último informe generado de un tipo (RF-100, RF-102, RF-103). */
function Resultado({ r, cancelado }: { r: InformeResultado | null; cancelado: boolean }) {
  const { ws } = useApp();
  if (cancelado) return <p className="alert alert-warn">Cancelado: no se escribió ningún informe.</p>;
  if (!r) return null;
  return (
    <div className="stack compact">
      <p>
        <strong>{r.informe}</strong>{' '}
        <a className="btn btn-sm" href={api.fileUrl(ws.id, r.informe, true)}>Descargar Word</a>{' '}
        <a className="btn btn-sm btn-ghost" href={api.fileUrl(ws.id, r.json, true)}>JSON</a>
      </p>
      {r.factible !== undefined && (
        <p className={`alert ${r.factible ? 'alert-ok' : 'alert-warn'}`}>
          {r.factible ? 'Factible.' : `No factible: ${(r.excesos ?? []).join('; ')}.`}
        </p>)}
      {r.huecos.length > 0 && (
        <details className="alert alert-warn"><summary>Huecos señalados en el Word: {r.huecos.length}</summary>
          <ul className="small">{r.huecos.map((h) => <li key={h}>{h}</li>)}</ul>
        </details>)}
      <small className="muted">Datos de: {r.estudios.join(', ')}.</small>
    </div>
  );
}

/**
 * 4.4 · Informes (spec 017): el informe de estudio eléctrico y el de factibilidad y punto
 * de diseño, con lo que la web ya guardó — flujos de 4.2, obras de «Con proyecto», cargas
 * nuevas del paso 3 y máxima de cabecera de 2.2 —, sin otra ejecución de DIgSILENT. Lo que
 * la web aún no obtiene sola (pérdidas reconocidas, transformador de la SET) se escribe a
 * mano; si falta, el Word lo deja señalado.
 */
export function InformesPF({ project, feeders }: { project: string; feeders: string[] }) {
  const { ws, run, active, jobs } = useApp();
  const [ctx, setCtx] = useState<InformesContexto | null>(null);
  const [limites, setLimites] = useState<Record<string, string>>({});
  const engineBusy = Boolean(active.engine);

  const cabeceraJob = Object.values(jobs).filter((j) => j.kind === 'demanda_cabecera' && j.result).pop();
  const maximas = (cabeceraJob?.result?.resultados ?? []) as MaximaCabecera[];
  // Cualquier trabajo terminado puede haber dejado un flujo, una carga o un informe nuevos.
  const hechos = Object.values(jobs).filter((j) => j.status === 'done').length;
  const marcados = feeders.join('|');
  useEffect(() => {
    let vivo = true;
    void run(() => api.informesContexto(ws.id, project, feeders, cabeceraJob?.id)).then((c) => {
      if (vivo && c) setCtx(c);
    });
    return () => { vivo = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ws.id, project, marcados, cabeceraJob?.id, hechos, run]);

  // RF-81: la banda y el umbral que no trae el perfil se piden; los demás no se tocan.
  const faltanLimites = LIMITES.filter(([k]) => ctx?.limites?.[k] == null);
  const limitesForm = (): Partial<Limites> => Object.fromEntries(
    faltanLimites.map(([k]) => [k, num(limites[k] ?? '')]).filter(([, v]) => v != null));
  const limitesCompletos = faltanLimites.every(([k]) => num(limites[k] ?? '') != null);

  if (!ctx) return <p className="muted">Leyendo lo que ya guardó la web…</p>;
  return (
    <div>
      <p className="muted">Los informes se arman con lo ya ejecutado desde la web: el último estudio de flujo de 4.2 en «Sin
        proyecto» (estado actual) y en «Con proyecto» (proyectado), las obras de 4.1 y las cargas nuevas del paso 3. Vuelva
        a ejecutar el flujo en 4.2 si cambió algo después.</p>
      {faltanLimites.length > 0 && (
        <div className="form-grid">
          {faltanLimites.map(([k, label]) => (
            <label key={k} className="field">
              <span>{label} *</span>
              <input value={limites[k] ?? ''} inputMode="decimal"
                onChange={(e) => setLimites((v) => ({ ...v, [k]: e.target.value }))} />
              <small className="muted">El perfil de empresa no lo trae.</small>
            </label>
          ))}
        </div>
      )}
      <h4>4.4.1 · Análisis eléctrico (informe de estudio)</h4>
      <InformeEstudio project={project} feeders={feeders} ctx={ctx} busy={engineBusy}
        limites={limitesForm} limitesOk={limitesCompletos} />
      <h4>4.4.2 · Conexión de un cliente nuevo (factibilidad y punto de diseño)</h4>
      <InformeFactibilidad project={project} feeders={feeders} ctx={ctx} busy={engineBusy}
        limites={limitesForm} limitesOk={limitesCompletos} maximas={maximas} />
      {ctx.generados.length > 0 && <>
        <h4>Informes generados</h4>
        <div className="table-wrap table-short">
          <table className="table">
            <thead><tr><th>Tipo</th><th>Fecha</th><th>Alimentadores</th><th>N.º</th><th>Huecos</th><th>Word</th></tr></thead>
            <tbody>{ctx.generados.map((g) => (
              <tr key={g.docx}>
                <td>{g.tipo === 'estudio' ? 'Estudio eléctrico' : `Factibilidad${g.factible == null ? ''
                  : g.factible ? ' · factible' : ' · no factible'}`}</td>
                <td>{g.fecha ?? '—'}</td><td>{g.alimentadores.join(', ')}</td><td>{g.numero ?? '—'}</td>
                <td className="num" title={g.huecos.join('\n')}>{g.huecos.length}</td>
                <td><a href={api.fileUrl(ws.id, g.docx, true)}>{g.docx}</a></td>
              </tr>
            ))}</tbody>
          </table>
        </div>
      </>}
    </div>
  );
}

interface Seccion {
  project: string; feeders: string[]; ctx: InformesContexto; busy: boolean;
  limites: () => Partial<Limites>; limitesOk: boolean;
}

/** Lo que va a usar el informe y por qué no se puede generar todavía (RF-75 a RF-78). */
function Origen({ ctx, alimentador, conCon }: { ctx: InformesContexto; alimentador: string; conCon: boolean }) {
  const fila = (rol: 'sin' | 'con', nombre: string): ReactNode => {
    const e = ctx.estudios[rol];
    const conv = e?.alimentadores[alimentador];
    return <li key={rol}>{nombre}: {e == null || conv === undefined
      ? <span className="alert-error">sin flujo de {alimentador} en 4.2</span>
      : <>{e.fichero}{conv ? '' : <span className="alert-error"> (no convergió)</span>}</>}</li>;
  };
  return <ul className="small">
    {fila('sin', 'Estado actual («Sin proyecto»)')}
    {(conCon || ctx.estudios.con) && fila('con', 'Estado proyectado («Con proyecto»)')}
  </ul>;
}

function InformeEstudio({ project, feeders, ctx, busy, limites, limitesOk }: Seccion) {
  const { ws, startJob, jobs } = useApp();
  const [alimentador, setAlimentador] = useState(feeders[0] ?? '');
  const [cab, setCab] = useState<Cabecera>({ fecha: hoy(), numero: '', lugar: '', asunto: '', destinatario: '' });
  const [antecedentes, setAntecedentes] = useState('');
  const [descripcion, setDescripcion] = useState('');
  const [anio, setAnio] = useState('');
  useEffect(() => { if (!feeders.includes(alimentador)) setAlimentador(feeders[0] ?? ''); }, [feeders, alimentador]);
  const asunto = cab.asunto || `ESTUDIO ELÉCTRICO DEL ALIMENTADOR ${alimentador}`;   // RF-80

  const ultimo = Object.values(jobs).filter((j) => j.kind === 'informe_estudio').pop();
  const faltan = ctx.faltan.estudio;
  const sinFlujo = ctx.estudios.sin?.alimentadores[alimentador] === undefined;
  const motivo = faltan.length ? `Falta en el perfil de empresa: ${faltan.join(', ')}.`
    : sinFlujo ? `Ejecute antes el estudio de flujo de ${alimentador} en 4.2.`
      : !limitesOk ? 'Escriba la banda de tensión y el umbral de cargabilidad.' : '';
  const generar = () => {
    const body: InformeEstudioForm = {
      project, alimentador, ...cab, asunto, antecedentes: parrafos(antecedentes), descripcion: parrafos(descripcion),
      limites: limites(), anio: num(anio),
    };
    void startJob(() => api.informeEstudio(ws.id, body));
  };
  return (
    <div className="stack compact">
      <div className="form-grid">
        <label className="field"><span>Alimentador</span>
          <select value={alimentador} onChange={(e) => setAlimentador(e.target.value)}>
            {feeders.map((f) => <option key={f} value={f}>{f}</option>)}
          </select>
        </label>
        <Campos campos={CABECERA} valores={{ ...cab, asunto }} fijar={(k, v) => setCab((c) => ({ ...c, [k]: v }))} />
        <label className="field"><span>Año de las obras (opcional)</span>
          <input value={anio} inputMode="numeric" onChange={(e) => setAnio(e.target.value)} /></label>
        <label className="field span-2"><span>Antecedentes</span>
          <textarea rows={3} value={antecedentes} onChange={(e) => setAntecedentes(e.target.value)}
            placeholder="Un párrafo por bloque; deje una línea en blanco entre párrafos." /></label>
        <label className="field span-2"><span>Descripción</span>
          <textarea rows={3} value={descripcion} onChange={(e) => setDescripcion(e.target.value)} /></label>
      </div>
      <Origen ctx={ctx} alimentador={alimentador} conCon />
      <small className="muted">Obras de 4.1 en «Con proyecto» de {alimentador}: {ctx.obras[alimentador] ?? 0}
        {(ctx.obras[alimentador] ?? 0) === 0 ? ' — sin obras, el informe solo da el estado actual.' : '.'}</small>
      <div className="row">
        <button className="btn btn-primary" disabled={busy || Boolean(motivo)} onClick={generar}>
          Generar informe de estudio
        </button>
        {motivo && <small className="muted">{motivo}</small>}
      </div>
      <Resultado r={(ultimo?.status === 'done' ? ultimo.result : null) as InformeResultado | null}
        cancelado={ultimo?.status === 'cancelled'} />
    </div>
  );
}

type Sol = Record<'cliente' | 'ubicacion' | 'tipo_solicitud' | 'potencia_kw' | 'fecha_solicitud' | 'set_nombre'
  | 'tension_kv' | 'transformador' | 'expediente', string>;
const SOLICITUD: [keyof Sol, string, string?][] = [
  ['cliente', 'Cliente *'], ['ubicacion', 'Ubicación del predio *'], ['tipo_solicitud', 'Tipo de solicitud *'],
  ['potencia_kw', 'Potencia solicitada (kW) *', 'decimal'], ['fecha_solicitud', 'Fecha de la solicitud *', 'date'],
  ['expediente', 'Expediente'], ['set_nombre', 'SET *'], ['tension_kv', 'Tensión (kV) *', 'decimal'],
  ['transformador', 'Transformador de la SET'],
];
type Perd = Record<'sistema_electrico' | 'codigo_sistema' | 'reconocido_kw_pct' | 'reconocido_kwh_pct' | 'precio_compra', string>;
const PERDIDAS: [keyof Perd, string, string?][] = [
  ['sistema_electrico', 'Sistema eléctrico'], ['codigo_sistema', 'Código del sistema'],
  ['reconocido_kw_pct', 'Pérdidas reconocidas en kW (%)', 'decimal'],
  ['reconocido_kwh_pct', 'Pérdidas reconocidas en kWh (%)', 'decimal'],
  ['precio_compra', 'Precio de compra (S/./kWh)', 'decimal'],
];
type Trafo = Record<'kv' | 'sin_pct' | 'con_pct' | 'caso', string>;
const TRAFO: [keyof Trafo, string, string?][] = [
  ['kv', 'Devanado (kV)', 'decimal'], ['sin_pct', 'Cargabilidad sin proyecto (%)', 'decimal'],
  ['con_pct', 'Cargabilidad con proyecto (%)', 'decimal'], ['caso', 'Caso del proyecto de transmisión'],
];

function InformeFactibilidad({ project, feeders, ctx, busy, limites, limitesOk, maximas }: Seccion & {
  maximas: MaximaCabecera[];
}) {
  const { ws, startJob, jobs } = useApp();
  const solas = ctx.cargas.filter((c) => c.sola);
  const enBloque = ctx.cargas.filter((c) => !c.sola);
  const [clave, setClave] = useState('');
  const carga = solas.find((c) => `${c.alimentador}|${c.sed}` === clave) ?? null;
  const [cab, setCab] = useState<Cabecera>({ fecha: hoy(), numero: '', lugar: '', asunto: '', destinatario: '' });
  const [sol, setSol] = useState<Sol>({
    cliente: '', ubicacion: '', tipo_solicitud: 'factibilidad de suministro', potencia_kw: '', fecha_solicitud: '',
    set_nombre: '', tension_kv: '', transformador: '', expediente: '',
  });
  const [concesion, setConcesion] = useState<'' | 'si' | 'no'>('');
  const [fc, setFc] = useState('');
  const [perd, setPerd] = useState<Perd>({ sistema_electrico: '', codigo_sistema: '', reconocido_kw_pct: '',
    reconocido_kwh_pct: '', precio_compra: '' });
  const [trafo, setTrafo] = useState<Trafo>({ kv: '', sin_pct: '', con_pct: '', caso: '' });
  const [codigo, setCodigo] = useState('');

  // RF-60 y RF-92: factor de carga del mes de la máxima del medidor de ese alimentador.
  const fcMedido = useMemo(() => {
    if (!carga) return null;
    const fila = maximas.find((m) => m.alimentador === carga.alimentador && ctx.factor_carga[m.medidor]);
    return fila ? { medidor: fila.medidor, ...ctx.factor_carga[fila.medidor] } : null;
  }, [carga, maximas, ctx.factor_carga]);

  // RF-91: al elegir la carga se rellenan su potencia y su punto de conexión; lo demás, editable.
  const elegir = (k: string) => {
    setClave(k);
    const c = solas.find((x) => `${x.alimentador}|${x.sed}` === k);
    if (!c) return;
    setSol((s) => ({ ...s, potencia_kw: c.kw != null ? String(c.kw) : s.potencia_kw }));
    setCodigo(c.barra);
  };
  useEffect(() => { if (fcMedido) setFc(String(fcMedido.fc)); }, [fcMedido]);

  const ultimo = Object.values(jobs).filter((j) => j.kind === 'informe_factibilidad').pop();
  const faltan = ctx.faltan.factibilidad;
  const requeridos = SOLICITUD.filter(([, label]) => label.endsWith('*')).map(([k]) => k);
  const vacios = requeridos.filter((k) => !sol[k].trim());
  const alim = carga?.alimentador ?? '';
  const motivo = faltan.length ? `Falta en el perfil de empresa: ${faltan.join(', ')}.`
    : !carga ? 'Elija la carga nueva del informe.'
      : ctx.estudios.sin?.alimentadores[alim] === undefined || ctx.estudios.con?.alimentadores[alim] === undefined
        ? `Ejecute antes el estudio de flujo de ${alim} en 4.2, en «Sin» y en «Con proyecto».`
        : vacios.length ? `Complete la solicitud: ${vacios.map((k) => SOLICITUD.find(([x]) => x === k)![1].replace(' *', '')).join(', ')}.`
          : !limitesOk ? 'Escriba la banda de tensión y el umbral de cargabilidad.' : '';
  const generar = () => {
    if (!carga) return;
    const body: InformeFactibilidadForm = {
      project, alimentador: carga.alimentador, sed: carga.sed, ...cab,
      asunto: cab.asunto || `FACTIBILIDAD DE SUMINISTRO DE ${sol.cliente.toUpperCase()}`,
      limites: limites(), factor_carga: num(fc), codigo_punto: codigo,
      solicitud: { ...sol, potencia_kw: num(sol.potencia_kw), tension_kv: num(sol.tension_kv),
        en_concesion: concesion === '' ? null : concesion === 'si' },
      perdidas_reconocidas: { sistema_electrico: perd.sistema_electrico, codigo_sistema: perd.codigo_sistema,
        reconocido_kw_pct: num(perd.reconocido_kw_pct), reconocido_kwh_pct: num(perd.reconocido_kwh_pct),
        precio_compra: num(perd.precio_compra) },
      transformador_set: { kv: num(trafo.kv), sin_pct: num(trafo.sin_pct), con_pct: num(trafo.con_pct), caso: trafo.caso },
    };
    void startJob(() => api.informeFactibilidad(ws.id, body));
  };

  if (!ctx.cargas.length || !solas.length) {
    return <p className="muted">No hay ninguna carga nueva ingresada sola y aplicada en {feeders.join(', ')}: intégrela en
      el paso 3 con «Una carga nueva» y aplíquela.{enBloque.length > 0 && ` Las ${enBloque.length} del libro van en bloque
      y entran como solicitudes vigentes.`}</p>;
  }
  return (
    <div className="stack compact">
      <div className="form-grid">
        <label className="field span-2"><span>Carga nueva del informe</span>
          <select value={clave} onChange={(e) => elegir(e.target.value)}>
            <option value="">Elija la carga…</option>
            {solas.map((c) => (
              <option key={`${c.alimentador}|${c.sed}`} value={`${c.alimentador}|${c.sed}`}>
                {c.sed} · {c.alimentador} · {c.kw != null ? `${fmtNum(c.kw, 0)} kW` : 's/ kW'} · barra {c.barra}
              </option>
            ))}
          </select>
          {enBloque.length > 0 && <small className="muted">{enBloque.length} carga(s) del libro en bloque: el informe las
            cita como solicitudes vigentes.</small>}
        </label>
      </div>
      {carga && <>
        <Origen ctx={ctx} alimentador={carga.alimentador} conCon />
        <div className="form-grid">
          <Campos campos={CABECERA} valores={cab} fijar={(k, v) => setCab((c) => ({ ...c, [k]: v }))} />
        </div>
        <p><strong>Solicitud</strong></p>
        <div className="form-grid">
          <Campos campos={SOLICITUD} valores={sol} fijar={(k, v) => setSol((s) => ({ ...s, [k]: v }))} />
          <label className="field"><span>¿Predio en el área de concesión?</span>
            <select value={concesion} onChange={(e) => setConcesion(e.target.value as '' | 'si' | 'no')}>
              <option value="">Sin confirmar (queda señalado)</option><option value="si">Sí</option><option value="no">No</option>
            </select>
          </label>
          <label className="field"><span>Código del punto de diseño</span>
            <input value={codigo} onChange={(e) => setCodigo(e.target.value)} />
            <small className="muted">Barra donde el paso 3 conectó la carga: {carga.barra}.</small>
          </label>
        </div>
        <p><strong>Pérdidas</strong></p>
        <div className="form-grid">
          <label className="field"><span>Factor de carga</span>
            <input value={fc} inputMode="decimal" onChange={(e) => setFc(e.target.value)} />
            <small className="muted">{fcMedido ? `De la medición de ${fcMedido.medidor} en ${fcMedido.mes} (2.2).`
              : 'Sin máxima de cabecera buscada en 2.2: escríbalo, o las pérdidas quedan señaladas.'}</small>
          </label>
          <Campos campos={PERDIDAS} valores={perd} fijar={(k, v) => setPerd((p) => ({ ...p, [k]: v }))} />
        </div>
        <p><strong>Transformador de la SET (del proyecto de transmisión)</strong></p>
        <div className="form-grid">
          <Campos campos={TRAFO} valores={trafo} fijar={(k, v) => setTrafo((t) => ({ ...t, [k]: v }))} />
        </div>
        <small className="muted">Sin la cargabilidad del transformador el informe no puede concluir que la carga es
          factible (RF-71): léala en el proyecto de transmisión de DIgSILENT.</small>
      </>}
      <div className="row">
        <button className="btn btn-primary" disabled={busy || Boolean(motivo)} onClick={generar}>
          Generar informe de factibilidad
        </button>
        {motivo && <small className="muted">{motivo}</small>}
      </div>
      <Resultado r={(ultimo?.status === 'done' ? ultimo.result : null) as InformeResultado | null}
        cancelado={ultimo?.status === 'cancelled'} />
    </div>
  );
}
