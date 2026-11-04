import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { api, fmtNum } from '../api';
import { useApp } from '../context';
import { acumularLeidos, alimentadoresDistintos, clienteAjeno, esOtraCarga, esPotenciaPropuesta, incrementoNoCuadra } from '../solicitudLeida';
import { FileDrop } from './ui';
import type {
  DocumentosResultado, InformeEstudioForm, InformeFactibilidadForm, InformeResultado, InformesContexto, Limites, MaximaCabecera,
  TrafoCargas, TrafoResultado,
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

/**
 * Estado de un formulario de 4.4 que se guarda en el servidor mientras se escribe
 * (017:RF-82): al recargar la página o reiniciar la web vuelve tal cual.
 */
function useGuardado<T extends object>(project: string, tipo: 'estudio' | 'factibilidad', guardado: unknown,
  inicial: T): [T, (cambio: Partial<T>) => void] {
  const { ws } = useApp();
  const [valor, setValor] = useState<T>(() => ({ ...inicial, ...((guardado ?? {}) as Partial<T>) }));
  const json = JSON.stringify(valor);
  const ultimo = useRef(json);
  useEffect(() => {
    if (json === ultimo.current) return undefined;
    const t = setTimeout(() => {
      ultimo.current = json;
      void api.informesFormulario(ws.id, project, tipo, JSON.parse(json)).catch(() => undefined);
    }, 800);
    return () => clearTimeout(t);
  }, [json, ws.id, project, tipo]);
  return [valor, (cambio) => setValor((v) => ({ ...v, ...cambio }))];
}

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

/** Nombre para el operador de cada dato que se lee de los PDF (017:RF-138). */
const DATO_LEIDO: Record<string, string> = {
  cliente: 'Cliente', ubicacion: 'Ubicación', tipo_solicitud: 'Tipo de solicitud', potencia_actual_kw: 'Potencia actual (kW)',
  potencia_kw: 'Potencia solicitada (kW)', fecha: 'Fecha', lugar: 'Lugar', asunto: 'Asunto', tension_kv: 'Tensión (kV)',
  nis: 'NIS', expediente: 'Expediente', solicitud: 'N.º de solicitud', referencias: 'Documentos citados',
  set_nombre: 'SET', alimentador: 'Alimentador', estructura: 'Estructura del punto de diseño', utm_x: 'UTM X',
  utm_y: 'UTM Y', pcc_mva: 'Potencia de cortocircuito (MVA)', destinatario: 'Destinatario',
};
const CLASE_DOC = { solicitud: 'Solicitud del interesado', respuesta: 'Respuesta de la distribuidora', ficha: 'Ficha técnica' };

/**
 * PDF del solicitante (017:RF-136 a RF-138): se suben, se leen en un trabajo —capa de texto
 * y, en las páginas escaneadas, OCR— y ``onLeido`` recibe lo leído una sola vez por lectura.
 */
function DocumentosSolicitante({ tipo, varios, titulo, onLeido }: {
  tipo: 'factibilidad' | 'estudio'; varios: boolean; titulo: string; onLeido: (r: DocumentosResultado) => void;
}) {
  const { ws, startJob, jobs, active } = useApp();
  const [files, setFiles] = useState<File[]>([]);
  const [jobId, setJobId] = useState<string | null>(null);
  const job = jobId ? jobs[jobId] : undefined;
  const r = (job?.status === 'done' ? job.result : null) as DocumentosResultado | null;
  const aplicado = useRef('');
  useEffect(() => {
    if (!r || !jobId || aplicado.current === jobId) return;
    aplicado.current = jobId;
    onLeido(r);
  }, [r, jobId]);  // eslint-disable-line react-hooks/exhaustive-deps
  const leer = async () => {
    const j = await startJob(() => api.informesDocumentos(ws.id, tipo, files));
    if (j) setJobId(j.id);
  };
  const corriendo = job?.status === 'queued' || job?.status === 'running';
  return (
    <div className="field span-2">
      <span>{titulo}</span>
      <FileDrop compact multiple={varios} accept=".pdf,application/pdf"
        onFiles={(fs) => setFiles(varios ? fs : fs.slice(0, 1))}>
        <span>{files.length
          ? <><strong>{files.map((f) => f.name).join(', ')}</strong> · reemplazar: soltar o <u>elegir</u></>
          : <>PDF{varios ? ' (uno o varios)' : ''}: soltar o <u>elegir</u></>}</span>
      </FileDrop>
      <div className="row">
        <button className="btn btn-sm" disabled={!files.length || corriendo || Boolean(active.engine)} onClick={leer}>
          Leer {files.length > 1 ? `los ${files.length} documentos` : 'el documento'}
        </button>
        {files.length > 0 && <button className="btn btn-ghost btn-sm" onClick={() => { setFiles([]); setJobId(null); }}>Quitar</button>}
        {corriendo && <small className="muted">Leyendo el texto (y con OCR las páginas escaneadas)…</small>}
        {job?.status === 'failed' && <small className="alert alert-error">{job.error}</small>}
      </div>
      <small className="muted">Se lee la capa de texto del PDF; una página escaneada pasa por OCR. Los PDF quedan solo en
        este equipo.</small>
      {r && r.documentos.map((d) => (
        <details key={d.fichero} className={`alert ${d.avisos.length ? 'alert-warn' : 'alert-ok'}`}>
          <summary>{`${d.fichero} · ${CLASE_DOC[d.clase]} · ${d.paginas} pág. por ${d.metodo === 'texto' ? 'texto' : 'OCR'}`}
            {` · ${Object.keys(d.datos).length} dato(s)`}{d.avisos.length ? ` · ${d.avisos.length} aviso(s)` : ''}</summary>
          {d.avisos.map((a) => <p key={a} className="small">{a}</p>)}
          <table className="table"><tbody>{Object.entries(d.datos).map(([k, v]) => (
            <tr key={k}><td className="small">{DATO_LEIDO[k] ?? k}</td>
              <td className="small">{Array.isArray(v) ? v.join(', ') : typeof v === 'number' ? fmtNum(v, 2) : v}</td></tr>
          ))}</tbody></table>
        </details>
      ))}
    </div>
  );
}

/** Un caso del JSON del informe (RF-25): tensión por fase o equilibrada, cargabilidad y pérdidas. */
interface CasoJson {
  nombre: string; converge: boolean; perdidas?: { kw: number } | null;
  tension_min?: Record<string, { valor: number; donde: string }> | { valor: number; donde: string } | null;
  cargabilidad_max?: { valor: number; donde: string } | null; nodos_fuera?: number; tramos_sobre?: number;
}
interface InformeJson {
  actual?: CasoJson; proyectado?: CasoJson; recomendada?: string | null; cumplen?: Record<string, boolean>;
  etapas?: { clave: string; caso: CasoJson | null; motivo?: string | null }[];
}

function tensionMinima(c: CasoJson): string {
  const t = c.tension_min;
  if (!t) return '—';
  const valores = 'valor' in t ? [t as { valor: number; donde: string }]
    : Object.values(t as Record<string, { valor: number; donde: string }>);
  const peor = valores.reduce((a, b) => (b.valor < a.valor ? b : a), valores[0]);
  return peor ? `${fmtNum(peor.valor, 3)} p.u. (${peor.donde})` : '—';
}

/**
 * Resumen por caso y por etapa al terminar (017:RF-100): sale del JSON que se escribe junto
 * al Word (RF-25), así lo que ve la página es lo que dice el documento.
 */
function ResumenCasos({ json }: { json: string }) {
  const { ws } = useApp();
  const [d, setD] = useState<InformeJson | null>(null);
  useEffect(() => {
    let vivo = true;
    fetch(api.fileUrl(ws.id, json)).then((r) => (r.ok ? r.json() : null))
      .then((x) => { if (vivo) setD(x as InformeJson | null); }).catch(() => undefined);
    return () => { vivo = false; };
  }, [ws.id, json]);
  if (!d?.actual) return null;
  const cumple = (c: CasoJson) => c.converge && !c.nodos_fuera && !c.tramos_sobre;
  const filas: [string, CasoJson | null, boolean | null][] = [['Estado actual', d.actual, cumple(d.actual)]];
  if (d.proyectado) filas.push(['Estado proyectado', d.proyectado, cumple(d.proyectado)]);
  for (const e of d.etapas ?? []) filas.push([`Etapa «${e.clave}»`, e.caso, d.cumplen?.[e.clave] ?? (e.caso ? cumple(e.caso) : null)]);
  return (
    <div className="table-wrap table-short">
      <table className="table">
        <thead><tr><th>Caso</th><th>Tensión mínima</th><th>Cargabilidad máxima</th>
          <th className="num">Pérdidas (kW)</th><th>Cumple</th></tr></thead>
        <tbody>{filas.map(([nombre, c, ok]) => (
          <tr key={nombre}>
            <td className="strong">{nombre}{d.recomendada && nombre === `Etapa «${d.recomendada}»` ? ' · recomendada' : ''}</td>
            {!c || !c.converge ? <td colSpan={3} className="muted">{c ? 'el flujo no converge' : 'sin evaluar'}</td> : <>
              <td>{tensionMinima(c)}</td>
              <td>{c.cargabilidad_max ? `${fmtNum(c.cargabilidad_max.valor, 1)} % (${c.cargabilidad_max.donde})` : '—'}</td>
              <td className="num">{c.perdidas ? fmtNum(c.perdidas.kw, 1) : '—'}</td></>}
            <td>{ok == null ? '—' : ok ? 'Sí' : 'No'}</td>
          </tr>
        ))}</tbody>
      </table>
    </div>
  );
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
        {/* 063:RF-42: el PDF, o por qué no se generó. */}
        {r.pdf && <><a className="btn btn-sm" href={api.fileUrl(ws.id, r.pdf, true)}>Descargar PDF</a>{' '}</>}
        {r.sin_pdf && <small className="alert alert-warn">Sin PDF: {r.sin_pdf}</small>}{' '}
        {/* 066:RF-11: el libro de la empresa, o por qué no se generó. */}
        {r.libro_xlsx && <><a className="btn btn-sm" href={api.fileUrl(ws.id, r.libro_xlsx, true)}>Descargar libro</a>{' '}</>}
        {r.sin_libro && <small className="alert alert-warn">Sin libro: {r.sin_libro}</small>}{' '}
        <a className="btn btn-sm btn-ghost" href={api.fileUrl(ws.id, r.json, true)}>JSON</a>{' '}
        {/* 017:RF-105: el plan repite el informe con tools/informe_web.py. */}
        {r.plan && <a className="btn btn-sm btn-ghost" href={api.fileUrl(ws.id, r.plan, true)}
          title="Para repetir este informe con tools/informe_web.py">Plan</a>}
      </p>
      {(r.avisos_libro?.length ?? 0) > 0 && <small className="alert alert-warn">Revise el libro: {r.avisos_libro!.join(' · ')}</small>}
      {(r.huecos_libro?.length ?? 0) > 0 && <small className="muted">Vacío en el libro: {r.huecos_libro!.join(' · ')}.</small>}
      <ResumenCasos json={r.json} />
      {/* 017:RF-101: las imágenes del informe en miniatura; al pulsar, a tamaño completo. */}
      {(r.imagenes ?? []).length > 0 && (
        <div className="miniaturas">
          {(r.imagenes ?? []).map((im) => (
            <a key={im.fichero} href={api.fileUrl(ws.id, im.fichero)} target="_blank" rel="noreferrer"
              title={`${im.estado} · ${im.modo}`}>
              <img src={api.fileUrl(ws.id, im.fichero)} alt={`${im.estado} · ${im.modo}`} loading="lazy" />
            </a>
          ))}
        </div>
      )}
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
  const [ctxDe, setCtxDe] = useState<{ project: string; ctx: InformesContexto } | null>(null);
  const ctx = ctxDe?.project === project ? ctxDe.ctx : null;
  const [limites, setLimites] = useState<Record<string, string>>({});
  const [recargas, setRecargas] = useState(0);
  const recargar = () => setRecargas((n) => n + 1);
  // 017:RF-98: tampoco mientras corre DIgSILENT: un estudio a medias dejaría el informe con
  // los resultados del flujo anterior.
  const engineBusy = Boolean(active.engine || active.powerfactory);

  const cabeceraJob = Object.values(jobs).filter((j) => j.kind === 'demanda_cabecera' && j.result).pop();
  const maximas = (cabeceraJob?.result?.resultados ?? []) as MaximaCabecera[];
  // Cualquier trabajo terminado puede haber dejado un flujo, una carga o un informe nuevos.
  const hechos = Object.values(jobs).filter((j) => j.status === 'done').length;
  const marcados = feeders.join('|');
  useEffect(() => {
    let vivo = true;
    void run(() => api.informesContexto(ws.id, project, feeders, cabeceraJob?.id)).then((c) => {
      if (!vivo || !c) return;
      // La primera vez en este proyecto, los límites escritos antes (RF-82).
      setCtxDe((prev) => {
        if (prev?.project !== project) setLimites((c.formularios.estudio?.limites ?? {}) as Record<string, string>);
        return { project, ctx: c };
      });
    });
    return () => { vivo = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ws.id, project, marcados, cabeceraJob?.id, hechos, recargas, run]);

  // RF-81: la banda y el umbral que no trae el perfil se piden; los demás no se tocan.
  const faltanLimites = LIMITES.filter(([k]) => ctx?.limites?.[k] == null);
  const limitesForm = (): Partial<Limites> => Object.fromEntries(
    faltanLimites.map(([k]) => [k, num(limites[k] ?? '')]).filter(([, v]) => v != null));
  const limitesCompletos = faltanLimites.every(([k]) => num(limites[k] ?? '') != null);
  // 086:RF-35: las bandas que el perfil no da se piden; vacías, el servidor las deriva de los límites y lo avisa.
  const faltanBandas = BANDAS.filter(([k]) => ctx?.bandas?.[k] == null);
  const bandasForm = (): BandasForm => Object.fromEntries(faltanBandas
    .map(([k, , clave]) => [k, listaDeBandas(limites[clave] ?? '')]).filter(([, v]) => v?.length)) as BandasForm;
  const bandasValidas = faltanBandas.every(([, , clave]) => listaDeBandas(limites[clave] ?? '') != null);

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
      {faltanBandas.length > 0 && (
        <div className="form-grid">
          {faltanBandas.map(([k, label, clave]) => (
            <label key={k} className="field">
              <span>{label}</span>
              <input value={limites[clave] ?? ''} placeholder="Porcentajes de menor a mayor, separados por espacios"
                onChange={(e) => setLimites((v) => ({ ...v, [clave]: e.target.value }))} />
              {listaDeBandas(limites[clave] ?? '') == null
                ? <small className="alert-error">Escriba porcentajes positivos, de menor a mayor.</small>
                : <small className="muted">El perfil no las trae. Vacío: salen de la banda de tensión y del umbral, y el informe lo avisa.</small>}
            </label>
          ))}
        </div>
      )}
      <h4>4.4.1 · Análisis eléctrico (informe de estudio)</h4>
      <InformeEstudio key={`e-${project}`} project={project} feeders={feeders} ctx={ctx} busy={engineBusy}
        limites={limitesForm} limitesOk={limitesCompletos && bandasValidas} limitesTexto={limites} bandas={bandasForm} />
      <h4>4.4.2 · Conexión de un cliente nuevo (factibilidad y punto de diseño)</h4>
      <InformeFactibilidad key={`f-${project}`} project={project} feeders={feeders} ctx={ctx} busy={engineBusy}
        limites={limitesForm} limitesOk={limitesCompletos && bandasValidas} maximas={maximas} recargar={recargar} bandas={bandasForm} />
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
  limites: () => Partial<Limites>; limitesOk: boolean; bandas: () => BandasForm;
}

type BandasForm = NonNullable<InformeEstudioForm['bandas']>;
const BANDAS: ['tension' | 'cargabilidad', string, string][] = [
  ['tension', 'Bandas del coloreado por tensión (%)', 'bandas_tension'],
  ['cargabilidad', 'Bandas del coloreado por cargabilidad (%)', 'bandas_cargabilidad'],
];

/** Los porcentajes escritos; vacío es una lista vacía y `null`, que no valen como bandas. */
function listaDeBandas(texto: string): number[] | null {
  const partes = texto.trim().split(/\s+/).filter(Boolean).map((x) => Number(x.replace(',', '.')));
  const validas = partes.every((v, i) => Number.isFinite(v) && v > 0 && (i === 0 || v > partes[i - 1]));
  return validas ? partes : null;
}

/** 086:RF-31: lo dice antes de generar: una empresa sin modelo también tiene su informe. */
function AvisoPlantilla({ neutra }: { neutra: boolean }) {
  return neutra ? <small className="muted">Su empresa no trae modelo de este informe: saldrá con la plantilla neutra.</small> : null;
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

function InformeEstudio({ project, feeders, ctx, busy, limites, limitesOk, limitesTexto, bandas }: Seccion & {
  limitesTexto: Record<string, string>;
}) {
  const { ws, startJob, jobs } = useApp();
  const [f, fijar] = useGuardado(project, 'estudio', ctx.formularios.estudio, {
    alimentador: feeders[0] ?? '',
    cab: { fecha: hoy(), numero: '', lugar: '', asunto: '', destinatario: '' } as Cabecera,
    antecedentes: '', descripcion: '', anio: '', limites: limitesTexto,
  });
  const { alimentador, cab, antecedentes, descripcion, anio } = f;
  const setAlimentador = (v: string) => fijar({ alimentador: v });
  const setCab = (cambio: (c: Cabecera) => Cabecera) => fijar({ cab: cambio(cab) });
  const setAntecedentes = (v: string) => fijar({ antecedentes: v });
  const setDescripcion = (v: string) => fijar({ descripcion: v });
  const setAnio = (v: string) => fijar({ anio: v });
  // Los límites de arriba se guardan con este formulario.
  const limitesJson = JSON.stringify(limitesTexto);
  useEffect(() => { fijar({ limites: limitesTexto }); }, [limitesJson]);  // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (!feeders.includes(alimentador)) setAlimentador(feeders[0] ?? '');
  }, [feeders, alimentador]);  // eslint-disable-line react-hooks/exhaustive-deps
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
      limites: limites(), bandas: bandas(), anio: num(anio),
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
        {/* 017:RF-136, RF-140: los PDF del expediente proponen los antecedentes, sin repetir. */}
        <DocumentosSolicitante tipo="estudio" varios titulo="Documentos del expediente (cartas, oficios, fichas)"
          onLeido={(r) => {
            const hay = parrafos(antecedentes);
            const nuevos = r.antecedentes.filter((p) => !hay.includes(p));
            if (nuevos.length) setAntecedentes([...hay, ...nuevos].join('\n\n'));
          }} />
      </div>
      <Origen ctx={ctx} alimentador={alimentador} conCon />
      <small className="muted">Obras de 4.1 en «Con proyecto» de {alimentador}: {ctx.obras[alimentador] ?? 0}
        {(ctx.obras[alimentador] ?? 0) === 0 ? ' — sin obras, el informe solo da el estado actual.' : '.'}</small>
      <div className="row">
        <button className="btn btn-primary" disabled={busy || Boolean(motivo)} onClick={generar}>
          Generar informe de estudio
        </button>
        <AvisoPlantilla neutra={ctx.plantilla_neutra.estudio} />
        {motivo && <small className="muted">{motivo}</small>}
        {!motivo && busy && <small className="muted">Espere a que termine el trabajo en curso.</small>}
      </div>
      <Resultado r={(ultimo?.status === 'done' ? ultimo.result : null) as InformeResultado | null}
        cancelado={ultimo?.status === 'cancelled'} />
    </div>
  );
}

