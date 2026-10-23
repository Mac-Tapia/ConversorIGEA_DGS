import { useEffect, useMemo, useRef, useState } from 'react';
import { api, fmtNum, type DemandaTipo } from '../api';
import { estadoCatalogoClientes } from '../clientesCatalogo';
import { useApp } from '../context';
import type { BarraDeSet, CentralTermica, SistemaDelProyecto, ClientesCruce, ClienteImportante, MaximaCabecera, MedidoresExternos } from '../types';
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
  const autoIndexado = useRef('');
  const indexando = Object.values(jobs).some((j) => j.kind === 'demanda_clientes_index'
    && (j.status === 'queued' || j.status === 'running'));
  const engineBusy = Boolean(active.engine);
  const indexar = () => startJob(() => api.demandaClientesIndexar(ws.id));

  // Al elegir o volver a abrir una fuente de clientes se reescanea la misma carpeta.
  useEffect(() => {
    if (tipo !== 'clientes' || !meta || indexando || engineBusy) return;
    const clave = `${ws.id}:${meta.origin}:${meta.name}`;
    if (autoIndexado.current === clave) return;
    autoIndexado.current = clave;
    void startJob(() => api.demandaClientesIndexar(ws.id)).then((job) => {
      if (!job) autoIndexado.current = '';
    });
  }, [engineBusy, indexando, meta, startJob, tipo, ws.id]);
  const subir = async (files: File[]) => {
    const r = await run(() => api.demandaSubir(ws.id, tipo, files));
    if (r) { autoIndexado.current = ''; setWs(r); }
  };
  const porRuta = async () => {
    const r = await run(() => api.demandaRuta(ws.id, tipo, ruta.trim()));
    if (r) { autoIndexado.current = ''; setWs(r); setRuta(''); }
  };
  const quitar = async () => {
    const r = await run(() => api.demandaQuitar(ws.id, tipo));
    if (r) setWs(r);
  };
  return (
    <div className="field">
      <span>{titulo}</span>
      {meta ? (
        <div className="row">
          <strong>{meta.name}</strong>
          {meta.libros && <span className="muted small">({meta.libros.length} libro(s): {meta.libros.join(', ')})</span>}
          <span className="muted small">{meta.origin === 'server' ? 'ruta del servidor' : 'subido'}</span>
          <button className="btn btn-ghost btn-sm" onClick={quitar}>Quitar</button>
        </div>
      ) : (
        <>
          <FileDrop compact accept={EXT} multiple={tipo === 'cabecera' || tipo === 'suministros' || tipo === 'clientes'} onFiles={subir}>
            <span>Soltar o <u>elegir</u>{tipo === 'cabecera' || tipo === 'suministros' || tipo === 'clientes' ? ' (varios)' : ''}</span>
          </FileDrop>
          {health.server_paths && (
            <div className="row">
              <input className="search" placeholder={tipo === 'cabecera' || tipo === 'suministros' || tipo === 'clientes' ? 'o ruta de la carpeta en el servidor' : 'o ruta en el servidor'}
                value={ruta} onChange={(e) => setRuta(e.target.value)} />
              <button className="btn btn-sm" disabled={!ruta.trim()} onClick={porRuta}>Usar ruta</button>
            </div>
          )}
        </>
      )}
      {tipo === 'clientes' && meta && (
        <CatalogoClientes meta={meta} indexando={indexando} bloqueado={engineBusy} actualizar={indexar} />
      )}
      {/* 004:RF-63: libros de clientes subidos en «Suministros», nombrados en su hueco. */}
      {tipo !== 'clientes' && meta?.avisos?.map((aviso) => <p className="alert alert-warn" key={aviso}>{aviso}</p>)}
      <small className="muted">{ayuda}</small>
    </div>
  );
}

