import { useEffect, useState } from 'react';
import { api } from '../../api/client';
import { useApp } from '../../shared/context';

type Propuesta = { id: string; titulo?: string; motivo?: string; decision?: string | null;
  suite?: { resumen?: string; codigo?: number } };
type Decision = 'aceptada' | 'rechazada' | 'modificada';

/** El resumen de la suite de la propuesta, en palabras del operador: «12 pruebas bien, 1 con fallo». */
function textoPruebas(resumen: string): string {
  const n = (clave: string) => Number(resumen.match(new RegExp(`(\\d+) ${clave}`))?.[1] ?? 0);
  const bien = n('passed');
  const mal = n('failed') + n('errors?');
  if (!bien && !mal) return 'sin resultado de las pruebas';
  return [bien && `${bien} ${bien === 1 ? 'prueba bien' : 'pruebas bien'}`, mal && `${mal} con fallo`].filter(Boolean).join(', ');
}

/**
 * 026:RF-28 (WEB-RUTAS): el humano decide sobre las mejoras que propone el asistente. Cada propuesta sin
 * decisión, con su motivo y el resultado de su suite, y tres decisiones; el comentario es opcional.
 */
export function MejorasPendientes() {
  const { run } = useApp();
  const [propuestas, setPropuestas] = useState<Propuesta[] | null>(null);
  const [comentario, setComentario] = useState<Record<string, string>>({});
  const [enviando, setEnviando] = useState<string>();

  const cargar = () => void run(api.asistenteRegistro).then((r) => {
    if (r) setPropuestas(((r.mejoras ?? []) as Propuesta[]).filter((p) => !p.decision));
  });
  useEffect(cargar, [run]);

  const decidir = async (p: Propuesta, decision: Decision) => {
    setEnviando(p.id);
    try {
      if (await run(() => api.asistenteDecision(p.id, decision, comentario[p.id] ?? ''))) cargar();
    } finally { setEnviando(undefined); }
  };

  if (!propuestas?.length) return null;
  return (
    <div className="stack">
      <p className="strong">Mejoras propuestas: {propuestas.length}</p>
      {propuestas.map((p) => (
        <div key={p.id} className="card">
          <p><b>{p.titulo ?? p.id}</b>{p.motivo ? ` · ${p.motivo}` : ''}</p>
          {p.suite?.resumen && <p className={p.suite.codigo === 0 ? 'muted' : 'alert alert-warn'}>Pruebas: {textoPruebas(p.suite.resumen)}</p>}
          <input aria-label="Comentario" placeholder="Comentario (opcional)" maxLength={2000}
            value={comentario[p.id] ?? ''} onChange={(e) => setComentario((c) => ({ ...c, [p.id]: e.target.value }))} />
          <div className="row">
            <button className="btn btn-sm" disabled={enviando === p.id} onClick={() => void decidir(p, 'aceptada')}>Aceptar</button>
            <button className="btn btn-sm" disabled={enviando === p.id} onClick={() => void decidir(p, 'modificada')}>Aceptar con cambios</button>
            <button className="btn btn-sm" disabled={enviando === p.id} onClick={() => void decidir(p, 'rechazada')}>Rechazar</button>
          </div>
        </div>
      ))}
    </div>
  );
}