type Sol = Record<'cliente' | 'ubicacion' | 'tipo_solicitud' | 'potencia_kw' | 'fecha_solicitud' | 'set_nombre'
  | 'tension_kv' | 'transformador' | 'expediente' | 'potencia_actual_kw' | 'nis' | 'codigo_ficha', string>;
const SOLICITUD: [keyof Sol, string, string?][] = [
  ['cliente', 'Cliente *'], ['ubicacion', 'Ubicación del predio *'], ['tipo_solicitud', 'Tipo de solicitud *'],
  // 063:RF-14: en una ampliación, la potencia actual y la solicitada; el incremento se muestra.
  ['potencia_actual_kw', 'Potencia actual (kW)', 'decimal'],
  ['potencia_kw', 'Potencia solicitada (kW) *', 'decimal'], ['fecha_solicitud', 'Fecha de la solicitud *', 'date'],
  // 063:RF-15, RF-18: el EXP de la distribuidora, el código interno de la ficha aparte y el NIS.
  ['expediente', 'Expediente'], ['codigo_ficha', 'Código de la ficha'], ['nis', 'NIS'],
  ['set_nombre', 'SET *'], ['tension_kv', 'Tensión (kV) *', 'decimal'],
  ['transformador', 'Transformador de la SET'],
];
/** 063:RF-17: datos documentales del punto de diseño (ficha); no son resultados del flujo. */
type PuntoFicha = Record<'pcc_mva' | 'utm_x' | 'utm_y', string>;
const PUNTO_FICHA: [keyof PuntoFicha, string, string?][] = [
  ['pcc_mva', 'Potencia de cortocircuito (MVA)', 'decimal'], ['utm_x', 'UTM X (m)', 'decimal'],
  ['utm_y', 'UTM Y (m)', 'decimal'],
];
type Perd = Record<'sistema_electrico' | 'codigo_sistema' | 'reconocido_kw_pct' | 'reconocido_kwh_pct' | 'precio_compra', string>;
const PERDIDAS: [keyof Perd, string, string?][] = [
  ['sistema_electrico', 'Sistema eléctrico'], ['codigo_sistema', 'Código del sistema'],
  ['reconocido_kw_pct', 'Pérdidas reconocidas en kW (%)', 'decimal'],
  ['reconocido_kwh_pct', 'Pérdidas reconocidas en kWh (%)', 'decimal'],
  ['precio_compra', 'Precio de compra (moneda/kWh)', 'decimal'],
];
type Trafo = Record<'kv' | 'sin_pct' | 'con_pct' | 'caso', string>;
const TRAFO: [keyof Trafo, string, string?][] = [
  ['kv', 'Devanado (kV)', 'decimal'], ['sin_pct', 'Cargabilidad sin proyecto (%)', 'decimal'],
  ['con_pct', 'Cargabilidad con proyecto (%)', 'decimal'], ['caso', 'Caso del proyecto de transmisión'],
];