function CatalogoClientes({ meta, indexando, bloqueado, actualizar }: {
  meta: NonNullable<ReturnType<typeof useApp>['ws']['demanda']>['clientes'];
  indexando: boolean;
  bloqueado: boolean;
  actualizar: () => unknown;
}) {
  if (!meta) return null;
  const catalogo = meta.catalogo ?? [];
  return <div className="stack compact">
    <div className="row">
      <button className="btn btn-sm" disabled={bloqueado} onClick={actualizar}>
        {indexando ? 'Actualizando índice…' : 'Actualizar índice'}
      </button>
      {meta.indexado_en && <small className="muted">{catalogo.length} libro(s) indexado(s)</small>}
    </div>
    {meta.avisos?.map((aviso) => <p className="alert alert-warn" key={aviso}>{aviso}</p>)}
    {catalogo.length > 0 && <div className="table-wrap table-short"><table className="table">
      <thead><tr><th>Libro</th><th>Mes</th><th>Origen</th><th>Estado</th></tr></thead>
      <tbody>{catalogo.map((libro) => <tr key={libro.nombre}>
        <td className="mono">{libro.nombre}</td><td>{libro.mes ?? 'Sin mes'}</td>
        <td>{libro.origen_mes}</td><td>{libro.activo ? 'Activo' : 'No usado'}
          {/* 004:RF-65: por qué no se usa (p. ej., sin hoja «resumen»). */}
          {!libro.activo && libro.avisos?.map((a) => <div className="muted small" key={a}>{a}</div>)}</td>
      </tr>)}</tbody>
    </table></div>}
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
  // 022:RF-39 a RF-41: la máxima de cada barra de SET y sus alimentadores en esa fecha.
  const [porBarra, setPorBarra] = useState(false);
  // 022:RF-52 a RF-54: un proyecto por sistema se calibra entero, con la máxima por barra.
  const [sistema, setSistema] = useState<SistemaDelProyecto | null>(null);
  // Spec 021, RF-25 a RF-27: central térmica en un tramo, por alimentador, y los medidores
  // del libro que no son de un alimentador de la red, donde se eligen los suyos.
  const [externos, setExternos] = useState<MedidoresExternos | null>(null);
  const [centrales, setCentrales] = useState<Record<string, CentralTermica>>({});
  const toast = useToast();
  const engineBusy = Boolean(active.engine);
  const estadoClientes = estadoCatalogoClientes(ws.demanda?.clientes, periodo);

  const ultimo = Object.values(jobs).filter((j) => j.kind === 'demanda_cabecera' && j.result).pop();
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
    setExternos(null);
    setCentrales({});
  }, [project, marcados]);

  useEffect(() => {
    if (!project) { setSistema(null); return; }
    let vivo = true;
    api.demandaSistema(ws.id, project).then((r) => {
      if (!vivo) return;
      setSistema(r.sistema);
      if (r.sistema) setPorBarra(true);
    }).catch(() => setSistema(null));
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
    startJob(() => api.demandaCabecera(ws.id, aBuscar, { periodo, instante, por_barra: porBarra && !instante }));
  };
  const instanteActual = (ultimo?.result?.instante as string | null | undefined) ?? '';
  const barrasSet = (ultimo?.result?.barras as BarraDeSet[] | undefined) ?? [];
  const periodoBuscado = (ultimo?.result?.periodo as string | null | undefined) ?? '';
  // RF-52: el instante de la máxima de cada alimentador marcado, para elegirlo como común.
  const instantes = cabecera.filter((r) => !r.error && r.fecha && feeders.includes(r.alimentador))
    .map((r) => ({ alimentador: r.alimentador, fecha: r.fecha as string, kw: r.kw }));
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
  const cruzar = async () => {
    setCruzando(true);
    try {
      const r = await run(() => api.demandaClientes(ws.id, feeders, periodo || undefined));
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
  const otrosMesesMaxima = periodo
    ? Object.entries(mesesMaxima).filter(([mes]) => mes !== periodo) : [];
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
  const selectorMes = estadoClientes.esCatalogo && estadoClientes.activos > 1 && (
    <label className="row">
      <span>Mes de los clientes</span>
      <select value={periodo} disabled={engineBusy} onChange={(e) => elegirPeriodo(e.target.value)}>
        <option value="">Todo el registro (elija un mes para cruzar clientes)</option>
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
      <h4>2.1 · Libros de medición</h4>
      <div className="form-grid">
        {LIBROS.map((l) => <Libro key={l.tipo} {...l} />)}
      </div>

      <h4>2.2 · Máxima de cabecera</h4>
      <div className="row">
        <button className="btn" disabled={!feeders.length || !ws.demanda?.medidores || buscando} onClick={buscar}>
          Buscar medidores de {cuales}
        </button>
        {!ws.demanda?.medidores && <small className="muted">Falta el libro de medidores por alimentador.</small>}
      </div>
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
      {periodo && <small className="muted">La máxima se busca en {nombreMes(periodo)}, el mes elegido en 2.3.</small>}
      <div className="row">
        <button className="btn btn-primary" disabled={!elegidos.length || !ws.demanda?.cabecera || engineBusy} onClick={() => maxima()}>
          Buscar la máxima ({aBuscar.length} medidor{aBuscar.length === 1 ? '' : 'es'})
        </button>
        <label className="check" title="La máxima de la barra de SET (suma de sus transformadores) y cada alimentador de la barra con su kW y kVAR de esa fecha y hora">
          <input type="checkbox" checked={porBarra} disabled={engineBusy} onChange={(e) => setPorBarra(e.target.checked)} />
          {' '}Máxima por barra de SET
        </label>
        {!ws.demanda?.cabecera && <small className="muted">Falta la medición de cabecera.</small>}
      </div>
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
                  <td className="mono">{r.fecha}</td>
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
              <select value={instanteActual} disabled={engineBusy}
                onChange={(e) => maxima(e.target.value ? e.target.value.replace(' ', 'T') : '')}>
                <option value="">La máxima de cada alimentador{periodoBuscado ? ` en ${nombreMes(periodoBuscado)}` : ''}</option>
                {instantes.map((x) => (
                  <option key={x.alimentador} value={x.fecha}>
                    Coincidente: la máxima de {x.alimentador} · {x.fecha}
                  </option>
                ))}
                {instanteActual && !instantes.some((x) => x.fecha === instanteActual) && (
                  <option value={instanteActual}>Coincidente: {instanteActual}</option>
                )}
              </select>
            </label>
          )}
          {barrasSet.length > 0 && <BarrasDeSet barras={barrasSet} />}
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
      {otrosMesesMaxima.length > 0 && (
        <small className="alert alert-warn">
          {otrosMesesMaxima.map(([mes, alims]) => `${alims.join(', ')} tiene su máxima en ${nombreMes(mes)}`).join('; ')}:
          el ajuste (2.4) reparte cada máxima con los clientes de su propio mes, no con los de {nombreMes(periodo)}.
        </small>
      )}
      <div className="row">
        <button className="btn" disabled={!feeders.length || !haySuministros || !ws.demanda?.clientes
          || !estadoClientes.listoParaCruzar || engineBusy || cruzando} onClick={cruzar}>
          {cruzando ? `Cruzando clientes de ${cuales}…` : `Cruzar clientes de ${cuales}`}
        </button>
        {librosFaltan.length > 0 && (
          <small className="muted">Falta {librosFaltan.join(' y ')} (2.1): sin {librosFaltan.length > 1 ? 'ellos' : 'él'} todas
            las SED se escalan con el factor de escala.</small>)}
        {ws.demanda?.clientes && estadoClientes.motivo && <small className="muted">{estadoClientes.motivo}</small>}
      </div>
      {cruce && <Cruce cruce={cruce} visibles={visibles} filtro={filtro} setFiltro={setFiltro}
        desconectados={desconectados} conmutar={conmutar} />}

      <div className="row">
        <button className="btn btn-ghost btn-sm" disabled={!cabecera.length && !cruce} onClick={excel}>
          Descargar máxima y clientes en Excel
        </button>
      </div>

      {/* Spec 006: la máxima de arriba, repartida entre las SED del proyecto de DIgSILENT. */}
      <h4>2.4 · Escalar las demás cargas y ajustar</h4>
      <AjusteCabecera project={project} maxima={ultimo} feeders={feeders} desconectados={desconectados}
        centrales={Object.fromEntries(Object.entries(centrales).filter(([, c]) => centralCompleta(c)))} />
    </div>
  );
}

