import { fmtNum } from '../../shared/formato';
import { useState } from 'react';
import { api } from '../../api/client';
import { useApp } from '../../shared/context';
import type { MaximoTransferencia, SentidoTransferencia, TransferenciaResultado, TransferenciaTemporal } from '../../api/types';
import { CASOS_OBRA } from './ObrasPF';

const maximo = (m?: MaximoTransferencia | null) =>
  (m ? `${m.punto}: ${fmtNum(m.carga_kw, 1)} kW (${fmtNum(m.carga_kva, 1)} kVA)` : '—');

// Sin lectura se dice «—», nunca 0 kW (013:RF-25).
const kw = (c?: Record<string, [number, number] | null> | null, f?: string) => {
  const v = c && f ? c[f] : null;
  return v ? `${fmtNum(v[0], 1)} kW` : '—';
};

/**
 * 4.3 · Transferencia de carga (spec 011, RF-104 a RF-129; spec 013, RF-22 a RF-29).
 *
 * Dos alimentadores marcados y el caso: cuánta carga pasa de uno a otro por su enlace,
 * en los dos sentidos, hasta qué seccionador o nodo, y la capacidad del enlace. Se calcula
 * en los registros de cabecera de un mismo instante del periodo elegido en 2, nunca con la
 * suma de máximas independientes, y el resultado es el del instante crítico.
 */
export function TransferenciaPF({ project, feeders }: { project: string; feeders: string[] }) {
  const { ws, startJob, active, jobs } = useApp();
  const [a, setA] = useState('');
  const [b, setB] = useState('');
  const [casos, setCasos] = useState<string[]>(['Sin proyecto']);
  const pfBusy = Boolean(active.powerfactory);
  const ultima = Object.values(jobs).filter((j) => j.kind === 'transferencia' && j.result).pop();
  const r = (ultima?.result ?? null) as TransferenciaResultado | null;
  // 013:RF-9, RF-22: la máxima de cabecera de 2.2, buscada con un periodo elegido.
  const cabecera = Object.values(jobs).filter((j) => j.kind === 'demanda_cabecera' && j.result).pop();
  const periodo = (cabecera?.result?.periodo as string | null | undefined) ?? null;
  const uno = a || feeders[0] || '';
  const otro = b || feeders.find((f) => f !== uno) || '';
  const elegir = (valor: string, fijar: (v: string) => void) => (
    <select value={valor} onChange={(e) => fijar(e.target.value)}>
      {feeders.map((f) => <option key={f} value={f}>{f}</option>)}
    </select>
  );

  if (feeders.length < 2) return <p className="muted">Marque al menos dos alimentadores en el paso 2.</p>;
  return (
    <div>
      <p className="muted">Cierra el enlace y abre, uno tras otro desde él hacia la cabecera del que cede, cada seccionador y
        cada barra, con un flujo de carga en cada paso. Nada queda cambiado en el proyecto.</p>
      <div className="row">
        <label className="field"><span>Alimentador</span>{elegir(uno, setA)}</label>
        <label className="field"><span>y</span>{elegir(otro, setB)}</label>
        <div className="field">
          <span>En</span>
          <div className="chips">
            {CASOS_OBRA.map((c) => (
              <button key={c} type="button" className={`chip ${casos.includes(c) ? 'on' : ''}`}
                onClick={() => setCasos((xs) => (xs.includes(c) ? xs.filter((x) => x !== c) : [...xs, c]))}>{c}</button>
            ))}
          </div>
        </div>
      </div>
      <div className="row">
        <button className="btn btn-pf" disabled={pfBusy || !casos.length || uno === otro || !project || !periodo}
          onClick={() => startJob(() => api.transferencia(ws.id, { project, feeders: [uno, otro], casos,
            cabecera_job_id: cabecera?.id ?? null }))}>
          Calcular la transferencia en los dos sentidos
        </button>
        {uno === otro && <small className="muted">Elija dos alimentadores distintos.</small>}
        {!periodo
          ? <small className="muted">Busque antes la máxima de cabecera de los dos con un mes (o todo el año) elegido
            en 2: la transferencia se calcula en sus registros de un mismo instante.</small>
          : <small className="muted">Periodo {periodo}: cada instante con registro de los dos se verifica en
            DIgSILENT, salvo los que otro supera en carga de los dos.</small>}
      </div>
      {r && (
        <div className="alert">
          {r.informe.avisos.map((x) => <p key={x} className="alert alert-warn">{x}</p>)}
          {r.informe.temporal && <Temporal t={r.informe.temporal} />}
          <div className="table-wrap table-short">
            <table className="table">
              <thead><tr><th>Caso</th><th>Sentido</th><th>Enlace</th><th>Instante crítico</th><th>Hasta seccionador</th>
                <th>Hasta nodo</th><th>Limita</th><th>Cabeceras antes → después</th><th>Capacidad del enlace</th></tr></thead>
              <tbody>{r.informe.resultados.map((s) => <FilaSentido key={`${s.caso}-${s.cede}-${s.enlace}`} s={s} />)}</tbody>
            </table>
          </div>
          {r.informe.resultados.filter((s) => s.sed_transferidas?.length).map((s) => (
            <details key={`sed-${s.caso}-${s.cede}-${s.enlace}`}>
              <summary>{s.caso} · {s.cede} → {s.recibe}: {s.sed_transferidas!.length} SED pasan
                hasta {s.punto_transferido}</summary>
              <div className="table-wrap table-short">
                <table className="table">
                  <thead><tr><th>SED</th><th className="num">kW</th><th className="num">kVA</th></tr></thead>
                  <tbody>{s.sed_transferidas!.map((x) => (
                    <tr key={x.sed}><td className="mono small">{x.sed}</td><td className="num">{fmtNum(x.kw, 1)}</td>
                      <td className="num">{fmtNum(x.kva, 1)}</td></tr>))}</tbody>
                </table>
              </div>
            </details>
          ))}
          {r.fichero && <a className="btn btn-sm btn-ghost" href={api.fileUrl(ws.id, r.fichero, true)}>{r.fichero}</a>}
        </div>
      )}
    </div>
  );
}

