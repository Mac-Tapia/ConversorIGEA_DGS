import { Fragment, useEffect, useMemo, useState } from 'react';
import { api, fmtNum, type DemandaTipo } from '../api';
import { estadoCatalogoClientes } from '../clientesCatalogo';
import { useApp } from '../context';
import type { BarraDeSet, CentralDeBarra, CentralTermica, ComparacionFijas, CriterioFijas, Escaneo, SistemaDelProyecto, ClientesCruce, ClienteImportante, MaximaCabecera, MedidoresExternos, ValorFija } from '../types';
import { AjusteCabecera } from './AjusteCabecera';
import { FileDrop, useToast } from './ui';

const LIBROS: { tipo: DemandaTipo; titulo: string; ayuda: string }[] = [
  { tipo: 'medidores', titulo: 'Medidor por alimentador', ayuda: 'Columnas «codigo alimentador» y «Medidor».' },
  { tipo: 'cabecera', titulo: 'Medición de cabecera', ayuda: 'Uno o varios libros (una hoja por medidor), o la carpeta que los contiene.' },
  { tipo: 'suministros', titulo: 'Suministros', ayuda: 'Uno o varios libros, o una carpeta. Se descubre el vigente por contenido; el nombre es libre.' },
  { tipo: 'clientes', titulo: 'Clientes importantes mensuales', ayuda: 'Carpeta o libros con hoja «resumen»: Nis/EA/ERI/Pot o SUMINISTRO/EA_TOTAL/ERI_TOTAL/POT_MAX.' },
  { tipo: 'estructura', titulo: 'Estructura zonal → SET (opcional)', ayuda: '«Zonal», «Código SET» y «Alimentador» (y sistema eléctrico, sector y siglas). Sin ella, la del perfil de empresa.' },
];
const EXT = '.xls,.xlsx,.xlsb,.xlsm';

/** Un libro de la demanda medida: subida o, en local, ruta del servidor (RF-39). */
function Libro({ tipo, titulo, ayuda }: (typeof LIBROS)[number]) {
  const { ws, setWs, run, health, startJob, jobs, active } = useApp();
  const [ruta, setRuta] = useState('');
  const meta = ws.demanda?.[tipo];
  // Spec 025, RF-28 y RF-32: la cabecera en carpeta también tiene su índice por año.
  const indexable = (m: typeof meta) => tipo === 'clientes' || (tipo === 'cabecera' && m?.source_kind === 'folder');
  const conIndice = indexable(meta);
  const tipoTrabajo = tipo === 'clientes' ? 'demanda_clientes_index' : 'demanda_cabecera_index';
  const indexando = Object.values(jobs).some((j) => j.kind === tipoTrabajo
    && (j.status === 'queued' || j.status === 'running'));
  const engineBusy = Boolean(active.engine);
  const indexar = () => startJob(() => (tipo === 'clientes'
    ? api.demandaClientesIndexar(ws.id) : api.demandaCabeceraIndexar(ws.id)));

  // 025:RF-78: el índice sale de asignar la fuente, no de montar la pestaña. Antes un efecto
  // lo lanzaba en cada montaje para la cabecera y los clientes a la vez: el segundo chocaba
  // con el primero en el carril del motor y salía «Ya hay un trabajo en curso» sin pedir nada.
  const asignada = (r: Awaited<ReturnType<typeof api.demandaRuta>>) => {
    setWs(r);
    if (indexable(r.demanda?.[tipo])) void indexar();
  };
  const subir = async (files: File[]) => {
    const r = await run(() => api.demandaSubir(ws.id, tipo, files));
    if (r) asignada(r);
  };
  const porRuta = async () => {
    const r = await run(() => api.demandaRuta(ws.id, tipo, ruta.trim()));
    if (r) { asignada(r); setRuta(''); }
  };
  const quitar = async () => {
    const r = await run(() => api.demandaQuitar(ws.id, tipo));
    if (r) setWs(r);
  };
  return (
    <div className="field">
      <span>{titulo}</span>
      {meta && (
        <div className="row">
          <strong>{meta.name}</strong>
          {meta.libros && !conIndice && <span className="muted small">({meta.libros.length} libro(s): {meta.libros.join(', ')})</span>}
          <span className="muted small">{meta.origin === 'server' ? 'ruta del servidor' : 'subido'}</span>
          <button className="btn btn-ghost btn-sm" disabled={engineBusy} onClick={quitar}>Quitar</button>
        </div>
      )}
      {/* Spec 025, RF-39 y RF-40: siempre se puede subir otro libro o indicar otra carpeta
          (un año nuevo, una entrega corregida) sin quitar antes el actual. */}
      <FileDrop compact accept={EXT} disabled={engineBusy}
        multiple={tipo === 'cabecera' || tipo === 'suministros' || tipo === 'clientes'} onFiles={subir}>
        <span>{meta ? 'Reemplazar: soltar' : 'Soltar'} o <u>elegir</u>{tipo === 'cabecera' || tipo === 'suministros' || tipo === 'clientes' ? ' (varios)' : ''}</span>
      </FileDrop>
      {health.server_paths && (
        <div className="row">
          <input className="search" disabled={engineBusy}
            placeholder={tipo === 'cabecera' || tipo === 'suministros' || tipo === 'clientes'
              ? `o ruta de la carpeta en el servidor${meta ? ' (reemplaza la actual)' : ''}`
              : `o ruta en el servidor${meta ? ' (reemplaza la actual)' : ''}`}
            value={ruta} onChange={(e) => setRuta(e.target.value)}
            // 091:RF-31: las rutas de las entradas se aplicaban con Intro; las de medición no.
            onKeyDown={(e) => { if (e.key === 'Enter' && ruta.trim() && !engineBusy) void porRuta(); }} />
          <button className="btn btn-sm" disabled={!ruta.trim() || engineBusy} onClick={porRuta}>Usar ruta</button>
        </div>
      )}
      {engineBusy && <small className="muted">Hay un trabajo del motor en curso: al terminar se pueden cambiar los libros.</small>}
      {conIndice && meta && (
        <LibrosPorAnio meta={meta} tipo={tipo} indexando={indexando} bloqueado={engineBusy} actualizar={indexar} />
      )}
      {/* 004:RF-63: libros de clientes subidos en «Suministros», nombrados en su hueco. */}
      {tipo !== 'clientes' && meta?.avisos?.map((aviso) => <p className="alert alert-warn" key={aviso}>{aviso}</p>)}
      <small className="muted">{ayuda}</small>
    </div>
  );
}

/** Una fila del panel por año: un libro de clientes o de cabecera, como entró. */
interface FilaLibro { libro: string; anio: number | null; meses: string[]; detalle: string; usado: boolean; motivos: string[] }

const ORIGEN_MES: Record<string, string> = {
  nombre: 'del nombre', contenido: 'de una fecha del libro', manual: 'asignado a mano', sin_mes: 'sin mes',
};

/** 035:RF-3: de dónde salen la P y la Q de un cliente fijo. */
const ORIGEN_VALORES: Record<string, string> = {
  REGISTRO_DEL_INSTANTE: 'registro de la máxima', ERI_DEL_REGISTRO: 'registro de su POT',
  'ERI/EA': 'POT y EA/ERI del mes', FP_CABECERA_FALLBACK: 'POT y FP de la cabecera',
};

/** 039:RF-1: los dos criterios de las fijas, con lo que toma cada uno de la hoja de 15 minutos. */
const CRITERIOS_FIJAS: { valor: CriterioFijas; texto: string; ayuda: string }[] = [
  { valor: 'coincidente', texto: 'Coincidentes con la máxima de cabecera',
    ayuda: 'Cada fija con su EA × 4 y ERI × 4 del registro de la fecha y hora de la máxima de su alimentador (039:RF-3)' },
  { valor: 'maximo_mes', texto: 'Máximo del mes de cada fija',
    ayuda: 'Cada fija con su POT máxima del mes y el ERI × 4 de ese mismo registro, cada una de su día (039:RF-2)' },
];
const criterioDe = (c?: CriterioFijas) => CRITERIOS_FIJAS.find((x) => x.valor === (c ?? 'coincidente')) ?? CRITERIOS_FIJAS[0];

/** 039:RF-1: un solo selector del criterio de todas las fijas, en 2.3 y en «Recalibrar». */
function SelectorCriterio({ valor, cambiar, disabled }: {
  valor: CriterioFijas; cambiar: (c: CriterioFijas) => void; disabled?: boolean;
}) {
  return (
    <label className="row" title={criterioDe(valor).ayuda}>
      <span>Fijas de la tabla cruzada</span>
      <select value={valor} disabled={disabled} onChange={(e) => cambiar(e.target.value as CriterioFijas)}
        aria-label="Criterio de las fijas de la tabla cruzada">
        {CRITERIOS_FIJAS.map((c) => <option key={c.valor} value={c.valor} title={c.ayuda}>{c.texto}</option>)}
      </select>
    </label>
  );
}

/** 039:RF-7: desplegable con los alimentadores que toman sus fijas con «máximo del mes»; los demás, el criterio general. */
function AlimentadoresMaximoMes({ alimentadores, marcados, cambiar, disabled }: {
  alimentadores: string[]; marcados: string[]; cambiar: (m: string[]) => void; disabled?: boolean;
}) {
  if (!alimentadores.length) return null;
  const suyos = marcados.filter((a) => alimentadores.includes(a));
  return (
    <details className="field" aria-label="Alimentadores con fijas en su máximo del mes">
      <summary className="small">Con «{CRITERIOS_FIJAS[1].texto}»: {suyos.length ? suyos.join(', ') : 'ninguno'}
        {' '}(los demás, el criterio de arriba; 039:RF-7)</summary>
      <div className="row">
        {alimentadores.map((a) => (
          <label key={a} className="row small">
            <input type="checkbox" checked={suyos.includes(a)} disabled={disabled}
              onChange={(e) => cambiar(e.target.checked ? [...suyos, a] : suyos.filter((x) => x !== a))} /> {a}
          </label>
        ))}
      </div>
    </details>
  );
}

/** 039:RF-9, RF-12: la P y la Q con que va una fija según la selección «a su máxima» de ahora, que puede haber
 * cambiado desde el cruce: marcada, la de su máxima del mes; desmarcada, la del criterio de su alimentador. */
const valorQueVa = (c: ClienteImportante, marcada: boolean): ValorFija | null => {
  if (marcada) return c.valores?.maximo_mes ?? (c.p_kw == null ? null : { p_kw: c.p_kw, q_kvar: c.q_kvar ?? null, fecha: c.fecha_valores, metodo: c.metodo });
  if (c.a_su_maxima && c.valores) return c.valores[c.criterio_alimentador ?? 'coincidente'];
  return c.p_kw == null ? null : { p_kw: c.p_kw, q_kvar: c.q_kvar ?? null, fecha: c.fecha_valores, metodo: c.metodo };
};
const kwKvar = (v: ValorFija | null | undefined) => (v ? `${fmtNum(v.p_kw, 1)} kW · ${v.q_kvar == null ? '—' : fmtNum(v.q_kvar, 1)} kvar` : '—');

const porAlimentador = (marcados: string[], de: string[]): Record<string, CriterioFijas> =>
  Object.fromEntries(marcados.filter((a) => de.includes(a)).map((a) => [a, 'maximo_mes' as CriterioFijas]));

