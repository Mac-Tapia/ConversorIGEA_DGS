import { useState, type ReactNode } from 'react';
import { api } from '../api/client';
import type { Diagnostico } from '../api/types';
import { Modal, Pill } from '../shared/ui';

/** Las pendientes primero: con todo bien, lo importante es lo que falta, no la lista de lo que está. */
function ordenar(d: Diagnostico) {
  return [...d.comprobaciones].sort((a, b) => Number(a.ok) - Number(b.ok) || Number(b.obligatoria) - Number(a.obligatoria));
}

export type BloqueNotas =
  | { tipo: 'titulo'; nivel: number; texto: string }
  | { tipo: 'lista'; items: string[] }
  | { tipo: 'parrafo'; texto: string };

const TITULO_SECCION = 'notas de la versión';

/**
 * 111 T17 (M2): el Markdown de las notas en bloques sencillos (títulos, listas y párrafos). El título de primer nivel
 * que repite el de la sección se omite. El texto se pinta con React, que lo escapa: nunca se interpreta como HTML.
 */
export function bloquesMarkdown(texto: string): BloqueNotas[] {
  const bloques: BloqueNotas[] = [];
  let parrafo: string[] = [];
  let lista: string[] | null = null;
  const cerrar = () => {
    if (parrafo.length) bloques.push({ tipo: 'parrafo', texto: parrafo.join(' ') });
    if (lista) bloques.push({ tipo: 'lista', items: lista });
    parrafo = [];
    lista = null;
  };
  for (const linea of texto.replace(/\r\n?/g, '\n').split('\n')) {
    const l = linea.trim();
    const titulo = l.match(/^(#{1,6})\s+(.*)$/);
    const item = l.match(/^(?:[-*+]|\d+[.)])\s+(.*)$/);
    if (!l) cerrar();
    else if (titulo) {
      cerrar();
      const nivel = titulo[1].length;
      if (!(nivel === 1 && titulo[2].trim().toLowerCase() === TITULO_SECCION)) {
        bloques.push({ tipo: 'titulo', nivel, texto: titulo[2].trim() });
      }
    } else if (item) {
      if (parrafo.length) { bloques.push({ tipo: 'parrafo', texto: parrafo.join(' ') }); parrafo = []; }
      (lista ??= []).push(item[1]);
    } else if (lista && /^\s/.test(linea)) lista[lista.length - 1] += ` ${l}`;
    else {
      if (lista) { bloques.push({ tipo: 'lista', items: lista }); lista = null; }
      parrafo.push(l);
    }
  }
  cerrar();
  return bloques;
}

/** Negritas y código en línea; el resto, texto tal cual (escapado por React). */
function enLinea(texto: string): ReactNode[] {
  return texto.split(/(\*\*[^*]+\*\*|\x60[^\x60]+\x60)/).filter(Boolean).map((p, i) => {
    if (p.startsWith('**') && p.endsWith('**') && p.length > 4) return <strong key={i}>{p.slice(2, -2)}</strong>;
    if (p.startsWith('\x60') && p.endsWith('\x60') && p.length > 2) return <code key={i}>{p.slice(1, -1)}</code>;
    return p;
  });
}

/**
 * 111 T17 (D3, M2): las notas con formato, en una zona desplazable que se alcanza con Tab (WCAG 2.1.1) y se nombra.
 * Los títulos bajan a h4 y h5: el diálogo ya tiene su h2 y la sección, su h3.
 */
export function NotasVersion({ texto }: { texto: string }) {
  const bloques = bloquesMarkdown(texto);
  return (
    <div className="report notas-version" tabIndex={0} role="region" aria-label="Notas de la versión">
      {!bloques.length && <p>Sin notas.</p>}
      {bloques.map((b, i) => {
        if (b.tipo === 'titulo') return b.nivel <= 2 ? <h4 key={i}>{enLinea(b.texto)}</h4> : <h5 key={i}>{enLinea(b.texto)}</h5>;
        if (b.tipo === 'lista') return <ul key={i}>{b.items.map((it, j) => <li key={j}>{enLinea(it)}</li>)}</ul>;
        return <p key={i}>{enLinea(b.texto)}</p>;
      })}
    </div>
  );
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
            <NotasVersion texto={notas} />
          </div>
        </Modal>
      )}
    </>
  );
}
