import { useEffect, useMemo, useState } from 'react';
import { evolucionFijas, type CurvaClienteFijo } from '../../api/evolucionFijas';
import { fmtNum } from '../../shared/formato';
import { colorSerie, marcas, tramos, useLetraFija } from '../../shared/graficos';
import { fmtInstante, nombreMes, reducir, type SerieMensual } from './datosTablero';

const W = 1000;
const H = 260;
const M = { l: 64, r: 14, t: 14, b: 30 };

/** Líneas por mes, una por cliente y los totales en trazo grueso (105:RF-23). Un mes sin dato corta la línea. */
export function GraficoMensual({ titulo, unidad, meses, series }: {
  titulo: string; unidad: string; meses: string[]; series: SerieMensual[];
}) {
  const [ocultas, setOcultas] = useState<Set<string>>(new Set());
  const visibles = series.filter((s) => !ocultas.has(s.clave));
  const g = useMemo(() => {
    const ys = visibles.flatMap((s) => s.valores.filter((v): v is number => v != null));
    if (!ys.length || !meses.length) return null;
    const yMax = Math.max(...ys, 0) * 1.08 || 1;
    const yMin = Math.min(0, ...ys);
    const sx = (i: number) => M.l + (meses.length === 1 ? 0.5 : i / (meses.length - 1)) * (W - M.l - M.r);
    const sy = (v: number) => H - M.b - ((v - yMin) / (yMax - yMin)) * (H - M.t - M.b);
    return {
      sx, sy, ejeY: marcas(yMin, yMax).map((v) => ({ y: sy(v), texto: fmtNum(v) })),
      trazos: visibles.map((s) => ({ ...s, color: colorSerie(series.indexOf(s)),
        lineas: tramos(s.valores.map((v, i) => [sx(i), v == null ? null : sy(v)])),
        puntos: s.valores.map((v, i) => (v == null ? null : { x: sx(i), y: sy(v), v })) })),
    };
  }, [visibles, meses, series]);
  const [letra, estiloLetra] = useLetraFija(W);
  const conmutar = (clave: string) => setOcultas((o) => {
    const n = new Set(o);
    if (!n.delete(clave)) n.add(clave);
    return n;
  });
  return (
    <div className="curva">
      <div className="curva-head"><strong>{titulo} ({unidad})</strong></div>
      <div className="curva-series" role="group" aria-label={`Series de ${titulo}`}>
        {series.map((s, i) => (
          <button key={s.clave} type="button" className="curva-serie-btn" aria-pressed={!ocultas.has(s.clave)}
            onClick={() => conmutar(s.clave)} title={ocultas.has(s.clave) ? 'Mostrar' : 'Ocultar'}>
            <i className="curva-muestra" style={{ background: colorSerie(i), height: s.total ? 4 : 2 }} />{s.etiqueta}
          </button>
        ))}
      </div>
      {!g ? <p className="muted">Sin datos que dibujar.</p> : (
        <svg ref={letra} className="curva-svg" style={estiloLetra} viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`${titulo} de ${meses.length} meses`}>
          {g.ejeY.map((m) => (
            <g key={m.texto}>
              <line className="curva-rejilla" x1={M.l} x2={W - M.r} y1={m.y} y2={m.y} />
              <text className="curva-texto" x={M.l - 6} y={m.y + 4} textAnchor="end">{m.texto}</text>
            </g>
          ))}
          {meses.map((m, i) => (
            <text key={m} className="curva-texto" x={g.sx(i)} y={H - 8} textAnchor="middle">{nombreMes(m)}</text>
          ))}
          {g.trazos.map((s) => (
            <g key={s.clave}>
              {s.lineas.map((pts, k) => (
                <polyline key={k} className="curva-serie" stroke={s.color} strokeWidth={s.total ? 3 : 1.5}
                  strokeDasharray={s.total ? '6 3' : undefined} points={pts} />
              ))}
              {s.puntos.map((p, k) => p && (
                <circle key={k} cx={p.x} cy={p.y} r={s.total ? 4 : 3} fill={s.color}>
                  <title>{`${s.etiqueta} · ${nombreMes(meses[k])}: ${fmtNum(p.v, 1)} ${unidad}`}</title>
                </circle>
              ))}
            </g>
          ))}
        </svg>
      )}
    </div>
  );
}

