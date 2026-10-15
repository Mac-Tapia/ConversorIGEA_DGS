import { useMemo, useState } from 'react';
import { api, fmtNum } from '../api';
import { useApp } from '../context';
import type {
  AjusteInforme, AjustePlan, AjusteResultado, BalanceCabecera, ConsumoDistinto, Job, MaximaCabecera,
} from '../types';
import { CurvaCabecera } from './CurvaCabecera';

const pct = (x: number | null | undefined) => (x == null ? '—' : `${x >= 0 ? '+' : ''}${fmtNum(x * 100, 2)} %`);

/**
 * Ajuste de las demandas de los alimentadores a su máxima de cabecera (spec 006, RF-23).
 *
 * Toma la máxima que se ve en la tabla de arriba y el proyecto del paso 1. Las SED con
 * clientes importantes llevan su P y Q; las demás conservan las del archivo original y
 * suben con un mismo factor de escala hasta que la cabecera dé la máxima (spec 015,
 * RF-43, RF-44). Todo queda en el escenario de «Sin proyecto», sin variaciones. Con varios
 * alimentadores marcados se ajustan uno tras otro en un solo trabajo (spec 008, RF-12).
 */
export function AjusteCabecera({ project, maxima, feeders, desconectados }: {
  project: string; maxima: Job | undefined; feeders: string[]; desconectados: Set<string>;
}) {
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
    const p = await run(() => api.ajustePlan(ws.id, {
      project, job_id: maxima.id, medidor: '', medidores, tolerancia: tol, desconectados: [...desconectados],
    }));
    if (!p) return;
    setPlan(p);
    await startJob(() => (simular ? api.ajusteSimular : api.ajusteAplicar)(ws.id, p.token));
  };
  const quien = grupos.length === 1 ? grupos[0].alimentador : `${grupos.length} alimentadores`;

  return (
    <div className="step-box">
      <h4>Ajustar a la máxima en DIgSILENT</h4>
      <p className="muted">Se calibra en «Sin proyecto», la copia del «Caso base» verificado. Las SED con clientes
        importantes llevan su P y Q (fijas, factor de escala 1); las demás conservan la P y Q del archivo original y
        suben todas con el mismo <strong>factor de escala</strong> de DIgSILENT hasta que la cabecera dé la máxima, con
        las pérdidas del flujo. Queda en el escenario de «Sin proyecto», sin variaciones; el «Caso base» no cambia.</p>
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
      {maxima && grupos.length > 0 && (
        // RF-38: por defecto, la del medidor que da el objetivo del primer alimentador.
        <CurvaCabecera wsId={ws.id} jobId={maxima.id} inicial={medidores[0] || grupos[0].filas[0].medidor}
          opciones={grupos.flatMap((g) => g.filas.map((r) => ({
            medidor: r.medidor, etiqueta: `${g.alimentador || '—'} · ${r.medidor} · ${fmtNum(r.kw, 1)} kW`,
          })))} />
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
      {plan && (
        <div className="callout">
          <strong>Contrato de datos demostrado antes de ajustar</strong>
          <div className="kv-grid">
            <span>Ejecución fuente</span><code>{plan.source.source_run_id}</code>
            <span>Huella fuente</span><code>{plan.source.source_fingerprint.slice(0, 12)}…</code>
            <span>Proyecto nativo vinculado</span>
            <span>{plan.project_binding.native_reread.status} · {plan.project_binding.native_inventory_sha256.slice(0, 12)}…</span>
            {(plan.ajustes ?? []).map((x) => (
              <div style={{ display: 'contents' }} key={x.feeder}>
                <span>{x.feeder}: período</span>
                <span>{x.periodo.status === 'CLIENT_PERIOD_MATCH'
                  ? `${x.periodo.maxima} = ${x.client_evidence.file} (${x.periodo.clientes})`
                  : `${x.periodo.maxima ?? '—'} · sin libro de clientes`}</span>
                <span>{x.feeder}: reparto</span>
                <span>{x.n_sed_fijas} SED fija(s) · {x.n_sed_escaladas_estimadas} SED escalada(s)</span>
              </div>
            ))}
          </div>
          {plan.client_evidence.fingerprint && (
            <small className="muted">Huella del libro de clientes: {plan.client_evidence.fingerprint}</small>
          )}
        </div>
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
  // Spec 015, RF-44: el mismo factor (scale0) en todas las escaladas, el del último flujo que
  // convergió. Antes salía de después/antes, que con el reparto por kVA ya no es el factor.
  const ultimoFlujo = [...(inf.historial ?? [])].reverse().find((h) => h.converge && h.a != null);
  const factor = ultimoFlujo?.a ?? null;
  // Spec 015, RF-49: la validación física no pasó; nada quedó grabado.
  const revertida = inf.status === 'FALLO_VALIDACION_NATIVA' || inf.calibracion_revertida;
  const validacion = inf.validacion_posterior_nativa;
  const consumoDistinto = validacion?.fallos.find((f) => f.tipo === 'CONSUMO_DISTINTO_DE_LO_ESCRITO');
  const fallosEscritura = (inf.fallos ?? []).filter((x) => !x.detalle);
  return (
    <div className="step-box">
      <h4>{simular ? 'Simulación' : 'Ajuste'} de {inf.feeder} en {inf.project}
        {inf.escenario ? ` · escenario «${inf.escenario}»` : inf.variacion ? ` · variación ${inf.variacion}` : ''}</h4>
      {simular && <p className="muted">Nada se ha escrito en el proyecto. Es el reparto antes de las pérdidas: al ajustar,
        las SED repartidas suben lo que pidan las pérdidas.</p>}
      {!simular && revertida && (
        <p className="alert alert-error">
          La validación física en DIgSILENT no pasa: las cargas no consumen en el flujo lo que tienen
          escrito o falta su resultado. La calibración no es válida: las cargas vuelven a como estaban y
          no se grabó nada.
        </p>
      )}
      {!simular && !revertida && (
        <p className={inf.cuadrado ? 'alert alert-ok' : 'alert alert-error'}>
          {inf.cuadrado
            ? <>Cuadrado de kW al {fmtNum((inf.tolerancia ?? 0) * 100, 1)} % en {inf.flujos} flujo(s) de carga
              {inf.status ? ` · ${inf.status}` : ''}. El kVAR es informativo.</>
            : <>No cumple el {fmtNum((inf.tolerancia ?? 0) * 100, 1)} %: {inf.motivo}. El escenario queda con el último reparto
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
              {inf.cabecera_con_escenario && <tr><td>Con el escenario {(inf.escenarios ?? [])[0]?.escenario ?? ''} activo</td>
                <td className="num">{fmtNum(inf.cabecera_con_escenario.kw, 1)}</td>
                <td className="num">{fmtNum(inf.cabecera_con_escenario.kvar, 1)}</td></tr>}
              {inf.perdidas && inf.perdidas.kw != null && <tr><td>Pérdidas</td>
                <td className="num">{fmtNum(inf.perdidas.kw, 1)}</td><td className="num">{fmtNum(inf.perdidas.kvar ?? 0, 1)}</td></tr>}
              {inf.factor_potencia_cargas && <tr><td>Factor de potencia</td>
                <td colSpan={2}>Fijas: {inf.factor_potencia_cargas.fijas} · Escaladas:{' '}
                  {inf.factor_potencia_cargas.escaladas == null ? 'el de cada SED en el archivo original'
                    : `${fmtNum(inf.factor_potencia_cargas.escaladas, 2)} (${inf.factor_potencia_cargas.escaladas_origen})`}
                  {inf.factor_potencia_cargas.escaladas_reparto
                    ? `, repartidas por ${inf.factor_potencia_cargas.escaladas_reparto}` : ''}</td></tr>}
              {factor != null && <tr><td>Factor de escala de las SED escaladas</td>
                <td className="num">{fmtNum(factor, 4)}</td><td className="num">—</td></tr>}
              {inf.desvio && <tr><td>Error</td><td className="num">{pct(inf.desvio.kw)}</td>
                <td className="num">{inf.solo_kw ? 'solo se cuadra el kW' : pct(inf.desvio.kvar)}</td></tr>}
              {inf.kvar_no_bloqueante && <tr><td>Diferencia de kVAR (no bloqueante)</td>
                <td className="num">—</td>
                <td className="num">{inf.kvar_no_bloqueante.diferencia_kvar == null ? 'sin lectura'
                  : `${fmtNum(inf.kvar_no_bloqueante.diferencia_kvar, 2)} kVAR · ${pct(inf.kvar_no_bloqueante.diferencia_relativa)}`}
                  {' · '}{inf.kvar_no_bloqueante.status}</td></tr>}
            </tbody>
          </table>
        </div>
      )}
      {validacion?.balance && <BalanceFisico b={validacion.balance} />}
      {(inf.fijas_sobre_su_transformador ?? []).length > 0 && (
        <details className="alert alert-warn" open>
          <summary>Clientes que piden más que el transformador de su SED: {inf.fijas_sobre_su_transformador!.length}</summary>
          <ul className="small">{inf.fijas_sobre_su_transformador!.map((x) => (
            <li key={x.sed}><strong>{x.sed}</strong> ({x.clientes.join(', ') || 'cambio manual'}):{' '}
              {fmtNum(x.kva_carga, 0)} kVA en {fmtNum(x.kva, 0)} kVA ({fmtNum(x.carga_pct, 0)} %).
              Revise el cruce del cliente con su SED o el transformador.</li>))}</ul>
        </details>
      )}
      {inf.bancos && (
        <details>
          <summary>Bancos de condensadores instalados en el proyecto: {inf.bancos.length}</summary>
          {inf.bancos.length === 0 ? <small className="muted">El alimentador no tiene bancos en el proyecto.</small> : (
            <div className="table-wrap">
              <table className="table">
                <thead><tr><th>Banco</th><th>Barra</th><th className="num">kvar nominales</th>
                  <th className="num">kvar en el flujo</th><th className="num">Tensión (p.u.)</th><th>Estado</th></tr></thead>
                <tbody>{inf.bancos.map((b) => (
                  <tr key={`${b.barra ?? ''}-${b.banco}`}><td>{b.banco}</td><td>{b.barra ?? '—'}</td>
                    <td className="num">{b.q_nominal_kvar == null ? '—' : fmtNum(b.q_nominal_kvar, 0)}</td>
                    <td className="num">{b.q_flujo_kvar == null ? '—' : fmtNum(b.q_flujo_kvar, 0)}</td>
                    <td className="num">{b.u_pu == null ? '—' : fmtNum(b.u_pu, 3)}</td>
                    <td>{b.en_servicio ? 'en servicio' : 'fuera de servicio'}</td></tr>))}</tbody>
              </table>
            </div>
          )}
        </details>
      )}
      {consumoDistinto?.cargas && consumoDistinto.cargas.length > 0 && (
        <ConsumoDistintoLista cargas={consumoDistinto.cargas} />
      )}
      {(inf.remedios ?? []).length > 0 && (
        <details open={!inf.cuadrado}><summary>Remedios para converger: {inf.remedios!.length}</summary>
          <ul className="small">{inf.remedios!.map((r) => (
            <li key={r.remedio}><strong>{r.remedio}</strong>{r.cambios.length ? `: ${r.cambios.join('; ')}` : ''}</li>))}</ul>
          <small className="muted">{inf.ajustes_del_flujo_conservados
            ? `Se quedan en el flujo de «Sin proyecto» para que converja: ${Object.entries(inf.ajustes_del_flujo_conservados).map(([k, v]) => `${k}=${v}`).join(', ')}.`
            : 'Los ajustes del flujo de carga se devolvieron a su valor al terminar.'}</small>
        </details>
      )}
      {inf.relectura_cargas_nativas && (
        <details>
          <summary>Relectura nativa de cargas: {inf.relectura_cargas_nativas.status} · {inf.relectura_cargas_nativas.cantidad} SED</summary>
          <small className="muted">P/Q/FP, estado e i_scale releídos después del flujo. Población:{' '}
            {Object.entries(inf.relectura_cargas_nativas.poblacion).map(([k, v]) => `${k}=${v}`).join(' · ')}</small>
        </details>
      )}
      {inf.diagnostico && <Diagnostico d={inf.diagnostico} />}
      {(inf.omitidas ?? []).length > 0 && (
        <details className="alert alert-warn"><summary>SED de clientes que no están en el alimentador: {inf.omitidas!.length}</summary>
          <ul className="small">{inf.omitidas!.map((x) => <li key={x.sed}><strong>{x.sed}</strong>: {x.motivo}
            {x.clientes ? ` (clientes ${x.clientes})` : ''}</li>)}</ul></details>
      )}
      {(inf.desconectadas ?? []).length > 0 && (
        <details className="alert alert-warn"><summary>SED fuera de servicio por clientes desmarcados: {inf.desconectadas!.length}</summary>
          <ul className="small">{inf.desconectadas!.map((x) => <li key={x.sed}><strong>{x.sed}</strong>: clientes {x.clientes.join(', ')}</li>)}</ul>
        </details>
      )}
      {fallosEscritura.length > 0 && (
        <details className="alert alert-error"><summary>SED que DIgSILENT no dejó escribir: {fallosEscritura.length}</summary>
          <ul className="small">{fallosEscritura.map((x, i) => (
            <li key={`${x.sed ?? ''}-${i}`}><strong>{x.sed}</strong>: {x.error}</li>))}</ul></details>
      )}
      {filas.length > 0 || filtro ? <>
        <input className="search" type="search" placeholder="Filtrar SED…" value={filtro} onChange={(e) => setFiltro(e.target.value)} />
        <div className="table-wrap table-short">
          <table className="table">
            <thead><tr><th>SED</th><th>Demanda de</th><th className="num">kVA</th><th className="num">kW antes</th>
              <th className="num">kW {simular ? 'sin pérdidas' : 'después'}</th><th className="num">kVAR {simular ? 'sin pérdidas' : 'después'}</th>
              <th className="num">FP</th></tr></thead>
            <tbody>{filas.map((x) => (
              <tr key={x.sed}>
                <td className="strong">{x.sed}</td>
                <td className="small">{x.origen === 'cliente' ? `clientes ${x.clientes.join(', ')}`
                  : x.origen === 'escala' ? 'escalada (factor de escala)' : 'reparto por kVA'}</td>
                <td className="num" title={x.kva_de === 'entrada' ? 'De la entrada original: sin transformador en DIgSILENT' : undefined}>
                  {x.kva == null ? '—' : fmtNum(x.kva)}{x.kva_de === 'entrada' ? ' *' : ''}</td>
                <td className="num">{fmtNum(x.antes.kw, 1)}</td>
                <td className="num">{fmtNum(x.despues.kw, 1)}</td>
                <td className="num">{fmtNum(x.despues.kvar, 1)}</td>
                <td className="num" title={(x.derivaciones ?? []).map((d) => `${d.cliente}: ${d.metodo}`).join('; ') || undefined}>
                  {fmtNum(x.despues.fp, 4)}</td>
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

/** Spec 015, RF-50: la cabecera con lo que consumen las cargas en el flujo, frente a lo escrito. */
function BalanceFisico({ b }: { b: BalanceCabecera }) {
  const kw = (x: number | null) => (x == null ? 'sin resultado' : fmtNum(x, 1));
  const consumido = b.fijas_consumida_kw == null || b.escaladas_consumida_kw == null
    ? null : b.fijas_consumida_kw + b.escaladas_consumida_kw;
  return (
    <details open={Boolean(b.causa_probable)}>
      <summary>Balance físico de la cabecera: lo que consumen las cargas en el flujo</summary>
      <div className="table-wrap">
        <table className="table">
          <thead><tr><th /><th className="num">Escrito (kW)</th><th className="num">Consumido en el flujo (kW)</th></tr></thead>
          <tbody>
            <tr><td>SED fijas (clientes importantes)</td>
              <td className="num">{kw(b.fijas_escrita_kw)}</td><td className="num">{kw(b.fijas_consumida_kw)}</td></tr>
            <tr><td>SED escaladas</td>
              <td className="num">{kw(b.escaladas_escrita_kw)}</td><td className="num">{kw(b.escaladas_consumida_kw)}</td></tr>
            <tr><td>Suma de las cargas</td>
              <td className="num">{fmtNum(b.escrita_kw, 1)}</td><td className="num">{kw(consumido)}</td></tr>
            <tr><td>Pérdidas (cabecera menos lo consumido)</td>
              <td className="num">—</td><td className="num">{kw(b.perdidas_kw)}</td></tr>
            <tr><td><strong>Entra por la cabecera</strong></td>
              <td className="num">—</td><td className="num"><strong>{fmtNum(b.cabecera_kw, 1)}</strong></td></tr>
          </tbody>
        </table>
      </div>
      {b.causa_probable && <p className="alert alert-warn">Causa probable: {b.causa_probable}.</p>}
    </details>
  );
}

/** Spec 015, RF-49: las cargas que no consumen lo suyo, primero las fijas y las que más se apartan. */
function ConsumoDistintoLista({ cargas }: { cargas: ConsumoDistinto[] }) {
  const orden = [...cargas].sort((a, b) => (a.clase === b.clase ? 0 : a.clase === 'FIJA' ? -1 : 1));
  const fijas = cargas.filter((c) => c.clase === 'FIJA').length;
  return (
    <details className="alert alert-error" open={fijas > 0}>
      <summary>Cargas que no consumen lo escrito: {cargas.length} ({fijas} fijas)</summary>
      <div className="table-wrap table-short">
        <table className="table">
          <thead><tr><th>SED</th><th>Clase</th><th className="num">P escrita (kW)</th>
            <th className="num">P consumida (kW)</th><th className="num">Tensión (p.u.)</th></tr></thead>
          <tbody>{orden.map((c) => (
            <tr key={c.sed}><td>{c.sed}</td><td>{c.clase === 'FIJA' ? 'fija' : 'escalada'}</td>
              <td className="num">{fmtNum(c.p_escrita_kw, 1)}</td><td className="num">{fmtNum(c.p_consumida_kw, 1)}</td>
              <td className="num">{c.u_pu == null ? '—' : fmtNum(c.u_pu, 3)}</td></tr>
          ))}</tbody>
        </table>
      </div>
    </details>
  );
}
