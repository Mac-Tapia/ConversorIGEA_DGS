import { fmtNum } from '../../shared/formato';
import { useLetraFija } from '../../shared/graficos';

import type { PerfilTension as Perfil } from '../../api/types';

// Coordenadas del viewBox, como la curva de cabecera: el SVG se escala al ancho de la caja.
const W = 1000;
const H = 260;
const M = { l: 60, r: 14, t: 14, b: 30 };

/** Valores «redondos» para las marcas de un eje. */
function marcas(min: number, max: number, n = 5): number[] {
  const paso0 = (max - min) / n || 1;
  const mag = 10 ** Math.floor(Math.log10(paso0));
  const paso = [1, 2, 2.5, 5, 10].map((k) => k * mag).find((k) => k >= paso0) ?? paso0;
  const out = [];
  for (let v = Math.ceil(min / paso) * paso; v <= max + 1e-9; v += paso) out.push(Number(v.toFixed(6)));
  return out;
}

/**
 * Perfil de tensión que dejó la calibración (spec 094, RF-3): cada barra de media por su distancia eléctrica a la
 * cabecera, la troncal unida por una línea y el límite de tensión del perfil de la empresa.
 *
 * AL209 (2026-11-06): el usuario pidió ver todo el perfil del alimentador para juzgar dónde van los bancos; las barras
 * bajo el límite salen en el color de error y la frase de abajo dice cuántas son.
 */
export function PerfilTension({ perfil, feeder }: { perfil: Perfil; feeder: string }) {
  const puntos = perfil.puntos.filter((p) => p.u != null && p.km != null);
  const [letra, estiloLetra] = useLetraFija(W);
  if (!puntos.length) return null;
  const banda = perfil.banda ?? null;
  const kmMax = Math.max(...puntos.map((p) => p.km), 0.001);
  const us = puntos.map((p) => p.u).concat(banda ?? []);
  const uMin = Math.min(...us) - 0.005;
  const uMax = Math.max(...us) + 0.005;
  const x = (km: number) => M.l + ((W - M.l - M.r) * km) / kmMax;
  const y = (u: number) => H - M.b - ((H - M.t - M.b) * (u - uMin)) / (uMax - uMin || 1);
  const porBarra = new Map(puntos.map((p) => [p.barra, p]));
  const troncal = perfil.troncal.map((b) => porBarra.get(b)).filter((p): p is (typeof puntos)[number] => !!p);
  const minima = puntos.reduce((a, b) => (b.u < a.u ? b : a));
  const bajo = banda ? puntos.filter((p) => p.u < banda[0]).length : null;

  return (
    <div className="curva">
      <div className="curva-head">
        <strong>Perfil de tensión de {feeder} tras la calibración</strong>
      </div>
      <svg ref={letra} className="curva-svg" style={estiloLetra} viewBox={`0 0 ${W} ${H}`} role="img"
        aria-label={`Perfil de tensión de ${feeder}: ${puntos.length} barras de media; mínima ${fmtNum(minima.u, 4)} p.u. en ${minima.barra}`}>
        {marcas(uMin, uMax).map((m) => (
          <g key={`u${m}`}>
            <line className="curva-rejilla" x1={M.l} x2={W - M.r} y1={y(m)} y2={y(m)} />
            <text className="curva-texto" x={M.l - 6} y={y(m) + 4} textAnchor="end">{fmtNum(m, 3)}</text>
          </g>
        ))}
        {marcas(0, kmMax).map((m) => (
          <text key={`k${m}`} className="curva-texto" x={x(m)} y={H - 8} textAnchor="middle">{fmtNum(m, 1)} km</text>
        ))}
        {banda && banda.map((u) => (
          <line key={`l${u}`} className="perfil-limite" x1={M.l} x2={W - M.r} y1={y(u)} y2={y(u)} />
        ))}
        {troncal.length > 1 && (
          <polyline className="curva-kw" points={troncal.map((p) => `${x(p.km).toFixed(1)},${y(p.u).toFixed(1)}`).join(' ')} />
        )}
        {puntos.map((p) => (
          <circle key={p.barra} className={banda && p.u < banda[0] ? 'perfil-punto perfil-punto-bajo' : 'perfil-punto'}
            cx={x(p.km)} cy={y(p.u)} r={2.5}>
            <title>{`${p.barra}: ${fmtNum(p.u, 4)} p.u. a ${fmtNum(p.km, 2)} km`}</title>
          </circle>
        ))}
      </svg>
      <small className="muted">
        {fmtNum(puntos.length)} barras de media; mínima {fmtNum(minima.u, 4)} p.u. en {minima.barra}, a {fmtNum(minima.km, 2)} km.
        {' '}La línea es la troncal{perfil.ramales_largos.length ? ` (y hay ${perfil.ramales_largos.length} ramal(es) largo(s))` : ''}.
        {banda && bajo != null
          ? ` Límite del perfil de la empresa: ${fmtNum(banda[0], 2)} a ${fmtNum(banda[1], 2)} p.u.; ${fmtNum(bajo)} barra(s) por debajo.`
          : ' Sin el límite de tensión del perfil de la empresa.'}
      </small>
      {perfil.aviso && <p className="alert alert-warn">{perfil.aviso}</p>}
    </div>
  );
}
