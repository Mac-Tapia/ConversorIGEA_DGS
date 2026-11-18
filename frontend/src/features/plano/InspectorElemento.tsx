import { Fragment } from 'react';

import type { DeducidoPlano } from '../../api/plano';
import { Pill } from '../../shared/ui';
import { textoValor, type Elemento, type Hallazgo } from './logicaPlano';
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

/** 111:RF-21: el hallazgo con su valor, su umbral, la norma que lo fija (de la biblioteca, por el servidor; si falta,
 * su motivo), el caso y el motor. Ninguna cita se escribe aquí: es la que da el servidor. */
function DelHallazgo({ h }: { h: Hallazgo }) {
  const n = h.norma;
  return (
    <section aria-label={TEXTOS.hallazgo} className="alert alert-warn">
      <p><b>{TEXTOS.hallazgo}</b>: {h.texto}</p>
      <dl className="datos">
        <dt>{TEXTOS.valor}</dt><dd>{textoValor(h.valor, h.unidad)}</dd>
        <dt>{TEXTOS.umbral}</dt><dd>{textoValor(h.umbral, h.unidad)}</dd>
        <dt>{TEXTOS.norma}</dt>
        <dd>{n?.criterio_empresa
          ? <>{TEXTOS.criterioEmpresa}: <span className="mono">{n.criterio_empresa}</span>{n.origen ? ` · ${n.origen}` : ''}</>
          : n && !n.falta
            ? <>{n.acto}{n.articulo ? `, ${n.articulo}` : ''}{n.cita ? <blockquote>{n.cita}</blockquote> : null}</>
            : <span className="muted">{n?.falta ?? 'Sin norma dada por el servidor.'}</span>}</dd>
        <dt>{TEXTOS.caso}</dt><dd>{h.caso}</dd>
        <dt>{TEXTOS.motor}</dt><dd>{h.motor}</dd>
      </dl>
    </section>
  );
}

/** 111:RF-2, RF-3: el elemento con su código de la fuente, su dato original, lo deducido con su motivo y su calidad.
 * RF-20: sus nodos se eligen desde aquí y la selección se quita con un botón (o Escape); RF-21: y su hallazgo. */
export function InspectorElemento({ elemento, hallazgo = null, onElegir, onQuitar }: {
  elemento: Elemento | null;
  hallazgo?: Hallazgo | null;
  onElegir?: (codigo: string) => void;
  onQuitar?: () => void;
}) {
  if (!elemento) return <p className="muted">{TEXTOS.nadaSeleccionado}</p>;
  const nodo = (codigo: string) => (onElegir
    ? <button type="button" className="link mono" onClick={() => onElegir(codigo)}>{codigo}</button>
    : <span className="mono">{codigo}</span>);
  const d = elemento.dato;
  const calidad = 'calidad' in d ? d.calidad : null;
  const avisos = 'avisos' in d ? [...d.avisos, ...d.errores] : [];
  return (
    <div aria-label={TEXTOS.inspector}>
      <p><b>{CLASE[elemento.clase]}</b> <span className="mono">{elemento.codigo}</span> · {elemento.alimentador}
        {calidad && <> <Pill tone={tono(calidad)}>{CALIDAD[calidad] ?? calidad}</Pill></>}
        {onQuitar && <> <button type="button" className="btn btn-sm btn-ghost" onClick={onQuitar}>{TEXTOS.quitarSeleccion}</button></>}</p>
      {hallazgo && <DelHallazgo h={hallazgo} />}
      {elemento.clase === 'tramo' && (
        <>
          <dl className="datos">
            <dt>{TEXTOS.desde}</dt><dd>{nodo(elemento.dato.desde)}</dd>
            <dt>{TEXTOS.hasta}</dt><dd>{nodo(elemento.dato.hasta)}</dd>
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