/** Periodo, cobertura, criterio y si la capacidad está comprobada o es parcial (013:RF-28, RF-29). */
function Temporal({ t }: { t: TransferenciaTemporal }) {
  const c = t.cobertura;
  return (
    <div className={`alert ${t.aceptable ? 'alert-info' : 'alert-warn'}`}>
      <p>
        <span className={`badge ${t.aceptable ? 'ok' : 'err'}`}>{t.aceptable ? 'comprobada' : 'parcial, no aceptable'}</span>
        {' '}Periodo {t.periodo ?? '—'}: {c.instantes_comunes ?? '—'} instantes con registro de los dos
        {c.desde ? ` (${c.desde} a ${c.hasta})` : ''}, {t.candidatos.length} verificados en DIgSILENT
        ({t.candidatos.filter((x) => x.verificado).length} cuadraron).
      </p>
      <small className="muted">{t.criterio}.</small>
      {t.faltantes.length > 0 && (
        <ul>{t.faltantes.map((f) => <li key={f}>{f}</li>)}</ul>
      )}
    </div>
  );
}

function FilaSentido({ s }: { s: SentidoTransferencia }) {
  const lim = s.limita;
  const cap = s.capacidad;
  const cab = s.cabeceras;
  return (
    <tr>
      <td>{s.caso}</td><td className="strong">{s.cede} → {s.recibe}</td><td className="mono small">{s.enlace}</td>
      <td className="small mono">{s.instante ?? '—'}</td>
      <td className="small">{s.admite === false ? <span className="badge err">no admite</span> : maximo(s.maximo_seccionador)}</td>
      <td className="small">{maximo(s.maximo_nodo)}</td>
      <td className="small">{lim ? `${lim.motivo}${lim.elemento ? ` en ${lim.elemento}` : ''}${lim.valor != null
        ? ` (${fmtNum(lim.valor, 3)})` : ''}` : '—'}
        {(s.avisos ?? []).map((a) => <div key={a} className="muted">{a}</div>)}</td>
      <td className="small">{cab ? <>{s.cede}: {kw(cab.antes, s.cede)} → {kw(cab.despues, s.cede)}<br />
        {s.recibe}: {kw(cab.antes, s.recibe)} → {kw(cab.despues, s.recibe)}</> : '—'}</td>
      <td className="small">{cap?.capacidad_kw != null ? `${fmtNum(cap.capacidad_kw, 1)} kW, margen ${fmtNum(cap.margen_kw, 1)} kW
        (${cap.metodo})` : '—'}</td>
    </tr>
  );
}
