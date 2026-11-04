import { useState } from 'react';
import { api } from '../api';
import type { Diagnostico } from '../types';
import { Modal, Pill } from './ui';

/** Las pendientes primero: con todo bien, lo importante es lo que falta, no la lista de lo que está. */
function ordenar(d: Diagnostico) {
  return [...d.comprobaciones].sort((a, b) => Number(a.ok) - Number(b.ok) || Number(b.obligatoria) - Number(a.obligatoria));
}

/**
 * 086:RF-40, RF-43: la versión de cabecera abre sus notas y el doctor, que dice qué falta, qué función afecta y cómo
 * arreglarlo. Se pide al abrir, y no al cargar la página: el doctor importa todas las librerías para comprobarlas.
 */
export function AcercaDe({ version }: { version: string }) {
  const [abierto, setAbierto] = useState(false);
  const [notas, setNotas] = useState('');
  const [informe, setInforme] = useState<Diagnostico | null>(null);
  const [error, setError] = useState('');

  const abrir = () => {
    setAbierto(true);
    setError('');
    setInforme(null);
    api.versionPrograma().then((v) => setNotas(v.notas)).catch(() => setNotas(''));
    api.diagnostico().then(setInforme).catch((e) => setError(String(e.message ?? e)));
  };

  return (
    <>
      <button type="button" className="btn-link small" title="Notas de la versión y diagnóstico de la instalación" onClick={abrir}>
        v{version}
      </button>
      {abierto && (
        <Modal title={`ConverterSmartGrid ${version}`} onClose={() => setAbierto(false)}
          actions={<button className="btn" onClick={() => setAbierto(false)}>Cerrar</button>}>
          <div className="stack">
            <h3>Diagnóstico de la instalación</h3>
            {error && <div className="alert alert-error">{error}</div>}
            {!informe && !error && <p className="muted">Comprobando…</p>}
            {informe && (
              <>
                <p>{informe.listo ? 'Lista para trabajar.' : 'Falta algo imprescindible: vea abajo qué y cómo arreglarlo.'}
                  {informe.pendientes > 0 && ` ${informe.pendientes} por revisar.`}</p>
                <ul className="doctor">
                  {ordenar(informe).map((c) => (
                    <li key={c.clave}>
                      <Pill tone={c.ok ? 'ok' : c.obligatoria ? 'error' : 'warn'}>{c.ok ? 'Bien' : c.obligatoria ? 'Falta' : 'Aviso'}</Pill>
                      {' '}<strong>{c.nombre}</strong>: {c.detalle}
                      {!c.ok && <p className="muted small">Afecta a: {c.afecta}</p>}
                      {!c.ok && c.arreglo && <p className="small">Cómo arreglarlo: {c.arreglo}</p>}
                    </li>
                  ))}
                </ul>
              </>
            )}
            <h3>Notas de la versión</h3>
            <pre className="report" style={{ whiteSpace: 'pre-wrap' }}>{notas || 'Sin notas.'}</pre>
          </div>
        </Modal>
      )}
    </>
  );
}
