import { useMemo, useRef, useState, type ReactNode } from 'react';
import { api, fmtNum } from '../api';
import { useApp } from '../context';
import type { FeederAcceptance, FeederRow } from '../types';
import { Pill, Stat, useConfirm } from './ui';

type SortKey = 'feeder' | 'network_id' | 'nominal_kv' | 'sections' | 'loads' | 'switches' | 'status';

function assignmentText(value?: FeederAcceptance | null): string | null {
  if (!value) return null;
  return `Alimentador: asignado ${value.loads.assigned}/${value.loads.expected} cargas, `
    + `${value.sources.assigned}/${value.sources.expected} fuentes`;
}

function statusOf(r: FeederRow): { rank: number; node: ReactNode } {
  const c = r.conversion;
  if (c?.status === 'ok') {
    const extra = c.errors_total ? ` · ${c.errors_total} err.` : '';
    return { rank: 3, node: <Pill tone={c.errors_total ? 'warn' : 'ok'} title={c.dgs ?? ''}>DGS listo{extra}</Pill> };
  }
  if (c?.status === 'failed') return { rank: 1, node: <Pill tone="error" title={c.error ?? ''}>Falló</Pill> };
  if (c?.status === 'skipped') return { rank: 0, node: <Pill tone="muted" title={c.error ?? ''}>Omitido</Pill> };
  if (!r.convertible) return { rank: 0, node: <Pill tone="muted">Stub (0 tramos)</Pill> };
  return { rank: 2, node: <Pill tone="info">Convertible</Pill> };
}

