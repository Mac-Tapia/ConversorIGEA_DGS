import { useEffect, useMemo, useRef, useState } from 'react';
import type { PointerEvent as ReactPointerEvent } from 'react';
import { api, fmtNum } from '../api';
import type { CurvaCabecera as Curva } from '../types';

// Coordenadas del viewBox: el SVG se escala al ancho de la caja y conserva la proporción.
const W = 1000;
const H = 280;
const M = { l: 60, r: 14, t: 14, b: 30 };
const HORA = 3_600_000;

/** Fecha ISO sin zona, como la manda el servidor: el registro del medidor es hora local. */
function isoLocal(d: Date): string {
  const p = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`;
}

const dia = (d: Date) => d.toLocaleDateString('es-PE', { day: '2-digit', month: '2-digit', year: '2-digit' });
const diaHora = (d: Date) => `${dia(d)} ${d.toLocaleTimeString('es-PE', { hour: '2-digit', minute: '2-digit' })}`;

/** Valores «redondos» para las marcas del eje del kW. */
function marcas(min: number, max: number, n = 5): number[] {
  const paso0 = (max - min) / n || 1;
  const mag = 10 ** Math.floor(Math.log10(paso0));
  const paso = [1, 2, 2.5, 5, 10].map((k) => k * mag).find((k) => k >= paso0) ?? paso0;
  const out = [];
  for (let v = Math.ceil(min / paso) * paso; v <= max + 1e-9; v += paso) out.push(Number(v.toFixed(6)));
  return out;
}

/** Tramos de puntos seguidos con valor: un kVAR vacío corta la línea, no la lleva a cero. */
function tramos(xs: [number, number | null][]): string[] {
  const out: string[] = [];
  let actual: string[] = [];
  for (const [x, y] of xs) {
    if (y == null) {
      if (actual.length) out.push(actual.join(' '));
      actual = [];
    } else actual.push(`${x.toFixed(1)},${y.toFixed(1)}`);
  }
  if (actual.length) out.push(actual.join(' '));
  return out;
}

/**
 * Curva del registro histórico del medidor de cabecera (spec 006, RF-32 a RF-38).
 *
 * El objetivo del ajuste es un solo registro de todo el histórico: la curva deja ver si
 * esa máxima es un día típico o un pico aislado (una maniobra, una transferencia de
 * carga) que no conviene usar para calibrar. Va del primer registro al último, con el
 * mes de la máxima sombreado; arrastrando sobre la gráfica se pide ese tramo con el
 * detalle de cada registro. Sin zoom con la rueda: la página hace scroll con ella.
 */
export function CurvaCabecera({ wsId, jobId, opciones, inicial }: {
  wsId: string; jobId: string; opciones: { medidor: string; etiqueta: string }[]; inicial: string;
}) {
  const [medidor, setMedidor] = useState(inicial);
  const [tramo, setTramo] = useState<{ desde: string; hasta: string } | null>(null);
  const [kvar, setKvar] = useState(false);
  const [datos, setDatos] = useState<Curva | null>(null);
  const [error, setError] = useState('');
  const [cargando, setCargando] = useState(false);
  const [arrastre, setArrastre] = useState<{ x0: number; x1: number } | null>(null);
  const svg = useRef<SVGSVGElement>(null);

  // Al cambiar el medidor que da el objetivo (otro alimentador, otra elección), se sigue.
  useEffect(() => { setMedidor(inicial); setTramo(null); }, [inicial, jobId]);

  useEffect(() => {
    if (!medidor) return;
    let vigente = true;
    setCargando(true);
    setError('');
    api.demandaCurva(wsId, jobId, medidor, tramo?.desde, tramo?.hasta)
      .then((c) => { if (vigente) setDatos(c); })
      .catch((e: Error) => { if (vigente) { setDatos(null); setError(e.message); } })
      .finally(() => { if (vigente) setCargando(false); });
    return () => { vigente = false; };
  }, [wsId, jobId, medidor, tramo]);

  const g = useMemo(() => {
    if (!datos || !datos.puntos.length) return null;
    const t0 = new Date(tramo?.desde ?? datos.inicio).getTime();
    let t1 = new Date(tramo?.hasta ?? datos.fin).getTime();
    if (t1 <= t0) t1 = t0 + HORA;
    const ys = datos.puntos.flatMap(([, kw, q]) => (kvar && q != null ? [kw, q] : [kw]));
    const yMin = Math.min(0, ...ys);
    const yMax = Math.max(...ys, 1) * 1.06;
    const sx = (t: number) => M.l + ((t - t0) / (t1 - t0)) * (W - M.l - M.r);
    const sy = (v: number) => H - M.b - ((v - yMin) / (yMax - yMin)) * (H - M.t - M.b);
    const ts = datos.puntos.map(([f]) => new Date(f).getTime());
    const kw = tramos(ts.map((t, i) => [sx(t), sy(datos.puntos[i][1])]));
    const q = kvar ? tramos(ts.map((t, i) => [sx(t), datos.puntos[i][2] == null ? null : sy(datos.puntos[i][2]!)])) : [];
    // RF-33: el mes natural de la máxima, recortado a lo que se ve.
    const fm = new Date(datos.maxima.fecha);
    const m0 = Math.max(t0, new Date(fm.getFullYear(), fm.getMonth(), 1).getTime());
    const m1 = Math.min(t1, new Date(fm.getFullYear(), fm.getMonth() + 1, 1).getTime());
    const franja = m1 > m0 ? { x: sx(m0), w: sx(m1) - sx(m0) } : null;
    const tm = fm.getTime();
    const pico = tm >= t0 && tm <= t1 ? { x: sx(tm), y: sy(datos.maxima.kw) } : null;
    const conHora = t1 - t0 <= 3 * 24 * HORA;
    // Con días, las marcas van a medianoche cada N días enteros: repartidas a tiempo igual
    // caían a media jornada y el rótulo del día parecía saltarse fechas (10, 11, 13…).
    const ejeX: { x: number; texto: string }[] = [];
    if (conHora) {
      for (let i = 0; i <= 5; i++) {
        const t = t0 + ((t1 - t0) * i) / 5;
        ejeX.push({ x: sx(t), texto: diaHora(new Date(t)) });
      }
    } else {
      const paso = Math.max(1, Math.ceil((t1 - t0) / (24 * HORA) / 6));
      const d = new Date(t0);
      d.setHours(0, 0, 0, 0);
      if (d.getTime() < t0) d.setDate(d.getDate() + 1);
      for (; d.getTime() <= t1; d.setDate(d.getDate() + paso)) ejeX.push({ x: sx(d.getTime()), texto: dia(d) });
    }
    const ejeY = marcas(yMin, yMax).map((v) => ({ y: sy(v), texto: fmtNum(v) }));
    return { t0, t1, kw, q, franja, pico, ejeX, ejeY, fm, mesTexto: fm.toLocaleDateString('es-PE', { month: 'long', year: 'numeric' }) };
  }, [datos, tramo, kvar]);

  // Coordenada x del viewBox bajo el puntero, dentro del área de la gráfica.
  const xDe = (e: ReactPointerEvent) => {
    const r = svg.current!.getBoundingClientRect();
    return Math.min(W - M.r, Math.max(M.l, ((e.clientX - r.left) / r.width) * W));
  };
  const soltar = () => {
    if (g && arrastre && Math.abs(arrastre.x1 - arrastre.x0) > 6) {
      const t = (x: number) => g.t0 + ((x - M.l) / (W - M.l - M.r)) * (g.t1 - g.t0);
      const [a, b] = [arrastre.x0, arrastre.x1].sort((p, q) => p - q);
      setTramo({ desde: isoLocal(new Date(t(a))), hasta: isoLocal(new Date(t(b))) });
    }
    setArrastre(null);
  };

  return (
    <div className="curva">
      <div className="curva-head">
        <strong>Registro del medidor {datos?.medidor ?? medidor}</strong>
        {opciones.length > 1 && (
          <select value={medidor} onChange={(e) => { setMedidor(e.target.value); setTramo(null); }} aria-label="Medidor de la curva">
            {opciones.map((o) => <option key={o.medidor} value={o.medidor}>{o.etiqueta}</option>)}
          </select>
        )}
        <label className="curva-check">
          <input type="checkbox" checked={kvar} onChange={(e) => setKvar(e.target.checked)} /> kVAR
        </label>
        {kvar && (
          <span className="curva-leyenda small">
            <i className="curva-muestra curva-muestra-kw" /> kW <i className="curva-muestra curva-muestra-kvar" /> kVAR
          </span>
        )}
        {tramo && <button className="btn btn-sm" onClick={() => setTramo(null)}>Ver todo</button>}
        {cargando && <small className="muted">Cargando…</small>}
      </div>
      {error && <p className="alert alert-error">{error}</p>}
      {datos && !datos.puntos.length && <p className="muted">Sin registros en este tramo.</p>}
      {g && datos && (
        <>
          <svg ref={svg} className="curva-svg" viewBox={`0 0 ${W} ${H}`} role="img"
            aria-label={`Curva de kW del medidor ${datos.medidor}; máxima ${fmtNum(datos.maxima.kw, 1)} kW el ${diaHora(g.fm)}`}
            onPointerDown={(e) => { const x = xDe(e); e.currentTarget.setPointerCapture(e.pointerId); setArrastre({ x0: x, x1: x }); }}
            onPointerMove={(e) => { if (arrastre) setArrastre({ ...arrastre, x1: xDe(e) }); }}
            onPointerUp={soltar} onPointerCancel={() => setArrastre(null)}>
            {g.franja && <rect className="curva-franja" x={g.franja.x} y={M.t} width={g.franja.w} height={H - M.t - M.b} />}
            {g.ejeY.map((m) => (
              <g key={m.texto}>
                <line className="curva-rejilla" x1={M.l} x2={W - M.r} y1={m.y} y2={m.y} />
                <text className="curva-texto" x={M.l - 6} y={m.y + 4} textAnchor="end">{m.texto}</text>
              </g>
            ))}
            {g.ejeX.map((m, i) => (
              <text key={i} className="curva-texto" x={m.x} y={H - 8}
                textAnchor={m.x < M.l + 40 ? 'start' : m.x > W - M.r - 40 ? 'end' : 'middle'}>{m.texto}</text>
            ))}
            {g.q.map((pts, i) => <polyline key={`q${i}`} className="curva-kvar" points={pts} />)}
            {g.kw.map((pts, i) => <polyline key={`p${i}`} className="curva-kw" points={pts} />)}
            {g.pico && (
              <g>
                <circle className="curva-pico" cx={g.pico.x} cy={g.pico.y} r={5} />
                <text className="curva-texto curva-pico-texto" x={g.pico.x + (g.pico.x > W * 0.7 ? -9 : 9)} y={Math.max(M.t + 10, g.pico.y - 8)}
                  textAnchor={g.pico.x > W * 0.7 ? 'end' : 'start'}>
                  {fmtNum(datos.maxima.kw, 1)} kW · {diaHora(g.fm)}
                </text>
              </g>
            )}
            {arrastre && (
              <rect className="curva-seleccion" x={Math.min(arrastre.x0, arrastre.x1)} y={M.t}
                width={Math.abs(arrastre.x1 - arrastre.x0)} height={H - M.t - M.b} />
            )}
          </svg>
          <small className="muted">
            {fmtNum(datos.total)} registros {tramo ? 'en el tramo' : `del ${dia(new Date(datos.inicio))} al ${dia(new Date(datos.fin))}`}
            {datos.reducida ? `, mostrados ${fmtNum(datos.puntos.length)} (mínimo y máximo de cada intervalo)` : ''}.
            {' '}Sombreado: {g.mesTexto}, el mes de la máxima. Arrastre sobre la gráfica para ver un tramo con cada registro.
          </small>
          {datos.fuera_de_curva > 0 && (
            <small className="muted">{fmtNum(datos.fuera_de_curva)} registro(s) sin fecha o sin kW numérico, fuera de la curva.</small>
          )}
        </>
      )}
    </div>
  );
}
