import { useEffect, useMemo, useState } from 'react';
import { api, fmtNum, type DemandaTipo } from '../api';
import { useApp } from '../context';
import type { ClientesCruce, ClienteImportante, MaximaCabecera } from '../types';
import { AjusteCabecera } from './AjusteCabecera';
import { FileDrop, useToast } from './ui';

const LIBROS: { tipo: DemandaTipo; titulo: string; ayuda: string }[] = [
  { tipo: 'medidores', titulo: 'Medidor por alimentador', ayuda: 'Columnas «codigo alimentador» y «Medidor».' },
  { tipo: 'cabecera', titulo: 'Medición de cabecera', ayuda: 'Uno o varios libros (una hoja por medidor), o la carpeta que los contiene.' },
  { tipo: 'suministros', titulo: 'Suministros', ayuda: '«Suministro Act», «Suministro», «SED» y «RADIAL».' },
  { tipo: 'clientes', titulo: 'Clientes importantes del mes', ayuda: 'Hoja «resumen»: Nis/EA/ERI/Pot o SUMINISTRO/EA_TOTAL/ERI_TOTAL/POT_MAX.' },
];
const EXT = '.xls,.xlsx,.xlsb,.xlsm';

/** Un libro de la demanda medida: subida o, en local, ruta del servidor (RF-39). */
function Libro({ tipo, titulo, ayuda }: (typeof LIBROS)[number]) {
  const { ws, setWs, run, health } = useApp();
  const [ruta, setRuta] = useState('');
  const meta = ws.demanda?.[tipo];
  const subir = async (files: File[]) => {
    const r = await run(() => api.demandaSubir(ws.id, tipo, files));
    if (r) setWs(r);
  };
  const porRuta = async () => {
    const r = await run(() => api.demandaRuta(ws.id, tipo, ruta.trim()));
    if (r) { setWs(r); setRuta(''); }
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
          <FileDrop compact accept={EXT} multiple={tipo === 'cabecera'} onFiles={subir}>
            <span>Soltar o <u>elegir</u>{tipo === 'cabecera' ? ' (varios)' : ''}</span>
          </FileDrop>
          {health.server_paths && (
            <div className="row">
              <input className="search" placeholder={tipo === 'cabecera' ? 'o ruta de la carpeta en el servidor' : 'o ruta en el servidor'}
                value={ruta} onChange={(e) => setRuta(e.target.value)} />
              <button className="btn btn-sm" disabled={!ruta.trim()} onClick={porRuta}>Usar ruta</button>
            </div>
          )}
        </>
      )}
      <small className="muted">{ayuda}</small>
    </div>
  );
}

const fp = (n: number | null) => (n == null ? '—' : fmtNum(n, 3));

type Par = { alimentador: string; medidor: string };
const clave = (p: Par) => `${p.alimentador}|${p.medidor}`;

/**
 * Calibración (spec 004, RF-22 a RF-41; spec 008, RF-8 a RF-11): máxima de cabecera de
 * cada alimentador marcado y clientes importantes con su SED. Se muestra y se descarga;
 * el ajuste de las demandas a la máxima (spec 006) va aparte, en ``AjusteCabecera``.
 */