function GroupsList() {
  const { ws, run, startJob, active } = useApp();
  const confirm = useConfirm();
  const grupos = ws.groups ?? [];
  if (!grupos.length) return null;
  return (
    <div className="table-wrap table-short" style={{ marginBottom: 10 }}>
      <table className="table">
        <thead><tr><th>DGS unido</th><th>Alimentadores</th><th>Estado</th><th>Hoja</th><th /></tr></thead>
        <tbody>
          {grupos.map((g) => (
            <tr key={g.name}>
              <td className="strong">{g.name}.dgs</td>
              <td className="small">{g.feeders.join(', ')}</td>
              <td>{g.status === 'ok'
                ? <Pill tone={g.completitud?.fallos?.length ? 'warn' : 'ok'}>completo</Pill>
                : <Pill tone="error" title={g.error ?? ''}>falló</Pill>}
                {assignmentText(g.feeder_acceptance) && (
                  <div className="small muted">{assignmentText(g.feeder_acceptance)}</div>
                )}
              </td>
              <td className="small">{g.hoja ? `${g.hoja.formato} ${g.hoja.orientacion} 1:${g.hoja.escala_1_a.toLocaleString('es-PE')}` : '—'}</td>
              <td className="row-actions">
                {g.dgs && <a className="link" href={api.fileUrl(ws.id, `${g.name}.dgs`, true)}>Descargar</a>}
                {g.name_feeder_mapping && (
                  <a className="link" href={api.fileUrl(ws.id, `${g.name}_name_alimentador.csv`, true)}>
                    Name → Alimentador
                  </a>
                )}
                {g.dgs && (
                  <button className="link" disabled={Boolean(active.powerfactory)} onClick={async () => {
                    if (await confirm('DigSILENT PowerFactory', <p>Se importará <b>{g.name}.dgs</b> en PowerFactory y se correrá el flujo.</p>)) {
                      await run(() => startJob(() => api.powerfactoryFlow(ws.id, [g.name])));
                    }
                  }}>Cargar en DigSILENT</button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function FeedersPanel() {
  const { ws, feeders, selected, setSelected, active, startJob, run } = useApp();
  const confirm = useConfirm();
  const [filter, setFilter] = useState('');
  const [sort, setSort] = useState<{ key: SortKey; dir: 1 | -1 }>({ key: 'feeder', dir: 1 });
  const anchor = useRef<string | null>(null);
  const engineBusy = Boolean(active.engine);
  const pfBusy = Boolean(active.powerfactory);

  const rows = useMemo(() => {
    const f = filter.trim().toLowerCase();
    const list = f
      ? feeders.filter((r) => r.feeder.toLowerCase().includes(f) || r.network_id.toLowerCase().includes(f))
      : feeders.slice();
    const val = (r: FeederRow): string | number => {
      switch (sort.key) {
        case 'status': return statusOf(r).rank;
        case 'nominal_kv': return Number(r.nominal_kv) || 0;
        default: return r[sort.key] as string | number;
      }
    };
    list.sort((a, b) => {
      const x = val(a), y = val(b);
      return (typeof x === 'number' && typeof y === 'number' ? x - y : String(x).localeCompare(String(y), 'es', { numeric: true })) * sort.dir;
    });
    return list;
  }, [feeders, filter, sort]);

  const sel = new Set(selected);
  const visibleNames = rows.map((r) => r.feeder);
  const allVisibleSelected = visibleNames.length > 0 && visibleNames.every((n) => sel.has(n));

  const toggle = (name: string, shift: boolean) => {
    const next = new Set(sel);
    if (shift && anchor.current && visibleNames.includes(anchor.current)) {
      const [a, b] = [visibleNames.indexOf(anchor.current), visibleNames.indexOf(name)].sort((p, q) => p - q);
      const on = !sel.has(name);
      for (const n of visibleNames.slice(a, b + 1)) (on ? next.add(n) : next.delete(n));
    } else {
      next.has(name) ? next.delete(name) : next.add(name);
      anchor.current = name;
    }
    setSelected(feeders.map((r) => r.feeder).filter((n) => next.has(n)));
  };

  const header = (key: SortKey, label: string, num = false) => (
    <th className={num ? 'num' : ''} aria-sort={sort.key === key ? (sort.dir === 1 ? 'ascending' : 'descending') : 'none'}>
      <button className="th-btn" onClick={() => setSort((s) => ({ key, dir: s.key === key ? (s.dir === 1 ? -1 : 1) : 1 }))}>
        {label}{sort.key === key ? (sort.dir === 1 ? ' ▲' : ' ▼') : ''}
      </button>
    </th>
  );

  const load = () => startJob(() => api.load(ws.id));

  const convert = async (names: string[], all: boolean) => {
    if (all) {
      const ok = await confirm('Convertir TODOS',
        <p>Se convertirán los <b>{feeders.length}</b> alimentadores cargados. Puede cancelar en cualquier
          momento: no se empieza ninguno más, lo que esté en marcha termina y todo lo convertido
          se conserva. Ningún DGS queda a medias.</p>,
        `Convertir ${feeders.length}`);
      if (!ok) return;
    }
    await startJob(() => api.convert(ws.id, names, all));
  };

  const unir = async () => {
    if (selected.length < 2) return;
    const sugerido = selected.slice(0, 4).join('_') + (selected.length > 4 ? '_ETC' : '');
    const nombre = window.prompt(
      `Unir ${selected.length} alimentadores en UN solo DGS.\n\nCada uno conserva su tensión y su fuente; `
      + 'los nodos compartidos quedan unidos por un interruptor abierto.\n\nNombre del DGS:', sugerido);
    if (nombre === null) return;
    await startJob(() => api.convertGroup(ws.id, selected, nombre.trim() || sugerido));
  };

  const pfFlow = async () => {
    const withDgs = selected.filter((n) => feeders.find((r) => r.feeder === n)?.conversion?.status === 'ok');
    const ok = await confirm('DigSILENT PowerFactory', <>
      <p>Se importarán <b>{withDgs.length}</b> DGS en PowerFactory: se activará el proyecto, se creará o activará
        un escenario de operación, se ejecutará el flujo de potencia (ComLdf, con correcciones si no converge) y la
        suite de estudios (corto circuito ComShc si la licencia lo permite).</p>
      {withDgs.length < selected.length && (
        <p className="alert alert-warn">{selected.length - withDgs.length} seleccionado(s) aún no tienen DGS y se omitirán.</p>
      )}
      <p className="muted">Requisito: PowerFactory instalado y, preferiblemente, abierto en el servidor.</p>
    </>);
    if (ok) await startJob(() => api.powerfactoryFlow(ws.id, selected));
  };

  const t = ws.totals;
  const cat = ws.catalog_report;
  const converted = feeders.filter((r) => r.conversion?.status === 'ok').length;

  return (
    <section className="card card-grow">
      <header className="card-head">
        <h2><span className="step">2</span> Alimentadores</h2>
        <button className="btn btn-primary" disabled={engineBusy || ws.missing_inputs.length > 0} onClick={load}>
          {ws.loaded ? 'Volver a cargar' : 'Cargar / listar alimentadores'}
        </button>
      </header>

      {!ws.loaded && (
        <p className="empty">
          {ws.missing_inputs.length
            ? 'Complete la entrada de datos y pulse «Cargar / listar alimentadores».'
            : 'Entrada lista. Pulse «Cargar / listar alimentadores» para analizar los ficheros.'}
        </p>
      )}

      {ws.loaded && t && (
        <>
          <div className="stats">
            <Stat label="alimentadores" value={fmtNum(t.feeders)} />
            <Stat label="convertibles" value={fmtNum(t.convertible_feeders)} />
            <Stat label="stubs sin tramos" value={fmtNum(t.stub_feeders)} tone={t.stub_feeders ? 'warn' : undefined} />
            <Stat label="tramos" value={fmtNum(t.sections)} />
            <Stat label="cargas" value={fmtNum(t.customer_loads)} />
            <Stat label="DGS convertidos" value={`${converted} / ${fmtNum(ws.conversion?.expected_dgs_files ?? 0)}`} tone={converted ? 'ok' : undefined} />
            {ws.integrity && (
              <Stat label="integridad" value={`${ws.integrity.errors} err · ${ws.integrity.warnings} av`}
                tone={ws.integrity.errors ? 'error' : ws.integrity.warnings ? 'warn' : 'ok'} />
            )}
          </div>

          {cat && cat.final_coverage < 1 && (
            <div className={`alert ${cat.critical ? 'alert-error' : 'alert-warn'}`}>
              <strong>
                {cat.critical ? 'El catálogo no cubre esta red: ' : 'Catálogo incompleto: '}
                {Math.round(cat.final_coverage * 100)} % de los {cat.types_in_network} tipos de línea.
              </strong>
              <p>
                El resto tomará la impedancia de DEFAULT: el modelo convertirá y convergerá igual, pero las pérdidas y
                caídas de tensión no significarán nada, y nada en el resultado lo delatará. Indique en «EQUIPOS
                complementario» el catálogo de otra entrega.
              </p>
              {cat.unresolved.length > 0 && (
                <p className="muted small">Sin catálogo: {cat.unresolved.slice(0, 12).join(', ')}{cat.unresolved.length > 12 ? '…' : ''}</p>
              )}
            </div>
          )}
          {ws.catalog_applied && (
            <p className="alert alert-info">Catálogo corregido activo (<b>{ws.catalog_file}</b>): toda conversión lo aplica.</p>
          )}

          <div className="toolbar">
            <input className="search" type="search" placeholder="Filtrar por nombre o NetworkID…" value={filter}
              onChange={(e) => setFilter(e.target.value)} aria-label="Filtrar alimentadores" />
            <span className="muted">{selected.length} seleccionado(s) de {feeders.length}</span>
            {selected.length > 0 && <button className="link" onClick={() => setSelected([])}>Limpiar selección</button>}
          </div>

          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th className="check">
                    <input type="checkbox" aria-label="Seleccionar visibles" checked={allVisibleSelected}
                      onChange={() => {
                        const next = new Set(sel);
                        visibleNames.forEach((n) => (allVisibleSelected ? next.delete(n) : next.add(n)));
                        setSelected(feeders.map((r) => r.feeder).filter((n) => next.has(n)));
                      }} />
                  </th>
                  {header('feeder', 'Alimentador')}
                  {header('network_id', 'NetworkID')}
                  {header('nominal_kv', 'kV', true)}
                  {header('sections', 'Tramos', true)}
                  {header('loads', 'Cargas', true)}
                  {header('switches', 'SW', true)}
                  {header('status', 'Estado')}
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.network_id} className={sel.has(r.feeder) ? 'selected' : ''}
                    onClick={(e) => toggle(r.feeder, e.shiftKey)}>
                    <td className="check" onClick={(e) => e.stopPropagation()}>
                      <input type="checkbox" checked={sel.has(r.feeder)} aria-label={`Seleccionar ${r.feeder}`}
                        onChange={(e) => toggle(r.feeder, (e.nativeEvent as MouseEvent).shiftKey)} />
                    </td>
                    <td className="strong">{r.feeder}</td>
                    <td className="mono muted">{r.network_id}</td>
                    <td className="num">{r.nominal_kv}</td>
                    <td className="num">{fmtNum(r.sections)}</td>
                    <td className="num">{fmtNum(r.loads)}</td>
                    <td className="num">{fmtNum(r.switches)}</td>
                    <td>{statusOf(r).node}
                      {assignmentText(r.conversion?.feeder_acceptance) && (
                        <div className="small muted">{assignmentText(r.conversion?.feeder_acceptance)}</div>
                      )}
                    </td>
                  </tr>
                ))}
                {rows.length === 0 && <tr><td colSpan={8} className="empty">Ningún alimentador coincide con el filtro.</td></tr>}
              </tbody>
            </table>
          </div>

          <p className="alert alert-info small">
            Reglas del proyecto en cada conversión: {ws.options.hoja === 'AUTO' ? 'lienzo adaptativo a escala real' : `hoja ${ws.options.hoja}`} ·
            coordenadas que falten completadas por el grafo · puentes DEFAULT fundidos (sus
            seccionadores quedan como interruptor) · trafomix (SED «M…») excluidos · SED con más carga que
            kVA redimensionadas y listadas · catálogo del proyecto · auditoría de completitud contra la entrada.
          </p>
          <GroupsList />
          <div className="actions">
            <button className="btn btn-primary" disabled={engineBusy || selected.length === 0}
              onClick={() => convert(selected, false)}>
              {selected.length === 1 ? `Convertir ${selected[0]} → DGS` : `Convertir ${selected.length || ''} seleccionados → DGS`}
            </button>
            <button className="btn" disabled={engineBusy || feeders.length === 0} onClick={() => convert([], true)}>
              Convertir TODOS ({feeders.length})
            </button>
            <button className="btn" disabled={engineBusy || selected.length < 2} onClick={unir}
              title="Los alimentadores seleccionados en un solo DGS (red unida)">
              Unir {selected.length >= 2 ? selected.length : ''} en un solo DGS…
            </button>
            <a className={`btn ${converted ? '' : 'btn-disabled'}`}
              href={converted ? api.zipUrl(ws.id, selected.length ? selected : []) : undefined}
              aria-disabled={!converted}>
              Descargar {selected.length ? 'selección' : 'todo'} (.zip)
            </a>
            <span className="spacer" />
            <button className="btn btn-pf" disabled={pfBusy || selected.length === 0} onClick={() => run(pfFlow)}
              title="Import del DGS + escenario + flujo de potencia + estudios">
              Cargar en DigSILENT + flujo
            </button>
          </div>
        </>
      )}
    </section>
  );
}
