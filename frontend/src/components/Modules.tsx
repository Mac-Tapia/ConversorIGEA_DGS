import { useMemo, useState, type FormEvent } from 'react';
import { api, download, fmtBytes, fmtNum } from '../api';
import { useApp } from '../context';
import type { CreatePlan, LoadPlan } from '../types';
import { FileDrop, Modal, Pill, useConfirm, useToast } from './ui';

// ------------------------------------------------------------------ utilidades

function useSingle(): { feeder: string | null; hint: string } {
  const { selected } = useApp();
  if (selected.length === 1) return { feeder: selected[0], hint: '' };
  return {
    feeder: null,
    hint: selected.length === 0
      ? 'Seleccione UN alimentador en la tabla: este módulo trabaja por alimentador.'
      : `Hay ${selected.length} seleccionados: este módulo trabaja con UNO.`,
  };
}

function PfWarning() {
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

  const previews = feeders.filter((r) => r.conversion?.preview_html && (!selected.length || selected.includes(r.feeder)));

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
          {previews.map((r) => (
            <button key={r.feeder} className={`chip ${preview === r.conversion!.preview_html ? 'on' : ''}`}
              onClick={() => setPreview(preview === r.conversion!.preview_html ? null : r.conversion!.preview_html)}>
              {r.feeder}
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

// ------------------------------------------------------------------ cargas de SED

export function LoadsTab() {
  const { ws, run, startJob, active } = useApp();
  const { feeder, hint } = useSingle();
  const [plan, setPlan] = useState<LoadPlan | null>(null);
  const confirm = useConfirm();

  const apply = async () => {
    if (!plan) return;
    if (plan.unknown.length) {
      const ok = await confirm('SED que no están en el modelo', <>
        <p>{plan.unknown.length} SED del fichero no existen en {plan.feeder}: {plan.unknown.slice(0, 10).join(', ')}
          {plan.unknown.length > 10 ? '…' : ''}</p>
        <p>Crear una SED nueva necesita datos que esta plantilla no trae; use el módulo «SED nuevas».
          ¿Actualizar solo las {plan.updates.length} existentes?</p>
      </>);
      if (!ok) return;
    }
    const job = await startJob(() => api.applyPlan(ws.id, plan.token));
    if (job) setPlan(null);
  };

  return (
    <div className="module">
      <p className="muted">Actualización masiva de la carga (kW, kvar) de las SED de un alimentador, sobre su proyecto de
        PowerFactory. Una sola fila con error bloquea todo: una actualización a medias es peor que ninguna.</p>
      {!feeder ? <p className="empty">{hint}</p> : (
        <div className="steps">
          <div className="step-box">
            <h3>1 · Descargar plantilla de {feeder}</h3>
            <div className="row">
              <button className="btn" onClick={() => run(() => download(api.loadTemplateUrl(ws.id, feeder, 'xlsx')))}>Excel</button>
              <button className="btn btn-ghost" onClick={() => run(() => download(api.loadTemplateUrl(ws.id, feeder, 'csv')))}>CSV</button>
            </div>
            <small className="muted">Por SED, rellene un par: «Kw» y «Kvar», «Kw» y «FP», o «(kVA)» y «FP». La SED que deje en blanco no cambia; la carga actual está en «Kw_actual». «accion» = omitir salta la fila.</small>
          </div>
          <div className="step-box">
            <h3>2 · Subir la plantilla rellenada</h3>
            <FileDrop compact accept=".xlsx,.csv" onFiles={async ([f]) => {
              const p = await run(() => api.loadPlan(ws.id, feeder, f));
              if (p) setPlan(p);
            }}><span>Soltar .xlsx / .csv o <u>elegir</u></span></FileDrop>
          </div>
        </div>
      )}
      <PfWarning />
      {plan && (
        <Modal wide title={`Plan de actualización de cargas — ${plan.feeder}`} onClose={() => setPlan(null)} actions={<>
          <button className="btn" onClick={() => setPlan(null)}>Cerrar</button>
          <button className="btn btn-pf" disabled={!plan.applicable || Boolean(active.powerfactory)} onClick={apply}>
            Aplicar en DigSILENT ({plan.updates.length} SED)
          </button>
        </>}>
          <div className="stats">
            {Object.entries(plan.summary).filter(([k]) => k !== 'feeder' && k !== 'applicable').map(([k, v]) => (
              <div className="stat" key={k}><span className="stat-value">{String(v)}</span><span className="stat-label">{k.replace('_', ' ')}</span></div>
            ))}
          </div>
          {plan.row_errors.length > 0 && (
            <div className="alert alert-error"><strong>{plan.row_errors.length} fila(s) con error — no se aplica nada.</strong>
              <ul>{plan.row_errors.slice(0, 20).map((e) => <li key={e}>{e}</li>)}</ul></div>
          )}
          {plan.updates.length > 0 && (
            <div className="table-wrap table-short">
              <table className="table">
                <thead><tr><th>SED</th><th className="num">kW antes</th><th className="num">kW después</th><th className="num">kvar antes</th><th className="num">kvar después</th></tr></thead>
                <tbody>{plan.updates.map((u) => (
                  <tr key={u.sed}><td className="strong">{u.sed}</td><td className="num">{fmtNum(u.kw_before, 1)}</td>
                    <td className="num">{fmtNum(u.kw_after, 1)}</td><td className="num">{fmtNum(u.kvar_before, 1)}</td>
                    <td className="num">{fmtNum(u.kvar_after, 1)}</td></tr>
                ))}</tbody>
              </table>
            </div>
          )}
          <details><summary>Informe completo</summary><pre className="report">{plan.report}</pre></details>
        </Modal>
      )}
    </div>
  );
}

// ------------------------------------------------------------------ SED nuevas

const SED_FIELDS: { key: string; label: string; help?: string; num?: boolean; required?: boolean; def?: string }[] = [
  { key: 'sed_code', label: 'Código de la SED', help: 'Por ejemplo SE31045.', required: true },
  { key: 'installed_kva', label: 'Potencia del transformador (kVA)', help: 'La de placa, no la carga.', num: true, required: true },
  { key: 'coord_x', label: 'Coordenada Este (X)', help: 'En el CRS del export. Se conecta al nodo más cercano.', num: true },
  { key: 'coord_y', label: 'Coordenada Norte (Y)', num: true },
  { key: 'node_id', label: 'Nodo de conexión', help: 'Solo si quiere imponerlo; en blanco se deduce del punto.' },
  { key: 'kw', label: 'Carga activa (kW)', help: 'En blanco si da kVA y FP.', num: true },
  { key: 'kvar', label: 'Carga reactiva (kvar)', num: true },
  { key: 'kva', label: 'Carga aparente (kVA)', num: true },
  { key: 'fp', label: 'Factor de potencia', num: true, def: '0.95' },
  { key: 'conductor', label: 'Conductor impuesto', help: 'En blanco se elige por ampacidad y caída de tensión.' },
];

export function NewSedTab() {
  const { ws, run, startJob, active } = useApp();
  const { feeder, hint } = useSingle();
  const [plan, setPlan] = useState<CreatePlan | null>(null);
  const [form, setForm] = useState(false);
  const toast = useToast();
  const [values, setValues] = useState<Record<string, string>>(
    Object.fromEntries(SED_FIELDS.map((f) => [f.key, f.def ?? ''])));

  // Solo convierte texto a número. Las reglas viven en loads_create.single_new_load,
  // el mismo camino que la plantilla: si el formulario validara por su cuenta, habría
  // dos definiciones de «fila válida».
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!feeder) return;
    const body: Record<string, unknown> = {};
    const bad: string[] = [];
    for (const f of SED_FIELDS) {
      const raw = values[f.key].trim();
      if (!f.num) { body[f.key] = raw; continue; }
      if (!raw) { body[f.key] = f.key === 'installed_kva' ? 0 : null; continue; }
      const n = Number(raw.replace(',', '.'));
      if (Number.isNaN(n)) bad.push(`«${f.label}»: ${raw} no es un número.`);
      body[f.key] = n;
    }
    if (bad.length) { toast('error', 'Dato no numérico', bad.join('\n')); return; }
    const p = await run(() => api.createPlanSingle(ws.id, feeder, body));
    if (p) { setPlan(p); setForm(false); }
  };

  const apply = async () => {
    if (!plan) return;
    const job = await startJob(() => api.applyPlan(ws.id, plan.token));
    if (job) setPlan(null);
  };

  return (
    <div className="module">
      <p className="muted">Las SED nuevas se sitúan por coordenadas: el punto se conecta al nodo más cercano con una
        derivación aérea, y la sección se elige por ampacidad y caída de tensión.</p>
      {!feeder ? <p className="empty">{hint}</p> : (
        <div className="steps">
          <div className="step-box">
            <h3>Plantilla de creación de {feeder}</h3>
            <div className="row">
              <button className="btn" onClick={() => run(() => download(api.createTemplateUrl(ws.id, feeder, 'xlsx')))}>Excel</button>
              <button className="btn btn-ghost" onClick={() => run(() => download(api.createTemplateUrl(ws.id, feeder, 'csv')))}>CSV</button>
            </div>
            <small className="muted">Basta con SED, CoordX, CoordY y kVA_instalado. La hoja «nodos_validos» lista los nodos.</small>
          </div>
          <div className="step-box">
            <h3>Subir la plantilla rellenada</h3>
            <FileDrop compact accept=".xlsx,.csv" onFiles={async ([f]) => {
              const p = await run(() => api.createPlan(ws.id, feeder, f));
              if (p) setPlan(p);
            }}><span>Soltar .xlsx / .csv o <u>elegir</u></span></FileDrop>
          </div>
          <div className="step-box">
            <h3>…o crear una sola</h3>
            <button className="btn" onClick={() => setForm(true)}>Formulario de una SED</button>
          </div>
        </div>
      )}
      <PfWarning />

      {form && feeder && (
        <Modal title={`Crear una SED en ${feeder}`} onClose={() => setForm(false)} actions={<>
          <button className="btn" onClick={() => setForm(false)}>Cancelar</button>
          <button className="btn btn-primary" type="submit" form="sed-form">Preparar plan</button>
        </>}>
          <form id="sed-form" className="form-grid" onSubmit={submit}>
            <p className="muted span-2">Indique las coordenadas del punto o bien el nodo de conexión.</p>
            {SED_FIELDS.map((f) => (
              <label key={f.key} className="field">
                <span>{f.label}{f.required && <span className="req">*</span>}</span>
                <input value={values[f.key]} inputMode={f.num ? 'decimal' : undefined}
                  onChange={(e) => setValues((v) => ({ ...v, [f.key]: e.target.value }))} />
                {f.help && <small className="muted">{f.help}</small>}
              </label>
            ))}
          </form>
        </Modal>
      )}

      {plan && (
        <Modal wide title={`Plan de creación de SED — ${plan.feeder}`} onClose={() => setPlan(null)} actions={<>
          <button className="btn" onClick={() => setPlan(null)}>Cerrar</button>
          <button className="btn btn-pf" disabled={!plan.applicable || Boolean(active.powerfactory)} onClick={apply}>
            Crear en DigSILENT ({plan.create.length})
          </button>
        </>}>
          {plan.row_errors.length > 0 && (
            <div className="alert alert-error"><strong>{plan.row_errors.length} fila(s) con error — no se crea nada.</strong>
              <ul>{plan.row_errors.slice(0, 20).map((e) => <li key={e}>{e}</li>)}</ul></div>
          )}
          {plan.already_exists.length > 0 && (
            <p className="alert alert-warn">{plan.already_exists.length} ya existen en {plan.feeder} ({plan.already_exists.slice(0, 8).join(', ')}):
              esas se actualizan en «Cargas de SED».</p>
          )}
          {plan.create.length > 0 && (
            <div className="table-wrap table-short">
              <table className="table">
                <thead><tr><th>SED</th><th className="num">kVA</th><th>Nodo</th><th className="num">Distancia</th><th>Conductor</th><th className="num">ΔV</th></tr></thead>
                <tbody>{plan.create.map((c) => (
                  <tr key={c.sed}><td className="strong">{c.sed}</td><td className="num">{fmtNum(c.installed_kva)}</td>
                    <td className="mono">{c.node_id}</td><td className="num">{fmtNum(c.distance_m)} m</td>
                    <td>{c.conductor} <span className="muted small">({c.binding})</span></td>
                    <td className="num">{fmtNum(c.voltage_drop_pct, 2)} %</td></tr>
                ))}</tbody>
              </table>
            </div>
          )}
          <p className="muted">Se creará en PowerFactory el nodo, la derivación aérea, la subestación, el transformador y la carga.</p>
          <details><summary>Informe completo</summary><pre className="report">{plan.report}</pre></details>
        </Modal>
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
