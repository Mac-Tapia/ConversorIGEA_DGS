import { useCallback, useEffect, useMemo, useState } from 'react';
import { api } from '../api/client';
import type { LibrosNuevos } from '../api/types';
import { useApp } from '../shared/context';

/** Un mes que repite otro o un libro que no se lee pide algo al operador; lo demás informa. */
function esAlerta(texto: string): boolean {
  return /repite los valores|no se pudo|incompleto/.test(texto);
}

/**
 * 104:RF-20, RF-21, RF-22: lo que la web reconoció sola en las carpetas de demanda. Antes había que pulsar
 * «Actualizar índice» y el libro de octubre de 2026 lo revisó una persona a mano.
 */
export function AvisosLibros() {
  const { ws, jobs, run } = useApp();
  const [estado, setEstado] = useState<LibrosNuevos | null>(null);
  const leer = useCallback(() => {
    // Sin libros de demanda no hay nada que reconocer; un fallo aquí no tapa la página (se ve en el Registro).
    if (!Object.keys(ws.demanda ?? {}).length) {
      setEstado(null);
      return;
    }
    api.librosNuevos(ws.id).then(setEstado).catch(() => setEstado(null));
  }, [ws.id, ws.demanda]);
  // Se vuelve a leer al terminar un reconocimiento: llega por el WebSocket como cualquier trabajo.
  const terminados = useMemo(() => Object.values(jobs)
    .filter((j) => j.workspace_id === ws.id && j.kind === 'libros_nuevos' && j.finished_at).length, [jobs, ws.id]);
  useEffect(() => { leer(); }, [leer, terminados]);

  if (!estado) return null;
  const dataset = estado.dataset as { estado?: string; libros_nuevos?: string[]; huella?: string } | null;
  const visto = (id: string) => void run(() => api.librosNuevosVisto(ws.id, id)).then((r) => r && setEstado(r));
  // RF-1: la misma revisión que la periódica, sin esperar al intervalo; con el motor ocupado se hará en la siguiente.
  const revisar = () => void run(() => api.librosNuevosRevisar(ws.id)).then((r) => r && setEstado(r.estado));
  const ultima = estado.ultima_revision ? new Date(estado.ultima_revision * 1000).toLocaleTimeString() : null;
  return (
    <>
      <p className="muted small row">
        Libros de demanda: se revisan solos{estado.intervalo_min ? ` cada ${estado.intervalo_min} min` : ' al abrir el espacio'}
        {ultima && `; última revisión a las ${ultima}`}.{' '}
        <button className="btn btn-sm btn-ghost" onClick={revisar}>Revisar ahora</button>
      </p>
      {estado.avisos.map((a) => (
        <div key={a.id} className={`alert ${esAlerta(a.texto) ? 'alert-warn' : 'alert-info'} stack`} role="status">
          <p><strong>Libro de demanda reconocido.</strong> {a.texto}</p>
          <div className="row">
            <span className="muted small">{new Date(a.cuando * 1000).toLocaleString()}</span>
            <button className="btn btn-sm btn-ghost" onClick={() => visto(a.id)}>Dar por visto</button>
          </div>
        </div>
      ))}
      {dataset?.estado === 'desactualizado' && (
        <p className="alert alert-info" role="status">
          El dataset del pronóstico está desactualizado por {dataset.libros_nuevos?.length ?? 0} libro(s) nuevo(s);
          se regenera solo cuando estén la cabecera y los medidores. No se entrena ningún modelo sin su orden.
        </p>
      )}
      {dataset?.estado === 'regenerando' && (
        <p className="alert alert-info" role="status">Regenerando el dataset del pronóstico con los libros nuevos…</p>
      )}
    </>
  );
}
