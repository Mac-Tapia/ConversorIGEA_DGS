import { useMemo, useState } from 'react';
import { api, fmtBytes, fmtNum } from '../api';
import { useApp } from '../context';
import { FileDrop, Pill, useConfirm, useToast } from './ui';

// ------------------------------------------------------------------ utilidades

export function PfWarning() {
  const { pf } = useApp();
  if (!pf || pf.available) return null;
  return (
    <p className="alert alert-warn">
      PowerFactory no está disponible en el servidor ({pf.interpreter_reason}
      {pf.api_version ? `; la API pide Python ${pf.api_version}` : ''}). Puede preparar el plan, pero no aplicarlo.
    </p>
  );
}

// ------------------------------------------------------------------ resultados

export function ResultsTab() {
  const { ws, outputs, selected, feeders } = useApp();
  const [preview, setPreview] = useState<string | null>(null);
  const [filter, setFilter] = useState('');

  const files = useMemo(() => {
    const f = filter.trim().toLowerCase();
    const names = selected.length ? selected : null;
    return outputs.filter((o) => {
      if (f && !o.path.toLowerCase().includes(f)) return false;
      if (!names) return true;
      return names.some((n) => o.path === `${n}.dgs` || o.path.startsWith(`${n}_`) || o.path.startsWith(`${n}/`));
    });
  }, [outputs, selected, filter]);

  // Mapas de los alimentadores sueltos y de las redes unidas: las dos salidas traen el suyo.
  const previews = [
    ...feeders
      .filter((r) => r.conversion?.preview_html && (!selected.length || selected.includes(r.feeder)))
      .map((r) => ({ name: r.feeder, html: r.conversion!.preview_html! })),
    ...(ws.groups ?? [])
      .filter((g) => g.preview_html && (!selected.length || g.feeders.some((f) => selected.includes(f))))
      .map((g) => ({ name: g.name, html: g.preview_html! })),
  ];

  return (
    <div className="module">
      <div className="toolbar">
        <input className="search" type="search" placeholder="Filtrar ficheros…" value={filter} onChange={(e) => setFilter(e.target.value)} />
        <span className="muted">{files.length} fichero(s){selected.length ? ' de la selección' : ''}</span>
        <span className="spacer" />
        {files.length > 0 && <a className="btn btn-sm" href={api.zipUrl(ws.id, selected)}>Descargar .zip</a>}
      </div>
      {previews.length > 0 && (
        <div className="chips">
          <span className="muted">Mapas:</span>
          {previews.map((p) => (
            <button key={p.html} className={`chip ${preview === p.html ? 'on' : ''}`}
              onClick={() => setPreview(preview === p.html ? null : p.html)}>
              {p.name}
            </button>
          ))}
        </div>
      )}
      {preview && (
        <iframe className="map-frame" title="Vista previa del alimentador" src={api.fileUrl(ws.id, preview)}
          sandbox="allow-scripts allow-same-origin allow-popups" />
      )}
      {files.length === 0 ? (
        <p className="empty">Todavía no hay salida{selected.length ? ' para la selección' : ''}. Convierta algún alimentador.</p>
      ) : (
        <div className="table-wrap table-short">
          <table className="table">
            <thead><tr><th>Fichero</th><th className="num">Tamaño</th><th>Modificado</th><th /></tr></thead>
            <tbody>
              {files.map((f) => (
                <tr key={f.path}>
                  <td className="mono">{f.path}</td>
                  <td className="num">{fmtBytes(f.size)}</td>
                  <td className="muted">{new Date(f.modified * 1000).toLocaleString('es-PE')}</td>
                  <td className="row-actions">
                    {/\.(html|txt|json)$/i.test(f.path) && (
                      <a className="link" href={api.fileUrl(ws.id, f.path)} target="_blank" rel="noreferrer">Abrir</a>
                    )}
                    <a className="link" href={api.fileUrl(ws.id, f.path, true)}>Descargar</a>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

// ------------------------------------------------------------------ catálogo

export function CatalogTab() {
  const { ws, setWs, selected, run, startJob, active, jobs, outputs } = useApp();
  const confirm = useConfirm();
  const toast = useToast();
  const [applied, setApplied] = useState<{ count: number; changes: { line: string; variation_pct: number | null }[]; preview_feeder: string | null } | null>(null);

  const lastBuild = Object.values(jobs).filter((j) => j.kind === 'catalog' && j.status === 'done').pop();
  const hasFile = outputs.some((o) => o.path === 'catalogo_parametros.xlsx');
  const findings = (lastBuild?.result?.findings ?? []) as {
    severity: string; element: string; code: string; attribute: string; model: number | string;
    reference: number | string; unit: string; deviation_pct: number | null; km: number; message: string;
  }[];

  return (
    <div className="module">
      <p className="muted">Compara los parámetros eléctricos del modelo con las fichas de fabricante. El catálogo corregido
        que suba aquí se aplica a <b>todas las conversiones siguientes</b>; el TXT de origen no se toca.</p>
      <div className="steps">
        <div className="step-box">
          <h3>1 · Generar catálogo y auditar</h3>
          <button className="btn" disabled={!ws.loaded || Boolean(active.engine)}
            onClick={() => startJob(() => api.catalogBuild(ws.id, selected))}>
            Auditar {selected.length ? `${selected.length} seleccionado(s)` : 'todos'}
          </button>
          {hasFile && (
            <a className="link" href={api.fileUrl(ws.id, 'catalogo_parametros.xlsx', true)}>Descargar catalogo_parametros.xlsx</a>
          )}
        </div>
        <div className="step-box">
          <h3>2 · Subir catálogo corregido</h3>
          <FileDrop compact accept=".xlsx" onFiles={async ([f]) => {
            const r = await run(() => api.catalogApply(ws.id, f, selected.length === 1 ? selected[0] : undefined));
            if (!r) return;
            setWs(r.workspace);
            setApplied(r);
            toast('ok', 'Catálogo aplicado', `${r.count} código(s). Reconvierta para llevarlo al DGS.`);
          }}><span>Soltar .xlsx o <u>elegir</u></span></FileDrop>
          <small className="muted">Solo cuentan las filas con estado «ficha» o «derivado».</small>
        </div>
        {ws.catalog_applied && (
          <div className="step-box">
            <h3>Catálogo activo</h3>
            <p><Pill tone="info">{ws.catalog_file}</Pill></p>
            <button className="btn btn-ghost" onClick={async () => {
              if (!(await confirm('Quitar catálogo corregido', <p>Las próximas conversiones volverán a usar los valores del export.</p>, 'Quitar', true))) return;
              const r = await run(() => api.catalogClear(ws.id));
              if (r) { setWs(r); setApplied(null); }
            }}>Quitar</button>
          </div>
        )}
      </div>

      {applied && applied.changes.length > 0 && (
        <div className="alert alert-info">
          <strong>Efecto sobre {applied.preview_feeder}: {applied.changes.length} característica(s)</strong>
          <ul>{applied.changes.slice(0, 15).map((c) => (
            <li key={c.line} className={c.variation_pct != null && Math.abs(c.variation_pct) >= 25 ? 'strong' : ''}>{c.line}</li>
          ))}</ul>
          {applied.changes.some((c) => c.variation_pct != null && Math.abs(c.variation_pct) >= 25) && (
            <p>Hay cambios de más del 25 %: las pérdidas y la caída de tensión de esos tramos cambian en la misma proporción.</p>
          )}
        </div>
      )}

      {lastBuild && (
        <>
          <p className="status-line">{lastBuild.result.summary}</p>
          {findings.length > 0 && (
            <div className="table-wrap table-short">
              <table className="table">
                <thead><tr><th>Sev.</th><th>Elemento</th><th>Código</th><th>Atributo</th><th className="num">Modelo</th><th className="num">Ref.</th><th className="num">Desv.</th><th className="num">km</th></tr></thead>
                <tbody>{findings.map((h, i) => (
                  <tr key={i} title={h.message}>
                    <td><Pill tone={h.severity === 'grave' ? 'error' : h.severity === 'aviso' ? 'warn' : 'muted'}>{h.severity}</Pill></td>
                    <td>{h.element}</td><td className="mono">{h.code}</td><td>{h.attribute}</td>
                    <td className="num">{String(h.model)}</td><td className="num">{String(h.reference)} {h.unit}</td>
                    <td className="num">{h.deviation_pct == null ? '—' : `${h.deviation_pct > 0 ? '+' : ''}${fmtNum(h.deviation_pct, 1)} %`}</td>
                    <td className="num">{fmtNum(h.km, 1)}</td>
                  </tr>
                ))}</tbody>
              </table>
            </div>
          )}
        </>
      )}
    </div>
  );
}

// ------------------------------------------------------------------ sistema completo

export function SystemTab() {
  const { ws, startJob, active } = useApp();
  const confirm = useConfirm();
  const ready = ws.missing_inputs.length === 0;

  const launch = async (action: 'grid' | 'base' | 'missing-data') => {
    if (action === 'grid' && !(await confirm('Convertir todo a una sola grid', <>
      <p>Se unirán TODOS los alimentadores en una sola red y se importará en DigSILENT. Cada alimentador conserva su
        tensión y su fuente, y los enlaces entre ellos quedan como interruptores normalmente abiertos.</p>
      <p className="muted">Sobre el export completo son unos 30 MB y varios minutos.</p>
    </>))) return;
    if (action === 'base' && !(await confirm('Escenario base del año 0', <>
      <p>Se construirá la red unida, se importará creando el caso ANIO_0_BASE con su escenario de operación, se hará
        converger el flujo y se ejecutarán los estudios.</p>
      <p className="muted">Contingencias N-1, fiabilidad y optimizaciones quedan fuera: sobre 53.000 barras pueden tardar
        horas. Es la operación más larga de la interfaz.</p>
    </>))) return;
    await startJob(() => api.system(ws.id, action));
  };

  return (
    <div className="module">
      <p className="muted">Los alimentadores en UNA sola red: es lo que permite preguntar si uno puede respaldar a otro o
        dónde conviene abrir, porque el respaldo y la reconfiguración ocurren entre alimentadores.</p>
      <div className="steps">
        <div className="step-box">
          <h3>¿Qué datos faltan?</h3>
          <p className="muted small">Qué estudios se pueden sustentar hoy y qué dato falta para los demás. No toca DigSILENT;
            tarda segundos.</p>
          <button className="btn" disabled={!ready || Boolean(active.engine)} onClick={() => launch('missing-data')}>Diagnosticar</button>
        </div>
        <div className="step-box">
          <h3>Red unida en una sola grid</h3>
          <p className="muted small">Genera SISTEMA.dgs, lo importa y corre el flujo.</p>
          <button className="btn btn-pf" disabled={!ready || Boolean(active.powerfactory)} onClick={() => launch('grid')}>Convertir TODO a una grid</button>
        </div>
        <div className="step-box">
          <h3>Escenario base año 0 + diagnóstico</h3>
          <p className="muted small">Caso ANIO_0_BASE, escenario, flujo y estudios.</p>
          <button className="btn btn-pf" disabled={!ready || Boolean(active.powerfactory)} onClick={() => launch('base')}>Construir año 0</button>
        </div>
      </div>
      <PfWarning />
    </div>
  );
}
