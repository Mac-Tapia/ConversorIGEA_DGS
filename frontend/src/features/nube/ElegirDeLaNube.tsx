import { useCallback, useState } from 'react';
import { nube, type CuentaNube, type ProveedorNube } from '../../api/nube';
import { useApp } from '../../shared/context';
import { Modal } from '../../shared/ui';
import { LIBROS, peticionImportar } from './logica';
import { useSelector } from './useSelector';

/**
 * 109:RF-3, RF-4: elegir uno o varios ficheros de la nube y que entren en una casilla o en un libro, como una subida.
 * La descarga es un trabajo del motor: mientras corre una conversión, no se importa.
 */
export function ElegirDeLaNube({ cuentas }: { cuentas: CuentaNube[] }) {
  const { ws, health, active, startJob } = useApp();
  const [abierto, setAbierto] = useState(false);
  const [proveedor, setProveedor] = useState<ProveedorNube>(cuentas[0]?.nombre ?? 'google');
  const [destino, setDestino] = useState('');
  const [error, setError] = useState<string | null>(null);
  const ocupado = Boolean(active.engine);
  const casillas = Object.entries(health.slots).map(([k, s]) => ({ clave: k, etiqueta: s.etiqueta.split(' —')[0] }));

  const alElegir = useCallback(async (ids: string[], p: ProveedorNube) => {
    if (ids.length === 0) return;
    try {
      const cuerpo = peticionImportar(p, ids, destino);
      const job = await startJob(() => nube.importar(ws.id, cuerpo));
      if (job) setAbierto(false);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, [destino, startJob, ws.id]);
  const abrirSelector = useSelector(ws.id, (ids, p) => void alElegir(ids, p), setError);

  return (
    <>
      <button className="btn btn-sm" onClick={() => { setError(null); setAbierto(true); }}>Importar</button>
      {abierto && (
        <Modal title="Importar de la nube" onClose={() => setAbierto(false)} actions={
          <button className="btn btn-primary" disabled={ocupado || !destino}
            onClick={() => { setError(null); abrirSelector(proveedor, 'ficheros'); }}>Elegir fichero</button>}>
          <div className="stack">
            <label className="field"><span>Cuenta</span>
              <select value={proveedor} onChange={(e) => setProveedor(e.target.value as ProveedorNube)}>
                {cuentas.map((c) => <option key={c.nombre} value={c.nombre}>{`${c.visible} · ${c.cuenta ?? ''}`}</option>)}
              </select>
            </label>
            <label className="field"><span>Entra en</span>
              <select value={destino} onChange={(e) => setDestino(e.target.value)}>
                <option value="">Elija…</option>
                <optgroup label="Entradas">
                  {casillas.map((c) => <option key={c.clave} value={`casilla:${c.clave}`}>{c.etiqueta}</option>)}
                </optgroup>
                <optgroup label="Libros de medición">
                  {LIBROS.map((l) => <option key={l.clave} value={`libro:${l.clave}`}>{l.etiqueta}</option>)}
                </optgroup>
              </select>
            </label>
            <small className="muted">Se guarda una copia fija: el estudio no cambia aunque el fichero cambie en la nube.</small>
            {ocupado && <small className="muted">Espere a que termine el trabajo en curso.</small>}
            <div aria-live="polite">{error && <p className="alert alert-error" role="alert">{error}</p>}</div>
          </div>
        </Modal>
      )}
    </>
  );
}