function Cruce({ cruce, visibles, filtro, setFiltro, desconectados, conmutar }: {
  cruce: ClientesCruce; visibles: ClienteImportante[]; filtro: string; setFiltro: (v: string) => void;
  desconectados: Set<string>; conmutar: (codigo: string) => void;
}) {
  const t = cruce.totales;
  const ali = cruce.alimentadores.join(', ');
  return <>
    <p>{ali ? <>{fmtNum(t.cruzados)} cliente(s) de <strong>{ali}</strong> de {fmtNum(t.clientes)}</> : <>{fmtNum(t.cruzados)} de {fmtNum(t.clientes)} cruzados</>}
      {' '}({fmtNum(t.por_actual)} por «Suministro Act», {fmtNum(t.por_anterior)} por «Suministro»); {fmtNum(t.no_cruzados)} aparte
      {ali ? `, ${fmtNum(t.de_otros)} de otros alimentadores sin mostrar` : ''}.
      {cruce.libro && <small className="muted"> Libro {cruce.libro}{cruce.mes ? ` (${nombreMes(cruce.mes)})` : ''}.</small>}</p>
    {ali && t.cruzados === 0 && t.de_otros > 0 && <p className="alert alert-warn">Ningún suministro tiene «{ali}» en la columna
      RADIAL: compruebe que el libro de suministros usa el mismo código de alimentador.</p>}
    {cruce.avisos.length > 0 && <details className="alert alert-warn"><summary>Avisos: {cruce.avisos.length}</summary>
      <ul className="small">{cruce.avisos.slice(0, 100).map((a) => <li key={a}>{a}</li>)}</ul></details>}
    <input className="search" type="search" placeholder="Filtrar por Nis, SED o radial…" value={filtro}
      onChange={(e) => setFiltro(e.target.value)} />
    <div className="table-wrap table-short">
      <table className="table">
        <thead><tr><th>Conectado</th><th>Nis / Suministro</th><th>Cliente</th><th>Cruzado por</th><th>SED</th><th>Radial</th>
          <th className="num">EA</th><th className="num">ERI</th><th className="num">Pot</th></tr></thead>
        <tbody>{visibles.map((c) => (
          <tr key={c.codigo} className={desconectados.has(c.codigo) ? 'muted' : undefined}>
            <td><input type="checkbox" checked={!desconectados.has(c.codigo)} onChange={() => conmutar(c.codigo)}
              aria-label={`Conectar ${c.codigo} en DIgSILENT`}
              title="Desmarcado: no suma a su SED y, si su SED se queda sin clientes conectados, su carga queda fuera de servicio en el ajuste" /></td>
            <td className="mono">{c.codigo}</td><td className="small">{c.nombre || '—'}</td><td className="small">{c.cruzado_por === 'actual' ? 'Suministro Act' : 'Suministro'}</td>
            <td className="strong">{c.sed}</td><td>{c.radial || '—'}</td><td className="num">{fmtNum(c.ea, 2)}</td>
            <td className="num">{fmtNum(c.eri, 2)}</td><td className="num">{fmtNum(c.pot, 2)}</td></tr>
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

/** Spec 022, RF-39 a RF-44: cada barra de SET con su máxima y sus alimentadores en esa fecha. */
function BarrasDeSet({ barras }: { barras: BarraDeSet[] }) {
  return (
    <div className="table-wrap">
      <strong>Máxima por barra de SET</strong>
      <table className="small">
        <thead><tr><th>Barra</th><th>Medidores</th><th>Fecha y hora</th><th>kW</th><th>kVAR</th>
          <th>Central</th><th>Alimentadores (en esa fecha)</th></tr></thead>
        <tbody>{barras.map((b) => (
          <tr key={b.clave}>
            <td>{b.clave}{b.suelta ? ' (suelta)' : ''}</td><td className="mono">{b.medidores.join(' + ')}</td>
            <td>{b.fecha}</td><td className="num">{fmtNum(b.kw, 1)}</td><td className="num">{fmtNum(b.kvar, 1)}</td>
            <td>{b.centrales.map((c) => `${c.medidor} ${c.kw === null ? '—' : fmtNum(c.kw, 1)} kW`).join('; ') || '—'}</td>
            <td>{b.alimentadores.join(', ')}</td>
          </tr>
        ))}</tbody>
      </table>
      <small className="muted">Cada alimentador de la barra se calibra con su kW y kVAR de esa fecha y hora, no con su máxima (022:RF-41).</small>
    </div>
  );
}
