import { useEffect, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import { api } from '../api';
import { useApp } from '../context';

/** 065:RF-18: comprimir es un trabajo visible; descargar entrega el ZIP terminado. */
export function DescargaZip({ feeders = [], disabled = false, children }: {
  feeders?: string[]; disabled?: boolean; children: ReactNode;
}) {
  const { ws, startJob, jobs, active } = useApp();
  const [id, setId] = useState<string>();
  const downloaded = useRef<string | undefined>(undefined);
  const job = id ? jobs[id] : undefined;
  const busy = job && (job.status === 'queued' || job.status === 'running');
  useEffect(() => {
    if (job?.status === 'done' && typeof job.result?.download === 'string' && downloaded.current !== job.id) {
      downloaded.current = job.id;
      window.location.assign(job.result.download);
    }
  }, [job]);
  return <button className="btn btn-sm" disabled={disabled || Boolean(busy) || Boolean(active.engine)}
    onClick={async () => {
      const created = await startJob(() => api.zipArchive(ws.id, feeders));
      if (created) setId(created.id);
    }}>
    {busy ? 'Preparando descarga…' : children}
  </button>;
}