const rangoMeses = (meses: string[]) => (meses.length === 0 ? '—'
  : meses.length === 1 ? nombreMes(meses[0]) : `${nombreMes(meses[0])} a ${nombreMes(meses[meses.length - 1])}`);

/**
 * Spec 025, RF-34 y RF-35: cómo entró cada libro, por año. Llegarán años, libros y hojas:
 * cada uno se ve con su ruta, sus meses y si se usa; y se dice dónde dejar uno nuevo.
 */
function LibrosPorAnio({ meta, tipo, indexando, bloqueado, actualizar }: {
  meta: NonNullable<NonNullable<ReturnType<typeof useApp>['ws']['demanda']>['clientes']>;
  tipo: DemandaTipo;
  indexando: boolean;
  bloqueado: boolean;
  actualizar: () => unknown;
}) {
  const filas: FilaLibro[] = tipo === 'clientes'
    ? (meta.catalogo ?? []).map((l) => ({
      libro: l.nombre, anio: l.anio ?? null, meses: l.mes ? [l.mes] : [],
      detalle: `mes ${ORIGEN_MES[l.origen_mes] ?? l.origen_mes}`, usado: l.activo,
      // 004:RF-65: por qué no se usa (p. ej., sin hoja «resumen»).
      motivos: l.activo ? [] : l.avisos ?? [] }))
    : (meta.indice ?? []).map((l) => ({
      libro: l.relativa, anio: l.anio, meses: l.meses,
      detalle: `${l.hojas.length} hoja(s) de medición`, usado: !l.error, motivos: l.error ? [l.error] : [] }));
  const anios = [...new Set(filas.map((f) => f.anio))].sort((a, b) => (a ?? 0) - (b ?? 0));
  return <div className="stack compact">
    <div className="row">
      <button className="btn btn-sm" disabled={bloqueado} onClick={actualizar}>
        {indexando ? 'Actualizando índice…' : 'Actualizar índice'}
      </button>
      {meta.indexado_en && <small className="muted">{filas.length} libro(s) indexado(s)
        {meta.anios?.length ? `, de ${meta.anios.join(', ')}` : ''}</small>}
    </div>
    {meta.avisos?.map((aviso) => <p className="alert alert-warn" key={aviso}>{aviso}</p>)}
    {filas.length > 0 && <div className="table-wrap table-short"><table className="table">
      <thead><tr><th>Año</th><th>Libro</th><th>Meses</th><th>Qué trae</th><th>Estado</th></tr></thead>
      <tbody>{anios.flatMap((anio) => filas.filter((f) => f.anio === anio).map((f, i) => (
        <tr key={f.libro}>
          <td className="strong">{i === 0 ? (anio ?? 'Sin año') : ''}</td>
          <td className="mono">{f.libro}</td><td>{rangoMeses(f.meses)}</td><td>{f.detalle}</td>
          <td>{f.usado ? 'Se usa' : 'No se usa'}
            {f.motivos.map((a) => <div className="muted small" key={a}>{a}</div>)}</td>
        </tr>
      )))}</tbody>
    </table></div>}
    {meta.source_kind === 'folder' && (
      <small className="muted">Para otro año, deje sus libros en «{meta.name}/AAAA/» (con las
        subcarpetas que quiera) y pulse «Actualizar índice»: solo se abren los nuevos o cambiados.</small>
    )}
  </div>;
}

const fp = (n: number | null) => (n == null ? '—' : fmtNum(n, 3));
/** «2026-04» → «abril 2026»; el índice guarda el mes en AAAA-MM. */
const nombreMes = (mes: string) => {
  const [anio, m] = mes.split('-').map(Number);
  return anio && m ? new Date(anio, m - 1, 1).toLocaleDateString('es', { month: 'long', year: 'numeric' }) : mes;
};

type Par = { alimentador: string; medidor: string };
const clave = (p: Par) => `${p.alimentador}|${p.medidor}`;
/** En la máxima, los medidores de una central van con este «alimentador»: no es uno de la
 * red, así que el ajuste no los toma por medidores de cabecera (spec 021, RF-25). */
export const alimentadorDeCentral = (f: string) => `Central ${f}`;
const CENTRAL_VACIA: CentralTermica = { generacion: '', llegada: '', salida: '', nodo: '' };
const centralCompleta = (c?: CentralTermica) => Boolean(c && c.generacion && c.llegada && c.salida);

/**
 * Calibración (spec 004, RF-22 a RF-41; spec 008, RF-8 a RF-11): máxima de cabecera de
 * cada alimentador marcado y clientes importantes con su SED. Se muestra y se descarga;
 * el ajuste de las demandas a la máxima (spec 006) va aparte, en ``AjusteCabecera``.
 */
