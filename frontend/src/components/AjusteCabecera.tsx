import { useMemo, useState } from 'react';
import { api, fmtNum } from '../api';
import { useApp } from '../context';
import type { AjusteInforme, AjustePlan, AjusteResultado, Job, MaximaCabecera } from '../types';

const pct = (x: number | null | undefined) => (x == null ? '—' : `${x >= 0 ? '+' : ''}${fmtNum(x * 100, 2)} %`);

/**
 * Ajuste de las demandas del alimentador a su máxima de cabecera (spec 006, RF-23).
 *
 * Toma la máxima que se ve en la tabla de arriba y el proyecto elegido en esta misma
 * pestaña. Las SED con clientes importantes llevan su demanda; las demás se reparten lo
 * que falta por kVA y el flujo de carga de DIgSILENT cuadra las pérdidas.
 */
export function AjusteCabecera({ project, maxima }: { project: string; maxima: Job | undefined }) {
  const { ws, run, startJob, active, jobs } = useApp();
  const [medidor, setMedidor] = useState('');
  const [tolerancia, setTolerancia] = useState('1');
  const [plan, setPlan] = useState<AjustePlan | null>(null);
  const pfBusy = Boolean(active.powerfactory);

  const filas = ((maxima?.result?.resultados ?? []) as MaximaCabecera[]).filter((r) => !r.error);
  // RF-2: con varios medidores hay que elegir el de la cabecera; con uno, es ese.
  const elegido = filas.length === 1 ? filas[0].medidor : medidor;
  const tol = Number(tolerancia.replace(',', '.')) / 100;
  const tolValida = Number.isFinite(tol) && tol >= 0.001 && tol <= 0.1;

  const ultimo = Object.values(jobs)
    .filter((j) => (j.kind === 'ajuste_simular' || j.kind === 'ajuste_aplicar') && j.result)
    .pop();
  const resultado = (ultimo?.result ?? null) as AjusteResultado | null;

  const falta = !maxima ? 'Busque antes la máxima de cabecera.'
    : !filas.length ? 'Ningún medidor tiene máxima: no hay objetivo.'
      : !elegido ? 'Elija el medidor de la cabecera.'
        : !project ? 'Elija arriba el proyecto de DIgSILENT («Leer proyectos de DIgSILENT»).'
          : !tolValida ? 'La tolerancia va de 0,1 % a 10 %.' : '';

  const lanzar = async (simular: boolean) => {
    if (!maxima || falta) return;
    const p = await run(() => api.ajustePlan(ws.id, { project, job_id: maxima.id, medidor: elegido, tolerancia: tol }));
    if (!p) return;
    setPlan(p);
    await startJob(() => (simular ? api.ajusteSimular : api.ajusteAplicar)(ws.id, p.token));
  };

  return (
    <div className="step-box">
      <h4>Ajustar a la máxima en DIgSILENT</h4>
      <p className="muted">Las SED con clientes importantes llevan su demanda; las demás se reparten lo que falta en
        proporción al kVA de su transformador, y el flujo de carga cuadra las pérdidas hasta que la cabecera dé la
        máxima. Se graba en una variación nueva.</p>
      <div className="row">
        {filas.length > 1 && (
          <label className="field">
            <span>Medidor de la cabecera</span>
            <select value={medidor} onChange={(e) => setMedidor(e.target.value)}>
              <option value="">— elija —</option>
              {filas.map((r) => <option key={r.medidor} value={r.medidor}>{r.medidor} · {fmtNum(r.kw, 1)} kW</option>)}
            </select>
          </label>
        )}
        <label className="field">
          <span>Tolerancia (%)</span>
          <input value={tolerancia} inputMode="decimal" size={5} onChange={(e) => setTolerancia(e.target.value)} />
        </label>
        <button className="btn" disabled={Boolean(falta) || pfBusy} onClick={() => lanzar(true)}
          title="El reparto por SED antes de las pérdidas, sin escribir en el proyecto">Simular</button>
        <button className="btn btn-pf" disabled={Boolean(falta) || pfBusy} onClick={() => lanzar(false)}>
          Ajustar en DIgSILENT
        </button>
      </div>
      {falta && <small className="muted">{falta}</small>}
      {project && !falta && <small className="muted">Proyecto: <span className="mono">{project}</span></small>}
      {plan && plan.avisos.map((a) => <p key={a} className="alert alert-warn">{a}</p>)}
      {resultado && <InformeAjuste inf={resultado.informe} report={resultado.report}
        cancelado={ultimo?.status === 'cancelled'} />}
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
