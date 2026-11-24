import { useState } from 'react';
import { api } from '../../api/client';
import { cuenta } from '../../shared/formato';
import { useApp } from '../../shared/context';
import type { PfdResultado } from '../../api/types';
import { FileDrop } from '../../shared/ui';

/**
 * Importar un `.pfd` de DIgSILENT desde la web (004:RF-118).
 *
 * El fichero se guarda en el espacio y se importa en un proyecto nuevo de la carpeta de la empresa, como trabajo del
 * carril de DIgSILENT; el resultado resume cada proyecto y agrupa los avisos iguales con sus veces (RF-117). El detalle
 * entero va en el informe que se descarga.
 */
export function ImportarPfd({ onImportado }: { onImportado: () => void }) {
  const { ws, startJob, active, jobs } = useApp();
  const [reimportar, setReimportar] = useState(false);
  const [expediente, setExpediente] = useState('');
  const pfBusy = Boolean(active.powerfactory);
  const ultimo = Object.values(jobs).filter((j) => j.kind === 'pfd_diagnostico' && j.status === 'done' && j.result).pop();
  const resultado = (ultimo?.result ?? null) as PfdResultado | null;
  const r = resultado?.resumen;

  const importar = async (file: File) => {
    if (await startJob(() => api.pfdImportar(ws.id, file, reimportar, expediente))) onImportado();
  };

  return (
    <details className="card">
      <summary>Importar un .pfd</summary>
      <FileDrop entrada="pfd" compact accept=".pfd" disabled={pfBusy} onFiles={([f]) => void importar(f)}>
        <span>Proyecto de DIgSILENT (.pfd): soltar o <u>elegir</u></span>
      </FileDrop>
      <label className="small">
        <input type="checkbox" checked={reimportar} onChange={(e) => setReimportar(e.target.checked)} />
        {' '}En un proyecto nuevo, aunque ya esté importado
      </label>
      <label className="small">
        Carpeta del expediente (opcional, en este equipo)
        <input type="text" value={expediente} onChange={(e) => setExpediente(e.target.value)}
          placeholder="D:\\proyectos\\expediente" disabled={pfBusy} />
      </label>
      {r && (
        <div className="small">
          <p><strong>{r.fichero}</strong> · carpeta «{r.carpeta}»</p>
          <ul>
            {r.proyectos.map((p) => (
              <li key={p.proyecto ?? ''}>
                {p.proyecto}: {cuenta(p.casos, 'caso', 'casos')}, {cuenta(p.escenarios, 'escenario', 'escenarios')},
                {' '}{cuenta(p.variaciones, 'variación', 'variaciones')}, {cuenta(p.alimentadores, 'alimentador', 'alimentadores')}
                {p.version_anterior && ` · versión anterior: ${p.version_anterior}`}
              </li>
            ))}
          </ul>
          {r.avisos.length > 0 && (
            <details>
              <summary>{cuenta(r.avisos.length, 'aviso', 'avisos')}
                {r.total_avisos > r.avisos.length && ` (${r.total_avisos} con los repetidos)`}</summary>
              <ul>{r.avisos.map((a) => <li key={a.aviso}>{a.aviso}{a.veces > 1 && <strong> ×{a.veces}</strong>}</li>)}</ul>
            </details>
          )}
          {(resultado?.vinculos ?? []).map((v) => (
            <details key={`v-${v.proyecto ?? ''}`}>
              <summary>Expediente de {v.proyecto}: {cuenta(v.vinculos.length, 'vínculo', 'vínculos')}
                {v.sin_vinculo.length > 0 && ` · ${cuenta(v.sin_vinculo.length, 'nombre', 'nombres')} sin fichero`}</summary>
              <ul>
                {v.vinculos.map((x) => (
                  <li key={`${x.tipo}-${x.nombre}-${x.fichero}-${String(x.ubicacion)}`}>
                    {x.tipo} «{x.nombre}» → {x.fichero}{x.ubicacion ? ` (${x.ubicacion})` : ''}: «{x.texto}»
                  </li>
                ))}
              </ul>
              {v.ficheros.filter((f) => f.estado !== 'ok').length > 0 && (
                <p>Sin leer: {v.ficheros.filter((f) => f.estado !== 'ok').map((f) => `${f.fichero} (${f.motivo ?? f.estado})`).join('; ')}</p>
              )}
              {v.sin_vinculo.length > 0 && <p>Sin fichero que lo nombre: {v.sin_vinculo.join(', ')}</p>}
            </details>
          ))}
          {resultado?.informe_texto && (
            <a className="link" href={api.fileUrl(ws.id, resultado.informe_texto, true)}>Descargar el informe</a>
          )}
        </div>
      )}
    </details>
  );
}
