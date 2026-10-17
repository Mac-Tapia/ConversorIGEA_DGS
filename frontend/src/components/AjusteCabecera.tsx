import { useEffect, useMemo, useState } from 'react';
import { api, fmtNum } from '../api';
import { useApp } from '../context';
import type {
  AjusteInforme, AjustePlan, AjusteResultado, BalanceCabecera, CentralTermica, ConsumoDistinto, Job,
  MaximaCabecera, MaximaConCentral, SedSobrecargada,
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
export function AjusteCabecera({ project, maxima, feeders, desconectados, centrales = {} }: {
  project: string; maxima: Job | undefined; feeders: string[]; desconectados: Set<string>;
  /** Spec 021: central térmica declarada en 2.2, por alimentador, con sus tres medidores. */
  centrales?: Record<string, CentralTermica>;
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
  // Spec 021, RF-33 y RF-34: con central, la máxima de demanda de cada alimentador, de las
  // curvas que ya leyó la máxima (memoria del servidor, sin volver a abrir los libros).
  const [conCentral, setConCentral] = useState<Record<string, MaximaConCentral | string>>({});
  const firmaCentrales = JSON.stringify(centrales);
  useEffect(() => {
    if (!maxima) { setConCentral({}); return; }
    let vivo = true;
    const pedidas = grupos.map((g, i) => ({ g, medidor: medidores[i] || g.filas[0].medidor }))
      .filter(({ g }) => centrales[g.alimentador])
      .map(({ g, medidor }) => api.demandaCentral(ws.id, maxima.id, g.alimentador, medidor, centrales[g.alimentador])
        .then((r): [string, MaximaConCentral | string] => [g.alimentador, r])
        .catch((e: Error): [string, MaximaConCentral | string] => [g.alimentador, e.message]));
    Promise.all(pedidas).then((xs) => { if (vivo) setConCentral(Object.fromEntries(xs)); });
    return () => { vivo = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ws.id, maxima?.id, firmaCentrales, medidores.join('|')]);
  const tol = Number(tolerancia.replace(',', '.')) / 100;
  const tolValida = Number.isFinite(tol) && tol >= 0.001 && tol <= 0.1;

  const ultimo = Object.values(jobs)
    .filter((j) => (j.kind === 'ajuste_simular' || j.kind === 'ajuste_aplicar'
      || j.kind === 'ajuste_transformadores') && j.result)
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
          })))}
          // 021:RF-17, RF-22: con varios alimentadores, una curva por cada uno, con el
          // medidor que el operador eligió como cabecera o, mientras no elija, el primero.
          series={grupos.map((g, i) => {
            const m = medidores[i] || g.filas[0].medidor;
            return { clave: g.alimentador || m, etiqueta: `${g.alimentador || '—'} · ${m}`, medidor: m };
          })} />
      )}
      {Object.entries(conCentral).map(([a, r]) => (
        <div key={a} className={`alert ${typeof r === 'string' || r.error ? 'alert-warn' : 'alert-info'} central-resumen`}>
          {typeof r === 'string' ? <><strong>{a}</strong>, central declarada: {r}</>
            : r.error ? <><strong>{a}</strong>, central declarada: {r.error}.</>
              : (
                <>
                  <strong>{a} con central</strong>: máxima de demanda <strong>{fmtNum(r.demanda_kw, 1)} kW</strong> el {r.fecha}
                  {' '}= aguas arriba {fmtNum(r.arriba_kw, 1)} kW + aguas abajo {fmtNum(r.abajo_kw, 1)} kW; la central
                  generaba {fmtNum(r.generacion_kw, 1)} kW y por la cabecera entraban {fmtNum(r.cabecera_kw, 1)} kW.
                  {r.maxima_cabecera && <> La máxima de cabecera, {fmtNum(r.maxima_cabecera.kw, 1)} kW el {r.maxima_cabecera.fecha}, no es la de la demanda.</>}
                  {r.descartados > 0 && <> {fmtNum(r.descartados)} registro(s) descartados: aguas arriba fuera de lo normal.</>}
                </>
              )}
        </div>
      ))}
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
            : <InformeAjuste key={`${inf.feeder}-${ultimo?.id}`} inf={inf}
              report={resultado?.reports?.[i] ?? resultado?.report ?? ''}
              cancelado={ultimo?.status === 'cancelled'} token={resultado?.token ?? plan?.token ?? null} />
      ))}
    </div>
  );
}

