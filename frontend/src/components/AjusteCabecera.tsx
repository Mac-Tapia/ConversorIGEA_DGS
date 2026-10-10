import { useMemo, useState } from 'react';
import { api, fmtNum } from '../api';
import { useApp } from '../context';
import type { AjusteInforme, AjustePlan, AjusteResultado, Job, MaximaCabecera } from '../types';

const pct = (x: number | null | undefined) => (x == null ? '—' : `${x >= 0 ? '+' : ''}${fmtNum(x * 100, 2)} %`);

/**
 * Ajuste de las demandas de los alimentadores a su máxima de cabecera (spec 006, RF-23).
 *
 * Toma la máxima que se ve en la tabla de arriba y el proyecto del paso 1. Las SED con
 * clientes importantes llevan su demanda; las demás se reparten lo que falta por kVA y
 * el flujo de carga de DIgSILENT cuadra las pérdidas. Con varios alimentadores marcados
 * se ajustan uno tras otro en un solo trabajo, cada uno en su variación (spec 008, RF-12).
 */
export function AjusteCabecera({ project, maxima, feeders }: { project: string; maxima: Job | undefined; feeders: string[] }) {
  const { ws, run, startJob, active, jobs } = useApp();
  const [elegido, setElegido] = useState<Record<string, string>>({});
  const [tolerancia, setTolerancia] = useState('1');
  const [plan, setPlan] = useState<AjustePlan | null>(null);
  const pfBusy = Boolean(active.powerfactory);

  const filas = useMemo(() => ((maxima?.result?.resultados ?? []) as MaximaCabecera[]).filter((r) => !r.error), [maxima]);
  // Un grupo por alimentador marcado con máxima, en el orden de los marcados.
  const grupos = useMemo(() => {
    const por = new Map<string, MaximaCabecera[]>();
    for (const r of filas) {
      const a = r.alimentador || '';
      if (feeders.length && !feeders.includes(a)) continue;
      por.set(a, [...(por.get(a) ?? []), r]);
    }
    const orden = [...feeders.filter((f) => por.has(f)), ...[...por.keys()].filter((a) => !feeders.includes(a))];
    return orden.map((a) => ({ alimentador: a, filas: por.get(a)! }));
  }, [filas, feeders]);
  // RF-13: con varios medidores en un alimentador hay que elegir el de su cabecera.
  const medidores = grupos.map((g) => (g.filas.length === 1 ? g.filas[0].medidor : elegido[g.alimentador] ?? ''));
  const sinElegir = grupos.filter((_g, i) => !medidores[i]).map((g) => g.alimentador || '—');
  const tol = Number(tolerancia.replace(',', '.')) / 100;
  const tolValida = Number.isFinite(tol) && tol >= 0.001 && tol <= 0.1;

  const ultimo = Object.values(jobs)
    .filter((j) => (j.kind === 'ajuste_simular' || j.kind === 'ajuste_aplicar') && j.result)
    .pop();
  const resultado = (ultimo?.result ?? null) as AjusteResultado | null;
  const informes = resultado ? (resultado.informes ?? [resultado.informe]) : [];

  const falta = !maxima ? 'Busque antes la máxima de cabecera.'
    : !grupos.length ? 'Ningún alimentador marcado tiene máxima: no hay objetivo.'
      : sinElegir.length ? `Elija el medidor de la cabecera de ${sinElegir.join(', ')}.`
        : !project ? 'Elija el proyecto de DIgSILENT en el paso 1.'
          : !tolValida ? 'La tolerancia va de 0,1 % a 10 %.' : '';

  const lanzar = async (simular: boolean) => {
    if (!maxima || falta) return;
    const p = await run(() => api.ajustePlan(ws.id, { project, job_id: maxima.id, medidor: '', medidores, tolerancia: tol }));
    if (!p) return;
    setPlan(p);
    await startJob(() => (simular ? api.ajusteSimular : api.ajusteAplicar)(ws.id, p.token));
  };
  const quien = grupos.length === 1 ? grupos[0].alimentador : `${grupos.length} alimentadores`;

  return (
    <div className="step-box">
      <h4>Ajustar a la máxima en DIgSILENT</h4>
      <p className="muted">Las SED con clientes importantes llevan su demanda (fija); las demás se reparten lo que falta en
        proporción al kVA de su transformador, y el flujo de carga cuadra las pérdidas hasta que la cabecera dé la
        máxima. Cada alimentador se graba en su propia variación.</p>
      {grupos.some((g) => g.filas.length > 1) && (
        <div className="row">
          {grupos.filter((g) => g.filas.length > 1).map((g) => (
            <label key={g.alimentador} className="field">
              <span>Medidor de la cabecera de {g.alimentador || '—'}</span>
              <select value={elegido[g.alimentador] ?? ''} onChange={(e) => setElegido((x) => ({ ...x, [g.alimentador]: e.target.value }))}>
                <option value="">— elija —</option>
                {g.filas.map((r) => <option key={r.medidor} value={r.medidor}>{r.medidor} · {fmtNum(r.kw, 1)} kW</option>)}
              </select>
            </label>
          ))}
        </div>
      )}
      <div className="row">
        <label className="field">
          <span>Tolerancia (%)</span>
          <input value={tolerancia} inputMode="decimal" size={5} onChange={(e) => setTolerancia(e.target.value)} />
        </label>
        <button className="btn" disabled={Boolean(falta) || pfBusy} onClick={() => lanzar(true)}
          title="El reparto por SED antes de las pérdidas, sin escribir en el proyecto">Simular</button>
        <button className="btn btn-pf" disabled={Boolean(falta) || pfBusy} onClick={() => lanzar(false)}>
          Ajustar {grupos.length ? quien : ''} en DIgSILENT
        </button>
      </div>
      {falta && <small className="muted">{falta}</small>}
      {!falta && grupos.length > 1 && (
        <small className="muted">Orden: {grupos.map((g, i) => `${g.alimentador} (${medidores[i]})`).join(' → ')}. Si uno falla,
          se sigue con el siguiente.</small>
      )}
      {plan && plan.avisos.map((a) => <p key={a} className="alert alert-warn">{a}</p>)}
      {informes.map((inf, i) => (
        inf.no_empezado
          ? <p key={inf.feeder} className="alert alert-warn">{inf.feeder}: cancelado antes de empezar.</p>
          : inf.error
            ? <p key={inf.feeder} className="alert alert-error"><strong>{inf.feeder}</strong>: {inf.error}</p>
            : <InformeAjuste key={inf.feeder} inf={inf} report={resultado?.reports?.[i] ?? resultado?.report ?? ''}
              cancelado={ultimo?.status === 'cancelled'} />
      ))}
    </div>
  );
}

