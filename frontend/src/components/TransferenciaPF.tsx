import { useState } from 'react';
import { api, fmtNum } from '../api';
import { useApp } from '../context';
import type { MaximoTransferencia, SentidoTransferencia, TransferenciaResultado } from '../types';
import { CASOS_OBRA } from './ObrasPF';

const maximo = (m?: MaximoTransferencia | null) =>
  (m ? `${m.punto}: ${fmtNum(m.carga_kw, 1)} kW (${fmtNum(m.carga_kva, 1)} kVA)` : '—');

/**
 * 4.3 · Transferencia de carga (spec 011, RF-104 a RF-129).
 *
 * Dos alimentadores marcados y el caso: cuánta carga pasa de uno a otro por su enlace,
 * en los dos sentidos, hasta qué seccionador o nodo, y la capacidad del enlace.
 */
export function TransferenciaPF({ project, feeders }: { project: string; feeders: string[] }) {
  const { ws, startJob, active, jobs } = useApp();
  const [a, setA] = useState('');
  const [b, setB] = useState('');
  const [casos, setCasos] = useState<string[]>(['Sin proyecto']);
  const pfBusy = Boolean(active.powerfactory);
  const ultima = Object.values(jobs).filter((j) => j.kind === 'transferencia' && j.result).pop();
  const r = (ultima?.result ?? null) as TransferenciaResultado | null;
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
        <button className="btn btn-pf" disabled={pfBusy || !casos.length || uno === otro || !project}
          onClick={() => startJob(() => api.transferencia(ws.id, { project, feeders: [uno, otro], casos }))}>
          Calcular la transferencia en los dos sentidos
        </button>
        {uno === otro && <small className="muted">Elija dos alimentadores distintos.</small>}
      </div>
      {r && (
        <div className="alert">
          {r.informe.avisos.map((x) => <p key={x} className="alert alert-warn">{x}</p>)}
          <div className="table-wrap table-short">
            <table className="table">
              <thead><tr><th>Caso</th><th>Sentido</th><th>Enlace</th><th>Hasta seccionador</th><th>Hasta nodo</th>
                <th>Limita</th><th>Capacidad del enlace</th></tr></thead>
              <tbody>{r.informe.resultados.map((s) => <FilaSentido key={`${s.caso}-${s.cede}-${s.enlace}`} s={s} />)}</tbody>
            </table>
          </div>
          {r.fichero && <a className="btn btn-sm btn-ghost" href={api.fileUrl(ws.id, r.fichero, true)}>{r.fichero}</a>}
        </div>
      )}
    </div>
  );
}

function FilaSentido({ s }: { s: SentidoTransferencia }) {
  const lim = s.limita;
  const cap = s.capacidad;
  return (
    <tr>
      <td>{s.caso}</td><td className="strong">{s.cede} → {s.recibe}</td><td className="mono small">{s.enlace}</td>
      <td className="small">{s.admite === false ? <span className="badge err">no admite</span> : maximo(s.maximo_seccionador)}</td>
      <td className="small">{maximo(s.maximo_nodo)}</td>
      <td className="small">{lim ? `${lim.motivo}${lim.elemento ? ` en ${lim.elemento}` : ''}${lim.valor != null
        ? ` (${fmtNum(lim.valor, 3)})` : ''}` : '—'}
        {(s.avisos ?? []).map((a) => <div key={a} className="muted">{a}</div>)}</td>
      <td className="small">{cap?.capacidad_kw != null ? `${fmtNum(cap.capacidad_kw, 1)} kW, margen ${fmtNum(cap.margen_kw, 1)} kW
        (${cap.metodo})` : '—'}</td>
    </tr>
  );
}
