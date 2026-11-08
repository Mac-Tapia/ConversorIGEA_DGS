import { fmtBytes } from '../../shared/formato';
import { useEffect, useRef, useState } from 'react';
import { api } from '../../api/client';
import { useApp } from '../../shared/context';
import type { InputMode, SourceScope, VnrPublication, VnrPublications } from '../../api/types';
import { FileDrop, Pill, useConfirm, useToast } from '../../shared/ui';

// Los formatos de VNR-GIS no van aquí: los fija el servidor (health.slots.vnr_package
// .extensiones), que es quien los lee. Una lista propia ofrecía .7z y .gdb, que luego
// se rechazaban, y escondía .mdb, .sqlite o .csv, que sí se leen (spec 001, RF-26).
const ACCEPT: Record<string, string> = {
  red: '.txt', loads: '.txt', equipment: '.txt', equipment_extra: '.txt',
  mdb: '.mdb,.accdb', equipment_mdb: '.mdb,.accdb', study: '.zxst,.xst', aliases: '.json',
};

function VnrDiscovery() {
  const { ws, run, startJob, jobs, active } = useApp();
  const [catalog, setCatalog] = useState<VnrPublications | null>(null);
  const [refreshJob, setRefreshJob] = useState<string>();
  const [empresa, setEmpresa] = useState('');
  const [fallo, setFallo] = useState('');
  // 080:RF-16: una sola búsqueda automática por apertura, aunque no encuentre nada.
  const autoBuscada = useRef(false);

  const discover = async (refresh: boolean) => {
    if (refresh) {
      setFallo('');
      const job = await startJob(() => api.vnrRefresh(ws.id));
      if (job) setRefreshJob(job.id);
      return;
    }
    const result = await run(() => api.vnrPublications());
    if (result) setCatalog(result);
  };
  useEffect(() => {
    const job = refreshJob ? jobs[refreshJob] : undefined;
    if (job?.status === 'done' && job.result?.publications) {
      setCatalog(job.result as VnrPublications);
      setRefreshJob(undefined);
    } else if (job?.status === 'failed') {
      setFallo(job.error || 'La búsqueda no terminó.');
      setRefreshJob(undefined);
    }
  }, [jobs, refreshJob]);
  useEffect(() => { void discover(false); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const packages = catalog?.publications.filter((item) => item.convertible) ?? [];
  useEffect(() => {
    if (catalog && !packages.length && !autoBuscada.current && !active.engine) {
      autoBuscada.current = true;
      void discover(true);
    }
  }, [catalog]); // eslint-disable-line react-hooks/exhaustive-deps

  const empresas = [...new Set(packages.map((item) => item.empresa))].sort((a, b) => a.localeCompare(b, 'es'));
  const deLaEmpresa = packages.filter((item) => item.empresa === empresa);
  const vigente = deLaEmpresa.find((item) => item.vigente);
  const anteriores = deLaEmpresa.filter((item) => !item.vigente);
  const errores = catalog?.refresh?.errors ?? [];

  const paquete = (item: VnrPublication) => (
    <div className="vnr-publication" key={item.publication_id}>
      <div>
        <b>{item.file_name}</b>
        <br /><span className="muted small">
          VNR {item.period_label}{item.regulatory_reference && <> · Resolución {item.regulatory_reference}</>}
        </span>
        <br /><span className="small">
          <a href={item.download_url} target="_blank" rel="noreferrer">Enlace oficial</a>
          {item.official_page && <> · <a href={item.official_page} target="_blank" rel="noreferrer">Página de la resolución</a></>}
        </span>
      </div>
      <button className="btn btn-sm" disabled={Boolean(active.engine)} onClick={async () => {
        await startJob(() => api.vnrDownload(ws.id, item.publication_id));
      }}>Descargar y usar</button>
    </div>
  );

  return (
    <div className="vnr-discovery">
      <div className="row">
        <strong>Paquete oficial VNR-GIS</strong>
        <button className="btn btn-sm" disabled={Boolean(active.engine)} onClick={() => discover(true)}>
          Buscar publicaciones
        </button>
      </div>
      {empresas.length > 0 && (
        <label className="field">
          <span>Distribuidora</span>
          <select value={empresa} onChange={(event) => setEmpresa(event.target.value)}>
            <option value="">— {empresas.length} encontradas, seleccione una —</option>
            {empresas.map((nombre) => <option key={nombre}>{nombre}</option>)}
          </select>
        </label>
      )}
      {vigente && paquete(vigente)}
      {anteriores.length > 0 && (
        <details>
          <summary className="muted small">Versiones anteriores ({anteriores.length})</summary>
          {anteriores.map(paquete)}
        </details>
      )}
      {catalog && !packages.length && !refreshJob && autoBuscada.current && (
        <p className="alert alert-warn">No se encontró un paquete oficial de datos convertible. Los PDF regulatorios no se usan como red. Suba abajo el paquete completo verificado.</p>
      )}
      {(fallo || errores.length > 0) && (
        <p className="alert alert-warn pre">{[fallo, ...errores.map((e) => `No se pudo leer ${e.page}: ${e.error}`)].filter(Boolean).join('\n')}</p>
      )}
      <p className="muted small">
        Son los paquetes públicos de Osinergmin{catalog?.portal && <> (<a href={catalog.portal} target="_blank" rel="noreferrer">portal oficial del VNR</a>)</>}.
        También puede subir abajo su propio paquete o copia. Cada uno es una fuente aparte: use un espacio de trabajo por empresa.
      </p>
    </div>
  );
}

function EmpresaEspacio() {
  const { ws, setWs, run, active } = useApp();
  const toast = useToast();
  const [empresa, setEmpresa] = useState(ws.options.empresa_espacio ?? '');
  const [guardando, setGuardando] = useState(false);
  const montada = useRef(true);
  const bloqueada = Boolean(active.engine || active.powerfactory) || guardando;
  const modificada = empresa.trim() !== (ws.options.empresa_espacio ?? '');

  useEffect(() => {
    setEmpresa(ws.options.empresa_espacio ?? '');
  }, [ws.options.empresa_espacio]);
  useEffect(() => {
    montada.current = true;
    return () => { montada.current = false; };
  }, []);

  const guardar = async () => {
    if (bloqueada || !modificada) return;
    setGuardando(true);
    try {
      const actualizado = await run(() => api.setOptions(ws.id, { empresa_espacio: empresa.trim() || null }));
      if (actualizado && montada.current) {
        setWs(actualizado);
        toast('ok', 'Empresa del espacio guardada');
      }
    } finally {
      if (montada.current) setGuardando(false);
    }
  };

  return (
    <form className="form-grid" onSubmit={(event) => { event.preventDefault(); void guardar(); }}>
      <label className="field">
        <span>Empresa del espacio</span>
        <input name="empresa_espacio" value={empresa} disabled={bloqueada}
          placeholder="Nombre de la empresa" onChange={(event) => setEmpresa(event.target.value)} />
      </label>
      <button type="submit" className="btn btn-sm" disabled={bloqueada || !modificada}>
        {guardando ? 'Guardando…' : 'Guardar empresa'}
      </button>
      <p className="muted small span-2">
        Se utiliza cuando la fuente no indica empresa. Si lo deja vacío, se informará el supuesto usado.
      </p>
    </form>
  );
}

function Slot({ slot }: { slot: string }) {
  const { ws, setWs, health, run, active } = useApp();
  const toast = useToast();
  const confirm = useConfirm();
  const spec = health.slots[slot];
  const meta = ws.inputs[slot];
  const [uploading, setUploading] = useState<number | null>(null);
  const [pathMode, setPathMode] = useState(false);
  const [path, setPath] = useState('');
  const locked = Boolean(active.engine);

  const afterAssign = async (res: { warning: string; workspace: typeof ws } | undefined) => {
    if (!res) return;
    setWs(res.workspace);
    if (res.warning) {
      const keep = await confirm(
        'El fichero no encaja con la casilla',
        <><p className="pre">{res.warning}</p><p>¿Usarlo de todos modos?</p></>,
        'Usarlo igualmente',
      );
      if (!keep) {
        const cleared = await run(() => api.clearInput(ws.id, slot));
        if (cleared) setWs(cleared);
      }
    }
  };

  const upload = async (files: File[]) => {
    const file = files[0];
    setUploading(file.size);
    try {
      await afterAssign(await run(() => api.uploadInput(ws.id, slot, file)));
    } finally {
      setUploading(null);
    }
  };

  const assignPath = async () => {
    if (!path.trim()) return;
    const res = await run(() => api.serverPathInput(ws.id, slot, path));
    if (res) {
      setPath('');
      setPathMode(false);
      toast('ok', 'Ruta asignada', res.workspace.inputs[slot]?.name);
    }
    await afterAssign(res);
  };

  return (
    <div className={`slot ${meta ? 'slot-set' : ''} ${spec.obligatorio && !meta ? 'slot-required' : ''}`}>
      <div className="slot-head">
        <span className="slot-label">{spec.etiqueta}{spec.obligatorio && <span className="req" title="Obligatorio">*</span>}</span>
        {meta && (
          <button className="link" disabled={locked} onClick={async () => {
            const r = await run(() => api.clearInput(ws.id, slot));
            if (r) setWs(r);
          }}>Quitar</button>
        )}
      </div>
      {meta && (
        <div className="slot-file">
          <span className="slot-name" title={meta.path}>{meta.name}</span>
          <span className="muted">{fmtBytes(meta.size)} · {meta.origin === 'server' ? 'ruta local' : 'subido'}</span>
          {meta.warning && <Pill tone="warn" title={meta.warning}>no encaja</Pill>}
        </div>
      )}
      {/* Spec 025, RF-39: con un fichero ya asignado se reemplaza directamente, sin quitarlo. */}
      {pathMode ? (
        <div className="slot-path">
          <input value={path} autoFocus placeholder="D:\ruta\al\fichero" onChange={(e) => setPath(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && assignPath()} />
          <button className="btn btn-sm" onClick={assignPath}>Usar</button>
          <button className="btn btn-sm btn-ghost" onClick={() => setPathMode(false)}>Cancelar</button>
        </div>
      ) : (
        <FileDrop onFiles={upload} accept={spec.extensiones?.join(',') ?? ACCEPT[slot]}
          disabled={locked || uploading !== null} compact>
          {uploading !== null
            ? <span>Subiendo {fmtBytes(uploading)}…</span>
            : meta ? <span>Reemplazar: soltar otro fichero o <u>elegir</u></span>
              : <span>Soltar el fichero o <u>elegir</u></span>}
        </FileDrop>
      )}
      {!meta && spec.extensiones && (
        <p className="muted small">Admite {spec.extensiones.join(' ')}. Un shapefile, dentro de un ZIP o RAR.</p>
      )}
      {!pathMode && health.server_paths && (
        <button className="link small" disabled={locked} onClick={() => setPathMode(true)}>
          {meta ? '…o reemplazarlo por una ruta de este equipo' : '…o indicar una ruta de este equipo'}</button>
      )}
      {locked && <p className="muted small">Mientras corre la conversión o la carga, las entradas no se cambian.</p>}
    </div>
  );
}

export function InputsPanel() {
  const { ws, setWs, health, run, active } = useApp();
  const toast = useToast();
  const mode = ws.options.input_mode;
  const [sourceScope, setSourceScope] = useState<SourceScope | null>(null);
  const slots = Object.entries(health.slots).filter(([, s]) => s.grupo === mode).map(([k]) => k);

  useEffect(() => {
    if (mode !== 'vnr' || !ws.inputs.vnr_package) {
      setSourceScope(null);
      return;
    }
    void run(() => api.sourceScope(ws.id)).then((scope) => {
      if (scope) setSourceScope(scope);
    });
  }, [mode, ws.id, ws.inputs.vnr_package?.set_at]); // eslint-disable-line react-hooks/exhaustive-deps

  const saveScope = async (company: string | null, period: string | null) => {
    const scope = await run(() => api.setSourceScope(ws.id, company, period));
    if (!scope) return;
    setSourceScope(scope);
    const refreshed = await run(() => api.workspace(ws.id));
    if (refreshed) setWs(refreshed);
  };

  const setMode = async (m: InputMode) => {
    const r = await run(() => api.setOptions(ws.id, { input_mode: m }));
    if (r) setWs(r);
  };

  const auto = async (files: File[]) => {
    const r = await run(() => api.autoInputs(ws.id, files));
    if (!r) return;
    setWs(r.workspace);
    const ok = r.assigned.map((a) => `${a.name} → ${health.slots[a.slot].etiqueta.split(' —')[0]}`).join('\n');
    const bad = r.unassigned.map((u) => `${u.name}: ${u.reason}`).join('\n');
    toast(r.unassigned.length ? 'warn' : 'ok', `${r.assigned.length} fichero(s) asignados por contenido`,
      [ok, bad].filter(Boolean).join('\n'));
  };

  const ready = ws.missing_inputs.length === 0;

  return (
    <section className="card">
      <header className="card-head">
        <h2><span className="step">1</span> Entrada de datos</h2>
        <div className="segmented" role="radiogroup" aria-label="Alternativa de entrada">
          <button role="radio" aria-checked={mode === 'txt'} className={mode === 'txt' ? 'on' : ''}
            disabled={Boolean(active.engine)} onClick={() => setMode('txt')}>Tres TXT de CYMDIST</button>
          <button role="radio" aria-checked={mode === 'mdb'} className={mode === 'mdb' ? 'on' : ''}
            disabled={Boolean(active.engine)} onClick={() => setMode('mdb')}>Base Access (.mdb)</button>
          <button role="radio" aria-checked={mode === 'vnr'} className={mode === 'vnr' ? 'on' : ''}
            disabled={Boolean(active.engine)} onClick={() => setMode('vnr')}>VNR-GIS</button>
        </div>
      </header>

      <EmpresaEspacio key={ws.id} />

      {mode === 'txt' && (
        <FileDrop onFiles={auto} multiple accept=".txt" disabled={Boolean(active.engine)}>
          <div className="auto-drop">
            <strong>Suelte aquí los TXT de la entrega</strong>
            <span className="muted">Cada uno va a su casilla por las tablas que trae dentro, no por el nombre.</span>
          </div>
        </FileDrop>
      )}
      {mode === 'mdb' && !health.capabilities.access && (
        <p className="alert alert-warn">Falta <code>pyodbc</code> o el driver «Microsoft Access Driver» de 64 bits en el servidor.</p>
      )}
      {mode === 'vnr' && <VnrDiscovery />}

      <div className="slots">
        {slots.map((s) => <Slot key={s} slot={s} />)}
        {(mode === 'txt' || mode === 'mdb') && <Slot slot="aliases" />}
      </div>

      {mode === 'vnr' && sourceScope && (
        <div className="form-grid">
          {sourceScope.companies.length > 1 && (
            <label className="field">
              <span>Empresa de la fuente</span>
              <select value={sourceScope.selected_company ?? ''} onChange={(event) => {
                const company = event.target.value || null;
                if (sourceScope.periods.length === 1) {
                  void saveScope(company, sourceScope.periods[0]);
                } else {
                  setSourceScope({ ...sourceScope, selected_company: company, selected_period: null });
                }
              }}>
                <option value="">— seleccione —</option>
                {sourceScope.companies.map((company) => <option key={company}>{company}</option>)}
              </select>
            </label>
          )}
          {sourceScope.periods.length > 1 && (
            <label className="field">
              <span>Periodo de la fuente</span>
              <select value={sourceScope.selected_period ?? ''} onChange={(event) => {
                void saveScope(sourceScope.selected_company, event.target.value || null);
              }} disabled={sourceScope.companies.length > 1 && !sourceScope.selected_company}>
                <option value="">— seleccione —</option>
                {sourceScope.periods.map((period) => <option key={period}>{period}</option>)}
              </select>
            </label>
          )}
          {sourceScope.ambiguous && (
            <p className="alert alert-warn span-2">Seleccione empresa y periodo para evitar mezclar entregas.</p>
          )}
        </div>
      )}

      <p className={`status-line ${ready ? 'ok' : ''}`}>
        {ready
          ? (mode === 'mdb' ? 'Base de datos lista.' : mode === 'vnr' ? 'Paquete VNR-GIS listo.' : 'Los tres TXT están listos.') + ' Pulse «Cargar / listar alimentadores».'
          : `Pendientes: ${ws.missing_inputs.join(', ')}.`}
      </p>
    </section>
  );
}
