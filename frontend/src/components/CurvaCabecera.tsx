import { useEffect, useMemo, useRef, useState } from 'react';
import type { PointerEvent as ReactPointerEvent } from 'react';
import { api, fmtNum } from '../api';
import type { CentralTermica, CurvaCabecera as Curva } from '../types';

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
/** Una curva de la gráfica: el medidor de cabecera de un alimentador (spec 021, RF-17). */
export interface SerieCurva {
  clave: string;
  etiqueta: string;
  medidor: string;
  /** Spec 021, RF-47: la demanda de un alimentador con central, calculada en el servidor
   * con todos los registros (aguas arriba + aguas abajo); ``medidor`` es su cabecera. */
  demanda?: { alimentador: string; central: CentralTermica };
}

/** Colores de las series: tokens de styles.css, con su versión oscura. */
const COLORES = 8;
const color = (i: number) => `var(--serie-${i % COLORES})`;

/**
 * Curva del registro histórico del medidor de cabecera (spec 006, RF-32 a RF-38).
 *
 * El objetivo del ajuste es un solo registro de todo el histórico: la curva deja ver si
 * esa máxima es un día típico o un pico aislado (una maniobra, una transferencia de
 * carga) que no conviene usar para calibrar. Va del primer registro al último, con el
 * mes de la máxima sombreado; arrastrando sobre la gráfica se pide ese tramo con el
 * detalle de cada registro. Sin zoom con la rueda: la página hace scroll con ella.
 *
 * Con dos o más alimentadores (spec 021, RF-17 a RF-23) van todas en la misma gráfica,
 * con el mismo eje de tiempo: un color por alimentador, su máxima marcada con un punto
 * de su color y una leyenda que oculta o muestra cada curva sin pedirla otra vez. Se
 * pide una curva por alimentador: la que falla no tumba las demás y la leyenda lo dice.
 */
