import { api } from '../../api/client';
import type { Job } from '../../api/types';
import { useApp } from '../../shared/context';
import { fmtNum } from '../../shared/formato';
import { useConfirm } from '../../shared/ui';

type Informe = { variacion?: string | null; feeders?: Record<string, unknown[]>[] };

/** «1 carga creada», «2 cargas creadas»: el número con su palabra en singular o en plural. */
const contar = (n: number, una: string, varias: string) => `${fmtNum(n)} ${n === 1 ? una : varias}`;

/** Cuántas cargas creó y cuántas demandas cambió la aplicación, sumando sus alimentadores. */
function cuentas(inf: Informe | undefined) {
  const n = (k: string) => (inf?.feeders ?? []).reduce((t, f) => t + (f[k]?.length ?? 0), 0);
  return { creadas: n('creadas'), actualizadas: n('actualizadas') };
}

/**
 * 007:RF-38 (WEB-RUTAS): deshacer un lote de cargas ya aplicado en DIgSILENT. Se ofrece en los lotes
 * aplicados de este espacio, pide confirmación con lo que se deshace y corre como trabajo de DIgSILENT.
 */
export function DeshacerLotes() {
  const { ws, jobs, startJob, active } = useApp();
  const confirm = useConfirm();
  const aplicados = Object.values(jobs)
    .filter((j: Job) => j.kind === 'cargas_aplicar' && j.status === 'done' && typeof j.result?.token === 'string')
    .sort((a, b) => Number(b.finished_at ?? 0) - Number(a.finished_at ?? 0));
  const deshechos = new Set(Object.values(jobs)
    .filter((j: Job) => j.kind === 'cargas_deshacer' && j.status === 'done')
    .map((j: Job) => j.result?.token as string | undefined));
  if (!aplicados.length) return null;
  const ocupado = Boolean(active.powerfactory);

  const deshacer = async (j: Job) => {
    const { creadas, actualizadas } = cuentas(j.result.informe);
    const ok = await confirm(`Deshacer el lote · ${j.result.project}`, <>
      <p>Se {creadas === 1 ? 'borra' : 'borran'} <b>{contar(creadas, 'carga creada', 'cargas creadas')}</b> y{' '}
        {actualizadas === 1 ? 'vuelve' : 'vuelven'} <b>{contar(actualizadas, 'demanda', 'demandas')}</b> a su valor
        anterior{j.result.informe?.variacion ? <> en <b>{j.result.informe.variacion}</b></> : null}.</p>
      <p className="muted">Solo lo que creó esta aplicación.</p>
    </>, 'Deshacer');
    if (ok) await startJob(() => api.cargasDeshacer(ws.id, j.result.token));
  };

  return (
    <section>
      <h4>Lotes aplicados</h4>
      <ul>
        {aplicados.map((j) => {
          const { creadas, actualizadas } = cuentas(j.result.informe);
          const hecho = deshechos.has(j.result.token);
          return (
            <li key={j.id}>
              <span>{j.result.project} · {contar(creadas, 'carga creada', 'cargas creadas')},{' '}
                {contar(actualizadas, 'demanda cambiada', 'demandas cambiadas')}</span>
              {hecho
                ? <span className="muted"> · deshecho</span>
                : <button className="btn btn-sm" disabled={ocupado} onClick={() => void deshacer(j)}>Deshacer…</button>}
            </li>
          );
        })}
      </ul>
    </section>
  );
}
