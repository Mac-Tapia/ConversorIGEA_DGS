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

/**
 * Demanda medida (spec 004, RF-22 a RF-41): máxima de cabecera por medidor y clientes
 * importantes con su SED. Se muestra y se descarga; el ajuste de las demandas a la
 * máxima (spec 006) va aparte, en ``AjusteCabecera``.
 */
export function DemandaMedida({ project }: { project: string }) {
  const { ws, run, startJob, active, jobs } = useApp();
  const [alimentador, setAlimentador] = useState('');
  const [medidores, setMedidores] = useState<string[]>([]);
  const [elegidos, setElegidos] = useState<string[]>([]);
  const [noEncontrado, setNoEncontrado] = useState('');
  const [manual, setManual] = useState('');
  const [cruce, setCruce] = useState<ClientesCruce | null>(null);
  const [filtro, setFiltro] = useState('');
  const [lista, setLista] = useState<string[]>([]);
  const toast = useToast();
  const engineBusy = Boolean(active.engine);

  const ultimo = Object.values(jobs).filter((j) => j.kind === 'demanda_cabecera' && j.result).pop();
  const cabecera = (ultimo?.result?.resultados ?? []) as MaximaCabecera[];
  // Los clientes se cruzan para el alimentador de la máxima mostrada (RF-43); sin máxima
  // todavía, para el escrito arriba; sin ninguno, toda la empresa.
  const deLaMaxima = [...new Set(cabecera.map((r) => r.alimentador).filter(Boolean))];
  const paraCruce = deLaMaxima.length ? deLaMaxima : alimentador.trim() ? [alimentador.trim()] : [];

  // Desplegable del código (RF-42): se vuelve a leer al cambiar el libro de medidores.
  const libroMedidores = ws.demanda?.medidores?.name ?? '';
  useEffect(() => {
    if (!libroMedidores) { setLista([]); return; }
    let vivo = true;
    api.demandaAlimentadores(ws.id).then((r) => { if (vivo) setLista(r.alimentadores); }).catch(() => setLista([]));
    return () => { vivo = false; };
  }, [ws.id, libroMedidores]);

  const buscar = async (codigo = alimentador) => {
    const r = await run(() => api.demandaMedidores(ws.id, codigo.trim()));
    if (!r) return;
    setMedidores(r.medidores);
    setElegidos(r.medidores);
    setNoEncontrado(r.encontrado ? '' : r.alimentador);
  };
  const anadir = () => {
    const m = manual.trim();
    if (!m) return;
    setMedidores((xs) => (xs.includes(m) ? xs : [...xs, m]));
    setElegidos((xs) => (xs.includes(m) ? xs : [...xs, m]));
    setManual('');
  };
  const maxima = () => {
    if (!elegidos.length) { toast('error', 'Elija al menos un medidor', ''); return; }
    startJob(() => api.demandaCabecera(ws.id, elegidos.map((medidor) => ({ alimentador: alimentador.trim(), medidor }))));
  };
  const cruzar = async () => {
    const r = await run(() => api.demandaClientes(ws.id, paraCruce));
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

  return (
    <div className="step-box">
      <h3>Demanda medida</h3>
      <p className="muted">Máxima demanda de cabecera por medidor y clientes importantes con su SED. Se muestra y se descarga
        en Excel; no cambia las demandas en bloque ni las cargas nuevas de arriba.</p>
      <div className="form-grid">
        {LIBROS.map((l) => <Libro key={l.tipo} {...l} />)}
      </div>

      <h4>Máxima de cabecera</h4>
      <div className="row">
        <label className="field">
          <span>Código de alimentador</span>
          <input value={alimentador} list="demanda-alimentadores" autoComplete="off"
            placeholder={lista.length ? `escriba o elija (${lista.length})` : undefined}
            onChange={(e) => {
              const v = e.target.value;
              setAlimentador(v);
              // Elegido de la lista: se buscan sus medidores sin pulsar el botón.
              if (lista.includes(v)) buscar(v);
            }}
            onKeyDown={(e) => { if (e.key === 'Enter' && alimentador.trim()) buscar(); }} />
          <datalist id="demanda-alimentadores">{lista.map((a) => <option key={a} value={a} />)}</datalist>
        </label>
        <button className="btn" disabled={!alimentador.trim() || !ws.demanda?.medidores} onClick={() => buscar()}>Buscar medidores</button>
      </div>
      {noEncontrado && <p className="alert alert-warn">{noEncontrado} no está en el libro de medidores: escriba el medidor a mano.</p>}
      <div className="row">
        <label className="field">
          <span>Código de medidor</span>
          <input value={manual} placeholder="a mano, si no sale arriba" onChange={(e) => setManual(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') anadir(); }} />
        </label>
        <button className="btn btn-sm btn-ghost" disabled={!manual.trim()} onClick={anadir}>Añadir</button>
      </div>
      {medidores.length > 0 && (
        <div className="chips">
          <span className="muted">Medidores:</span>
          {medidores.map((m) => (
            <button key={m} className={`chip ${elegidos.includes(m) ? 'on' : ''}`}
              onClick={() => setElegidos((xs) => (xs.includes(m) ? xs.filter((x) => x !== m) : [...xs, m]))}>{m}</button>
          ))}
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

      <h4>Clientes importantes</h4>
      <div className="row">
        <button className="btn" disabled={!ws.demanda?.suministros || !ws.demanda?.clientes} onClick={cruzar}>
          {paraCruce.length ? `Cruzar clientes de ${paraCruce.join(', ')}` : 'Cruzar clientes con suministros'}
        </button>
        {!paraCruce.length && <small className="muted">Sin alimentador: se cruzan los de toda la empresa.</small>}
        {(!ws.demanda?.suministros || !ws.demanda?.clientes) && <small className="muted">Faltan los suministros o los clientes.</small>}
      </div>
      {cruce && <Cruce cruce={cruce} visibles={visibles} filtro={filtro} setFiltro={setFiltro} />}

      <div className="row">
        <button className="btn" disabled={!cabecera.length && !cruce} onClick={excel}>Descargar en Excel</button>
      </div>

      {/* Spec 006: la máxima de arriba, repartida entre las SED del proyecto de DIgSILENT. */}
      <AjusteCabecera project={project} maxima={ultimo} />
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
