import { useMemo } from 'react';

import type { CapasPlano, VistaPlano } from '../../api/plano';
import { bandasPorCodigo, disposicionUnifilar, puntoDe } from './logicaUnifilar';
import { TEXTOS } from './textosPlano';

/**
 * 111:RF-23: el unifilar del alimentador, junto al plano y con la misma selección y los mismos resultados (111:RF-2,
 * RF-10, RF-20). Es un esquema: no cambia las geometrías ni las impedancias, y su forma la da el servidor desde la
 * cabecera. Con el ratón se elige un elemento; con el teclado, el buscador y la tabla eligen el mismo (111:RF-14).
 */
export function UnifilarRed({ vista, elegido, capas, onElegir }: {
  vista: VistaPlano;
  elegido: string | null;
  capas: CapasPlano | null;
  onElegir: (codigo: string) => void;
}) {
  const d = useMemo(() => disposicionUnifilar(vista), [vista]);
  const bandas = useMemo(() => bandasPorCodigo(capas), [capas]);
  const clase = (base: string, codigo: string) => {
    const b = bandas.get(codigo);
    return [base, b ? `unifilar-${b}` : '', codigo === elegido ? 'unifilar-elegido' : ''].filter(Boolean).join(' ');
  };
  // 111:RF-13: un incumplimiento se dice también con texto, no solo con color.
  const texto = (codigo: string, detalle?: string) =>
    [codigo, detalle, bandas.get(codigo) === 'alerta' ? TEXTOS.incumple : ''].filter(Boolean).join(' · ');
  const titulo = `${TEXTOS.unifilar} ${vista.alimentador}`;
  return (
    // Un alimentador largo no cabe: la caja se desplaza, y con el teclado se llega a ella y se recorre (WCAG 2.1.1).
    <div className="unifilar" role="region" aria-label={titulo} tabIndex={0}>
      <svg role="img" aria-labelledby="unifilar-titulo" viewBox={`0 0 ${d.ancho} ${d.alto}`}
        width={d.ancho} height={d.alto} className="unifilar-dibujo">
        <title id="unifilar-titulo">{titulo}</title>
        {d.tramos.map((t) => (
          <line key={t.codigo} data-codigo={t.codigo} className={clase('unifilar-tramo', t.codigo)}
            x1={t.x1} y1={t.y1} x2={t.x2} y2={t.y2} onClick={() => onElegir(t.codigo)}>
            <title>{texto(t.codigo)}</title>
          </line>
        ))}
        {vista.maniobras.map((m) => {
          const p = puntoDe(d, m.barra, m.tramo);
          return p && (
            <rect key={`${m.codigo}|${m.barra ?? ''}|${m.tramo ?? ''}`} data-codigo={m.codigo}
              className={clase(`unifilar-maniobra unifilar-${m.estado}`, m.codigo)}
              x={p.x - 5} y={p.y - 5} width={10} height={10} onClick={() => onElegir(m.codigo)}>
              <title>{texto(m.codigo, m.estado)}</title>
            </rect>
          );
        })}
        {d.barras.map((b) => (
          <circle key={b.codigo} data-codigo={b.codigo} className={clase(b.codigo === d.fuente ? 'unifilar-barra unifilar-fuente' : 'unifilar-barra', b.codigo)}
            cx={b.x} cy={b.y} r={b.codigo === d.fuente ? 7 : 4} onClick={() => onElegir(b.codigo)}>
            <title>{texto(b.codigo, b.codigo === d.fuente ? TEXTOS.cabecera : undefined)}</title>
          </circle>
        ))}
        {vista.sed.map((s) => {
          const p = puntoDe(d, s.barra, s.tramo);
          return p && (
            <path key={s.codigo} data-codigo={s.codigo} className={clase('unifilar-sed', s.codigo)}
              d={`M ${p.x} ${p.y + 6} l 6 10 l -12 0 z`} onClick={() => onElegir(s.codigo)}>
              <title>{texto(s.codigo, 'SED')}</title>
            </path>
          );
        })}
      </svg>
      {(d.sinAlcanzar.length > 0 || d.sinDibujar.length > 0) && (
        <p className="muted" role="status">
          {d.sinAlcanzar.length > 0 && `${TEXTOS.sinAlcanzar}: ${d.sinAlcanzar.length}. `}
          {d.sinDibujar.length > 0 && `${TEXTOS.sinDibujar}: ${d.sinDibujar.length}.`}
        </p>
      )}
    </div>
  );
}