function InformeAjuste({ inf, report, cancelado }: { inf: AjusteInforme; report: string; cancelado: boolean }) {
  const [filtro, setFiltro] = useState('');
  const simular = inf.modo === 'simular';
  const filas = useMemo(() => {
    const f = filtro.trim().toLowerCase();
    const xs = inf.sed ?? [];
    return f ? xs.filter((x) => x.sed.toLowerCase().includes(f)) : xs;
  }, [inf.sed, filtro]);
  const o = inf.objetivo;
  return (
    <div className="step-box">
      <h4>{simular ? 'Simulación' : 'Ajuste'} de {inf.feeder} en {inf.project}
        {inf.variacion ? ` · variación ${inf.variacion}` : ''}</h4>
      {simular && <p className="muted">Nada se ha escrito en el proyecto. Es el reparto antes de las pérdidas: al ajustar,
        las SED repartidas suben lo que pidan las pérdidas.</p>}
      {!simular && (
        <p className={inf.cuadrado ? 'alert alert-ok' : 'alert alert-error'}>
          {inf.cuadrado
            ? <>Cuadrado al {fmtNum((inf.tolerancia ?? 0) * 100, 1)} % en {inf.flujos} flujo(s) de carga.</>
            : <>No cumple el {fmtNum((inf.tolerancia ?? 0) * 100, 1)} %: {inf.motivo}. La variación queda con el último reparto
              que convergió.</>}
        </p>
      )}
      {(inf.cancelado || cancelado) && <p className="alert alert-warn">Cancelado: terminó el flujo en curso.</p>}
      {inf.avisos.map((a) => <p key={a} className="alert alert-warn">{a}</p>)}
      {o && (
        <div className="table-wrap">
          <table className="table">
            <thead><tr><th /><th className="num">kW</th><th className="num">kVAR</th></tr></thead>
            <tbody>
              <tr><td>Objetivo ({o.medidor}{o.fecha ? `, ${o.fecha}` : ''})</td>
                <td className="num">{fmtNum(o.kw, 1)}</td><td className="num">{fmtNum(o.kvar, 1)}</td></tr>
              {inf.totales_sin_perdidas && <tr><td>Suma de las SED, sin pérdidas</td>
                <td className="num">{fmtNum(inf.totales_sin_perdidas.kw, 1)}</td>
                <td className="num">{fmtNum(inf.totales_sin_perdidas.kvar, 1)}</td></tr>}
              {inf.cabecera && <tr><td>Entra por la cabecera</td>
                <td className="num">{fmtNum(inf.cabecera.kw, 1)}</td><td className="num">{fmtNum(inf.cabecera.kvar, 1)}</td></tr>}
              {inf.perdidas && inf.perdidas.kw != null && <tr><td>Pérdidas</td>
                <td className="num">{fmtNum(inf.perdidas.kw, 1)}</td><td className="num">{fmtNum(inf.perdidas.kvar ?? 0, 1)}</td></tr>}
              {inf.desvio && <tr><td>Error</td><td className="num">{pct(inf.desvio.kw)}</td>
                <td className="num">{inf.solo_kw ? 'solo se cuadra el kW' : pct(inf.desvio.kvar)}</td></tr>}
            </tbody>
          </table>
        </div>
      )}
      {(inf.remedios ?? []).length > 0 && (
        <details open={!inf.cuadrado}><summary>Remedios para converger: {inf.remedios!.length}</summary>
          <ul className="small">{inf.remedios!.map((r) => (
            <li key={r.remedio}><strong>{r.remedio}</strong>{r.cambios.length ? `: ${r.cambios.join('; ')}` : ''}</li>))}</ul>
          <small className="muted">Los ajustes del flujo de carga se devolvieron a su valor al terminar.</small>
        </details>
      )}
      {inf.diagnostico && <Diagnostico d={inf.diagnostico} />}
      {(inf.omitidas ?? []).length > 0 && (
        <details className="alert alert-warn"><summary>SED de clientes que no están en el alimentador: {inf.omitidas!.length}</summary>
          <ul className="small">{inf.omitidas!.map((x) => <li key={x.sed}><strong>{x.sed}</strong>: {x.motivo}
            {x.clientes ? ` (clientes ${x.clientes})` : ''}</li>)}</ul></details>
      )}
      {(inf.fallos ?? []).length > 0 && (
        <details className="alert alert-error"><summary>SED que DIgSILENT no dejó escribir: {inf.fallos!.length}</summary>
          <ul className="small">{inf.fallos!.map((x) => <li key={x.sed}><strong>{x.sed}</strong>: {x.error}</li>)}</ul></details>
      )}
      {filas.length > 0 || filtro ? <>
        <input className="search" type="search" placeholder="Filtrar SED…" value={filtro} onChange={(e) => setFiltro(e.target.value)} />
        <div className="table-wrap table-short">
          <table className="table">
            <thead><tr><th>SED</th><th>Demanda de</th><th className="num">kVA</th><th className="num">kW antes</th>
              <th className="num">kW {simular ? 'sin pérdidas' : 'después'}</th><th className="num">kVAR {simular ? 'sin pérdidas' : 'después'}</th></tr></thead>
            <tbody>{filas.map((x) => (
              <tr key={x.sed}>
                <td className="strong">{x.sed}</td>
                <td className="small">{x.origen === 'cliente' ? `clientes ${x.clientes.join(', ')}` : 'reparto por kVA'}</td>
                <td className="num" title={x.kva_de === 'entrada' ? 'De la entrada original: sin transformador en DIgSILENT' : undefined}>
                  {x.kva == null ? '—' : fmtNum(x.kva)}{x.kva_de === 'entrada' ? ' *' : ''}</td>
                <td className="num">{fmtNum(x.antes.kw, 1)}</td>
                <td className="num">{fmtNum(x.despues.kw, 1)}</td>
                <td className="num">{fmtNum(x.despues.kvar, 1)}</td>
              </tr>
            ))}</tbody>
          </table>
        </div>
        <small className="muted">* kVA de la entrada original. Informe completo: {report}, en «Resultados».</small>
      </> : null}
    </div>
  );
}