function InformeFactibilidad({ project, feeders, ctx, busy, limites, limitesOk, maximas, recargar, bandas }: Seccion & {
  maximas: MaximaCabecera[]; recargar: () => void;
}) {
  const { ws, startJob, jobs, run, health } = useApp();
  const solas = ctx.cargas.filter((c) => c.sola);
  const enBloque = ctx.cargas.filter((c) => !c.sola);
  const [f, fijar] = useGuardado(project, 'factibilidad', ctx.formularios.factibilidad, {
    clave: '', cab: { fecha: hoy(), numero: '', lugar: '', asunto: '', destinatario: '' } as Cabecera,
    sol: { cliente: '', ubicacion: '', tipo_solicitud: 'factibilidad de suministro', potencia_kw: '',
      fecha_solicitud: '', set_nombre: '', tension_kv: '', transformador: '', expediente: '',
      potencia_actual_kw: '', nis: '', codigo_ficha: '' } as Sol,
    punto: { pcc_mva: '', utm_x: '', utm_y: '' } as PuntoFicha,
    /** 063:RF-19: cada alimentador leído en los PDF, con su documento. */
    leidos: [] as { valor: string; fichero: string }[],
    /** 063:RF-20: cada fecha leída en los PDF, con su documento. */
    fechas: [] as { valor: string; fichero: string }[],
    concesion: '' as '' | 'si' | 'no', fc: '',
    perd: { sistema_electrico: '', codigo_sistema: '', reconocido_kw_pct: '', reconocido_kwh_pct: '',
      precio_compra: '' } as Perd,
    trafo: { kv: '', sin_pct: '', con_pct: '', caso: '' } as Trafo, codigo: '', trafoCarga: '',
  });
  const { clave, cab, concesion, fc, perd, trafo, codigo } = f;
  // Un formulario guardado antes de la spec 063 no trae los campos nuevos: se completan vacíos.
  const sol: Sol = { ...{ potencia_actual_kw: '', nis: '', codigo_ficha: '' }, ...f.sol } as Sol;
  const punto: PuntoFicha = { ...{ pcc_mva: '', utm_x: '', utm_y: '' }, ...(f.punto ?? {}) } as PuntoFicha;
  const leidos = f.leidos ?? [];
  const fechasLeidas = f.fechas ?? [];
  const carga = solas.find((c) => `${c.alimentador}|${c.sed}` === clave) ?? null;
  const setCab = (cambio: (c: Cabecera) => Cabecera) => fijar({ cab: cambio(cab) });
  const setSol = (cambio: (s: Sol) => Sol) => fijar({ sol: cambio(sol) });
  const setConcesion = (v: '' | 'si' | 'no') => fijar({ concesion: v });
  const setFc = (v: string) => fijar({ fc: v });
  const setPerd = (cambio: (p: Perd) => Perd) => fijar({ perd: cambio(perd) });
  const setTrafo = (cambio: (t: Trafo) => Trafo) => fijar({ trafo: cambio(trafo) });
  const setCodigo = (v: string) => fijar({ codigo: v });
  const [ruta, setRuta] = useState('');
  const libro = ctx.libro_perdidas;
  const lectura = carga ? libro?.lecturas[carga.alimentador] : undefined;
  const subirLibro = async (files: File[]) => {
    if (files[0] && await run(() => api.informesPerdidasSubir(ws.id, files[0]))) recargar();
  };
  const libroPorRuta = async () => {
    if (await run(() => api.informesPerdidasRuta(ws.id, ruta.trim()))) { setRuta(''); recargar(); }
  };
  const quitarLibro = async () => { if (await run(() => api.informesPerdidasQuitar(ws.id))) recargar(); };

  // T10: la carga de la barra de la SET en el proyecto de transmisión y su caso; el
  // cálculo suma a esa carga el Δ de cabecera de los flujos de 4.2 y rellena el devanado.
  const { active } = useApp();
  const pfBusy = Boolean(active.powerfactory);
  const jobCargas = Object.values(jobs).filter((j) => j.kind === 'informe_trafo_cargas').pop();
  const ad08 = (jobCargas?.status === 'done' ? jobCargas.result : null) as TrafoCargas | null;
  const jobTrafo = Object.values(jobs).filter((j) => j.kind === 'informe_trafo').pop();
  const anio = cab.fecha.slice(0, 4);
  const casoPropuesto = ad08?.casos.includes(`${anio}_D`) ? `${anio}_D` : ad08?.caso_activo ?? '';
  const [caso, setCaso] = useState('');
  const casoElegido = caso || trafo.caso || casoPropuesto;
  const aplicado = useRef('');
  useEffect(() => {
    if (jobTrafo?.status !== 'done' || !jobTrafo.result || aplicado.current === jobTrafo.id) return;
    aplicado.current = jobTrafo.id;
    const r = jobTrafo.result as TrafoResultado;
    const t = (v: number | null) => (v == null ? '' : String(Math.round(v * 100) / 100));
    fijar({ trafo: { kv: t(r.devanado.kv), sin_pct: t(r.devanado.sin_pct), con_pct: t(r.devanado.con_pct), caso: r.caso } });
  }, [jobTrafo?.id, jobTrafo?.status]);  // eslint-disable-line react-hooks/exhaustive-deps
  const calcularTrafo = () => {
    if (!carga) return;
    void startJob(() => api.informesTrafo(ws.id, { project, alimentador: carga.alimentador, carga: f.trafoCarga,
      caso: casoElegido }));
  };

  // RF-60 y RF-92: factor de carga del mes de la máxima del medidor de ese alimentador.
  const fcMedido = useMemo(() => {
    if (!carga) return null;
    const fila = maximas.find((m) => m.alimentador === carga.alimentador && ctx.factor_carga[m.medidor]);
    return fila ? { medidor: fila.medidor, ...ctx.factor_carga[fila.medidor] } : null;
  }, [carga, maximas, ctx.factor_carga]);

  // RF-91: al elegir la carga se rellenan su potencia y su punto de conexión; lo demás, editable.
  const elegir = (k: string) => {
    const c = solas.find((x) => `${x.alimentador}|${x.sed}` === k);
    // 063:RF-48: la solicitud, el punto y lo leído son de la carga anterior; la cabecera de la empresa sigue.
    if (esOtraCarga(clave, k)) {
      const vacia: Sol = { cliente: '', ubicacion: '', tipo_solicitud: 'factibilidad de suministro', potencia_kw:
        c?.kw != null ? String(c.kw) : '', fecha_solicitud: '', set_nombre: '', tension_kv: '', transformador: '',
        expediente: '', potencia_actual_kw: '', nis: '', codigo_ficha: '' };
      const otroAlimentador = clave.split('|')[0] !== k.split('|')[0];
      fijar({ clave: k, codigo: c?.barra ?? '', sol: vacia, punto: { pcc_mva: '', utm_x: '', utm_y: '' }, leidos: [],
        fechas: [], concesion: '', cab: { ...cab, asunto: '', numero: '' },
        ...(otroAlimentador ? { fc: '', trafoCarga: '', trafo: { kv: '', sin_pct: '', con_pct: '', caso: '' },
          perd: { sistema_electrico: '', codigo_sistema: '', reconocido_kw_pct: '', reconocido_kwh_pct: '',
            precio_compra: '' } } : {}) });
      return;
    }
    // 063:RF-16: la estructura ya leída de la ficha no se pisa con la barra.
    const conservar = codigo.trim() && !solas.some((x) => x.barra === codigo);
    fijar(c ? { clave: k, codigo: conservar ? codigo : c.barra,
      sol: { ...sol, potencia_kw: c.kw != null ? String(c.kw) : sol.potencia_kw } }
      : { clave: k });
  };
  /**
   * 017:RF-139: lo leído de la carta va a los campos en blanco; lo escrito por el operador no
   * se pisa. El tipo propuesto por defecto («factibilidad de suministro») cuenta como blanco.
   */
  const leidoDelSolicitante = (r: DocumentosResultado) => {
    const valor = (k: string) => {
      const v = r.propuesta[k]?.valor;
      return v == null ? '' : String(v);
    };
    const de: Partial<Sol> = { cliente: valor('cliente'), ubicacion: valor('ubicacion'),
      tipo_solicitud: valor('tipo_solicitud'), potencia_kw: valor('potencia_kw'), fecha_solicitud: valor('fecha'),
      expediente: [valor('solicitud'), valor('expediente')].filter(Boolean).join(' y '),
      set_nombre: valor('set_nombre'), tension_kv: valor('tension_kv'),
      potencia_actual_kw: valor('potencia_actual_kw'), nis: valor('nis'), codigo_ficha: valor('codigo_ficha') };
    const nueva = { ...sol };
    for (const [k, v] of Object.entries(de) as [keyof Sol, string][]) {
      const libre = !nueva[k].trim() || (k === 'tipo_solicitud' && nueva[k] === 'factibilidad de suministro')
        || (k === 'potencia_kw' && esPotenciaPropuesta(nueva[k], carga?.kw));
      if (v && libre) nueva[k] = v;
    }
    const nuevoPunto = { ...punto };
    for (const k of ['pcc_mva', 'utm_x', 'utm_y'] as const) if (valor(k) && !nuevoPunto[k].trim()) nuevoPunto[k] = valor(k);
    // 063:RF-16: la estructura de la ficha es el código del punto de diseño; la barra del modelo
    // sigue siendo la del cálculo. Solo si el operador no escribió otro.
    const estructura = valor('estructura');
    const codigoLibre = !codigo.trim() || (carga && codigo === carga.barra);
    // 063:RF-19, RF-20: este bloque lee un PDF por vez: lo de los anteriores se conserva.
    const fichero = r.documentos[0]?.fichero ?? '';
    fijar({ sol: nueva, punto: nuevoPunto, leidos: acumularLeidos(leidos, fichero, r.alimentadores_leidos),
      fechas: acumularLeidos(fechasLeidas, fichero, r.fechas),
      ...(estructura && codigoLibre ? { codigo: estructura } : {}),
      ...(valor('lugar') && !cab.lugar.trim() ? { cab: { ...cab, lugar: valor('lugar') } } : {}) });
  };
  /** 063:RF-19: un alimentador de los PDF que no es el de la carga elegida. */
  const otroAlimentador = alimentadoresDistintos(leidos, carga?.alimentador);
  /** 063:RF-14: el incremento de una ampliación. */
  const incremento = num(sol.potencia_kw) != null && num(sol.potencia_actual_kw) != null
    ? (num(sol.potencia_kw) as number) - (num(sol.potencia_actual_kw) as number) : null;

  // 017:RF-124: la vista previa se dibuja en el servidor con lo guardado; no es un trabajo.
  const [vista, setVista] = useState<{ fichero: string; rotulo: string; cuando: number } | null>(null);
  const verUbicacion = async () => {
    if (!carga) return;
    const r = await run(() => api.informesUbicacion(ws.id, { project, alimentador: carga.alimentador,
      sed: carga.sed, cliente: sol.cliente, potencia_kw: num(sol.potencia_kw), codigo_punto: codigo }));
    if (r) setVista({ ...r, cuando: Date.now() });
  };

  // El factor medido se propone solo si el operador no escribió otro.
  useEffect(() => { if (fcMedido && !fc) setFc(String(fcMedido.fc)); }, [fcMedido]);  // eslint-disable-line react-hooks/exhaustive-deps

  const ultimo = Object.values(jobs).filter((j) => j.kind === 'informe_factibilidad').pop();
  const faltan = ctx.faltan.factibilidad;
  const requeridos = SOLICITUD.filter(([, label]) => label.endsWith('*')).map(([k]) => k);
  const vacios = requeridos.filter((k) => !sol[k].trim());
  // 063:RF-1, RF-2: el botón prepara los casos y corre sus flujos en el mismo trabajo; ya no
  // exige haber pasado por 4.2. Usa DIgSILENT: espera a que su carril quede libre.
  const motivo = faltan.length ? `Falta en el perfil de empresa: ${faltan.join(', ')}.`
    : !carga ? 'Elija la carga nueva del informe.'
      : vacios.length ? `Complete la solicitud: ${vacios.map((k) => SOLICITUD.find(([x]) => x === k)![1].replace(' *', '')).join(', ')}.`
        : !limitesOk ? 'Escriba la banda de tensión y el umbral de cargabilidad.'
          : pfBusy ? 'DIgSILENT está ocupado con otro trabajo: espere a que termine.' : '';
  // 063:RF-18: el NIS va en el asunto propuesto.
  const asuntoPropuesto = `FACTIBILIDAD DE SUMINISTRO DE ${sol.cliente.toUpperCase()}`
    + (sol.nis.trim() ? ` (NIS ${sol.nis.trim()})` : '');
  const generar = () => {
    if (!carga) return;
    const body: InformeFactibilidadForm = {
      project, alimentador: carga.alimentador, sed: carga.sed, ...cab,
      asunto: cab.asunto || asuntoPropuesto,
      limites: limites(), bandas: bandas(), factor_carga: num(fc), codigo_punto: codigo, preparar_casos: true,
      punto_ficha: { pcc_mva: num(punto.pcc_mva), utm_x: num(punto.utm_x), utm_y: num(punto.utm_y) },
      solicitud: { ...sol, potencia_kw: num(sol.potencia_kw), tension_kv: num(sol.tension_kv),
        potencia_actual_kw: num(sol.potencia_actual_kw),
        en_concesion: concesion === '' ? null : concesion === 'si' },
      perdidas_reconocidas: { sistema_electrico: perd.sistema_electrico, codigo_sistema: perd.codigo_sistema,
        reconocido_kw_pct: num(perd.reconocido_kw_pct), reconocido_kwh_pct: num(perd.reconocido_kwh_pct),
        precio_compra: num(perd.precio_compra) },
      transformador_set: { kv: num(trafo.kv), sin_pct: num(trafo.sin_pct), con_pct: num(trafo.con_pct), caso: trafo.caso },
    };
    void startJob(() => api.informeFactibilidad(ws.id, body));
  };

  // 017:RF-136: la carta suele llegar antes que la carga; se lee ya y lo leído queda en el
  // formulario guardado hasta que la carga se aplique en 3.2.
  const documento = (
    <DocumentosSolicitante tipo="factibilidad" varios={false}
      titulo="Carta, oficio u otro documento del solicitante" onLeido={leidoDelSolicitante} />
  );
  if (!ctx.cargas.length || !solas.length) {
    const leido = SOLICITUD.filter(([k]) => sol[k].trim() && k !== 'tipo_solicitud');
    return <div className="stack compact">
      <p className="muted">No hay ninguna carga nueva ingresada sola y aplicada en {feeders.join(', ')}: intégrela en
        el paso 3 con «Una carga nueva» y aplíquela.{enBloque.length > 0 && ` Las ${enBloque.length} del libro van en bloque
        y entran como solicitudes vigentes.`}</p>
      <div className="form-grid">{documento}</div>
      {leido.length > 0 && <small className="muted">Solicitud guardada para el informe: {leido.map(([k, l]) =>
        `${l.replace(' *', '')}: ${sol[k]}`).join(' · ')}.</small>}
    </div>;
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
          {/* 017:RF-136, RF-139: la carta u oficio del solicitante rellena lo que está en blanco. */}
          {documento}
          <Campos campos={SOLICITUD} valores={sol} fijar={(k, v) => setSol((s) => ({ ...s, [k]: v }))} />
          {incremento != null && <small className="muted span-2">Ampliación de {fmtNum(num(sol.potencia_actual_kw) as number, 0)} kW
            a {fmtNum(num(sol.potencia_kw) as number, 0)} kW: incremento de {fmtNum(incremento, 0)} kW (063:RF-14).</small>}
          {incrementoNoCuadra(incremento, carga.kw) && <small className="alert alert-warn span-2">El incremento de la
            solicitud es de {fmtNum(incremento as number, 0)} kW y la carga del modelo vale {fmtNum(carga.kw as number, 0)} kW:
            compruebe las potencias antes de generar.</small>}
          {fechasLeidas.length > 1 && <small className="muted span-2">Fechas leídas: {fechasLeidas.map((x) =>
            `${x.valor} (${x.fichero})`).join(' · ')}. Se propone la de la solicitud del interesado.</small>}
          {clienteAjeno(carga.sed, sol.cliente) && <small className="alert alert-warn span-2">El cliente «{sol.cliente}» no
            parece el de la carga «{carga.sed}»: compruebe la solicitud antes de generar; si se genera así, el
            informe lo señala.</small>}
          {otroAlimentador.length > 0 && <small className="alert alert-warn span-2">Los PDF dicen {otroAlimentador.map((x) =>
            `${x.valor} (${x.fichero})`).join(', ')}, y la carga elegida está en {carga.alimentador}: compruebe que es la
            carga correcta antes de generar.</small>}
          <label className="field"><span>¿Predio en el área de concesión?</span>
            <select value={concesion} onChange={(e) => setConcesion(e.target.value as '' | 'si' | 'no')}>
              <option value="">Sin confirmar (queda señalado)</option><option value="si">Sí</option><option value="no">No</option>
            </select>
          </label>
          <label className="field"><span>Código del punto de diseño</span>
            <input value={codigo} onChange={(e) => setCodigo(e.target.value)} />
            <small className="muted">Barra donde el paso 3 conectó la carga: {carga.barra}. Con la ficha, la
              estructura del punto de diseño; el cálculo sigue en la barra.</small>
          </label>
        </div>
        <p><strong>Punto de diseño (ficha)</strong></p>
        <div className="form-grid">
          <Campos campos={PUNTO_FICHA} valores={punto} fijar={(k, v) => fijar({ punto: { ...punto, [k]: v } })} />
        </div>
        {/* 017:RF-124: la imagen de ubicación antes de generar, con la geografía de 4.2. */}
        <div className="row">
          <button className="btn btn-sm" onClick={verUbicacion}>Vista previa de la ubicación</button>
          {vista && <small className="muted">{vista.rotulo}</small>}
        </div>
        {vista && <img className="vista-ubicacion" alt={`Ubicación de ${vista.rotulo}`}
          src={`${api.fileUrl(ws.id, vista.fichero)}?v=${vista.cuando}`} />}
        <p><strong>Pérdidas</strong></p>
        <div className="form-grid">
          <label className="field"><span>Factor de carga</span>
            <input value={fc} inputMode="decimal" onChange={(e) => setFc(e.target.value)} />
            <small className="muted">{fcMedido ? `De la medición de ${fcMedido.medidor} en ${fcMedido.mes} (2.2).`
              : 'Sin máxima de cabecera buscada en 2.2: escríbalo, o las pérdidas quedan señaladas.'}</small>
          </label>
          <div className="field span-2">
            <span>Libro de pérdidas de la empresa</span>
            {libro && <>
              <div className="row"><strong>{libro.name}</strong>
                <button className="btn btn-ghost btn-sm" onClick={quitarLibro}>Quitar</button></div>
              {libro.error ? <small className="alert alert-warn">{libro.error}</small>
                : lectura && <small className="muted">{carga.alimentador}: sistema {lectura.sistema_electrico ?? '—'},
                  reconocidas {lectura.reconocido_kw_pct ?? '—'} % en kW y {lectura.reconocido_kwh_pct ?? '—'} % en kWh,
                  precio {lectura.precio_compra ?? '—'}{lectura.faltan.length ? ` · falta: ${lectura.faltan.join(', ')}` : ''}.
                  Se usa si deja en blanco los campos de abajo.</small>}
            </>}
            {/* Spec 025, RF-39: otro libro se sube o se indica sin quitar antes el actual. */}
            <FileDrop compact accept=".xlsx,.xlsm" onFiles={subirLibro}>
              <span>{libro ? 'Reemplazar: soltar' : 'Soltar'} o <u>elegir</u></span></FileDrop>
            {health.server_paths && <div className="row">
              <input className="search" placeholder={`o ruta en el servidor${libro ? ' (reemplaza la actual)' : ''}`} value={ruta}
                onChange={(e) => setRuta(e.target.value)} />
              <button className="btn btn-sm" disabled={!ruta.trim()} onClick={libroPorRuta}>Usar ruta</button>
            </div>}
            {!libro && <small className="muted">Sin libro, escriba lo reconocido abajo; si falta, queda señalado en el Word.</small>}
          </div>
          <Campos campos={PERDIDAS.map(([k, label, modo]): [keyof Perd, string, string?] => [k, label.replace('moneda/', `${ctx.moneda ?? 'moneda'}/`), modo])}
            valores={perd} fijar={(k, v) => setPerd((p) => ({ ...p, [k]: v }))} />
        </div>
        <p><strong>Transformador de la SET (del proyecto de transmisión)</strong></p>
        <p className="muted small">El proyecto de transmisión tiene una carga por barra de SET, no por alimentador: elija
          la de la barra de {carga.alimentador}. Sin proyecto se calcula el caso tal cual; con proyecto, esa carga más lo
          que sube la cabecera de {carga.alimentador} entre los flujos de 4.2. Nada se guarda en el proyecto de
          transmisión.</p>
        <div className="form-grid">
          <div className="field">
            <span>Carga de la barra de la SET</span>
            <input list="ad08-cargas" value={f.trafoCarga} placeholder={ad08 ? `${ad08.cargas.length} cargas` : 'lea antes las cargas'}
              onChange={(e) => fijar({ trafoCarga: e.target.value })} />
            <datalist id="ad08-cargas">{(ad08?.cargas ?? []).map((c) => (
              <option key={c.nombre} value={c.nombre}>{c.barra} · {c.kv ?? '?'} kV · {c.trafos.join(', ')}</option>
            ))}</datalist>
          </div>
          <label className="field"><span>Caso de estudio</span>
            {ad08 ? <select value={casoElegido} onChange={(e) => setCaso(e.target.value)}>
              {ad08.casos.map((c) => <option key={c} value={c}>{c}</option>)}
            </select> : <input value={casoElegido} onChange={(e) => setCaso(e.target.value)} placeholder={`${anio}_D`} />}
          </label>
        </div>
        <div className="row">
          <button className="btn btn-sm" disabled={pfBusy} onClick={() => void startJob(() => api.informesTrafoCargas(ws.id))}>
            Leer cargas del proyecto de transmisión
          </button>
          <button className="btn btn-sm btn-pf" disabled={pfBusy || !f.trafoCarga.trim()} onClick={calcularTrafo}>
            Calcular la cargabilidad en DIgSILENT
          </button>
          {jobTrafo?.status === 'failed' && <small className="alert alert-error">{jobTrafo.error}</small>}
          {jobTrafo?.status === 'done' && jobTrafo.result && <small className="muted">
            {(jobTrafo.result as TrafoResultado).transformador} en {(jobTrafo.result as TrafoResultado).caso}, con
            Δ {fmtNum((jobTrafo.result as TrafoResultado).delta_kw, 0)} kW.</small>}
        </div>
        <div className="form-grid">
          <Campos campos={TRAFO} valores={trafo} fijar={(k, v) => setTrafo((t) => ({ ...t, [k]: v }))} />
        </div>
        <small className="muted">Sin la cargabilidad del transformador el informe no puede concluir que la carga es
          factible (RF-71).</small>
      </>}
      <div className="row">
        <button className="btn btn-primary" disabled={busy || Boolean(motivo)} onClick={generar}>
          Generar informe de factibilidad
        </button>
        <AvisoPlantilla neutra={ctx.plantilla_neutra.factibilidad} />
        {motivo && <small className="muted">{motivo}</small>}
        {!motivo && busy && <small className="muted">Espere a que termine el trabajo en curso.</small>}
      </div>
      <Resultado r={(ultimo?.status === 'done' ? ultimo.result : null) as InformeResultado | null}
        cancelado={ultimo?.status === 'cancelled'} />
    </div>
  );
}