/** La curva de 15 minutos de un cliente, P y Q, pedida al elegirlo (105:RF-25). */
export function CurvaCliente({ wsId, cliente }: { wsId: string; cliente: string }) {
  const [curva, setCurva] = useState<CurvaClienteFijo | null>(null);
  const [error, setError] = useState('');
  useEffect(() => {
    let vigente = true;
    setCurva(null);
    setError('');
    evolucionFijas.curva(wsId, cliente)
      .then((c) => { if (vigente) setCurva(c); })
      .catch((e) => { if (vigente) setError(e instanceof Error ? e.message : String(e)); });
    return () => { vigente = false; };
  }, [wsId, cliente]);
  const g = useMemo(() => {
    if (!curva?.puntos.length) return null;
    const pts = reducir(curva.puntos as [string, number, number | null][]);
    const ts = pts.map(([t]) => Date.parse(`${t}:00Z`));
    const t0 = ts[0];
    const t1 = Math.max(ts[ts.length - 1], t0 + 1);
    const ys = pts.flatMap(([, p, q]) => (q == null ? [p] : [p, q]));
    const yMin = Math.min(0, ...ys);
    const yMax = Math.max(...ys, 1) * 1.06;
    const sx = (t: number) => M.l + ((t - t0) / (t1 - t0)) * (W - M.l - M.r);
    const sy = (v: number) => H - M.b - ((v - yMin) / (yMax - yMin)) * (H - M.t - M.b);
    let i = 0;
    curva.puntos.forEach((p, k) => { if (p[1] > curva.puntos[i][1]) i = k; });
    const pico = curva.puntos[i];
    const ejeX = Array.from({ length: 6 }, (_v, k) => {
      const t = t0 + ((t1 - t0) * k) / 5;
      return { x: sx(t), texto: fmtInstante(new Date(t).toISOString().slice(0, 10)) };
    });
    return {
      p: tramos(pts.map(([, p], k) => [sx(ts[k]), sy(p)])),
      q: tramos(pts.map(([, , q], k) => [sx(ts[k]), q == null ? null : sy(q)])),
      ejeY: marcas(yMin, yMax).map((v) => ({ y: sy(v), texto: fmtNum(v) })), ejeX,
      pico: { x: sx(Date.parse(`${pico[0]}:00Z`)), y: sy(pico[1]), v: pico[1], t: pico[0] },
      reducida: pts.length < curva.puntos.length,
    };
  }, [curva]);
  const [letra, estiloLetra] = useLetraFija(W);
  if (error) return <p className="alert alert-error">{error}</p>;
  if (!curva) return <p className="muted">Cargando la curva de {cliente}…</p>;
  if (!g) return <p className="muted">{cliente} no tiene registros.</p>;
  return (
    <div className="curva">
      <span className="curva-leyenda small">
        <i className="curva-muestra curva-muestra-kw" /> P (kW) <i className="curva-muestra curva-muestra-kvar" /> Q (kVAR)
      </span>
      <svg ref={letra} className="curva-svg" style={estiloLetra} viewBox={`0 0 ${W} ${H}`} role="img"
        aria-label={`Curva de 15 minutos de ${cliente}; máxima ${fmtNum(g.pico.v, 1)} kW el ${fmtInstante(g.pico.t)}`}>
        {g.ejeY.map((m) => (
          <g key={m.texto}>
            <line className="curva-rejilla" x1={M.l} x2={W - M.r} y1={m.y} y2={m.y} />
            <text className="curva-texto" x={M.l - 6} y={m.y + 4} textAnchor="end">{m.texto}</text>
          </g>
        ))}
        {g.ejeX.map((m, k) => (
          <text key={k} className="curva-texto" x={m.x} y={H - 8} textAnchor={k === 0 ? 'start' : k === 5 ? 'end' : 'middle'}>{m.texto}</text>
        ))}
        {g.q.map((pts, k) => <polyline key={`q${k}`} className="curva-kvar" points={pts} />)}
        {g.p.map((pts, k) => <polyline key={`p${k}`} className="curva-kw" points={pts} />)}
        <circle className="curva-pico" cx={g.pico.x} cy={g.pico.y} r={5} />
        <text className="curva-texto curva-pico-texto" x={g.pico.x + (g.pico.x > W * 0.7 ? -9 : 9)} y={Math.max(M.t + 10, g.pico.y - 8)}
          textAnchor={g.pico.x > W * 0.7 ? 'end' : 'start'}>{fmtNum(g.pico.v, 1)} kW · {fmtInstante(g.pico.t)}</text>
      </svg>
      <small className="muted">{fmtNum(curva.puntos.length)} registros de 15 minutos
        {g.reducida ? '; se dibujan el mínimo y el máximo de cada intervalo' : ''}.</small>
    </div>
  );
}