export function CurvaCabecera({ wsId, jobId, opciones, inicial, series = [] }: {
  wsId: string; jobId: string; opciones: { medidor: string; etiqueta: string }[]; inicial: string;
  series?: SerieCurva[];
}) {
  const varias = series.length > 1;
  const [medidor, setMedidor] = useState(inicial);
  const [tramo, setTramo] = useState<{ desde: string; hasta: string } | null>(null);
  const [kvar, setKvar] = useState(false);
  const [datos, setDatos] = useState<Record<string, Curva>>({});
  const [errores, setErrores] = useState<Record<string, string>>({});
  const [ocultas, setOcultas] = useState<Set<string>>(new Set());
  const [cargando, setCargando] = useState(false);
  const [arrastre, setArrastre] = useState<{ x0: number; x1: number } | null>(null);
  const svg = useRef<SVGSVGElement>(null);

  // Al cambiar el medidor que da el objetivo (otro alimentador, otra elección), se sigue.
  useEffect(() => { setMedidor(inicial); setTramo(null); }, [inicial, jobId]);

  // Lo que se dibuja: con varios alimentadores, su serie; con uno, el medidor elegido.
  const pedidas: SerieCurva[] = useMemo(
    () => (varias ? series : medidor ? [{ clave: medidor, etiqueta: medidor, medidor }] : []),
    [varias, series, medidor],
  );
  const firma = pedidas.map((s) => `${s.clave}=${s.medidor}${s.demanda ? '+demanda' : ''}`).join('|');

  useEffect(() => {
    if (!pedidas.length) return;
    let vigente = true;
    setCargando(true);
    // RF-23: cada curva por su lado; la que falla queda con su error y las demás se ven.
    Promise.allSettled(pedidas.map((s) => (s.demanda
      ? api.demandaCurvaCentral(wsId, jobId, s.demanda.alimentador, s.medidor, s.demanda.central, tramo?.desde, tramo?.hasta)
      : api.demandaCurva(wsId, jobId, s.medidor, tramo?.desde, tramo?.hasta))))
      .then((res) => {
        if (!vigente) return;
        const ok: Record<string, Curva> = {};
        const mal: Record<string, string> = {};
        res.forEach((r, i) => {
          if (r.status === 'fulfilled') ok[pedidas[i].clave] = r.value;
          else mal[pedidas[i].clave] = (r.reason as Error)?.message || 'sin curva';
        });
        setDatos(ok);
        setErrores(mal);
      })
      .finally(() => { if (vigente) setCargando(false); });
    return () => { vigente = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [wsId, jobId, firma, tramo]);

  const visibles = pedidas
    .map((s, i) => ({ ...s, color: color(i), curva: datos[s.clave] }))
    .filter((s) => s.curva && s.curva.puntos.length && !ocultas.has(s.clave));
  const una = !varias ? datos[pedidas[0]?.clave ?? ''] : undefined;

  const g = useMemo(() => {
    if (!visibles.length) return null;
    // RF-17: el mismo eje de tiempo para todas, del primer al último registro de ellas.
    const t0 = new Date(tramo?.desde ?? visibles.map((s) => s.curva!.inicio).sort()[0]).getTime();
    let t1 = new Date(tramo?.hasta ?? visibles.map((s) => s.curva!.fin).sort().at(-1)!).getTime();
    if (t1 <= t0) t1 = t0 + HORA;
    const ys = visibles.flatMap((s) => s.curva!.puntos.flatMap(([, kw, q]) => (kvar && q != null ? [kw, q] : [kw])));
    const yMin = Math.min(0, ...ys);
    const yMax = Math.max(...ys, 1) * 1.06;
    const sx = (t: number) => M.l + ((t - t0) / (t1 - t0)) * (W - M.l - M.r);
    const sy = (v: number) => H - M.b - ((v - yMin) / (yMax - yMin)) * (H - M.t - M.b);
    const trazos = visibles.map((s) => {
      const c = s.curva!;
      const ts = c.puntos.map(([f]) => new Date(f).getTime());
      const fm = new Date(c.maxima.fecha);
      const tm = fm.getTime();
      return {
        clave: s.clave, color: s.color, fm, kwMax: c.maxima.kw,
        kw: tramos(ts.map((t, i) => [sx(t), sy(c.puntos[i][1])])),
        q: kvar ? tramos(ts.map((t, i) => [sx(t), c.puntos[i][2] == null ? null : sy(c.puntos[i][2]!)])) : [],
        // RF-19: la máxima de cada alimentador, con un punto de su color.
        pico: tm >= t0 && tm <= t1 ? { x: sx(tm), y: sy(c.maxima.kw) } : null,
      };
    });
    // RF-33 (006): con un solo alimentador, el mes natural de su máxima, recortado.
    let franja: { x: number; w: number } | null = null;
    const fm = trazos[0].fm;
    if (!varias) {
      const m0 = Math.max(t0, new Date(fm.getFullYear(), fm.getMonth(), 1).getTime());
      const m1 = Math.min(t1, new Date(fm.getFullYear(), fm.getMonth() + 1, 1).getTime());
      franja = m1 > m0 ? { x: sx(m0), w: sx(m1) - sx(m0) } : null;
    }
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
    return { t0, t1, trazos, franja, ejeX, ejeY, fm, mesTexto: fm.toLocaleDateString('es-PE', { month: 'long', year: 'numeric' }) };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [datos, ocultas, firma, tramo, kvar, varias]);

  // Coordenada x del viewBox bajo el puntero, dentro del área de la gráfica.
  const xDe = (e: ReactPointerEvent) => {
    const r = svg.current!.getBoundingClientRect();
    return Math.min(W - M.r, Math.max(M.l, ((e.clientX - r.left) / r.width) * W));
  };
  // RF-20: el tramo arrastrado se pide para todas las curvas a la vez.
  const soltar = () => {
    if (g && arrastre && Math.abs(arrastre.x1 - arrastre.x0) > 6) {
      const t = (x: number) => g.t0 + ((x - M.l) / (W - M.l - M.r)) * (g.t1 - g.t0);
      const [a, b] = [arrastre.x0, arrastre.x1].sort((p, q) => p - q);
      setTramo({ desde: isoLocal(new Date(t(a))), hasta: isoLocal(new Date(t(b))) });
    }
    setArrastre(null);
  };
  // RF-21: ocultar o mostrar una curva no la pide otra vez.
  const conmutar = (clave: string) => setOcultas((o) => {
    const n = new Set(o);
    if (n.has(clave)) n.delete(clave); else n.add(clave);
    return n;
  });
  const total = visibles.reduce((n, s) => n + (s.curva?.total ?? 0), 0);
  const fuera = visibles.reduce((n, s) => n + (s.curva?.fuera_de_curva ?? 0), 0);
  const reducida = visibles.some((s) => s.curva?.reducida);
  // Las curvas de una central («NA205·demanda»…) son del mismo alimentador: se cuentan alimentadores.
  const nAlimentadores = new Set(series.map((s) => s.clave.split('·')[0])).size;
  const titulo = varias
    ? (nAlimentadores > 1 ? `Registro de cabecera de ${nAlimentadores} alimentadores` : `Registro de cabecera de ${series[0].clave} con su central`)
    : `Registro del medidor ${una?.medidor ?? medidor}`;
  const errorUnico = !varias ? errores[pedidas[0]?.clave ?? ''] : '';

  return (
    <div className="curva">
      <div className="curva-head">
        <strong>{titulo}</strong>
        {!varias && opciones.length > 1 && (
          <select value={medidor} onChange={(e) => { setMedidor(e.target.value); setTramo(null); }} aria-label="Medidor de la curva">
            {opciones.map((o) => <option key={o.medidor} value={o.medidor}>{o.etiqueta}</option>)}
          </select>
        )}
        <label className="curva-check">
          <input type="checkbox" checked={kvar} onChange={(e) => setKvar(e.target.checked)} /> kVAR
        </label>
        {kvar && !varias && (
          <span className="curva-leyenda small">
            <i className="curva-muestra curva-muestra-kw" /> kW <i className="curva-muestra curva-muestra-kvar" /> kVAR
          </span>
        )}
        {kvar && varias && <span className="curva-leyenda small">kVAR en trazo discontinuo</span>}
        {tramo && <button className="btn btn-sm" onClick={() => setTramo(null)}>Ver todo</button>}
        {cargando && <small className="muted">Cargando…</small>}
      </div>
      {varias && (
        <div className="curva-series" role="group" aria-label="Alimentadores de la gráfica">
          {series.map((s, i) => (
            errores[s.clave]
              ? <span key={s.clave} className="curva-serie-falta">{s.etiqueta}: sin curva ({errores[s.clave]})</span>
              : (
                <button key={s.clave} type="button" className="curva-serie-btn" aria-pressed={!ocultas.has(s.clave)}
                  onClick={() => conmutar(s.clave)} title={ocultas.has(s.clave) ? 'Mostrar su curva' : 'Ocultar su curva'}>
                  <i className="curva-muestra" style={{ background: color(i) }} />
                  {s.etiqueta}
                  {datos[s.clave] ? ` · máx. ${fmtNum(datos[s.clave].maxima.kw, 1)} kW el ${diaHora(new Date(datos[s.clave].maxima.fecha))}` : ''}
                </button>
              )
          ))}
        </div>
      )}
      {errorUnico && <p className="alert alert-error">{errorUnico}</p>}
      {!varias && una && !una.puntos.length && <p className="muted">Sin registros en este tramo.</p>}
      {varias && !g && !cargando && Object.keys(datos).length > 0 && (
        <p className="muted">{ocultas.size ? 'Todas las curvas están ocultas: pulse un alimentador para verlo.' : 'Sin registros en este tramo.'}</p>
      )}
      {g && (
        <>
          <svg ref={svg} className="curva-svg" viewBox={`0 0 ${W} ${H}`} role="img"
            aria-label={varias
              ? `Curvas de kW de ${g.trazos.length} alimentadores`
              : `Curva de kW del medidor ${una?.medidor ?? medidor}; máxima ${fmtNum(g.trazos[0].kwMax, 1)} kW el ${diaHora(g.fm)}`}
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
            {g.trazos.map((s) => (
              varias ? (
                <g key={s.clave}>
                  {s.q.map((pts, i) => <polyline key={`q${i}`} className="curva-serie-kvar" stroke={s.color} points={pts} />)}
                  {s.kw.map((pts, i) => <polyline key={`p${i}`} className="curva-serie" stroke={s.color} points={pts} />)}
                </g>
              ) : (
                <g key={s.clave}>
                  {s.q.map((pts, i) => <polyline key={`q${i}`} className="curva-kvar" points={pts} />)}
                  {s.kw.map((pts, i) => <polyline key={`p${i}`} className="curva-kw" points={pts} />)}
                </g>
              )
            ))}
            {g.trazos.map((s) => s.pico && (
              varias
                ? <circle key={`m${s.clave}`} className="curva-pico-serie" cx={s.pico.x} cy={s.pico.y} r={5} fill={s.color} />
                : (
                  <g key={`m${s.clave}`}>
                    <circle className="curva-pico" cx={s.pico.x} cy={s.pico.y} r={5} />
                    <text className="curva-texto curva-pico-texto" x={s.pico.x + (s.pico.x > W * 0.7 ? -9 : 9)} y={Math.max(M.t + 10, s.pico.y - 8)}
                      textAnchor={s.pico.x > W * 0.7 ? 'end' : 'start'}>
                      {fmtNum(s.kwMax, 1)} kW · {diaHora(s.fm)}
                    </text>
                  </g>
                )
            ))}
            {arrastre && (
              <rect className="curva-seleccion" x={Math.min(arrastre.x0, arrastre.x1)} y={M.t}
                width={Math.abs(arrastre.x1 - arrastre.x0)} height={H - M.t - M.b} />
            )}
          </svg>
          <small className="muted">
            {fmtNum(total)} registros {tramo ? 'en el tramo' : `del ${dia(new Date(g.t0))} al ${dia(new Date(g.t1))}`}
            {reducida ? ', mostrados el mínimo y el máximo de cada intervalo' : ''}.
            {' '}{varias
              ? 'El punto de cada color es la máxima de ese alimentador. '
              : `Sombreado: ${g.mesTexto}, el mes de la máxima. `}
            Arrastre sobre la gráfica para ver un tramo con cada registro.
          </small>
          {fuera > 0 && (
            <small className="muted">{fmtNum(fuera)} registro(s) sin fecha o sin kW numérico, fuera de la curva.</small>
          )}
        </>
      )}
    </div>
  );
}
