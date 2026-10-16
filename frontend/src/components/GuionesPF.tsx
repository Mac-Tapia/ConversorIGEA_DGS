import { useState } from 'react';
import { api } from '../api';
import { useApp } from '../context';
import type { GuionOperador, GuionResultado } from '../types';
import { CASOS_OBRA } from './ObrasPF';

/** Rol que da el guion de estudios a cada caso. */
const ROL: Record<string, string> = { 'Sin proyecto': 'sin', 'Con proyecto': 'con' };

/**
 * Guiones DPL y Python del operador, dentro de 4.2 (spec 011, RF-27 a RF-30).
 *
 * Se leen del proyecto con sus parámetros; el elegido se ejecuta en «Sin proyecto» y en
 * «Con proyecto» con los valores que escriba el operador, y se ve por caso su código y su
 * ventana de salida. Lo que haga el guion en la red es cosa suya: no se protege.
 */
export function GuionesPF({ project }: { project: string }) {
  const { ws, startJob, active, jobs } = useApp();
  const [elegido, setElegido] = useState('');
  const [valores, setValores] = useState<Record<string, string>>({});
  const [casos, setCasos] = useState<string[]>([...CASOS_OBRA]);
  const pfBusy = Boolean(active.powerfactory);
  const todos = Object.values(jobs);
  const lectura = todos.filter((j) => j.kind === 'guiones_listar' && j.status === 'done' && j.result).pop();
  const guiones = (lectura?.result?.guiones ?? []) as GuionOperador[];
  const ultima = todos.filter((j) => j.kind === 'guion_ejecutar' && j.result).pop();
  const resultado = (ultima?.result ?? null) as GuionResultado | null;
  const clave = (g: GuionOperador) => `${g.origen}|${g.nombre}`;
  const guion = guiones.find((g) => clave(g) === elegido) ?? null;
  // Un guion de un caso solo se ejecuta en los casos que lo tienen.
  const posibles: string[] = CASOS_OBRA.filter((c) => !guion || guion.casos.includes(ROL[c]));

  const elegir = (k: string) => {
    setElegido(k);
    const g = guiones.find((x) => clave(x) === k);
    setValores(Object.fromEntries((g?.parametros ?? []).map((p) => [p.nombre, p.valor])));
  };
  const ejecutar = () => guion && startJob(() => api.guionEjecutar(ws.id, {
    project, nombre: guion.nombre, origen: guion.origen, parametros: valores,
    casos: casos.filter((c) => posibles.includes(c)),
  }));

  return (
    <div>
      <h5>Guiones del proyecto (DPL y Python)</h5>
      <div className="row">
        <button className="btn" disabled={pfBusy || !project} onClick={() => startJob(() => api.guiones(ws.id, project))}>
          {lectura ? 'Volver a leer los guiones' : 'Leer los guiones del proyecto'}
        </button>
        {lectura && !guiones.length && <small className="muted">El proyecto no tiene guiones en sus casos ni en su carpeta.</small>}
      </div>
      {guiones.length > 0 && <>
        <label className="field">
          <span>Guion</span>
          <select value={elegido} onChange={(e) => elegir(e.target.value)}>
            <option value="">— elija —</option>
            {guiones.map((g) => (
              <option key={clave(g)} value={clave(g)}>
                {g.nombre} · {g.clase === 'ComDpl' ? 'DPL' : 'Python'} · {g.origen === 'proyecto' ? 'carpeta de guiones' : 'caso'}
              </option>
            ))}
          </select>
        </label>
        {guion && (
          <div className="form-grid">
            {guion.parametros.map((p) => (
              <label key={p.nombre} className="field">
                <span>{p.nombre}{p.unidad ? ` (${p.unidad})` : ''}</span>
                <input value={valores[p.nombre] ?? ''} onChange={(e) => setValores((v) => ({ ...v, [p.nombre]: e.target.value }))} />
                {p.descripcion && <small className="muted">{p.descripcion}</small>}
              </label>
            ))}
            {guion.objetos.map((o) => (
              <label key={o} className="field">
                <span>{o} (objeto)</span>
                <input value={valores[o] ?? ''} placeholder="nombre.Clase, p. ej. B12.ElmTerm"
                  onChange={(e) => setValores((v) => ({ ...v, [o]: e.target.value }))} />
              </label>
            ))}
            <div className="field span-2">
              <span>Ejecutar en</span>
              <div className="chips">
                {posibles.map((c) => (
                  <button key={c} type="button" className={`chip ${casos.includes(c) ? 'on' : ''}`}
                    onClick={() => setCasos((xs) => (xs.includes(c) ? xs.filter((x) => x !== c) : [...xs, c]))}>{c}</button>
                ))}
              </div>
            </div>
            <div className="row span-2">
              <button className="btn btn-pf" disabled={pfBusy || !casos.some((c) => posibles.includes(c))} onClick={ejecutar}>
                Ejecutar {guion.nombre}
              </button>
            </div>
          </div>
        )}
      </>}
      {resultado && (
        <div className="alert">
          <p><strong>Guion {resultado.guion}</strong>{resultado.cancelado ? ' · cancelado' : ''}</p>
          {resultado.resultados.map((r) => (
            <details key={r.caso} open={Boolean(r.error)}>
              <summary>{r.caso}: {r.no_terminado ? 'no terminó en su límite'
                : r.error ? <span className="badge err">código {r.codigo_guion ?? '—'}</span> : `código ${r.codigo_guion ?? 0}`}</summary>
              {r.error && <p className="alert alert-error">{r.error}</p>}
              <pre className="report">{r.salida.join('\n') || '(sin salida)'}</pre>
            </details>
          ))}
        </div>
      )}
    </div>
  );
}
