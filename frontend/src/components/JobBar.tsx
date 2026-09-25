import { useEffect, useState } from 'react';
import { api } from '../api';
import type { Job } from '../types';

const elapsed = (j: Job) => {
  const s = Math.max(0, Math.round(Date.now() / 1000 - (j.started_at ?? j.created_at)));
  return s < 60 ? `${s} s` : `${Math.floor(s / 60)} min ${s % 60} s`;
};

export function JobBar({ jobs }: { jobs: Job[] }) {
  // Reloj para el tiempo transcurrido; solo corre mientras hay trabajos.
  const [, tick] = useState(0);
  useEffect(() => {
    if (!jobs.length) return;
    const t = window.setInterval(() => tick((n) => n + 1), 1000);
    return () => window.clearInterval(t);
  }, [jobs.length]);
  if (!jobs.length) return null;
  return (
    <div className="jobbar">
      {jobs.map((j) => {
        const p = j.progress;
        const pct = p && p.total ? Math.round((p.index / p.total) * 100) : null;
        return (
          <div key={j.id} className="job">
            <div className="job-top">
              <span className={`lane lane-${j.lane}`}>{j.lane === 'powerfactory' ? 'DigSILENT' : 'Motor'}</span>
              <strong>{j.title}</strong>
              <span className="muted">
                {j.status === 'queued' ? 'en cola' : p ? `${p.index}/${p.total}${p.label ? ` · ${p.label}` : ''}` : 'trabajando…'}
                {j.status === 'running' && ` · ${elapsed(j)}`}
              </span>
              <span className="spacer" />
              <button className="btn btn-sm btn-danger" disabled={j.cancel_requested}
                onClick={() => void api.cancelJob(j.id)}>
                {j.cancel_requested ? 'Cancelando…' : 'Cancelar'}
              </button>
            </div>
            <div className={`bar ${pct === null ? 'bar-indeterminate' : ''}`}>
              <span style={{ width: pct === null ? undefined : `${pct}%` }} />
            </div>
          </div>
        );
      })}
    </div>
  );
}
