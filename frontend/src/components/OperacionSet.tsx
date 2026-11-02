import { useState } from 'react';
import { api } from '../api';
import { cuerpoOperacionSet, FORMULARIO_SET, type AccionSet, type FormularioSet } from '../operacionSet';
import type { Job } from '../types';

interface ResultadoSet {
  aceptada?: boolean;
  report?: string;
  informe?: { error?: string; motivos?: string[]; avisos?: string[] };
}

/**
 * 063:RF-36 a RF-38: diagnosticar o reforzar una SET que ya está en el proyecto, sin recrearla. La ruta
 * existía solo en la API; aquí la lanza el operador, por el carril de DIgSILENT.
 */
export function OperacionSet({ wsId, project, feeders, ocupado, jobs, startJob }: {
  wsId: string; project: string; feeders: string[]; ocupado: boolean; jobs: Job[];
  startJob: (fn: () => Promise<Job>) => unknown;
}) {
  const [f, setF] = useState<FormularioSet>(FORMULARIO_SET);
  const { cuerpo, error } = cuerpoOperacionSet(project, feeders, f);
  const ultimo = jobs.filter((j) => j.kind === 'set_nueva_operacion'
    && (j.result as { project?: string } | null)?.project === project).pop();
  const r = (ultimo?.result ?? null) as ResultadoSet | null;
  const poner = <K extends keyof FormularioSet>(k: K, v: FormularioSet[K]) => setF((x) => ({ ...x, [k]: v }));
  const casilla = (k: 'verificarFlujos' | 'sincronizarCargas' | 'conciliarFases' | 'reabrir', texto: string) => (
    <label className="small"><input type="checkbox" checked={f[k]} onChange={(e) => poner(k, e.target.checked)} /> {texto}</label>
  );
  const json = (k: 'cambios' | 'salidas' | 'ajustes', texto: string, ejemplo: string) => (
    <label className="field span-2"><span>{texto}</span>
      <textarea rows={2} value={f[k]} placeholder={ejemplo} onChange={(e) => poner(k, e.target.value)} />
    </label>
  );
  return (
    <details className="step-box">
      <summary><strong>Operación de una SET existente</strong></summary>
      <p className="muted small">Diagnostica o refuerza la SET que ya está en {project}. Evaluar ensaya en una copia del
        escenario y no deja nada; aplicar exige que los dos flujos cumplan y relee el resultado al reabrir.
        Nunca se crea ni se mueve la SET, ni se reduce la demanda.</p>
      <div className="form-grid">
        <label className="field"><span>Acción</span>
          <select value={f.accion} onChange={(e) => poner('accion', e.target.value as AccionSet)}>
            <option value="diagnostico">Diagnóstico</option>
            <option value="evaluar">Evaluar</option>
            <option value="aplicar">Aplicar</option>
          </select>
        </label>
        <label className="field"><span>Variaciones por desactivar</span>
          <input value={f.desactivar} placeholder="separadas por comas" onChange={(e) => poner('desactivar', e.target.value)} />
        </label>
        {json('cambios', 'Cambios (JSON)', '[{"clase": "ElmLne", "elemento": "ruta completa", "atributos": {"nlnum": 2}}]')}
        {json('salidas', 'Salidas (JSON)', '[{…}]')}
        {json('ajustes', 'Ajustes del flujo (JSON)', '{"iopt_at": 1}')}
      </div>
      <div className="row">
        {casilla('verificarFlujos', 'Verificar los flujos')}
        {casilla('sincronizarCargas', 'Sincronizar las cargas')}
        {casilla('conciliarFases', 'Conciliar las fases')}
        {casilla('reabrir', 'Reabrir para comprobar')}
      </div>
      <div className="row">
        <button className="btn btn-sm btn-pf" disabled={ocupado || !cuerpo}
          onClick={() => { if (cuerpo) void startJob(() => api.setNuevaOperacion(wsId, cuerpo)); }}>
          Ejecutar en DIgSILENT
        </button>
        {error && <small className="muted">{error}</small>}
        {!error && ocupado && <small className="muted">Espere a que termine el trabajo de DIgSILENT en curso.</small>}
      </div>
      {ultimo?.status === 'failed' && <small className="alert alert-error">{ultimo.error}</small>}
      {r && <div className="small">
        <p><strong>{r.aceptada ? 'Aceptada' : 'No aceptada'}</strong>{r.report ? ` · ${r.report}` : ''}</p>
        {(r.informe?.motivos ?? []).map((m) => <div key={m} className="muted">{m}</div>)}
        {(r.informe?.avisos ?? []).map((m) => <div key={m} className="muted">{m}</div>)}
      </div>}
    </details>
  );
}
