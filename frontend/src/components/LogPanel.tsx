import { useEffect, useRef, useState } from 'react';
import type { LogLine } from '../useWorkspace';

const lineTone = (t: string) =>
  /^\s*(FAIL|ERROR|Traceback)|error:/i.test(t) ? 'log-error'
    : /^\s*(AVISO|WARN|OMITIDO)/i.test(t) ? 'log-warn'
      : /^\s*OK\b/.test(t) ? 'log-ok'
        : /^---/.test(t) ? 'log-sec' : '';

export function LogPanel({ lines, onClear, connected }: { lines: LogLine[]; onClear: () => void; connected: boolean }) {
  const box = useRef<HTMLDivElement>(null);
  const [follow, setFollow] = useState(true);
  const [filter, setFilter] = useState('');

  useEffect(() => {
    if (follow && box.current) box.current.scrollTop = box.current.scrollHeight;
  }, [lines, follow]);

  const shown = filter ? lines.filter((l) => l.text.toLowerCase().includes(filter.toLowerCase())) : lines;

  return (
    <section className="log" aria-label="Registro">
      <header className="log-head">
        <strong>Registro</strong>
        <span className={`dot ${connected ? 'dot-on' : ''}`} title={connected ? 'Conectado en vivo' : 'Reconectando…'} />
        <input className="search search-sm" type="search" placeholder="Buscar en el registro…" value={filter}
          onChange={(e) => setFilter(e.target.value)} />
        <label className="small"><input type="checkbox" checked={follow} onChange={(e) => setFollow(e.target.checked)} /> Seguir</label>
        <button className="link small" onClick={() => {
          const blob = new Blob([lines.map((l) => l.text).join('\n')], { type: 'text/plain' });
          const a = document.createElement('a');
          a.href = URL.createObjectURL(blob);
          a.download = 'registro_igea_dgs.txt';
          a.click();
          URL.revokeObjectURL(a.href);
        }}>Guardar</button>
        <button className="link small" onClick={onClear}>Limpiar</button>
      </header>
      <div className="log-body" ref={box}
        onScroll={(e) => {
          const el = e.currentTarget;
          setFollow(el.scrollHeight - el.scrollTop - el.clientHeight < 24);
        }}>
        {shown.length === 0
          ? <span className="muted">Sin actividad todavía.</span>
          : shown.map((l, i) => <div key={`${l.seq}-${i}`} className={lineTone(l.text)}>{l.text || ' '}</div>)}
      </div>
    </section>
  );
}
