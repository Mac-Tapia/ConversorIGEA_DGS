import { useMemo, useState } from 'react';
import type { ClienteEvolucion, EvolucionResultado, TotalEvolucion } from '../../api/evolucionFijas';
import { fmtNum } from '../../shared/formato';
import { CurvaCliente, GraficoMensual } from './Graficos';
import {
  MAGNITUDES, avisosPorTipo, buscarClientes, claseVariacion, fmtInstante, fmtPct, nombreMes, seriesMensuales,
  tablaVariaciones,
} from './datosTablero';

const VEREDICTO = { confirmado: 'confirmado', discrepa: 'discrepa', una_fuente: 'una sola fuente' } as const;

type Resumen = ClienteEvolucion['resumen'];

function Indicadores({ r }: { r: Resumen }) {
  const crec = r.crecimiento.p_max;
  return (
    <dl className="tarjeta-datos">
      <dt>P máx del periodo</dt><dd><b>{fmtNum(r.p_max, 1)} kW</b> · {fmtInstante(r.fecha_p_max)}</dd>
      <dt>Crecimiento de la P máx</dt>
      <dd className={claseVariacion(crec?.pct)}>{fmtPct(crec?.pct)}{crec?.pct != null && ` (${nombreMes(crec.desde)} → ${nombreMes(crec.hasta)})`}</dd>
      <dt>Tendencia</dt><dd className={claseVariacion(r.tendencia.p_max)}>{fmtPct(r.tendencia.p_max)} por mes</dd>
      <dt>Mayor P máx · Q máx</dt><dd>{nombreMes(r.mes_mayor.p_max)} · {nombreMes(r.mes_mayor.q_max)}</dd>
      <dt>Mayor energía activa · reactiva</dt><dd>{nombreMes(r.mes_mayor.energia_p)} · {nombreMes(r.mes_mayor.energia_q)}</dd>
    </dl>
  );
}

function TarjetaTotal({ t }: { t: TotalEvolucion }) {
  const coinc = t.meses.reduce<{ v: number; f?: string | null } | null>(
    (m, d) => (d.p_max_coincidente != null && !d.copia_de && (!m || d.p_max_coincidente > m.v)
      ? { v: d.p_max_coincidente, f: d.fecha_coincidente } : m), null);
  return (
    <article className="tarjeta tarjeta-total">
      <h5>Total {t.alimentador} <small className="muted">· {t.clientes} cliente(s) fijo(s)</small></h5>
      <Indicadores r={t.resumen} />
      <p className="small muted">P máx del periodo: la de la suma de los fijos en un mismo instante
        ({fmtNum(coinc?.v, 1)} kW, crece {fmtPct(t.resumen.crecimiento.p_max_coincidente?.pct)}). Crecimiento, tendencia y
        meses: sobre la suma de las máximas de cada cliente, como el libro.</p>
    </article>
  );
}