function InformeAjuste({ inf, report, cancelado, token }: {
  inf: AjusteInforme; report: string; cancelado: boolean; token: string | null;
}) {
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
      {(inf.fijas_sobre_su_transformador ?? []).length > 0 && (
        <SedSobrecargadas inf={inf} token={token} />
      )}
      {inf.transformadores_implementados && <TransformadoresImplementados inf={inf} />}
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
      {(inf.fijas_compensadas ?? []).length > 0 && (
        <details className="alert alert-warn" open>
          <summary>Clientes fijos compensados por su banco propio: {inf.fijas_compensadas!.length}</summary>
          <div className="table-wrap">
            <table className="table">
              <thead><tr><th>SED</th><th>Cliente</th><th className="num">P (kW)</th><th className="num">FP real (EA/ERI)</th>
                <th className="num">FP corregido</th><th className="num">Q real (kvar)</th><th className="num">Q modelada (kvar)</th></tr></thead>
              <tbody>{inf.fijas_compensadas!.map((c) => (
                <tr key={`${c.sed}-${c.cliente}`}><td>{c.sed}</td><td>{c.cliente}</td>
                  <td className="num">{fmtNum(c.p_kw, 1)}</td><td className="num">{fmtNum(c.fp_ea_eri, 3)}</td>
                  <td className="num">{fmtNum(c.fp_escrito, 3)}</td><td className="num">{fmtNum(c.q_ea_eri_kvar, 1)}</td>
                  <td className="num">{fmtNum(c.q_escrita_kvar, 1)}</td></tr>))}</tbody>
            </table>
          </div>
        </details>
      )}
      {inf.bancos && (
        <details>
          <summary>Bancos de condensadores instalados en el proyecto: {inf.bancos.length}
            {(inf.bancos_puestos_a_maxima ?? []).length > 0
              ? ` · ${inf.bancos_puestos_a_maxima!.length} puesto(s) a su máxima capacidad` : ''}</summary>
          <small className="muted">Trabajan a su máxima capacidad (todos los escalones, en servicio); lo que
            entregan es su potencia por el cuadrado de la tensión de su barra.</small>
          {inf.bancos.length === 0 ? <small className="muted">El alimentador no tiene bancos en el proyecto.</small> : (
            <div className="table-wrap">
              <table className="table">
                <thead><tr><th>Banco</th><th>Barra</th><th className="num">Escalones</th><th className="num">kvar nominales</th>
                  <th className="num">kvar en el flujo</th><th className="num">Tensión (p.u.)</th><th>Estado</th></tr></thead>
                <tbody>{inf.bancos.map((b) => (
                  <tr key={`${b.barra ?? ''}-${b.banco}`}><td>{b.banco}</td><td>{b.barra ?? '—'}</td>
                    <td className="num">{b.escalones ?? '—'}</td>
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

const instalada = (x: SedSobrecargada) => {
  const trs = x.transformadores ?? [];
  if (trs.length !== 1) return `${fmtNum(x.kva, 0)} kVA`;
  const t = trs[0];
  return `${t.unidades > 1 ? `${t.unidades} × ` : ''}${fmtNum(t.kva, 0)} kVA · ${t.tipo ?? '—'}`;
};

/**
 * Spec 020, RF-3 a RF-14: las SED fijas por encima del 100 % de su potencia instalada, al
 * principio del resultado, con la propuesta de transformadores nuevos por SED (todas
 * marcadas) y el botón que los implementa en «Sin proyecto» y vuelve a calibrar. En PA217
 * (2026-10-16) SE30940 pedía 3818 kVA sobre 400 kVA y solo se veía en un desplegable.
 */
function SedSobrecargadas({ inf, token }: { inf: AjusteInforme; token: string | null }) {
  const { ws, startJob, active } = useApp();
  const sobre = inf.fijas_sobre_su_transformador ?? [];
  const conPropuesta = sobre.filter((x) => x.propuesta?.kva != null);
  const [marcadas, setMarcadas] = useState<Set<string>>(() => new Set(conPropuesta.map((x) => x.sed)));
  const pfBusy = Boolean(active.powerfactory);
  const causa = inf.sobrecarga_causa_probable;
  const fichas = inf.fichas_transformador_sed;
  const alternar = (sed: string) => setMarcadas((m) => {
    const n = new Set(m);
    if (n.has(sed)) n.delete(sed); else n.add(sed);
    return n;
  });
  const implementar = () => {
    if (!token || !marcadas.size) return;
    void startJob(() => api.ajusteTransformadores(ws.id, token, inf.feeder, [...marcadas]));
  };
  const motivoBoton = !token ? 'Vuelva a simular: falta el plan del ajuste.'
    : !marcadas.size ? 'Marque al menos una SED.' : pfBusy ? 'DIgSILENT está ocupado con otro trabajo.' : '';
  return (
    <div className={causa ? 'alert alert-error' : 'alert alert-warn'}>
      <strong>{sobre.length} SED fija(s) sobrecargada(s): piden más que su potencia instalada.</strong>
      {causa
        ? <p>Es la causa probable de que la calibración no converja o no sea válida. Implemente los transformadores
          propuestos y se volverá a calibrar.</p>
        : <p>La calibración sigue igual; con estas SED el flujo puede no converger o las cargas no consumir lo escrito.</p>}
      <div className="table-wrap">
        <table className="table">
          <thead><tr><th /><th>SED</th><th>Clientes</th><th className="num">Demanda (kVA)</th><th>Instalada</th>
            <th className="num">Carga</th><th>Propuesta</th><th className="num">Po / Pc (W)</th>
            <th className="num">Io / uk (%)</th><th className="num">Carga prevista</th></tr></thead>
          <tbody>{sobre.map((x) => {
            const p = x.propuesta;
            const hay = p?.kva != null;
            return (
              <tr key={x.sed}>
                <td>{hay && <input type="checkbox" aria-label={`Implementar ${x.sed}`} checked={marcadas.has(x.sed)}
                  disabled={pfBusy} onChange={() => alternar(x.sed)} />}</td>
                <td><strong>{x.sed}</strong></td>
                <td>{x.clientes.join(', ') || 'cambio manual'}</td>
                <td className="num">{fmtNum(x.kva_carga, 0)}</td>
                <td>{instalada(x)}</td>
                <td className="num">{fmtNum(x.carga_pct, 0)} %</td>
                {hay
                  ? <><td>{(p!.unidades ?? 1) > 1 ? `${p!.unidades} × ` : ''}{fmtNum(p!.kva!, 0)} kVA
                      <br /><small className="muted">{p!.norma}</small></td>
                    <td className="num">{fmtNum(p!.po_w ?? 0, 0)} / {fmtNum(p!.pc_w ?? 0, 0)}</td>
                    <td className="num">{fmtNum(p!.io_pct ?? 0, 2)} / {fmtNum(p!.uk_pct ?? 0, 1)}</td>
                    <td className="num">{fmtNum(p!.carga_pct_prevista ?? 0, 0)} %</td></>
                  : <td colSpan={4}><small className="muted">Sin propuesta: {p?.motivo ?? 'sin datos'}.</small></td>}
              </tr>
            );
          })}</tbody>
        </table>
      </div>
      {fichas?.falta && <p className="small">Sin propuesta: {fichas.falta}.</p>}
      {(fichas?.avisos ?? []).map((a) => <p key={a} className="small">{a}</p>)}
      {conPropuesta.length > 0 && (
        <div className="row">
          <button className="btn btn-pf" disabled={Boolean(motivoBoton)} title={motivoBoton || undefined}
            onClick={implementar}>Implementar transformadores ({marcadas.size})</button>
          <small className="muted">Se cambian en «Sin proyecto», en la red y sin variación, con un tipo propio de la ficha
            {fichas?.umbral_carga_pct ? ` (máxima al ${fmtNum(fichas.umbral_carga_pct, 0)} % o menos)` : ''}; los tipos
            existentes no se tocan. Después se vuelve a calibrar.</small>
        </div>
      )}
    </div>
  );
}

/** Spec 020, RF-24, RF-26, RF-32: lo que se cambió y si la recalibración salió válida. */
function TransformadoresImplementados({ inf }: { inf: AjusteInforme }) {
  const t = inf.transformadores_implementados!;
  const r = inf.resultado_transformadores;
  const ok = r?.status === 'VALIDO';
  return (
    <div className={!r ? 'alert alert-warn' : ok ? 'alert alert-ok' : 'alert alert-error'}>
      <strong>Transformadores nuevos en «Sin proyecto»: {t.cambios.length}</strong>
      {r && <p>{ok ? 'La calibración salió válida con ellos.'
        : `Se quedan, pero no salió: ${r.motivos.join('; ')}.`}</p>}
      {!r && t.cambios.length > 0 && <p>Quedan en la red; falta calibrar.</p>}
      {t.cambios.length > 0 && (
        <ul className="small">{t.cambios.map((c) => (
          <li key={c.sed}><strong>{c.sed}</strong> ({c.transformador}): {c.antes.unidades} × {fmtNum(c.antes.kva, 0)} kVA
            ({c.antes.tipo ?? '—'}) → {c.despues.unidades} × {fmtNum(c.despues.kva, 0)} kVA ({c.despues.tipo})</li>
        ))}</ul>
      )}
      {t.omitidas.length > 0 && (
        <ul className="small">{t.omitidas.map((o) => <li key={o.sed}>{o.sed}: no cambiado, {o.motivo}.</li>)}</ul>
      )}
    </div>
  );
}
