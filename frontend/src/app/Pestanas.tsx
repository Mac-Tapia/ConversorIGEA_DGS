import { useRef, type KeyboardEvent, type ReactNode } from 'react';
import { indicePorTecla } from './teclado';

/** Una pestaña de los módulos: su clave, lo que se lee en ella y los avisos que esperan en su paso. */
export interface Pestana { id: string; etiqueta: ReactNode; avisos?: number }

export const idPestana = (id: string) => `pestana-${id}`;
export const idPanel = (id: string) => `panel-${id}`;

/**
 * Las pestañas de los módulos con el patrón de pestañas de WAI-ARIA (WCAG 2.2 AA, 2.1.1, 2.4.3 y 4.1.2):
 * un solo punto de tabulación (la elegida), ← → Inicio y Fin mueven el foco, y Intro o Espacio la abren.
 * La activación es manual: abrir una pestaña monta su panel y puede pedir datos al servidor, así que pasar por
 * ella con las flechas no la abre. ``montadas``: las que tienen panel en la página; solo a esas apunta
 * ``aria-controls``, porque un id que no existe es un error de ARIA.
 */
export function PestanasModulos({ pestanas, actual, montadas, onElegir }: {
  pestanas: Pestana[]; actual: string; montadas: ReadonlySet<string>; onElegir: (id: string) => void;
}) {
  const botones = useRef(new Map<string, HTMLButtonElement>());
  const alPulsar = (e: KeyboardEvent<HTMLButtonElement>, i: number) => {
    const j = indicePorTecla(pestanas.length, i, e.key);
    if (j === null) return;
    e.preventDefault();
    botones.current.get(pestanas[j].id)?.focus();
  };
  return (
    <div className="tabs" role="tablist" aria-label="Módulos">
      {pestanas.map((t, i) => {
        const elegida = t.id === actual;
        const n = t.avisos ?? 0;
        return (
          <button key={t.id} type="button" role="tab" id={idPestana(t.id)} aria-selected={elegida}
            aria-controls={montadas.has(t.id) ? idPanel(t.id) : undefined} tabIndex={elegida ? 0 : -1}
            className={elegida ? 'on' : ''}
            ref={(el) => { if (el) botones.current.set(t.id, el); else botones.current.delete(t.id); }}
            onKeyDown={(e) => alPulsar(e, i)} onClick={() => onElegir(t.id)}>
            {t.etiqueta}
            {n > 0 && <> <span className="badge warn" title="Trabajos que no terminaron bien en esta pestaña">
              <span aria-hidden="true">⚠ </span>{n} aviso{n > 1 ? 's' : ''}</span></>}
          </button>
        );
      })}
    </div>
  );
}

/** El panel de una pestaña, enlazado con ella; oculto si no es la elegida, para no perder lo que tenía. */
export function PanelPestana({ id, hidden, children }: { id: string; hidden: boolean; children: ReactNode }) {
  return (
    <div role="tabpanel" id={idPanel(id)} aria-labelledby={idPestana(id)} hidden={hidden} tabIndex={hidden ? -1 : 0}>
      {children}
    </div>
  );
}
