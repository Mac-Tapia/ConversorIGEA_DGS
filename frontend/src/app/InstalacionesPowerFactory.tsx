import { useEffect, useState } from 'react';
import { api } from '../api/client';
import type { InstalacionesPowerFactory } from '../api/types';
import { Modal, Pill } from '../shared/ui';

/**
 * 103:RF-3: las PowerFactory encontradas en esta máquina. Se usa sola la más nueva que funciona; el operador puede
 * elegir otra, que se recuerda en la máquina. Solo se pueden elegir las que tienen intérprete de Python para su API.
 */
export function InstalacionesPowerFactoryModal({ onClose, onCambio }: { onClose: () => void; onCambio: () => void }) {
  const [datos, setDatos] = useState<InstalacionesPowerFactory | null>(null);
  const [error, setError] = useState('');
  const [ocupado, setOcupado] = useState(false);

  useEffect(() => {
    api.pfInstalaciones().then(setDatos).catch((e: unknown) => setError(String((e as Error)?.message ?? e)));
  }, []);

  const elegir = async (carpeta: string | null) => {
    setOcupado(true);
    setError('');
    try {
      setDatos(await api.pfElegir(carpeta));
      onCambio();
    } catch (e) {
      setError(String((e as Error)?.message ?? e));
    } finally {
      setOcupado(false);
    }
  };

  return (
    <Modal title="DIgSILENT PowerFactory en esta máquina" onClose={onClose} wide
      actions={datos?.eleccion ? <button className="btn btn-ghost" disabled={ocupado}
        onClick={() => void elegir(null)}>Usar la más nueva</button> : undefined}>
      {error && <p className="alert alert-error">{error}</p>}
      {!datos && !error && <p className="muted">Buscando las instalaciones…</p>}
      {datos && datos.instalaciones.length === 0 && (
        <p>No se encontró ninguna PowerFactory (2021 o posterior). La conversión a DGS sigue funcionando.</p>
      )}
      {datos?.fijada_por_variable && (
        <p className="alert">La carpeta de la API está fijada con la variable PF_PYTHON: la elección de aquí no se usa.</p>
      )}
      {datos && datos.instalaciones.length > 0 && (
        <table className="table">
          <thead><tr><th>Instalación</th><th>API de Python</th><th>Intérprete</th><th></th></tr></thead>
          <tbody>
            {datos.instalaciones.map((i) => {
              const enUso = !!i.api && i.api === datos.en_uso;
              return (
                <tr key={i.carpeta}>
                  <td>{i.nombre} {enUso && <Pill tone="ok">en uso</Pill>}</td>
                  <td>{i.api ? i.api.split(/[\\/]/).pop() : '—'} <span className="muted small">(trae {i.apis.join(', ')})</span></td>
                  <td className="small">{i.motivo}</td>
                  <td>
                    {i.api && !enUso && (
                      <button className="btn btn-sm" disabled={ocupado || datos.fijada_por_variable}
                        onClick={() => void elegir(i.api)}>Usar esta</button>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
    </Modal>
  );
}