function Diagnostico({ d }: { d: NonNullable<AjusteInforme['diagnostico']> }) {
  const sed = d.sed_por_encima_de_su_transformador ?? [];
  return (
    <details className="alert alert-warn" open>
      <summary>Por qué no convergió</summary>
      <ul className="small">
        {d.tension_minima && <li>Tensión mínima: {fmtNum(d.tension_minima.u_pu, 3)} p.u. en {d.tension_minima.barra}.</li>}
        {d.n_barras_sin_tension > 0 && <li>{d.n_barras_sin_tension} barra(s) sin tensión o aisladas:
          {' '}{d.barras_sin_tension.join(', ')}{d.n_barras_sin_tension > d.barras_sin_tension.length ? '…' : ''}</li>}
        {d.sobrecargados.length > 0 && <li>Sobrecargados: {d.sobrecargados.map((x) =>
          `${x.elemento} (${fmtNum(x.carga_pct, 0)} %)`).join(', ')}</li>}
        {sed.length > 0 && <li>SED que pedían más que su transformador: {sed.map((x) =>
          `${x.sed} (${fmtNum(x.carga_kva, 0)} de ${fmtNum(x.kva, 0)} kVA)`).join(', ')}</li>}
        {!d.tension_minima && !d.n_barras_sin_tension && !d.sobrecargados.length && !sed.length &&
          <li>Sin causa clara en los resultados: revise el alimentador en DIgSILENT.</li>}
      </ul>
    </details>
  );
}
