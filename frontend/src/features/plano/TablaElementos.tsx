import { useRef, useState, type KeyboardEvent } from 'react';

import { siguienteIndice, ventanaDeFilas } from './logicaPlano';
import { CLASE, TEXTOS } from './textosPlano';

export interface FilaTabla { clase: string; codigo: string; alimentador: string; detalle: string }

const ALTO_FILA = 30;
const ALTO_VENTANA = 300;

/** 111:RF-1, RF-2, RF-14: la tabla enlazada con el plano, virtualizada (solo pinta su ventana de filas) y con teclado:
 * flechas, Inicio, Fin y página; Intro elige la fila. */
export function TablaElementos({ filas, seleccionado, onElegir }: {
  filas: FilaTabla[];
  seleccionado: string | null;
  onElegir: (codigo: string) => void;
}) {
  const [scroll, setScroll] = useState(0);
  const [foco, setFoco] = useState(0);
  const caja = useRef<HTMLDivElement>(null);
  const v = ventanaDeFilas(scroll, ALTO_VENTANA, ALTO_FILA, filas.length);
  const mover = (e: KeyboardEvent<HTMLDivElement>) => {
    if (e.key === 'Enter' && filas[foco]) { onElegir(filas[foco].codigo); e.preventDefault(); return; }
    const n = siguienteIndice(foco, e.key, filas.length, Math.floor(ALTO_VENTANA / ALTO_FILA));
    if (n === null) return;
    e.preventDefault();
    setFoco(n);
    const c = caja.current;
    if (c && (n * ALTO_FILA < c.scrollTop || (n + 1) * ALTO_FILA > c.scrollTop + ALTO_VENTANA)) {
      c.scrollTop = Math.max(0, n * ALTO_FILA - ALTO_VENTANA / 2);
    }
  };
  return (
    <div ref={caja} className="table-wrap" style={{ maxHeight: ALTO_VENTANA, overflowY: 'auto' }} tabIndex={0}
      role="grid" aria-label={TEXTOS.tabla} aria-rowcount={filas.length + 1}
      aria-activedescendant={filas[foco] ? `plano-fila-${foco}` : undefined}
      onScroll={(e) => setScroll(e.currentTarget.scrollTop)} onKeyDown={mover}>
      <table className="table">
        <thead><tr aria-rowindex={1}><th>{TEXTOS.codigo}</th><th>{TEXTOS.clase}</th><th>{TEXTOS.alimentador}</th><th /></tr></thead>
        <tbody>
          {v.antes > 0 && <tr aria-hidden="true" style={{ height: v.antes }} />}
          {filas.slice(v.inicio, v.fin).map((f, i) => {
            const n = v.inicio + i;
            return (
              <tr key={`${f.clase}|${f.alimentador}|${f.codigo}`} id={`plano-fila-${n}`} aria-rowindex={n + 2}
                aria-selected={f.codigo === seleccionado} className={n === foco ? 'fila-foco' : undefined}
                style={{ height: ALTO_FILA }} onClick={() => { setFoco(n); onElegir(f.codigo); }}>
                <td className="mono">{f.codigo}</td><td>{CLASE[f.clase] ?? f.clase}</td><td>{f.alimentador}</td>
                <td className="muted">{f.detalle}</td>
              </tr>
            );
          })}
          {v.despues > 0 && <tr aria-hidden="true" style={{ height: v.despues }} />}
        </tbody>
      </table>
    </div>
  );
}