export function DemandaMedida({ project, feeders }: { project: string; feeders: string[] }) {
  const { ws, run, startJob, active, jobs } = useApp();
  // Medidores del libro por alimentador marcado; ``null``: no está en el libro (RF-9).
  const [porAlim, setPorAlim] = useState<Record<string, string[] | null>>({});
  const [elegidos, setElegidos] = useState<Par[]>([]);
  const [manual, setManual] = useState<Record<string, string>>({});
  const [otroCodigo, setOtroCodigo] = useState<Record<string, string>>({});
  const [lista, setLista] = useState<string[]>([]);
  const [buscando, setBuscando] = useState(false);
  const [cruce, setCruce] = useState<ClientesCruce | null>(null);
  const [filtro, setFiltro] = useState('');
  const toast = useToast();
  const engineBusy = Boolean(active.engine);

  const ultimo = Object.values(jobs).filter((j) => j.kind === 'demanda_cabecera' && j.result).pop();
  const cabecera = (ultimo?.result?.resultados ?? []) as MaximaCabecera[];

  // Otro proyecto u otros alimentadores: lo buscado para los anteriores ya no vale.
  const marcados = feeders.join('|');
  useEffect(() => {
    setPorAlim({});
    setElegidos([]);
    setCruce(null);
  }, [project, marcados]);

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
  const maxima = () => {
    if (!elegidos.length) { toast('error', 'Elija al menos un medidor', ''); return; }
    startJob(() => api.demandaCabecera(ws.id, elegidos));
  };
  // RF-11: los clientes de los alimentadores marcados.
  const cruzar = async () => {
    const r = await run(() => api.demandaClientes(ws.id, feeders));
    if (r) setCruce(r);
  };
  const excel = () => run(() => api.demandaExcel(ws.id, {
    cabecera, clientes: cruce?.cruzados ?? [], no_cruzados: cruce?.no_cruzados ?? [],
  }));

  const visibles = useMemo(() => {
    const f = filtro.trim().toLowerCase();
    const xs = cruce?.cruzados ?? [];
    return f ? xs.filter((c) => [c.codigo, c.sed, c.radial].some((v) => v.toLowerCase().includes(f))) : xs;
  }, [cruce, filtro]);
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
            <thead><tr><th>Alimentador</th><th>Medidores (se buscan los marcados)</th><th>A mano</th></tr></thead>
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
              </tr>
            ))}</tbody>
          </table>
        </div>
      )}
      <div className="row">
        <button className="btn btn-primary" disabled={!elegidos.length || !ws.demanda?.cabecera || engineBusy} onClick={maxima}>
          Buscar la máxima ({elegidos.length} medidor{elegidos.length === 1 ? '' : 'es'})
        </button>
        {!ws.demanda?.cabecera && <small className="muted">Falta la medición de cabecera.</small>}
      </div>
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
          <small className="muted">kVAR, kVA y FP son del mismo registro que el kW máximo. * calculado con kW y kVAR.
            {ultimo?.status === 'cancelled' ? ' Cancelado: faltan medidores.' : ''}</small>
        </div>
      )}

      <h4>2.3 · Clientes importantes (demanda fija)</h4>
      <div className="row">
        <button className="btn" disabled={!feeders.length || !ws.demanda?.suministros || !ws.demanda?.clientes} onClick={cruzar}>
          Cruzar clientes de {cuales}
        </button>
        {(!ws.demanda?.suministros || !ws.demanda?.clientes) && (
          <small className="muted">Faltan los suministros o los clientes: sin ellos todas las SED se reparten por kVA.</small>)}
      </div>
      {cruce && <Cruce cruce={cruce} visibles={visibles} filtro={filtro} setFiltro={setFiltro} />}

      <div className="row">
        <button className="btn btn-ghost btn-sm" disabled={!cabecera.length && !cruce} onClick={excel}>
          Descargar máxima y clientes en Excel
        </button>
      </div>

      {/* Spec 006: la máxima de arriba, repartida entre las SED del proyecto de DIgSILENT. */}
      <h4>2.4 · Escalar las demás cargas y ajustar</h4>
      <AjusteCabecera project={project} maxima={ultimo} feeders={feeders} />
    </div>
  );
}

function Cruce({ cruce, visibles, filtro, setFiltro }: {
  cruce: ClientesCruce; visibles: ClienteImportante[]; filtro: string; setFiltro: (v: string) => void;
}) {
  const t = cruce.totales;
  const ali = cruce.alimentadores.join(', ');
  return <>
    <p>{ali ? <>{fmtNum(t.cruzados)} cliente(s) de <strong>{ali}</strong> de {fmtNum(t.clientes)}</> : <>{fmtNum(t.cruzados)} de {fmtNum(t.clientes)} cruzados</>}
      {' '}({fmtNum(t.por_actual)} por «Suministro Act», {fmtNum(t.por_anterior)} por «Suministro»); {fmtNum(t.no_cruzados)} aparte
      {ali ? `, ${fmtNum(t.de_otros)} de otros alimentadores sin mostrar` : ''}.</p>
    {ali && t.cruzados === 0 && t.de_otros > 0 && <p className="alert alert-warn">Ningún suministro tiene «{ali}» en la columna
      RADIAL: compruebe que el libro de suministros usa el mismo código de alimentador.</p>}
    {cruce.avisos.length > 0 && <details className="alert alert-warn"><summary>Avisos: {cruce.avisos.length}</summary>
      <ul className="small">{cruce.avisos.slice(0, 100).map((a) => <li key={a}>{a}</li>)}</ul></details>}
    <input className="search" type="search" placeholder="Filtrar por Nis, SED o radial…" value={filtro}
      onChange={(e) => setFiltro(e.target.value)} />
    <div className="table-wrap table-short">
      <table className="table">
        <thead><tr><th>Nis / Suministro</th><th>Cruzado por</th><th>SED</th><th>Radial</th>
          <th className="num">EA</th><th className="num">ERI</th><th className="num">Pot</th></tr></thead>
        <tbody>{visibles.map((c) => (
          <tr key={c.codigo}><td className="mono">{c.codigo}</td><td className="small">{c.cruzado_por === 'actual' ? 'Suministro Act' : 'Suministro'}</td>
            <td className="strong">{c.sed}</td><td>{c.radial || '—'}</td><td className="num">{fmtNum(c.ea, 2)}</td>
            <td className="num">{fmtNum(c.eri, 2)}</td><td className="num">{fmtNum(c.pot, 2)}</td></tr>
        ))}</tbody>
      </table>
    </div>
    {cruce.no_cruzados.length > 0 && (
      <details className="alert alert-warn"><summary>No cruzados: {cruce.no_cruzados.length}</summary>
        <ul className="small">{cruce.no_cruzados.map((c) => <li key={c.codigo}><strong>{c.codigo}</strong>: {c.motivo}</li>)}</ul>
      </details>
    )}
  </>;
}
