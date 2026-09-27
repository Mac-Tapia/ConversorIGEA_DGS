import { useState } from 'react';
import { api, fmtBytes } from '../api';
import { useApp } from '../context';
import type { InputMode } from '../types';
import { FileDrop, Pill, useConfirm, useToast } from './ui';

const ACCEPT: Record<string, string> = {
  red: '.txt', loads: '.txt', equipment: '.txt', equipment_extra: '.txt',
  mdb: '.mdb,.accdb', equipment_mdb: '.mdb,.accdb', study: '.zxst,.xst', aliases: '.json',
};

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
    <div className={`slot ${meta ? 'slot-set' : ''} ${meta?.stale ? 'slot-required' : ''} ${spec.obligatorio && !meta ? 'slot-required' : ''}`}>
      <div className="slot-head">
        <span className="slot-label">{spec.etiqueta}{spec.obligatorio && <span className="req" title="Obligatorio">*</span>}</span>
        {meta && (
          <button className="link" disabled={locked} onClick={async () => {
            const r = await run(() => api.clearInput(ws.id, slot));
            if (r) setWs(r);
          }}>Quitar</button>
        )}
      </div>
      {meta ? (
        <div className="slot-file">
          <span className="slot-name" title={meta.path}>{meta.name}</span>
          <span className="muted">{fmtBytes(meta.size)} · {meta.origin === 'server' ? 'ruta local' : 'subido'}</span>
          {meta.stale && <Pill tone="error" title={meta.custody_error}>cambió</Pill>}
          {meta.warning && <Pill tone="warn" title={meta.warning}>no encaja</Pill>}
          {!meta.stale && meta.sha256 && <span className="muted small mono" title={meta.sha256}>SHA-256 {meta.sha256.slice(0, 12)}…</span>}
        </div>
      ) : pathMode ? (
        <div className="slot-path">
          <input value={path} autoFocus placeholder="D:\ruta\al\fichero" onChange={(e) => setPath(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && assignPath()} />
          <button className="btn btn-sm" onClick={assignPath}>Usar</button>
          <button className="btn btn-sm btn-ghost" onClick={() => setPathMode(false)}>Cancelar</button>
        </div>
      ) : (
        <FileDrop onFiles={upload} accept={ACCEPT[slot]} disabled={locked || uploading !== null} compact>
          {uploading !== null
            ? <span>Subiendo {fmtBytes(uploading)}…</span>
            : <span>Soltar el fichero o <u>elegir</u></span>}
        </FileDrop>
      )}
      {!meta && !pathMode && health.server_paths && (
        <button className="link small" onClick={() => setPathMode(true)}>…o indicar una ruta de este equipo</button>
      )}
    </div>
  );
}

export function InputsPanel() {
  const { ws, setWs, health, run, active } = useApp();
  const toast = useToast();
  const mode = ws.options.input_mode;
  const slots = Object.entries(health.slots).filter(([, s]) => s.grupo === mode).map(([k]) => k);

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
            disabled={Boolean(active.engine)} onClick={() => setMode('txt')}>Tres TXT de IGEA/CYMDIST</button>
          <button role="radio" aria-checked={mode === 'mdb'} className={mode === 'mdb' ? 'on' : ''}
            disabled={Boolean(active.engine)} onClick={() => setMode('mdb')}>Base Access (.mdb)</button>
        </div>
      </header>

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

      <div className="slots">
        {slots.map((s) => <Slot key={s} slot={s} />)}
        <Slot slot="aliases" />
      </div>

      <p className={`status-line ${ready ? 'ok' : ''}`}>
        {ready
          ? (mode === 'mdb' ? 'Base de datos lista.' : 'Los tres TXT están listos.') + ' Pulse «Cargar / listar alimentadores».'
          : `Pendientes: ${ws.missing_inputs.join(', ')}.`}
      </p>
    </section>
  );
}
