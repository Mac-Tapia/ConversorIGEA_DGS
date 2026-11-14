import { useEffect, useState } from 'react';
import { api } from '../../api/client';
import type { AvanceDisco, ClaveTipoAnalisis, TipoAnalisis, TiposAnalisis } from '../../api/types';

/** Dónde está cada paso en «Cargas en DIgSILENT»: los `id` de sus secciones (072:RF-33). */
export const DESTINO = {
  proyecto: 'paso-proyecto', calibracion: 'paso-calibracion', nuevas: 'paso-nuevas', obras: 'paso-obras',
  estudios: 'paso-estudios', informes: 'paso-informes', planificacion: 'paso-planificacion',
  obrasAutomaticas: 'paso-obras-automaticas',
} as const;

/** Lo que ya consta del proyecto en la sesión, leído de sus trabajos (072:RF-33). */
export interface EstadoPasos {
  proyecto: boolean;
  alimentadores: boolean;
  calibrado: boolean;
  cargas: boolean;
  conProyecto: boolean;
  informes: boolean;
  pide: boolean;
  largo: boolean;
}

/**
 * 072:RF-33: lo de la sesión o lo guardado en disco, de los alimentadores marcados. Con solo la sesión, tras
 * reiniciar la web, CA101_CHN102 (2026-11-13) ya calibrado y con su carga nueva salía con todo «pendiente».
 */
export function estadoConDisco(e: EstadoPasos, avance: AvanceDisco | null, order: string[]): EstadoPasos {
  if (!avance) return e;
  const marcado = (f: string) => order.includes(f);
  return {
    ...e,
    cargas: e.cargas || avance.cargas.some((c) => marcado(c.alimentador)),
    conProyecto: e.conProyecto || avance.obras,
    informes: e.informes || avance.informes.some((i) => i.alimentadores.some(marcado)),
  };
}

function irA(destino: string) {
  const el = document.getElementById(destino);
  if (!el) return;
  el.scrollIntoView({ behavior: 'smooth', block: 'start' });
  el.focus({ preventScroll: true });
}

/**
 * 072:RF-33: con los alimentadores marcados ya calibrados, el camino directo a lo que sigue: 4.2 si falta el flujo de
 * «Con proyecto» de alguno y 4.4 para el informe. No salta nada: los pasos anteriores siguen ahí para recalibrar.
 */
export function SeguirDondeQuedo({ avance, calibrados, order }: {
  avance: AvanceDisco | null; calibrados: string[]; order: string[];
}) {
  const listos = order.filter((f) => calibrados.includes(f));
  if (!order.length || listos.length < order.length) return null;
  const cargas = (avance?.cargas ?? []).filter((c) => order.includes(c.alimentador));
  const sinFlujo = order.filter((f) => !(avance?.estudiados ?? []).includes(f));
  const informes = (avance?.informes ?? []).filter((i) => i.alimentadores.some((a) => order.includes(a)));
  return (
    <div className="callout" role="status">
      <strong>Seguir donde quedó</strong>
      <ul className="small">
        <li>Calibrados en «Sin proyecto»: {listos.join(', ')}.</li>
        <li>{cargas.length
          ? `Cargas nuevas aplicadas: ${cargas.map((c) => `${c.sed} (${c.alimentador}${c.sola ? '' : ', en bloque'})`).join(', ')}.`
          : 'Sin cargas nuevas aplicadas.'}</li>
        <li>{sinFlujo.length
          ? `Falta el flujo de «Con proyecto» de ${sinFlujo.join(', ')} (4.2).`
          : `Flujos de «Con proyecto» ya corridos: ${order.join(', ')}.`}</li>
        {informes.length > 0 && <li>Informes ya escritos: {informes.map((i) => i.docx).join(', ')}.</li>}
      </ul>
      <div className="row">
        <button type="button" className="btn btn-sm" onClick={() => irA(DESTINO.obrasAutomaticas)}>Ir a obras automáticas</button>
        <button type="button" className="btn btn-sm" onClick={() => irA(DESTINO.estudios)}>Ir a 4.2 · Estudios</button>
        <button type="button" className={`btn btn-sm${sinFlujo.length ? ' btn-ghost' : ''}`}
          onClick={() => irA(DESTINO.informes)}>Ir a 4.4 · Preparar informe</button>
      </div>
      <small className="muted">Para recalibrar o cambiar cargas, los pasos 2 y 3 siguen abajo.</small>
    </div>
  );
}

export interface Paso {
  clave: string;
  titulo: string;
  destino: string;
  /** `null`: opcional, no cuenta como pendiente. */
  hecho: boolean | null;
  nota?: string;
}

const CLAVE_GUARDADA = 'csg.tipoDeAnalisis';
const CLAVES: readonly ClaveTipoAnalisis[] = ['corto_plazo', 'pide', 'largo_plazo'];