/** El tablero de la evolución (105:RF-22 a RF-26): tarjetas, gráficos, variaciones, curva y avisos. */
export function Tablero({ r, wsId, enlace }: { r: EvolucionResultado; wsId: string; enlace?: string }) {
  const [cliente, setCliente] = useState(r.clientes[0]?.codigo ?? '');
  const [magVar, setMagVar] = useState<'p_max' | 'energia_p'>('p_max');
  const avisos = avisosPorTipo(r.avisos);
  const variaciones = tablaVariaciones(r, magVar);
  const cabecera = r.totales.filter((t) => t.cabecera?.length);
  const [consulta, setConsulta] = useState('');
  const encontrados = useMemo(() => buscarClientes(r.clientes, consulta), [r.clientes, consulta]);
  const conciliacion = r.conciliacion;
  return (
    <div className="tablero-fijas">
      <p className="muted small">
        {r.alimentadores.join(', ')} · {nombreMes(r.desde)} a {nombreMes(r.hasta)} · {r.clientes.length} cliente(s) fijo(s)
        según {r.suministros} · {r.libros.length} libro(s) de clientes
        {r.renumeraciones.length > 0 && <> · renumerados: {r.renumeraciones.map((x) => `${x.anterior} → ${x.actual}`).join('; ')}</>}
      </p>
      <div className="row">
        {enlace && <a className="btn btn-primary" href={enlace} download>Descargar el libro Excel</a>}
        {r.archivo.ruta && <small className="muted">Archivado en {r.archivo.ruta}</small>}
        {r.archivo.aviso && <small className="alert alert-warn">{r.archivo.aviso}</small>}
      </div>

      {avisos.length > 0 && (
        <section aria-label="Avisos de calidad">
          {avisos.map((g) => (
            <details key={g.tipo} className={`alert ${['copia', 'incompleto', 'sin_medicion', 'contradiccion', 'discrepancia', 'fijos_sobre_cabecera'].includes(g.tipo) ? 'alert-warn' : 'alert-info'}`}
              open={['copia', 'discrepancia', 'fijos_sobre_cabecera'].includes(g.tipo)}>
              <summary><b>{g.titulo}</b> ({g.textos.length})</summary>
              <ul>{g.textos.map((t) => <li key={t}>{t}</li>)}</ul>
            </details>
          ))}
        </section>
      )}

      <h4>Clientes fijos</h4>
      {conciliacion && (
        <p className="small">Conciliación de fuentes (suministros, resumen de los libros{r.red ? ' y red convertida' : ''}):
          {' '}<span className="pill-ok">{conciliacion.confirmado} confirmado(s)</span>
          {' '}<span className={conciliacion.discrepa ? 'pill-warn' : 'muted'}>{conciliacion.discrepa} con discrepancias</span>
          {' '}<span className="muted">{conciliacion.una_fuente} en una sola fuente</span>
          {!r.red && <small className="muted"> · sin red cargada, la SED no se comprueba en la red</small>}</p>
      )}
      <label className="row">
        <span>Buscar cliente</span>
        <input className="search" type="search" value={consulta} placeholder="NIS, código CL, nombre, SED o alimentador"
          aria-label="Buscar cliente" onChange={(e) => setConsulta(e.target.value)} />
      </label>
      {consulta.trim() && (
        <ol className="resultados-busqueda" aria-label="Resultados de la búsqueda">
          {encontrados.length === 0 && <li className="muted">Ningún cliente con ese NIS, CL, nombre, SED o alimentador.</li>}
          {encontrados.map((e) => {
            const c = r.clientes.find((x) => x.codigo === e.codigo)!;
            return (
              <li key={e.codigo}>
                <button type="button" className="link" onClick={() => setCliente(e.codigo)}>{e.codigo}</button>
                {' '}{c.nombre && <>· {c.nombre} </>}· {c.sed} · {c.alimentador}
                {' '}<small className="muted">({e.campo}: {e.valor} · puntaje {e.puntaje})</small>
              </li>
            );
          })}
        </ol>
      )}
      <div className="tarjetas">
        {r.totales.map((t) => <TarjetaTotal key={t.alimentador} t={t} />)}
        {r.clientes.map((c) => (
          <article key={c.codigo} className={`tarjeta ${c.codigo === cliente ? 'on' : ''}`}>
            <h5><button type="button" className="link" onClick={() => setCliente(c.codigo)}
              title="Ver su curva de 15 minutos">{c.codigo}</button>
              {' '}<small className="muted">· {c.sed} · {c.alimentador}{c.anteriores.length ? ` · antes ${c.anteriores.join(', ')}` : ''}</small></h5>
            {(c.nombre || c.cl) && <p className="small muted">{c.nombre}{c.cl ? ` · ${c.cl}` : ''}{c.suministrador ? ` · ${c.suministrador}` : ''}</p>}
            {c.veredicto && (
              <p className={`small veredicto veredicto-${c.veredicto.estado}`} title={c.veredicto.texto}>
                {VEREDICTO[c.veredicto.estado]}{c.veredicto.estado === 'confirmado' ? ` en ${c.veredicto.fuentes} fuentes` : ''}
                {c.veredicto.estado !== 'confirmado' && `: ${c.veredicto.texto}`}</p>
            )}
            <Indicadores r={c.resumen} />
          </article>
        ))}
      </div>

      <h4>Evolución mensual</h4>
      {MAGNITUDES.map((m) => {
        const s = seriesMensuales(r, m.clave);
        return <GraficoMensual key={m.clave} titulo={m.titulo} unidad={m.unidad} meses={s.meses} series={s.series} />;
      })}

      <h4>Variación mes a mes</h4>
      <label className="row">
        <span>Magnitud</span>
        <select value={magVar} onChange={(e) => setMagVar(e.target.value as 'p_max' | 'energia_p')}>
          <option value="p_max">P máxima</option>
          <option value="energia_p">Energía activa</option>
        </select>
      </label>
      <div className="table-wrap table-short">
        <table className="table tabla-variaciones">
          <thead><tr><th>Cliente</th>{variaciones.meses.map((m) => <th key={m}>{nombreMes(m)}</th>)}</tr></thead>
          <tbody>{variaciones.filas.map((f) => (
            <tr key={f.clave} className={f.total ? 'strong' : ''}>
              <td>{f.etiqueta}</td>
              {f.celdas.map((v, i) => <td key={variaciones.meses[i]} className={claseVariacion(v)}>{fmtPct(v)}</td>)}
            </tr>
          ))}</tbody>
        </table>
      </div>
      {r.copias.length > 0 && <small className="muted">Sin {r.copias.map((c) => nombreMes(c.mes)).join(', ')}: copia del mes anterior.</small>}

      {cabecera.length > 0 && (
        <>
          <h4>Participación en la máxima de cabecera</h4>
          <div className="table-wrap table-short">
            <table className="table">
              <thead><tr><th>Alimentador</th><th>Mes</th><th>Máxima de cabecera (kW)</th><th>Instante</th>
                <th>Fijos en ese instante (kW)</th><th>Participación</th></tr></thead>
              <tbody>{cabecera.flatMap((t) => (t.cabecera ?? []).map((c) => (
                <tr key={`${t.alimentador}${c.mes}`}>
                  <td>{t.alimentador}</td><td>{nombreMes(c.mes)}</td><td>{fmtNum(c.p_max, 1)}</td><td>{fmtInstante(c.fecha)}</td>
                  <td>{c.copia_de ? `— (copia de ${nombreMes(c.copia_de)})` : fmtNum(c.fijas_kw, 1)}</td>
                  <td>{c.participacion == null ? '—' : `${fmtNum(c.participacion, 1)} %`}</td>
                </tr>
              )))}</tbody>
            </table>
          </div>
        </>
      )}

      <h4>Curva de 15 minutos</h4>
      <label className="row">
        <span>Cliente</span>
        <select value={cliente} onChange={(e) => setCliente(e.target.value)}>
          {r.clientes.map((c) => <option key={c.codigo} value={c.codigo}>{c.codigo} · {c.sed} · {c.alimentador}</option>)}
        </select>
      </label>
      {cliente && <CurvaCliente wsId={wsId} cliente={cliente} />}
    </div>
  );
}
