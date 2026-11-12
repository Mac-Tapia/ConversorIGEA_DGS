import { useEffect, useState } from 'react';
import { EVENTO_ARCHIVO, evolucionFijas } from '../api/evolucionFijas';
import { useApp } from '../shared/context';

/**
 * 105:RF-29: la carpeta donde se archivan los informes de esta máquina, como dataset (`config/archivo.json`). Sin ella
 * no se archiva nada; la web nunca supone una ruta.
 */
export function ArchivoInformes() {
  const { run, health } = useApp();
  const [ruta, setRuta] = useState<string | null>(null);
  const [texto, setTexto] = useState('');
  useEffect(() => {
    void run(() => evolucionFijas.archivo()).then((r) => { if (r) { setRuta(r.ruta); setTexto(r.ruta ?? ''); } });
  }, [run]);
  const guardar = async (valor: string | null) => {
    const r = await run(() => evolucionFijas.ponerArchivo(valor));
    if (r) {
      setRuta(r.ruta);
      setTexto(r.ruta ?? '');
      // La pestaña de la evolución dice dónde se archivará: que lo vuelva a leer.
      window.dispatchEvent(new Event(EVENTO_ARCHIVO));
    }
  };
  const rutasLocales = health.server_paths;
  return (
    <section className="card">
      <header className="card-head"><h2>Archivo de informes</h2></header>
      <p className="muted">Carpeta de esta máquina donde se conserva una copia de los libros e informes, por tipo,
        alimentador y periodo. Nunca se borra nada de ella.</p>
      <p>{ruta ? <>Se archiva en <code>{ruta}</code>.</> : 'Sin carpeta: no se archiva nada.'}</p>
      <div className="row">
        <input className="search" value={texto} placeholder="G:/Mi unidad/…" disabled={!rutasLocales}
          aria-label="Carpeta de archivo" onChange={(e) => setTexto(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter' && texto.trim()) void guardar(texto.trim()); }} />
        <button className="btn btn-sm" disabled={!rutasLocales || !texto.trim() || texto.trim() === ruta}
          onClick={() => guardar(texto.trim())}>Guardar</button>
        {ruta && <button className="btn btn-sm btn-ghost" onClick={() => guardar(null)}>Quitar</button>}
      </div>
      {!rutasLocales && <small className="muted">Este servidor no admite rutas locales.</small>}
    </section>
  );
}