/** El tipo elegido la última vez en este navegador; sin almacenamiento (navegación privada), ninguno. */
export function tipoGuardado(): ClaveTipoAnalisis | null {
  try {
    const v = localStorage.getItem(CLAVE_GUARDADA);
    return CLAVES.includes(v as ClaveTipoAnalisis) ? (v as ClaveTipoAnalisis) : null;
  } catch { return null; }
}

export function guardarTipo(t: ClaveTipoAnalisis): void {
  try { localStorage.setItem(CLAVE_GUARDADA, t); } catch { /* sin almacenamiento: se elige cada vez */ }
}

/**
 * 072:RF-33: los pasos de cada tipo, en su orden, con lo que ya consta. Son los pasos que ya existen en la web; aquí
 * solo se ordenan y se enlazan, ninguno se repite. Sin el paso 5 en esta edición, PIDE y largo plazo lo dicen.
 */
export function pasosDelTipo(tipo: ClaveTipoAnalisis, e: EstadoPasos, planificacion: boolean): Paso[] {
  const comunes: Paso[] = [
    { clave: 'proyecto', titulo: '1 · Proyecto de DIgSILENT', destino: DESTINO.proyecto, hecho: e.proyecto },
    { clave: 'calibracion', titulo: '2 · Alimentadores, «Caso base» y calibración en «Sin proyecto»',
      destino: DESTINO.calibracion, hecho: e.alimentadores && e.calibrado },
  ];
  const sinPaso5 = planificacion ? undefined : 'La planificación no está activa en esta edición.';
  if (tipo === 'corto_plazo') {
    return [...comunes,
      { clave: 'nuevas', titulo: '3 · Cargas nuevas en «Con proyecto»', destino: DESTINO.nuevas, hecho: e.cargas ? true : null,
        nota: 'Solo si el estudio trae cargas nuevas.' },
      { clave: 'obras', titulo: '3 y 4.1 · Obras de corto plazo en «Con proyecto» (escalera u obra definida)',
        destino: DESTINO.obras, hecho: e.conProyecto,
        nota: 'Tras aplicar las cargas, «Proponer obras en escalera»; si no, 4.1 · Obras de mejora.' },
      { clave: 'informes', titulo: '4.4 · Informes de estudio y de factibilidad', destino: DESTINO.informes, hecho: e.informes }];
  }
  if (tipo === 'pide') {
    return [...comunes,
      { clave: 'obras', titulo: 'Obra de corto plazo en «Con proyecto» (punto de partida)', destino: DESTINO.obras,
        hecho: e.conProyecto, nota: 'El PIDE parte de ella y del año en que vuelve a fallar (098:RF-37).' },
      { clave: 'planificar', titulo: '5 · Planificar como PIDE (plan de largo plazo incluido)', destino: DESTINO.planificacion,
        hecho: e.pide, nota: sinPaso5 },
      { clave: 'entregables', titulo: '5 · Módulos del PIDE (F08 a F15) y del plan (F01 a F07)', destino: DESTINO.planificacion,
        hecho: e.pide, nota: sinPaso5 }];
  }
  return [...comunes,
    { clave: 'planificar', titulo: '5 · Planificar el largo plazo (sin aplicar obras)', destino: DESTINO.planificacion,
      hecho: e.largo || e.pide, nota: sinPaso5 },
    { clave: 'entregables', titulo: '5 · Módulos del plan de largo plazo (F01 a F07)', destino: DESTINO.planificacion,
      hecho: e.largo || e.pide, nota: sinPaso5 }];
}

/** 072:RF-29: los tipos del servidor, con el año de presentación si el operador lo escribió. */
export function useTiposAnalisis(anio: string): { tipos: TiposAnalisis | null; error: string } {
  const [tipos, setTipos] = useState<TiposAnalisis | null>(null);
  const [error, setError] = useState('');
  const n = Number(anio);
  // Mientras se escribe (menos de cuatro cifras) cuenta como sin año: no se avisa a cada tecla.
  const valido = anio.trim().length < 4 ? null : Number.isInteger(n) && n >= 1900 && n <= 2200 ? n : undefined;
  useEffect(() => {
    if (valido === undefined) return;
    let vivo = true;
    api.planeamientoTipos(valido).then((t) => { if (vivo) { setTipos(t); setError(''); } })
      .catch((e: unknown) => { if (vivo) setError(e instanceof Error ? e.message : String(e)); });
    return () => { vivo = false; };
  }, [valido]);
  return { tipos, error: valido === undefined ? 'El año de presentación tiene que ser un año de cuatro cifras.' : error };
}

const anio2 = (a: { relativo: number; calendario: number | null }) =>
  `${String(a.relativo).padStart(2, '0')}${a.calendario != null ? ` (${a.calendario})` : ''}`;

