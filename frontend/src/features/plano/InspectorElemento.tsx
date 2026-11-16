import { Fragment } from 'react';

import type { DeducidoPlano } from '../../api/plano';
import { Pill } from '../../shared/ui';
import type { Elemento } from './logicaPlano';
import { CALIDAD, CLASE, TEXTOS } from './textosPlano';

const tono = (c: string) => (c === 'ok' ? 'ok' : c === 'aviso' ? 'warn' : c === 'error' ? 'error' : 'muted');
const valor = (v: unknown) => (v === null || v === undefined || v === '' ? '—' : String(v));

function Deducidos({ filas }: { filas: DeducidoPlano[] }) {
  if (!filas.length) return null;
  return (
    <>
      <h4>{TEXTOS.deducido}</h4>
      <ul className="lista-compacta">
        {filas.map((d, i) => (
          <li key={`${d.campo}-${i}`}><b>{d.campo}</b>: {valor(d.original)} → {valor(d.valor)}. {d.motivo}</li>
        ))}
      </ul>
    </>
  );
}

/** 111:RF-2, RF-3: el elemento con su código de la fuente, su dato original, lo deducido con su motivo y su calidad. */
export function InspectorElemento({ elemento }: { elemento: Elemento | null }) {
  if (!elemento) return <p className="muted">{TEXTOS.nadaSeleccionado}</p>;
  const d = elemento.dato;
  const calidad = 'calidad' in d ? d.calidad : null;
  const avisos = 'avisos' in d ? [...d.avisos, ...d.errores] : [];
  return (
    <div aria-label={TEXTOS.inspector}>
      <p><b>{CLASE[elemento.clase]}</b> <span className="mono">{elemento.codigo}</span> · {elemento.alimentador}
        {calidad && <> <Pill tone={tono(calidad)}>{CALIDAD[calidad] ?? calidad}</Pill></>}</p>
      {elemento.clase === 'tramo' && (
        <>
          <dl className="datos">
            <dt>{TEXTOS.desde}</dt><dd className="mono">{elemento.dato.desde}</dd>
            <dt>{TEXTOS.hasta}</dt><dd className="mono">{elemento.dato.hasta}</dd>
            <dt>{TEXTOS.conductor}</dt><dd>{elemento.dato.tipo}</dd>
            <dt>{TEXTOS.fases}</dt><dd>{elemento.dato.fases}</dd>
            <dt>Longitud</dt><dd>{elemento.dato.longitud_m.toLocaleString('es-PE', { maximumFractionDigits: 1 })} m</dd>
          </dl>
          <h4>{TEXTOS.original}</h4>
          <dl className="datos">
            {Object.entries(elemento.dato.original).map(([k, v]) => <Fragment key={k}><dt>{k}</dt><dd>{valor(v)}</dd></Fragment>)}
          </dl>
        </>
      )}
      {elemento.clase === 'maniobra' && <p>{elemento.dato.clase} · {elemento.dato.estado}</p>}
      {elemento.clase === 'sed' && <p>{elemento.dato.kva == null ? '' : `${elemento.dato.kva} kVA`}</p>}
      {(elemento.clase === 'tramo' || elemento.clase === 'barra') && <Deducidos filas={elemento.dato.deducido} />}
      {avisos.length > 0 && <ul className="lista-compacta">{avisos.map((a) => <li key={a}>{a}</li>)}</ul>}
    </div>
  );
}