export function DemandaMedida({ project, feeders }: { project: string; feeders: string[] }) {
  const { ws, run, startJob, active, jobs, refresh } = useApp();
  // Medidores del libro por alimentador marcado; ``null``: no está en el libro (RF-9).
  const [porAlim, setPorAlim] = useState<Record<string, string[] | null>>({});
  const [elegidos, setElegidos] = useState<Par[]>([]);
  const [manual, setManual] = useState<Record<string, string>>({});
  const [otroCodigo, setOtroCodigo] = useState<Record<string, string>>({});
  const [lista, setLista] = useState<string[]>([]);
  const [buscando, setBuscando] = useState(false);
  const [cruzando, setCruzando] = useState(false);
  const [cruce, setCruce] = useState<ClientesCruce | null>(null);
  // Spec 006, RF-25/RF-26: Nis desmarcados en la tabla del cruce; vacío, todos conectados.
  const [desconectados, setDesconectados] = useState<Set<string>>(new Set());
  const [filtro, setFiltro] = useState('');
  // Spec 013, RF-8 y RF-10: mes del libro de clientes, siempre elegido por el operador.
  const [periodo, setPeriodo] = useState('');
  // 039:RF-1: el criterio de todas las fijas; por defecto, coincidentes con la cabecera.
  const [criterioFijas, setCriterioFijas] = useState<CriterioFijas>('coincidente');
  // 039:RF-7: los alimentadores marcados con «máximo del mes».
  const [maximoMes, setMaximoMes] = useState<string[]>([]);
  // 039:RF-12, RF-15: los clientes fijos subidos «a su máxima»; se guardan en el espacio y vuelven al reabrir la web.
  const [aSuMaxima, setASuMaxima] = useState<string[]>(ws.fijas_a_su_maxima ?? []);
  const firmaASuMaxima = (ws.fijas_a_su_maxima ?? []).join('|');
  useEffect(() => { setASuMaxima(ws.fijas_a_su_maxima ?? []); }, [ws.id, firmaASuMaxima]); // eslint-disable-line react-hooks/exhaustive-deps
  const guardarASuMaxima = async (codigos: string[]) => {
    const r = await run(() => api.demandaASuMaxima(ws.id, codigos));
    if (r) setASuMaxima(r.a_su_maxima);
  };
  const conmutarMaxima = (codigo: string) => void guardarASuMaxima(
    aSuMaxima.includes(codigo) ? aSuMaxima.filter((c) => c !== codigo) : [...aSuMaxima, codigo]);
  // Spec 025, RF-22: el año de las mediciones, siempre elegido por el operador; con él,
  // ``periodo`` es «AAAA» (todo el año) o uno de sus meses.
  const [anio, setAnio] = useState('');
  // 028:RF-27: el operador elige el análisis: alimentadores (1 a 3 juntos), SET (máxima de barra, 022:RF-39
  // a RF-41) o sistema eléctrico (barras de 60 kV coincidentes, RF-31). «Son cosas diferentes, no se mezclan».
  const [tipoAnalisis, setTipoAnalisis] = useState<'alimentadores' | 'set' | 'sistema'>('alimentadores');
  const porBarra = tipoAnalisis !== 'alimentadores';
  // 028:RF-30: el último escaneo de cada proyecto, también el automático de una recalibración.
  const [escaneosGuardados, setEscaneosGuardados] = useState<Record<string, Escaneo>>({});
  // 022:RF-88: las centrales térmicas (CT…) del libro y dónde se conecta cada una: en la
  // barra de su SET (vacío) o en el tramo de un alimentador. Se piden en un sistema.
  const [centralesLibro, setCentralesLibro] = useState<CentralDeBarra[] | null>(null);
  const [centralTramo, setCentralTramo] = useState<Record<string, string>>({});
  useEffect(() => {
    if (!porBarra || centralesLibro !== null || !ws.demanda?.medidores) return;
    let vigente = true;
    api.demandaCentrales(ws.id).then((r) => {
      if (!vigente) return;
      setCentralesLibro(r.centrales);
      setCentralTramo(Object.fromEntries(r.centrales.filter((c) => c.tramo).map((c) => [c.medidor, c.tramo])));
    }).catch(() => { if (vigente) setCentralesLibro([]); });
    return () => { vigente = false; };
  }, [porBarra, centralesLibro, ws.id, ws.demanda?.medidores]);
  // 022:RF-52 a RF-54: un proyecto por sistema se calibra entero, con la máxima por barra.
  const [sistema, setSistema] = useState<SistemaDelProyecto | null>(null);
  // Spec 021, RF-25 a RF-27: central térmica en un tramo, por alimentador, y los medidores
  // del libro que no son de un alimentador de la red, donde se eligen los suyos.
  const [externos, setExternos] = useState<MedidoresExternos | null>(null);
  const [centrales, setCentrales] = useState<Record<string, CentralTermica>>({});
  const toast = useToast();
  const engineBusy = Boolean(active.engine);
  const estadoClientes = estadoCatalogoClientes(ws.demanda?.clientes, periodo, anio);
  // 025:RF-4: los años de la cabecera y de los clientes; sin carpetas de año, ninguno.
  const anios = useMemo(() => [...new Set([...(ws.demanda?.cabecera?.anios ?? []),
    ...(ws.demanda?.clientes?.anios ?? [])])].sort((a, b) => a - b).map(String),
  [ws.demanda?.cabecera?.anios, ws.demanda?.clientes?.anios]);
  const faltaAnio = anios.length > 0 && !periodo;

  // 091:RF-16: la de este proyecto y este año: en uno recién importado se ofrecía la última del espacio.
  const ultimo = faltaAnio ? undefined : Object.values(jobs).filter((j) => j.kind === 'demanda_cabecera' && j.result
    && (j.result as { project?: string }).project === project
    && (!anio || String(j.result.periodo ?? '').startsWith(anio))).pop();
  const cabecera = (ultimo?.result?.resultados ?? []) as MaximaCabecera[];
  // Mes de la máxima de cada alimentador: el ajuste (2.4) cruza con el libro de ese mes.
  const mesesMaxima = useMemo(() => {
    const m: Record<string, string[]> = {};
    cabecera.forEach((r) => {
      const mes = r.fecha?.slice(0, 7);
      if (mes && !r.error) (m[mes] ??= []).push(r.alimentador || r.medidor);
    });
    return m;
  }, [cabecera]);

  // Otro proyecto u otros alimentadores: lo buscado para los anteriores ya no vale.
  const marcados = feeders.join('|');
  useEffect(() => {
    setPorAlim({});
    setElegidos([]);
    setCruce(null);
    setDesconectados(new Set());
    setPeriodo('');
    setAnio('');
    setExternos(null);
    setCentrales({});
  }, [project, marcados]);
  // 091:RF-18: la tabla escribe lo de su máxima; con otra máxima hay que volver a verla.
  useEffect(() => {
    setCruce(null);
    setDesconectados(new Set());
  }, [ultimo?.id]);

  useEffect(() => {
    if (!project) { setSistema(null); setTipoAnalisis('alimentadores'); return; }
    let vivo = true;
    api.demandaSistema(ws.id, project).then((r) => {
      if (!vivo) return;
      setSistema(r.sistema);
      setTipoAnalisis(r.sistema ? 'sistema' : 'alimentadores');
    }).catch(() => { setSistema(null); setTipoAnalisis('alimentadores'); });
    return () => { vivo = false; };
  }, [ws.id, project, ws.demanda?.medidores?.name]);

  // Desplegable de códigos del libro (spec 004, RF-42): se vuelve a leer al cambiar el libro.
  const libroMedidores = ws.demanda?.medidores?.name ?? '';
  useEffect(() => {
    if (!libroMedidores) { setLista([]); return; }
    let vivo = true;
    api.demandaAlimentadores(ws.id).then((r) => { if (vivo) setLista(r.alimentadores); }).catch(() => setLista([]));
    return () => { vivo = false; };
  }, [ws.id, libroMedidores]);

  /** El alimentador de DIgSILENT con otro código en el libro: se busca con ese código. */
  const buscarComo = async (alimentador: string) => {
    const codigo = (otroCodigo[alimentador] ?? '').trim();
    if (!codigo) return;
    const r = await run(() => api.demandaMedidores(ws.id, codigo));
    if (!r) return;
    if (!r.encontrado) { toast('error', `${codigo} no está en el libro de medidores`, ''); return; }
    setPorAlim((m) => ({ ...m, [alimentador]: r.medidores }));
    setElegidos((xs) => [...xs.filter((x) => x.alimentador !== alimentador),
      ...r.medidores.map((medidor) => ({ alimentador, medidor }))]);
  };

  const buscar = async () => {
    setBuscando(true);
    try {
      const rs = await run(() => Promise.all(feeders.map((f) => api.demandaMedidores(ws.id, f))));
      if (!rs) return;
      const mapa: Record<string, string[] | null> = {};
      const pares: Par[] = [];
      rs.forEach((r, i) => {
        mapa[feeders[i]] = r.encontrado ? r.medidores : null;
        r.medidores.forEach((medidor) => pares.push({ alimentador: feeders[i], medidor }));
      });
      setPorAlim(mapa);
      setElegidos(pares);
      // RF-26, RF-27: los medidores que no son de la red, y la central que guarda el perfil
      // de cada alimentador marcado, ya rellena.
      const ext = await run(() => api.demandaMedidoresExternos(ws.id, feeders));
      if (ext) {
        setExternos(ext);
        if (ext.aviso_perfil) toast('error', 'Centrales del perfil', ext.aviso_perfil);
        const delPerfil: Record<string, CentralTermica> = {};
        feeders.forEach((f) => { if (ext.centrales_perfil[f]) delPerfil[f] = ext.centrales_perfil[f]; });
        setCentrales(delPerfil);
      }
    } finally {
      setBuscando(false);
    }
  };
  const anadir = (alimentador: string) => {
    const medidor = (manual[alimentador] ?? '').trim();
    if (!medidor) return;
    setPorAlim((m) => ({ ...m, [alimentador]: [...new Set([...(m[alimentador] ?? []), medidor])] }));
    setElegidos((xs) => (xs.some((x) => clave(x) === clave({ alimentador, medidor })) ? xs : [...xs, { alimentador, medidor }]));
    setManual((m) => ({ ...m, [alimentador]: '' }));
  };
  const marcado = (par: Par) => elegidos.some((x) => clave(x) === clave(par));
  const alternar = (par: Par) => setElegidos((xs) => (xs.some((x) => clave(x) === clave(par))
    ? xs.filter((x) => clave(x) !== clave(par)) : [...xs, par]));
  // RF-10: todos los medidores elegidos en un solo trabajo.
  // Spec 021, RF-25: con los tres de cada central declarada, en el mismo trabajo.
  const deCentrales: Par[] = feeders.filter((f) => centralCompleta(centrales[f])).flatMap((f) => {
    const c = centrales[f];
    return [c.generacion, c.llegada, c.salida].map((medidor) => ({ alimentador: alimentadorDeCentral(f), medidor }));
  });
  const aBuscar = [...elegidos, ...deCentrales.filter((p) => !elegidos.some((x) => x.medidor === p.medidor))];
  // 013:RF-11: la máxima del mes de análisis (el de los clientes); 021:RF-50: con un
  // instante, el registro de esa fecha y hora en todos, para calibrar a la vez.
  const maxima = (instante = '') => {
    if (!elegidos.length) { toast('error', 'Elija al menos un medidor', ''); return; }
    startJob(() => api.demandaCabecera(ws.id, aBuscar, { project, periodo, instante, por_barra: porBarra && !instante,
      sistema_60kv: tipoAnalisis === 'sistema' && !instante,
      centrales_tramo: centralTramo, coincidente: !porBarra && !instante && feeders.length > 1,
      centrales: Object.fromEntries(feeders.filter((f) => centralCompleta(centrales[f])).map((f) => [f, {
        generacion: centrales[f].generacion, llegada: centrales[f].llegada, salida: centrales[f].salida }])) }));
  };
  const demasiados = tipoAnalisis === 'alimentadores' && feeders.length > 3;
  const instanteActual = (ultimo?.result?.instante as string | null | undefined) ?? '';
  const barrasSet = (ultimo?.result?.barras as BarraDeSet[] | undefined) ?? [];
  const periodoBuscado = (ultimo?.result?.periodo as string | null | undefined) ?? '';
  // 028:RF-32: por defecto, el instante común de la mayor demanda conjunta; a mano, la máxima de una cabecera.
  const instantes = (ultimo?.result?.maximas_propias as { alimentador: string; fecha: string; kw: number }[] | undefined) ?? [];
  const instanteElegido = ultimo?.result?.coincidente ? '' : instanteActual;
  // Spec 028: el último escaneo de este proyecto en DIgSILENT (solo lectura).
  const trabajosDePf = Object.values(jobs).filter((j) => j.status === 'done' && (j.kind === 'pf_escaneo'
    || j.kind.startsWith('ajuste_') || j.kind.includes('recalibr'))).length;
  useEffect(() => {
    // 028:RF-30: al terminar una calibración o recalibración, su escaneo automático ya está guardado.
    let vivo = true;
    api.pfEscaneoGuardado(ws.id).then((r) => { if (vivo) setEscaneosGuardados(r.escaneo ?? {}); }).catch(() => undefined);
    return () => { vivo = false; };
  }, [ws.id, trabajosDePf]);
  const escaneo = (Object.values(jobs)
    .filter((j) => j.kind === 'pf_escaneo' && j.result && (j.result as unknown as Escaneo).project === project)
    .pop()?.result as unknown as Escaneo | undefined) ?? escaneosGuardados[project];
  const escanear = () => startJob(() => api.pfEscanear(ws.id, project, feeders, anio ? Number(anio) : null));
  const firmaEscaneo = escaneo ? JSON.stringify(Object.keys(escaneo.alimentadores)) + escaneo.project : '';
  useEffect(() => {
    // RF-11, RF-12: un generador en servicio encontrado declara la central de su alimentador
    // con su barra; el operador elige después los tres medidores.
    if (!escaneo) return;
    setCentrales((m) => {
      const n = { ...m };
      Object.entries(escaneo.alimentadores).forEach(([f, d]) => {
        const gens = (d.generadores ?? []).filter((g) => g.en_servicio && g.barra);
        const barras = [...new Set(gens.filter((g) => g.origen === 'operador').map((g) => g.barra as string))];
        const elegidas = barras.length ? barras : [...new Set(gens.map((g) => g.barra as string))];
        if (elegidas.length !== 1) return;
        if (!n[f]) n[f] = { ...CENTRAL_VACIA, nodo: elegidas[0] };
        else if (!n[f].nodo) n[f] = { ...n[f], nodo: elegidas[0] };
      });
      return n;
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [firmaEscaneo]);
  const ponerCentral = (f: string, campo: keyof CentralTermica, valor: string) =>
    setCentrales((m) => ({ ...m, [f]: { ...(m[f] ?? CENTRAL_VACIA), [campo]: valor } }));
  const quitarCentral = (f: string) => setCentrales((m) => {
    const n = { ...m };
    delete n[f];
    return n;
  });
  const opcionesExternas = externos?.medidores ?? [];
  // RF-11: los clientes de los alimentadores marcados.
  // Abrir libros de 50 a 150 MB tarda; sin «Cruzando…» el botón parecía no hacer nada.
  // 035:RF-1: cada alimentador con la fecha y hora de su máxima buscada, la misma con
  // que el ajuste (2.4) escribe las fijas; sin ella, la POT de cada cliente.
  const maximas = Object.fromEntries(cabecera
    .filter((m) => !m.error && m.fecha && feeders.includes(m.alimentador))
    .map((m) => [m.alimentador, { fecha: m.fecha, kw: m.kw, kvar: m.kvar, fp: m.fp }]));
  const hayMaximas = Object.keys(maximas).length > 0;
  // 091:RF-19 (cambia 025:RF-10): con el año entero, cada alimentador con el libro del mes de su máxima, a la
  // vista en 2.3; antes solo lo hacía el ajuste por dentro y se calibraba sin ver la tabla.
  const cruzaPorSuMes = /^\d{4}$/.test(periodo) && hayMaximas && Boolean(estadoClientes.porAnio || estadoClientes.listoParaCruzar);
  const cruzar = async () => {
    setCruzando(true);
    try {
      const r = await run(() => api.demandaClientes(ws.id, feeders, periodo || undefined,
        hayMaximas ? maximas : undefined, criterioFijas, porAlimentador(maximoMes, feeders), aSuMaxima));
      if (r) { setCruce(r); setDesconectados(new Set()); }
      // 004:RF-64: un fallo puede dejar el hueco de suministros sin libro y con su aviso.
      else await refresh().catch(() => undefined);
    } finally {
      setCruzando(false);
    }
  };
  // Los clientes de otro mes son otros: el cruce mostrado deja de valer.
  const elegirPeriodo = (mes: string) => {
    setPeriodo(mes);
    setCruce(null);
    setDesconectados(new Set());
  };
  // 039:RF-1: con otro criterio las fijas son otras; el plan (2.4) lleva el mismo.
  const elegirCriterio = (c: CriterioFijas) => {
    setCriterioFijas(c);
    setCruce(null);
    setDesconectados(new Set());
  };
  const elegirMaximoMes = (m: string[]) => {
    setMaximoMes(m);
    setCruce(null);
    setDesconectados(new Set());
  };
  // 039:RF-5: los dos criterios frente a la cabecera y a la red simulada, sin DIgSILENT.
  const comparar = () => startJob(() => api.demandaCompararFijas(ws.id, {
    project, alimentadores: feeders, periodo: periodo.length === 7 ? periodo : undefined, maximas }));
  const comparacion = Object.values(jobs)
    .filter((j) => j.kind === 'demanda_comparar_fijas' && j.status === 'done' && j.result).pop()
    ?.result as unknown as ComparacionFijas | undefined;
  // Con todo el año, cada máxima va con su mes (025:RF-10): no hay otro mes que avisar.
  const otrosMesesMaxima = periodo.length === 7
    ? Object.entries(mesesMaxima).filter(([mes]) => mes !== periodo) : [];
  const elegirAnio = (a: string) => {
    setAnio(a);
    elegirPeriodo(a);                  // 025:RF-23: al elegir el año, todo el año
  };
  const conmutar = (codigo: string) => setDesconectados((s) => {
    const n = new Set(s);
    if (!n.delete(codigo)) n.add(codigo);
    return n;
  });
  const excel = () => run(() => api.demandaExcel(ws.id, {
    cabecera, clientes: cruce?.cruzados ?? [], no_cruzados: cruce?.no_cruzados ?? [],
  }));

  const visibles = useMemo(() => {
    const f = filtro.trim().toLowerCase();
    const xs = cruce?.cruzados ?? [];
    return f ? xs.filter((c) => [c.codigo, c.nombre ?? '', c.sed, c.radial].some((v) => v.toLowerCase().includes(f))) : xs;
  }, [cruce, filtro]);
  // Un solo selector, en 2.3 junto al cruce (013:RF-12); cada mes dice qué alimentadores
  // tienen ahí su máxima de 2.2, para elegir el mismo (RF-15).
  const selectorMes = ((estadoClientes.esCatalogo && estadoClientes.activos > 1) || anio) && (
    <label className="row">
      <span>Mes de los clientes</span>
      <select value={periodo} disabled={engineBusy || faltaAnio} onChange={(e) => elegirPeriodo(e.target.value)}>
        {anio
          ? <option value={anio}>Todo {anio} (cada alimentador con el mes de su máxima)</option>
          : <option value="">Todo el registro (elija un mes para cruzar clientes)</option>}
        {estadoClientes.meses.map(({ mes, libro }) => (
          <option key={mes} value={mes}>
            {nombreMes(mes)} · {libro}{mesesMaxima[mes] ? ` · máxima de ${mesesMaxima[mes].join(', ')}` : ''}
          </option>
        ))}
      </select>
    </label>
  );
  // Se nombra el libro que falta: «los suministros o los clientes» no decía cuál asignar.
  // 004:RF-64: un hueco de suministros con solo libros de clientes queda guardado sin elección.
  const haySuministros = Boolean(ws.demanda?.suministros) && ws.demanda?.suministros?.seleccion !== null;
  const librosFaltan = [!haySuministros && 'el libro de suministros',
    !ws.demanda?.clientes && 'el de clientes importantes'].filter(Boolean) as string[];
  const buscados = Object.keys(porAlim).length > 0;
  const cuales = feeders.length === 1 ? feeders[0] : `${feeders.length} alimentadores`;

  return (
    <div className="calibracion">
      <Recalibrar project={project} criterioFijas={criterioFijas} elegirCriterio={elegirCriterio} />
      <h4>2.1 · Libros de medición</h4>
      <div className="form-grid">
        {LIBROS.map((l) => <Libro key={l.tipo} {...l} />)}
      </div>

      <h4>2.2 · Máxima de cabecera</h4>
      <div className="row">
        <button className="btn" disabled={!feeders.length || !ws.demanda?.medidores || buscando} onClick={buscar}>
          Buscar medidores de {cuales}
        </button>
        <button className="btn btn-ghost" disabled={!project || !feeders.length || Boolean(active.powerfactory)}
          onClick={escanear}
          title="Lee en DIgSILENT, sin cambiar nada, los generadores (centrales), bancos, variaciones y cargas cambiadas a mano de cada alimentador (spec 028)">
          Escanear en DIgSILENT</button>
        {!ws.demanda?.medidores && <small className="muted">Falta el libro de medidores por alimentador.</small>}
      </div>
      {escaneo && <DetectadoEnElEscaneo escaneo={escaneo} centrales={centrales} />}
      {escaneo && <EscaneoTabla escaneo={escaneo} />}
      <datalist id="demanda-alimentadores">{lista.map((a) => <option key={a} value={a} />)}</datalist>
      {buscados && (
        <div className="table-wrap table-short">
          <table className="table">
            <thead><tr><th>Alimentador</th><th>Medidores (se buscan los marcados)</th><th>A mano</th>
              <th title="Central térmica en un tramo del alimentador (spec 021)">Central térmica</th></tr></thead>
            <tbody>{feeders.map((f) => (
              <tr key={f}>
                <td className="strong">{f}</td>
                <td>
                  {porAlim[f] === null && <>
                    <small className="alert alert-warn">{f} no está en el libro de medidores: elija su código en el libro o
                      escriba su medidor a mano.</small>
                    <span className="row">
                      <input className="search" list="demanda-alimentadores" autoComplete="off" value={otroCodigo[f] ?? ''}
                        placeholder={lista.length ? `código en el libro (${lista.length})` : 'código en el libro'}
                        onChange={(e) => setOtroCodigo((m) => ({ ...m, [f]: e.target.value }))}
                        onKeyDown={(e) => { if (e.key === 'Enter') buscarComo(f); }} />
                      <button className="btn btn-sm btn-ghost" disabled={!(otroCodigo[f] ?? '').trim()} onClick={() => buscarComo(f)}>
                        Buscar con este código</button>
                    </span>
                  </>}
                  <div className="chips">
                    {(porAlim[f] ?? []).map((m) => (
                      <button key={m} className={`chip ${marcado({ alimentador: f, medidor: m }) ? 'on' : ''}`}
                        onClick={() => alternar({ alimentador: f, medidor: m })}>{m}</button>
                    ))}
                  </div>
                </td>
                <td>
                  <span className="row">
                    <input className="search" value={manual[f] ?? ''} placeholder="código de medidor"
                      onChange={(e) => setManual((m) => ({ ...m, [f]: e.target.value }))}
                      onKeyDown={(e) => { if (e.key === 'Enter') anadir(f); }} />
                    <button className="btn btn-sm btn-ghost" disabled={!(manual[f] ?? '').trim()} onClick={() => anadir(f)}>Añadir</button>
                  </span>
                </td>
                <td>
                  {!centrales[f] ? (
                    <button className="btn btn-sm btn-ghost" onClick={() => setCentrales((m) => ({ ...m, [f]: CENTRAL_VACIA }))}
                      title="Si el alimentador tiene una central en su troncal, se calibra con su generación y en dos zonas">
                      Declarar central</button>
                  ) : (
                    <div className="central-campos">
                      {([['generacion', 'Generación'], ['llegada', 'Llegada (lado SET)'], ['salida', 'Salida (lado carga)']] as const).map(([campo, texto]) => (
                        <label key={campo} className="field">
                          <span>{texto}</span>
                          <select value={centrales[f][campo]} onChange={(e) => ponerCentral(f, campo, e.target.value)}>
                            <option value="">— medidor —</option>
                            {opcionesExternas.map((m) => (
                              <option key={`${m.alimentador}|${m.medidor}`} value={m.medidor}>{m.medidor} · {m.alimentador}</option>
                            ))}
                            {centrales[f][campo] && !opcionesExternas.some((m) => m.medidor === centrales[f][campo]) && (
                              <option value={centrales[f][campo]}>{centrales[f][campo]}</option>
                            )}
                          </select>
                        </label>
                      ))}
                      <label className="field">
                        <span>Barra de la central en DIgSILENT</span>
                        <input className="search" value={centrales[f].nodo} placeholder="nodo del troncal"
                          onChange={(e) => ponerCentral(f, 'nodo', e.target.value)} />
                      </label>
                      <button className="btn btn-sm btn-ghost" onClick={() => quitarCentral(f)}>Quitar central</button>
                      {!centralCompleta(centrales[f]) && <small className="muted">Elija los tres medidores.</small>}
                    </div>
                  )}
                </td>
              </tr>
            ))}</tbody>
          </table>
        </div>
      )}
      {anios.length > 0 && (
        <label className="row" title="Cada año se calibra aparte, en sus propios casos de DIgSILENT (spec 025)">
          <span>Año de las mediciones</span>
          <select value={anio} disabled={engineBusy} onChange={(e) => elegirAnio(e.target.value)}>
            <option value="">— elija el año —</option>
            {anios.map((a) => <option key={a} value={a}>{a}</option>)}
          </select>
          {anio && <small className="muted">Se calibra en «Sin proyecto {anio}» si los casos sin año son de otro
            año; los de otro año no se tocan.</small>}
        </label>
      )}
      {periodo && <small className="muted">La máxima se busca en {periodo.length === 4 ? `todo ${periodo}` : nombreMes(periodo)}
        {periodo.length === 7 ? ', el mes elegido en 2.3' : ''}, solo con los libros de ese año.</small>}
      {faltaAnio && <small className="muted">Hay mediciones de {anios.join(', ')}: elija el año antes de buscar la
        máxima, para no mezclar años.</small>}
      <div className="row">
        <button className="btn btn-primary" disabled={!elegidos.length || !ws.demanda?.cabecera || engineBusy || faltaAnio || demasiados} onClick={() => maxima()}>
          Buscar la máxima ({aBuscar.length} medidor{aBuscar.length === 1 ? '' : 'es'})
        </button>
        <label className="field-inline">Tipo de análisis{' '}
          <select value={tipoAnalisis} disabled={engineBusy}
            onChange={(e) => setTipoAnalisis(e.target.value as 'alimentadores' | 'set' | 'sistema')}>
            <option value="alimentadores">Alimentadores (1 a 3 juntos): su máxima coincidente</option>
            <option value="set">Por SET: máxima de barra de SET (alta tensión → media tensión)</option>
            <option value="sistema">Sistema eléctrico: máxima coincidente de sus barras de alta tensión</option>
          </select>
        </label>
        {demasiados && <small className="muted">Son {feeders.length} alimentadores: elija SET o sistema eléctrico, o marque hasta 3.</small>}
        {!ws.demanda?.cabecera && <small className="muted">Falta la medición de cabecera.</small>}
      </div>
      {porBarra && !!centralesLibro?.length && (
        <div className="table-wrap">
          <strong>Centrales térmicas del libro (CT…): dónde se conectan</strong>
          <table className="small">
            <thead><tr><th>Medidor</th><th>SET</th><th>Nivel</th><th>Conexión</th></tr></thead>
            <tbody>{centralesLibro.map((c) => (
              <tr key={c.medidor}>
                <td className="mono">{c.medidor}</td>
                <td>{c.set_rotulo || c.set || '—'}</td>
                <td>{c.kv === null ? '—' : `${fmtNum(c.kv, 1)} kV`}</td>
                <td>
                  <select value={centralTramo[c.medidor] ?? ''} disabled={engineBusy}
                    aria-label={`Conexión de ${c.medidor}`}
                    onChange={(e) => setCentralTramo((m) => {
                      const n = { ...m };
                      if (e.target.value) n[c.medidor] = e.target.value; else delete n[c.medidor];
                      return n;
                    })}>
                    <option value="">En la barra de {c.kv === null ? '' : `${fmtNum(c.kv, 1)} kV `}de su SET</option>
                    {c.alimentadores.map((a) => <option key={a} value={a}>En un tramo de {a}</option>)}
                  </select>
                </td>
              </tr>
            ))}</tbody>
          </table>
          <small className="muted">En la barra: generador en esa barra de su SET con su
            medida en el instante de la barra de alta tensión. En un tramo (una central en la troncal de un alimentador): se
            mide con su alimentador en ese mismo instante y no va a la barra (022:RF-88).</small>
        </div>
      )}
      {sistema && (() => {
        const sin = sistema.alimentadores.filter((a) => !(sistema.medidores?.[a] ?? []).length);
        return (
          <p className="muted">
            Proyecto por sistema eléctrico ({sistema.grupo}): sus {sistema.alimentadores.length} alimentadores
            se calibran a la vez, con la máxima por barra de SET.
            {sin.length > 0 && ` Sin medidor (quedan con la demanda del archivo, en los mismos flujos): ${sin.join(', ')}.`}
          </p>
        );
      })()}
      {cabecera.length > 0 && (
        <div className="table-wrap table-short">
          <table className="table">
            <thead><tr><th>Alimentador</th><th>Medidor</th><th>Fecha y hora del kW máx.</th><th className="num">kW máx.</th>
              <th className="num">kVAR</th><th className="num">kVA</th><th className="num">FP</th><th>Libro › hoja</th></tr></thead>
            <tbody>{cabecera.map((r) => (
              <tr key={`${r.alimentador}-${r.medidor}`}>
                <td>{r.alimentador || '—'}</td>
                <td className="strong">{r.medidor}</td>
                {r.error ? <td colSpan={6} className="alert-error small">{r.error}</td> : <>
                  <td className="mono">{r.fecha}
                    {/* 013:RF-14: junto a la del mes, la del periodo entero y su mes. */}
                    {r.maxima_periodo && (
                      <div className="muted small">Periodo: {fmtNum(r.maxima_periodo.kw, 2)} kW
                        en {nombreMes(r.maxima_periodo.mes)} ({r.maxima_periodo.fecha})</div>)}</td>
                  <td className="num">{fmtNum(r.kw, 2)}</td>
                  <td className="num">{fmtNum(r.kvar, 2)}</td>
                  <td className="num" title={r.kva_calculado ? 'Calculado con kW y kVAR' : undefined}>
                    {fmtNum(r.kva, 2)}{r.kva_calculado ? ' *' : ''}</td>
                  <td className="num" title={r.columnas.fp}>{fp(r.fp)}{r.fp_calculado ? ' *' : ''}</td>
                </>}
                <td className="small">{r.libro ? `${r.libro} › ${r.hojas.join(', ')}` : ''}
                  {r.avisos.length > 0 && <div className="muted">{r.avisos.join(' · ')}</div>}</td>
              </tr>
            ))}</tbody>
          </table>
          {instantes.length > 1 && (
            <label className="row">
              <span>Instante de la calibración</span>
              <select value={instanteElegido} disabled={engineBusy}
                onChange={(e) => maxima(e.target.value ? e.target.value.replace(' ', 'T') : '')}>
                <option value="">Máxima coincidente de los seleccionados{periodoBuscado ? ` en ${nombreMes(periodoBuscado)}` : ''} (por defecto)</option>
                {instantes.map((x) => (
                  <option key={x.alimentador} value={x.fecha}>
                    Máxima de la cabecera de {x.alimentador} · {x.fecha} · {fmtNum(x.kw)} kW
                  </option>
                ))}
                {instanteElegido && !instantes.some((x) => x.fecha === instanteElegido) && (
                  <option value={instanteElegido}>Instante común: {instanteElegido}</option>
                )}
              </select>
            </label>
          )}
          {barrasSet.length > 0 && <BarrasDeSet barras={barrasSet} avisos={(ultimo?.result?.avisos as string[] | undefined) ?? []} />}
          {instanteActual && (
            <small className="alert alert-info">Todos los medidores, también los de una central, en el
              registro del {instanteActual}: se calibra a la vez, no en la máxima de cada uno (021:RF-50).</small>
          )}
          <small className="muted">kVAR, kVA y FP son del mismo registro que el kW máximo. * calculado con kW y kVAR.
            {ultimo?.status === 'cancelled' ? ' Cancelado: faltan medidores.' : ''}</small>
        </div>
      )}

      <h4>2.3 · Clientes importantes (demanda fija)</h4>
      {selectorMes}
      <SelectorCriterio valor={criterioFijas} cambiar={elegirCriterio} disabled={engineBusy || cruzando} />
      <AlimentadoresMaximoMes alimentadores={feeders} marcados={maximoMes} cambiar={elegirMaximoMes}
        disabled={engineBusy || cruzando} />
      {otrosMesesMaxima.length > 0 && (
        <small className="alert alert-warn">
          {otrosMesesMaxima.map(([mes, alims]) => `${alims.join(', ')} tiene su máxima en ${nombreMes(mes)}`).join('; ')}:
          el ajuste (2.4) reparte cada máxima con los clientes de su propio mes, no con los de {nombreMes(periodo)}.
        </small>
      )}
      <div className="row">
        <button className="btn" disabled={!feeders.length || !haySuministros || !ws.demanda?.clientes
          || !(estadoClientes.listoParaCruzar || cruzaPorSuMes) || engineBusy || cruzando} onClick={cruzar}>
          {cruzando ? `Cruzando clientes de ${cuales}…` : `Cruzar clientes de ${cuales}`}
        </button>
        <button className="btn btn-ghost" disabled={!hayMaximas || !haySuministros || !ws.demanda?.clientes
          || !(estadoClientes.listoParaCruzar || cruzaPorSuMes) || engineBusy || cruzando} onClick={comparar}
          title={hayMaximas ? 'Las fijas con los dos criterios frente a la cabecera y a la Q de la red y de los bancos de la última calibración; no abre DIgSILENT (039:RF-5)'
            : 'Busque antes la máxima de cabecera (2.2)'}>
          Comparar los criterios de las fijas</button>
        {librosFaltan.length > 0 && (
          <small className="muted">Falta {librosFaltan.join(' y ')} (2.1): sin {librosFaltan.length > 1 ? 'ellos' : 'él'} todas
            las SED se escalan con el factor de escala.</small>)}
        {ws.demanda?.clientes && estadoClientes.motivo && !cruzaPorSuMes && <small className="muted">{estadoClientes.motivo}</small>}
      </div>
      {cruce && <Cruce cruce={cruce} visibles={visibles} filtro={filtro} setFiltro={setFiltro}
        desconectados={desconectados} conmutar={conmutar} aSuMaxima={aSuMaxima} conmutarMaxima={conmutarMaxima}
        desmarcarTodos={() => void guardarASuMaxima([])} bloqueado={engineBusy || cruzando} />}
      {cruce && <RecalibrarConCriterios project={project} periodo={periodo} feeders={feeders} criterioFijas={criterioFijas}
        maximoMes={maximoMes} aSuMaxima={aSuMaxima} />}
      {comparacion && <CompararFijas comparacion={comparacion} />}

      <div className="row">
        <button className="btn btn-ghost btn-sm" disabled={!cabecera.length && !cruce} onClick={excel}>
          Descargar máxima y clientes en Excel
        </button>
      </div>

      {/* Spec 006: la máxima de arriba, repartida entre las SED del proyecto de DIgSILENT. */}
      <h4>2.4 · Escalar las demás cargas y ajustar</h4>
      <AjusteCabecera project={project} maxima={ultimo} feeders={feeders} desconectados={desconectados}
        centrales={Object.fromEntries(Object.entries(centrales).filter(([, c]) => centralCompleta(c)))}
        criterioFijas={criterioFijas} criterioPorAlimentador={porAlimentador(maximoMes, feeders)} aSuMaxima={aSuMaxima}
        faltaCruce={Boolean(hayMaximas && haySuministros && ws.demanda?.clientes && !cruce?.maximas)} />
    </div>
  );
}

function Cruce({ cruce, visibles: todas, filtro, setFiltro, desconectados, conmutar, aSuMaxima, conmutarMaxima,
  desmarcarTodos, bloqueado }: {
  cruce: ClientesCruce; visibles: ClienteImportante[]; filtro: string; setFiltro: (v: string) => void;
  desconectados: Set<string>; conmutar: (codigo: string) => void;
  /** 039:RF-12, RF-13: los clientes a su máxima y las acciones de marcar, desmarcar y desmarcar todos. */
  aSuMaxima: string[]; conmutarMaxima: (codigo: string) => void; desmarcarTodos: () => void; bloqueado: boolean;
}) {
  const t = cruce.totales;
  const ali = cruce.alimentadores.join(', ');
  const conMaxima = Boolean(cruce.maximas && Object.keys(cruce.maximas).length);
  const marcadas = useMemo(() => new Set(aSuMaxima), [aSuMaxima]);
  // 039:RF-11: ordenar por la diferencia entre su máxima del mes y la coincidente, o quedarse con las que suben al
  // menos un %. Nada se marca solo: el operador decide qué cliente sube (usuario, 2026-11-07, calidad de producto).
  const [orden, setOrden] = useState<'sed' | 'kw' | 'pct'>('sed');
  const [minPct, setMinPct] = useState('');
  const umbral = minPct.trim() ? Number(minPct.replace(',', '.')) : null;
  const visibles = useMemo(() => {
    const dif = (c: ClienteImportante) => (orden === 'kw' ? c.diferencia_kw : c.diferencia_pct) ?? Number.NEGATIVE_INFINITY;
    let xs = todas;
    if (umbral != null && Number.isFinite(umbral)) xs = xs.filter((c) => c.diferencia_pct != null && c.diferencia_pct >= umbral);
    if (orden !== 'sed') xs = [...xs].sort((a, b) => (dif(a) === dif(b) ? 0 : dif(b) > dif(a) ? 1 : -1));
    return xs;
  }, [todas, orden, umbral]);
  // 035:RF-2: lo que se escribe en las fijas, por SED, como lo suma el ajuste; con la selección «a su máxima» de ahora.
  const porSed = conMaxima ? visibles.filter((c) => !desconectados.has(c.codigo) && valorQueVa(c, marcadas.has(c.codigo)))
    .reduce<Record<string, { p: number; q: number }>>((m, c) => {
      const v = valorQueVa(c, marcadas.has(c.codigo))!;
      const s = (m[c.sed] ??= { p: 0, q: 0 });
      s.p += v.p_kw; s.q += v.q_kvar ?? 0;
      return m;
    }, {}) : {};
  const cambiada = [...marcadas].sort().join('|') !== [...(cruce.a_su_maxima ?? [])].sort().join('|');
  // SM218, 2026-10-29: máxima el 23/10 y el último libro de clientes, el de septiembre (035:RF-17).
  // Sus hojas no llegan a esa fecha, así que cada cliente va con el registro de su POT, cada uno
  // de su día; la columna «Registro» no coincide con la máxima y hay que decir por qué.
  // 039:RF-2: con «máximo del mes» cada fija va de su día a propósito; 039:RF-4: la que no tiene
  // el registro de la máxima se dice aparte, y aquí quedan las que no tienen hoja.
  const maximoMes = cruce.criterio === 'maximo_mes';
  const fueraDelInstante = conMaxima && !maximoMes
    ? cruce.cruzados.filter((c) => c.metodo && !c.metodo.startsWith('REGISTRO_DEL_INSTANTE') && !c.sin_coincidente) : [];
  // 039:RF-21: la marcada «a su máxima» no espera el registro del instante.
  const sinCoincidente = (cruce.no_coincidentes ?? []).filter((m) => !aSuMaxima.some((c) => m.startsWith(`${c}:`)));
  const sinRegistro = Object.entries(cruce.maximas ?? {})
    .filter(([f, fecha]) => fecha && fueraDelInstante.some((c) => c.alimentador_maxima === f))
    .map(([f, fecha]) => {
      const mesMaxima = String(fecha).slice(0, 7);
      const sinLibro = cruce.mes && cruce.mes !== mesMaxima;
      return `${f} (máxima el ${fecha}): ${sinLibro
        ? `no hay libro de clientes de ${nombreMes(mesMaxima)} y el de ${nombreMes(cruce.mes!)} no trae ese registro`
        : 'sus hojas no traen ese registro'}`;
    });
  return <>
    <p className="alert alert-info small">La pertenencia de las SED se contrasta con la fuente de red cargada antes
      de filtrar los clientes. Cuando difiere del libro y la pertenencia es inequívoca, se usa el alimentador de la red
      y se deja una nota en su fila.
      Los planos de la distribuidora previos a la exportación quedan fuera del alcance del conversor; aquí se usa la fuente
      exportada cargada (TXT, MDB o VNR-GIS).</p>
    <p className="small"><strong>Fijas: {criterioDe(cruce.criterio).texto}</strong> ({criterioDe(cruce.criterio).ayuda}).</p>
    {sinCoincidente.length > 0 && <div className="alert alert-error small">
      <p>{fmtNum(sinCoincidente.length)} fija(s) sin su registro del instante de la máxima: no toman otro y el ajuste
        (2.4) no se prepara hasta que elija el mes de los clientes de esa fecha o «{CRITERIOS_FIJAS[1].texto}» (039:RF-4).</p>
      <ul>{sinCoincidente.slice(0, 50).map((m) => <li key={m}>{m}</li>)}</ul></div>}
    {conMaxima && <p className="small">Clientes {maximoMes ? 'de' : 'en la máxima de'} {Object.entries(cruce.maximas ?? {})
      .map(([f, fecha]) => `${f} (${fecha ?? 'sin fecha'})`).join(', ')}: su P y su Q van a su SED como carga fija,
      con factor de escala 1; las demás SED se escalan hasta la cabecera (035:RF-4). {Object.keys(porSed).length} SED fija(s):
      {' '}{fmtNum(Object.values(porSed).reduce((a, s) => a + s.p, 0), 1)} kW y
      {' '}{fmtNum(Object.values(porSed).reduce((a, s) => a + s.q, 0), 1)} kvar.</p>}
    {sinRegistro.length > 0 && <p className="alert alert-warn small">{sinRegistro.join('; ')}.
      {' '}{fmtNum(fueraDelInstante.length)} cliente(s) sin hoja de 15 minutos van con su EA/ERI del mes con los dos
      criterios: por eso su «Registro» no coincide.</p>}
    <p>{ali ? <>{fmtNum(t.cruzados)} cliente(s) de <strong>{ali}</strong> de {fmtNum(t.clientes)}</> : <>{fmtNum(t.cruzados)} de {fmtNum(t.clientes)} cruzados</>}
      {' '}({fmtNum(t.por_actual)} por «Suministro Act», {fmtNum(t.por_anterior)} por «Suministro»{t.por_hoja ? `, ${fmtNum(t.por_hoja)} por su hoja` : ''}); {fmtNum(t.no_cruzados)} aparte
      {ali ? `, ${fmtNum(t.de_otros)} de otros alimentadores sin mostrar` : ''}.
      {cruce.libro && <small className="muted"> Libro {cruce.libro}{cruce.mes ? ` (${nombreMes(cruce.mes)})` : ''}.</small>}</p>
    {ali && t.cruzados === 0 && t.de_otros > 0 && <p className="alert alert-warn">Ningún suministro tiene «{ali}» en la columna
      RADIAL: compruebe que el libro de suministros usa el mismo código de alimentador.</p>}
    {cruce.avisos.length > 0 && <details className="alert alert-warn"><summary>Avisos: {cruce.avisos.length}</summary>
      <ul className="small">{cruce.avisos.slice(0, 100).map((a) => <li key={a}>{a}</li>)}</ul></details>}
    <input className="search" type="search" placeholder="Filtrar por Nis, SED o radial…" value={filtro}
      onChange={(e) => setFiltro(e.target.value)} />
    {conMaxima && <div className="row" aria-label="Clientes a su máxima">
      <label className="row small"><span>Ordenar por</span>
        <select value={orden} onChange={(e) => setOrden(e.target.value as 'sed' | 'kw' | 'pct')}
          aria-label="Ordenar la tabla cruzada">
          <option value="sed">Alimentador y SED</option>
          <option value="kw">Diferencia de su máxima (kW), de mayor a menor</option>
          <option value="pct">Diferencia de su máxima (%), de mayor a menor</option>
        </select></label>
      <label className="row small" title="039:RF-11: solo las fijas cuya máxima del mes supera su valor coincidente en al menos ese %">
        <span>Diferencia mínima (%)</span>
        <input type="number" min={0} step={5} value={minPct} placeholder="todas" style={{ width: '6rem' }}
          onChange={(e) => setMinPct(e.target.value)} aria-label="Diferencia mínima en %" /></label>
      <small className="muted">A su máxima: {aSuMaxima.length ? `${fmtNum(aSuMaxima.length)} cliente(s)` : 'ninguno'}
        {' '}(su P y su Q de máxima del mes; los demás, el criterio de su alimentador; 039:RF-12)</small>
      <button className="btn btn-ghost btn-sm" disabled={!aSuMaxima.length || bloqueado} onClick={desmarcarTodos}>
        Desmarcar todos «a su máxima»</button>
    </div>}
    {conMaxima && cambiada && <small className="alert alert-info">La selección «a su máxima» cambió desde el cruce: la P y la Q
      de la tabla ya la siguen y el ajuste (2.4) la usa; cruce de nuevo para releer los avisos de sus hojas.</small>}
    {(cruce.avisos_a_su_maxima ?? []).length > 0 && <ul className="alert alert-warn small">
      {cruce.avisos_a_su_maxima!.map((a) => <li key={a}>{a}</li>)}</ul>}
    <div className="table-wrap table-short">
      <table className="table table-ajustada">
        <thead><tr><th>Conectado</th><th>Nis / Suministro</th><th>Cliente</th><th>Cruzado por</th><th>SED</th><th>Radial</th>
          <th className="num">EA</th><th className="num">ERI</th><th className="num">Pot del mes</th>
          {conMaxima ? <>
            <th title="035:RF-1: el registro de 15 minutos de la fecha y hora de la máxima de su alimentador">Registro</th>
            <th className="num" title="035:RF-2: la P que el ajuste escribe en su SED, fija a escala 1">P (kW)</th>
            <th className="num" title="035:RF-2: la Q que el ajuste escribe en su SED, fija a escala 1">Q (kvar)</th>
            <th title="035:RF-3: de dónde salen su P y su Q">De</th>
            <th title="039:RF-14: el criterio con que va: el de su alimentador o «a su máxima»">Criterio</th>
            <th title="039:RF-9: su P y su Q en el registro de la fecha y hora de la máxima de cabecera">Coincidente</th>
            <th title="039:RF-9: su POT máxima del mes y el ERI × 4 de ese mismo registro">Su máxima del mes</th>
            <th className="num" title="039:RF-10: P de su máxima del mes menos la coincidente">Diferencia</th>
            <th title="039:RF-12: subir este cliente a su máxima del mes (calidad de producto)">A su máxima</th>
          </> : <>
            <th title="004:RF-66: el registro de 15 minutos de su hoja en que se dio su Pot">Registro de su Pot</th>
            <th className="num" title="004:RF-66: ERI de ese registro × 4">kVAR en él</th>
          </>}</tr></thead>
        <tbody>{visibles.map((c) => (
          <tr key={c.codigo} className={desconectados.has(c.codigo) ? 'muted' : undefined}>
            <td><input type="checkbox" checked={!desconectados.has(c.codigo)} onChange={() => conmutar(c.codigo)}
              aria-label={`Conectar ${c.codigo} en DIgSILENT`}
              title="Desmarcado: no suma a su SED y, si su SED se queda sin clientes conectados, su carga queda fuera de servicio en el ajuste" /></td>
            <td className="mono">{c.codigo}</td><td className="small">{c.nombre || '—'}</td><td className="small">{c.cruzado_por === 'hoja' ? 'Su hoja' : c.cruzado_por === 'actual' ? 'Suministro Act' : 'Suministro'}</td>
            <td className="strong">{c.sed}</td><td>{c.radial || '—'}
              {c.radial_fuente && <small className="muted"> Según la fuente de red.</small>}
              {c.radial_libro && c.radial_libro !== c.radial && <small className="muted"> Libro: {c.radial_libro}.</small>}
              {c.nota_asignacion && <p className="small">{c.nota_asignacion}</p>}
            </td><td className="num">{fmtNum(c.ea, 2)}</td>
            <td className="num">{fmtNum(c.eri, 2)}</td><td className="num">{fmtNum(c.pot, 2)}</td>
            {conMaxima ? <>
              {(() => {
                const marcada = marcadas.has(c.codigo);
                const va = valorQueVa(c, marcada);
                const criterio = c.criterio_alimentador ?? (c.criterio === 'a_su_maxima' ? cruce.criterio : c.criterio);
                return <>
                  <td className="small">{va?.fecha || '—'}</td>
                  <td className="num strong">{va == null ? '—' : fmtNum(va.p_kw, 2)}</td>
                  <td className="num strong">{va?.q_kvar == null ? '—' : fmtNum(va.q_kvar, 2)}</td>
                  <td className="small">{c.sin_coincidente && !marcada
                    ? <span className="badge err" title={c.sin_coincidente}>sin el registro de la máxima</span>
                    : ORIGEN_VALORES[(va?.metodo ?? '').split(' ')[0]] ?? va?.metodo ?? '—'}</td>
                  <td className="small">{marcada
                    ? <strong title="039:RF-14">A su máxima: {kwKvar(c.valores?.maximo_mes ?? va)}{(c.valores?.maximo_mes ?? va)?.fecha
                      ? ` (${(c.valores?.maximo_mes ?? va)!.fecha})` : ' (POT y EA/ERI del mes)'}</strong>
                    : criterioDe(criterio as CriterioFijas | undefined).texto}</td>
                  <td className="small">{c.valores?.coincidente ? <>{kwKvar(c.valores.coincidente)}
                    {c.valores.coincidente.fecha && <span className="muted"> · {c.valores.coincidente.fecha}</span>}</>
                    : <span className="muted">sin registro</span>}</td>
                  <td className="small">{c.valores?.maximo_mes ? <>{kwKvar(c.valores.maximo_mes)}
                    {c.valores.maximo_mes.fecha && <span className="muted"> · {c.valores.maximo_mes.fecha}</span>}</>
                    : '—'}</td>
                  <td className="num">{c.diferencia_kw == null ? '—' : <>{fmtNum(c.diferencia_kw, 1)} kW
                    {c.diferencia_pct != null && <span className="muted"> ({fmtNum(c.diferencia_pct, 1)} %)</span>}</>}</td>
                  <td><input type="checkbox" checked={marcada} disabled={bloqueado} onChange={() => conmutarMaxima(c.codigo)}
                    aria-label={`Subir ${c.codigo} a su máxima del mes`}
                    title="Marcado: va con la POT máxima de su hoja y el ERI × 4 de ese registro; su subida se descuenta de las escaladas (039:RF-12, RF-19)" /></td>
                </>;
              })()}
            </> : <>
              <td className="small">{c.fecha_registro || '— (ERI/EA del mes)'}</td>
              <td className="num">{c.q_registro_kvar == null ? '—' : fmtNum(c.q_registro_kvar, 2)}</td>
            </>}</tr>
        ))}</tbody>
      </table>
    </div>
    {desconectados.size > 0 && <small className="muted">{fmtNum(desconectados.size)} cliente(s) desmarcado(s): no suman a su
      SED en el ajuste, y la SED que se queda sin ningún cliente conectado queda fuera de servicio en el escenario de
      «Sin proyecto».</small>}
    {cruce.no_cruzados.length > 0 && (
      <details className="alert alert-warn"><summary>No cruzados: {cruce.no_cruzados.length}</summary>
        <ul className="small">{cruce.no_cruzados.map((c) => <li key={c.codigo}><strong>{c.codigo}</strong>: {c.motivo}</li>)}</ul>
      </details>
    )}
  </>;
}

/** 039:RF-17: recalibrar desde 2.3 con los criterios de la tabla (el general, los alimentadores con «máximo del mes»
 * y los clientes a su máxima), por la misma vía que «Recalibrar» (028:RF-21). */
function RecalibrarConCriterios({ project, periodo, feeders, criterioFijas, maximoMes, aSuMaxima }: {
  project: string; periodo: string; feeders: string[]; criterioFijas: CriterioFijas; maximoMes: string[]; aSuMaxima: string[];
}) {
  const { ws, startJob, active } = useApp();
  const [datos, setDatos] = useState<{ alimentadores?: string[]; del_sistema?: string[] } | null>(null);
  const [error, setError] = useState('');
  useEffect(() => {
    setDatos(null); setError('');
    if (!project) return;
    void api.recalibrarDatos(ws.id, project).then(setDatos).catch((e: Error) => setError(e.message));
  }, [ws.id, project]);
  const calibrado = Object.keys(ws.calibraciones ?? {}).some((clave) => clave.split('@')[0] === project.trim());
  // 028:RF-40: en un sistema, solo los alimentadores de esta tabla; un proyecto de uno o de varios unidos, entero.
  const delSistema = datos?.alimentadores?.length ? [] : datos?.del_sistema ?? [];
  const solo = delSistema.length ? feeders.filter((f) => delSistema.includes(f)) : [];
  const candidatos = solo.length ? solo : datos?.alimentadores?.length ? datos.alimentadores : delSistema;
  const motivo = !project ? 'Elija el proyecto de DIgSILENT en el paso 1.' : error
    || (!calibrado ? 'Se activa con la primera calibración del proyecto (2.4).'
      : !/^\d{4}(-(0[1-9]|1[0-2]))?$/.test(periodo) ? 'Elija arriba el año o el mes de los clientes.' : '');
  return (
    <div className="row">
      <button className="btn btn-pf" disabled={Boolean(motivo) || !datos || Boolean(active.asistente) || Boolean(active.powerfactory)}
        title="Escanea el proyecto, busca la máxima del periodo y recalibra «Sin proyecto» con el criterio de las fijas, los alimentadores con su máximo del mes y los clientes a su máxima de esta tabla (039:RF-17, 028:RF-21)"
        onClick={() => startJob(() => api.recalibrar(ws.id, {
          project, periodo, criterio_fijas: criterioFijas, solo,
          maximo_mes: maximoMes.filter((a) => candidatos.includes(a)), a_su_maxima: aSuMaxima }))}>
        Recalibrar con estos criterios</button>
      <small className="muted">{motivo || `${criterioDe(criterioFijas).texto}; ${aSuMaxima.length
        ? `${fmtNum(aSuMaxima.length)} cliente(s) a su máxima` : 'ningún cliente a su máxima'}${solo.length ? `; solo ${solo.join(', ')}` : ''}.`}</small>
    </div>
  );
}

/** 039:RF-5: por alimentador, cada fija con los dos criterios, sus sumas, la cabecera medida en
 * la máxima, la Q de la red y de los bancos de la última calibración y la Q que queda para las
 * escaladas con cada criterio. Solo lee: el operador elige después el criterio en 2.3. */
function CompararFijas({ comparacion }: { comparacion: ComparacionFijas }) {
  const v = (x: number | null | undefined, d = 1) => (x == null ? '—' : fmtNum(x, d));
  return (
    <details className="step-box" open>
      <summary className="strong">Comparación de los criterios de las fijas · libro {comparacion.libro}</summary>
      {comparacion.avisos.length > 0 && <details className="alert alert-warn"><summary>Avisos: {comparacion.avisos.length}</summary>
        <ul className="small">{comparacion.avisos.slice(0, 100).map((a) => <li key={a}>{a}</li>)}</ul></details>}
      {comparacion.alimentadores.map((a) => (
        <div key={a.alimentador}>
          <h5>{a.alimentador} · máxima del {a.cabecera.fecha ?? 'sin fecha'}: {v(a.cabecera.kw)} kW y {v(a.cabecera.kvar)} kvar</h5>
          <div className="table-wrap">
            <table className="table table-ajustada">
              <thead>
                <tr><th rowSpan={2}>Nis</th><th rowSpan={2}>SED</th>
                  {CRITERIOS_FIJAS.map((c) => <th key={c.valor} colSpan={3} title={c.ayuda}>{c.texto}</th>)}</tr>
                <tr>{CRITERIOS_FIJAS.map((c) => <Fragment key={c.valor}><th>Registro</th>
                  <th className="num">P (kW)</th><th className="num">Q (kvar)</th></Fragment>)}</tr>
              </thead>
              <tbody>
                {a.fijas.map((f) => (
                  <tr key={f.codigo}><td className="mono">{f.codigo}</td><td className="strong">{f.sed}</td>
                    {CRITERIOS_FIJAS.map(({ valor }) => {
                      const x = f[valor];
                      return x?.sin_coincidente
                        ? <td key={valor} colSpan={3}><span className="badge err" title={x.sin_coincidente}>sin el registro de la máxima</span></td>
                        : <Fragment key={valor}><td className="small">{x?.fecha ?? '— (EA/ERI del mes)'}</td>
                          <td className="num">{v(x?.p_kw, 2)}</td><td className="num">{v(x?.q_kvar, 2)}</td></Fragment>;
                    })}</tr>
                ))}
                <tr className="strong"><td colSpan={2}>Suma de las fijas</td>
                  {CRITERIOS_FIJAS.map(({ valor }) => <Fragment key={valor}><td className="small">
                    {a.sumas[valor].sin_registro ? `${a.sumas[valor].sin_registro} sin registro, fuera de la suma` : ''}</td>
                    <td className="num">{v(a.sumas[valor].p_kw)}</td><td className="num">{v(a.sumas[valor].q_kvar)}</td></Fragment>)}</tr>
                <tr><td colSpan={2} title="035:RF-28: Q de cabecera que puede dar la red con las escaladas entre FP 1 y su mínimo, frente a la medida">
                  Q de cabecera alcanzable</td>
                  {CRITERIOS_FIJAS.map(({ valor }) => {
                    const c = a.coherencia[valor];
                    return <Fragment key={valor}><td className="small">{!c ? 'sin calibración con la red'
                      : c.coherente ? <span className="badge ok">coherente: se cuadra</span>
                        : <span className="badge err">no coherente{c.lado === 'alta' ? ': la medida está por debajo' : ': la medida está por encima'}</span>}</td>
                      <td className="num" colSpan={2}>{c ? `${v(c.q_fp1_kvar)} a ${v(c.q_fp_minimo_kvar)} kvar (FP 1 a ${v(c.fp_minimo, 3)})` : '—'}</td></Fragment>;
                  })}</tr>
              </tbody>
            </table>
          </div>
          <p className="small">{a.red
            ? <>Red y bancos en {a.red.calibracion}: cabecera simulada {v(a.red.cabecera_kvar)} kvar y cargas {v(a.red.cargas_kvar)} kvar;
              la red y los bancos ponen {v(a.red.red_y_bancos_kvar)} kvar
              {a.red.bancos_kvar != null ? ` (los bancos entregan ${v(a.red.bancos_kvar)} kvar)` : ''}.</>
            : 'Sin calibración guardada de este alimentador: no se sabe la P y la Q de la red ni si la medida es coherente.'}</p>
          <p className="small muted">Medida coherente: la recalibración cuadra la Q con el FP de las escaladas. No coherente:
            no se fuerza; queda la Q que da DIgSILENT con las escaladas a su FP de perfil, y se dice (035:RF-28, RF-29).</p>
        </div>
      ))}
    </details>
  );
}

/** Spec 022, RF-39 a RF-44 y RF-84 a RF-87: por SET, la barra de 60 kV con su máxima y
 * debajo sus barras de 22,9 y 10 kV en ese mismo instante, con el transformador de cada
 * medidor, las centrales térmicas (CT…) y los alimentadores que se calibran en esa fecha. */
function BarrasDeSet({ barras, avisos }: { barras: BarraDeSet[]; avisos: string[] }) {
  // Orden: SET, y dentro de cada una la de 60 kV primero y luego de mayor a menor tensión.
  const filas = [...barras].sort((a, b) => a.set.localeCompare(b.set) || Number(!!b.alta) - Number(!!a.alta) || b.kv - a.kv);
  const medidores = (b: BarraDeSet) => b.medidores.map((m) => {
    const t = b.transformadores?.[m];
    return t ? `${m} (${t})` : m;
  }).join(' + ');
  const conAlta = barras.some((b) => b.alta);
  return (
    <div className="table-wrap">
      <strong>Máxima por barra de SET{conAlta ? ': instante de la barra de alta tensión' : ''}</strong>
      <table className="small">
        <thead><tr><th>SET</th><th>Barra</th><th>Medidores (transformador)</th><th>Fecha y hora</th>
          <th>kW</th><th>kVAR</th><th>Centrales térmicas (CT)</th><th>Alimentadores (en esa fecha)</th></tr></thead>
        <tbody>{filas.map((b) => (
          <tr key={b.clave}>
            <td>{b.set}</td>
            <td>{b.alta ? <strong>{fmtNum(b.kv, 1)} kV (máxima)</strong> : `${fmtNum(b.kv, 1)} kV`}
              {b.suelta ? ' (suelta)' : ''}
              {b.de_alta && <div className="muted">en el instante de {b.de_alta}</div>}</td>
            <td className="mono">{medidores(b) || '—'}</td>
            <td>{b.fecha}</td>
            <td className="num">{b.kw === null ? 'sin registro' : fmtNum(b.kw, 1)}</td>
            <td className="num">{b.kvar === null ? '—' : fmtNum(b.kvar, 1)}</td>
            <td>{b.centrales.map((c) => `${c.medidor} ${c.kw === null ? '—' : fmtNum(c.kw, 1)} kW`).join('; ') || '—'}</td>
            <td>{b.alimentadores.join(', ') || '—'}</td>
          </tr>
        ))}</tbody>
      </table>
      <small className="muted">
        {conAlta
          ? 'En cada SET con medidor de alta tensión, la máxima es la suma de sus transformadores (T1, T2, T3) en alta tensión; sus barras de media tensión, sus centrales y cada alimentador se toman en esa misma fecha y hora (022:RF-84, RF-87). '
          : ''}
        Cada alimentador se calibra con su kW y kVAR de esa fecha y hora, no con su máxima (022:RF-41).
      </small>
      {avisos.length > 0 && (
        <details className="alert alert-warn"><summary>Avisos del libro de medidores: {avisos.length}</summary>
          <ul className="small">{avisos.map((a) => <li key={a}>{a}</li>)}</ul>
        </details>
      )}
    </div>
  );
}

/** 028:RF-30: lo que el escaneo halló y qué falta: los medidores de cada central, aquí mismo arriba. */
function DetectadoEnElEscaneo({ escaneo, centrales }: { escaneo: Escaneo; centrales: Record<string, CentralTermica> }) {
  const avisos: string[] = [];
  Object.entries(escaneo.alimentadores).forEach(([f, d]) => {
    const gens = (d.generadores ?? []).filter((g) => g.en_servicio);
    if (gens.length) {
      const nombres = gens.map((g) => `${g.generador} en ${g.barra}`).join(', ');
      avisos.push(centralCompleta(centrales[f]) ? `${f}: central ${nombres}, con sus medidores.`
        : `${f}: central ${nombres}. Elija sus medidores de generación, llegada y salida; sin ellos se calibra con el generador tal como está.`);
    }
    const enBarra = (d.generadores_en_barra ?? []).filter((g) => g.en_servicio);
    if (enBarra.length) avisos.push(`${f}, barra de cabecera: central ${enBarra.map((g) => `${g.generador} en ${g.barra}`).join(', ')}.`);
    const bancosBarra = (d.bancos_en_barra ?? []).filter((b) => b.en_servicio);
    if (bancosBarra.length) avisos.push(`${f}, barra de cabecera: ${bancosBarra.length} banco(s) en ${bancosBarra[0].barra}.`);
    const bancos = (d.bancos ?? []).filter((b) => b.en_servicio);
    if (bancos.length) avisos.push(`${f}: ${bancos.length} banco(s) en servicio en el alimentador.`);
  });
  if (!avisos.length) return null;
  return (
    <div className="alert alert-info" role="status">
      <strong>Detectado en DIgSILENT</strong>
      {avisos.map((a) => <p key={a}>{a}</p>)}
    </div>
  );
}

/** Spec 028, RF-10: lo que encontró el escaneo, por alimentador. */
function EscaneoTabla({ escaneo }: { escaneo: Escaneo }) {
  const deQuien = (o: string) => (o === 'operador' ? 'a mano' : 'del conversor');
  const ajenas = escaneo.variaciones.filter((v) => v.origen === 'operador');
  return (
    <div className="table-wrap table-short">
      <p className="muted">Escaneo de {escaneo.project}{escaneo.caso ? ` en «${escaneo.caso}»` : ''}: solo lectura.</p>
      <table className="table">
        <thead><tr><th>Alimentador</th><th>Generadores (centrales)</th><th>Bancos</th><th>Tramos nuevos</th><th>Tramos cambiados a mano</th><th>Cargas cambiadas</th></tr></thead>
        <tbody>{Object.entries(escaneo.alimentadores).map(([f, d]) => (
          <tr key={f}>
            <td className="strong">{f}</td>
            {d.error ? <td colSpan={5} className="err">{d.error}</td> : <>
              <td>{(d.generadores ?? []).length ? (d.generadores ?? []).map((g) => (
                <div key={g.generador}>{g.generador} · barra {g.barra ?? '—'} · {fmtNum(g.p_kw ?? 0)} kW
                  {g.en_servicio ? '' : ' (fuera de servicio)'} · <small className="muted">{deQuien(g.origen)}</small></div>
              )) : <span className="muted">ninguno</span>}</td>
              <td>{(d.bancos ?? []).length ? (d.bancos ?? []).map((b) => (
                <div key={b.banco}>{b.banco} · {b.barra ?? '—'} · {fmtNum(b.q_nominal_kvar ?? 0)} kvar
                  {b.en_servicio ? '' : ' (fuera de servicio)'} · <small className="muted">{deQuien(b.origen)}</small></div>
              )) : <span className="muted">ninguno</span>}</td>
              <td>{(d.tramos_nuevos ?? []).length ? (d.tramos_nuevos ?? []).map((x) => (
                <div key={x.tramo}>{x.tramo} · {x.desde ?? '—'} → {x.hasta ?? '—'}{x.km != null ? ` · ${fmtNum(x.km)} km` : ''}</div>
              )) : <span className="muted">ninguno</span>}</td>
              <td>{(d.tramos_cambiados ?? []).length ? (d.tramos_cambiados ?? []).map((x) => (
                <div key={x.tramo}>{x.tramo} · {x.tipo ?? '—'}{x.km != null ? ` · ${fmtNum(x.km)} km` : ''}
                  {x.en_servicio ? '' : ' (fuera de servicio)'} · <small className="muted">{x.variacion}</small></div>
              )) : <span className="muted">ninguno</span>}</td>
              <td>{(d.cargas_cambiadas ?? []).length || <span className="muted">ninguna</span>}</td>
            </>}
          </tr>
        ))}</tbody>
      </table>
      {ajenas.length > 0 && <p className="muted">Variaciones hechas a mano: {ajenas.map((v) =>
        `${v.variacion}${v.activa ? ' (activa)' : ''}, ${v.objetos} objeto(s)`).join('; ')}</p>}
      {escaneo.avisos.map((a) => <p key={a} className="muted">{a}</p>)}
    </div>
  );
}

/** Spec 028, RF-21 a RF-23: recalibrar «Sin proyecto» del sistema ya importado, aparte de la
 * calibración inicial: escanea lo que hay en DIgSILENT, busca la máxima y recalibra. */
function Recalibrar({ project, criterioFijas, elegirCriterio }: {
  project: string; criterioFijas: CriterioFijas; elegirCriterio: (c: CriterioFijas) => void;
}) {
  const { ws, startJob, active } = useApp();
  const [periodo, setPeriodo] = useState('');
  const [zonal, setZonal] = useState('');
  const [alimentadores, setAlimentadores] = useState<string[]>([]);
  // 028:RF-40: los del sistema y los marcados; sin marcar ninguno se recalibran todos.
  const [delSistema, setDelSistema] = useState<string[]>([]);
  const [solo, setSolo] = useState<string[]>([]);
  // 039:RF-8: los que toman sus fijas con «máximo del mes» en la recalibración.
  const [maximoMesR, setMaximoMesR] = useState<string[]>([]);
  const [carpeta, setCarpeta] = useState('');
  const [transformadores, setTransformadores] = useState(false);
  const [error, setError] = useState('');
  useEffect(() => {
    setError(''); setSolo([]); setMaximoMesR([]);
    if (!project) return;
    void api.recalibrarDatos(ws.id, project).then((d) => {
      setZonal(d.zonal); setCarpeta(d.demanda_dir); setAlimentadores(d.alimentadores ?? []);
      setDelSistema(d.del_sistema ?? []);
    })
      .catch((e: Error) => setError(e.message));
  }, [ws.id, project]);
  // 035:RF-21: se activa con la primera calibración del proyecto.
  const calibrado = Object.keys(ws.calibraciones ?? {}).some((clave) => clave.split('@')[0] === project.trim());
  // 039:RF-8: los que pueden tomar «máximo del mes»: los elegidos, o todos los del proyecto.
  const candidatos = solo.length ? solo : delSistema.length ? delSistema : alimentadores;
  const listo = calibrado && Boolean(project) && /^\d{4}(-(0[1-9]|1[0-2]))?$/.test(periodo.trim()) && !error;
  return (
    <div className="step-box">
      <h4>Recalibrar «Sin proyecto»</h4>
      <p className="muted small">Para un proyecto ya calibrado de un sistema, un alimentador o varios unidos:
        escanea en DIgSILENT los tramos nuevos, centrales,
        bancos y cambios hechos a mano, busca la máxima del periodo y vuelve a calibrar con todo eso. No reconvierte
        ni vuelve a importar, y el «Caso base» no se toca. La primera calibración sigue en los pasos 2.1 a 2.3.</p>
      {error ? <p className="muted small">{error}</p> : (
        <div className="row">
          {alimentadores.length ? <label className="field"><span>Alimentadores del proyecto</span>
            <input value={alimentadores.join(' + ')} readOnly /></label> :
            <label className="field"><span>Sistema</span>
              <input value={zonal} onChange={(e) => setZonal(e.target.value)} /></label>}
          <label className="field"><span>Periodo</span>
            <input value={periodo} placeholder="2026-07" onChange={(e) => setPeriodo(e.target.value)} /></label>
          <label className="field"><span>Carpeta de los libros</span>
            <input value={carpeta} onChange={(e) => setCarpeta(e.target.value)} /></label>
          <label className="row small"><input type="checkbox" checked={transformadores}
            onChange={(e) => setTransformadores(e.target.checked)} /> Implementar transformadores</label>
          <SelectorCriterio valor={criterioFijas} cambiar={elegirCriterio} />
          <button className="btn btn-pf" disabled={!listo || Boolean(active.asistente) || Boolean(active.powerfactory)}
            onClick={() => startJob(() => api.recalibrar(ws.id, {
              project, periodo: periodo.trim(), zonal: zonal.trim(), demanda_dir: carpeta.trim(), transformadores,
              criterio_fijas: criterioFijas, solo, maximo_mes: maximoMesR.filter((a) => candidatos.includes(a)) }))}>
            {solo.length ? `Recalibrar ${solo.join(' + ')}` : 'Recalibrar'}</button>
        </div>
      )}
      {!error && <AlimentadoresMaximoMes alimentadores={candidatos} marcados={maximoMesR} cambiar={setMaximoMesR}
        disabled={Boolean(active.powerfactory)} />}
      {!error && !alimentadores.length && delSistema.length > 0 && (
        <fieldset className="step-box" aria-label="Alimentadores a recalibrar">
          <legend className="small">Solo estos alimentadores (sin marcar ninguno, todos). El instante es el del sistema y
            los demás conservan su última calibración (028:RF-40, RF-41).</legend>
          <div className="row">
            {delSistema.map((a) => (
              <label key={a} className="row small">
                <input type="checkbox" checked={solo.includes(a)} disabled={Boolean(active.powerfactory)}
                  onChange={(e) => setSolo((s) => e.target.checked ? [...s, a] : s.filter((x) => x !== a))} /> {a}
              </label>
            ))}
            {solo.length > 0 && <button className="btn" onClick={() => setSolo([])}>Todos</button>}
          </div>
        </fieldset>
      )}
      {!calibrado && project && <small className="muted">Se activa con la primera calibración del proyecto (2.2 a 2.4).
        Para recalibrar eligiendo antes la máxima del alimentador o de su barra y SET y revisando la tabla cruzada, use
        esos mismos pasos: después de la primera, el botón de 2.4 es «Recalibrar (n.º k)».</small>}
    </div>
  );
}