function Ficha({ t }: { t: TipoAnalisis }) {
  return (
    <dl className="ficha-tipo small">
      <div><dt>Horizonte</dt><dd>Años {t.anios.map(anio2).join(', ')}</dd></div>
      {t.articulos.length > 0 && <div><dt>Artículos</dt>
        <dd>{t.articulos.map((a) => `${a.numero} ${a.titulo}`).join(' · ')}</dd></div>}
      <div><dt>Obras admitidas</dt><dd>{t.obras_admitidas.map((o) => o.titulo).join(' · ')}</dd></div>
      {t.obras_excluidas.length > 0 && <div><dt>No entran</dt>
        <dd>{t.obras_excluidas.map((o) => o.titulo).join(' · ')} (proyecto integral: PIDE o largo plazo)</dd></div>}
      <div><dt>Entregables</dt><dd>{t.entregables.map((e) => e.formatos.length
        ? `${e.titulo} (${e.formatos.join(', ')})` : e.titulo).join(' · ')}</dd></div>
      <div><dt>Obras en «Con proyecto»</dt><dd>{t.aplica_obras ? 'se aplican' : 'se plantean, no se aplican'}</dd></div>
    </dl>
  );
}

/**
 * Tipo de análisis (spec 072, RF-29 a RF-38).
 *
 * El operador elige corto plazo, PIDE o planeamiento de largo plazo; la ficha (horizonte, obras, entregables y norma)
 * la da el servidor, y los pasos llevan a las secciones que ya existen. Nada se oculta: el tipo ordena y explica.
 */
export function TipoDeAnalisis({ tipo, onTipo, anio, onAnio, tipos, error, estado, planificacion }: {
  tipo: ClaveTipoAnalisis | null; onTipo: (t: ClaveTipoAnalisis) => void;
  anio: string; onAnio: (a: string) => void;
  tipos: TiposAnalisis | null; error: string; estado: EstadoPasos; planificacion: boolean;
}) {
  const elegido = tipos?.tipos.find((t) => t.clave === tipo) ?? null;
  const pasos = tipo ? pasosDelTipo(tipo, estado, planificacion) : [];
  const sinAnio = tipo !== null && tipo !== 'corto_plazo' && !anio.trim() && tipos?.anio_presentacion_perfil == null;
  return (
    <div className="step-box" id="paso-tipo" tabIndex={-1}>
      <h3>Tipo de análisis</h3>
      <div className="chips" role="radiogroup" aria-label="Tipo de análisis">
        {(tipos?.tipos ?? []).map((t) => (
          <button key={t.clave} type="button" role="radio" aria-checked={tipo === t.clave}
            className={`chip${tipo === t.clave ? ' on' : ''}`} onClick={() => onTipo(t.clave)}>{t.titulo}</button>))}
        {tipo === null && tipos && <span className="muted small">Elija uno: cada tipo tiene su horizonte, sus obras y sus entregables.</span>}
      </div>
      {error && <p role="alert" className="alert alert-error">{error}</p>}
      {tipos && <p className="small muted">
        Según {tipos.norma.acto}{tipos.norma.titulo ? `, «${tipos.norma.titulo}»` : ''}
        {tipos.norma.vigente ? '.' : ` (${tipos.norma.estado_juridico || 'sin estado jurídico'}: no se presenta como norma vigente).`}
      </p>}
      {tipo !== null && tipo !== 'corto_plazo' && (
        <label className="field"><span>Año de presentación{tipos?.ciclo_anios ? ` (se presenta cada ${tipos.ciclo_anios} años)` : ''}</span>
          <input type="number" min={1900} max={2200} value={anio} onChange={(e) => onAnio(e.target.value)}
            placeholder={tipos?.anio_presentacion_perfil ? `el del perfil: ${tipos.anio_presentacion_perfil}` : 'p. ej. el próximo año de presentación'} />
          {sinAnio && <small className="alert alert-warn">Sin año de presentación aquí ni en el perfil, «Planificar» se rechaza.</small>}
        </label>)}
      {elegido && <>
        <p>{elegido.descripcion}</p>
        <Ficha t={elegido} />
        {/* 072:RF-38: el PIDE parte de la obra de corto plazo; sin ella se avisa y no se bloquea. */}
        {tipo === 'pide' && !estado.conProyecto && (
          <p className="alert alert-warn">No consta un «Con proyecto» con su obra de corto plazo en esta sesión: el PIDE parte
            de ella. Puede planificar igual; el diagnóstico lo dirá.</p>)}
        <ol className="pasos-tipo">
          {pasos.map((p) => (
            <li key={p.clave}>
              <span className={`badge ${p.hecho ? 'ok' : p.hecho === null ? '' : 'warn'}`}>
                {p.hecho ? 'hecho' : p.hecho === null ? 'opcional' : 'pendiente'}</span>{' '}
              <span>{p.titulo}</span>
              {p.nota && <small className="muted"> — {p.nota}</small>}{' '}
              <button type="button" className="btn btn-ghost btn-sm" onClick={() => irA(p.destino)}>Ir al paso</button>
            </li>))}
        </ol>
      </>}
    </div>
  );
}
