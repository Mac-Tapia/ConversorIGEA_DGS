import { useEffect, useMemo, useRef, useState } from 'react';

import { plano, type CapasPlano, type ComparacionPlano, type EdicionPlano, type Plano, type PropuestaAjuste,
  type VariacionesPlano, type VariacionPlano } from '../../api/plano';
import { useApp } from '../../shared/context';
import { CapasResultados, Comparacion } from './CapasResultados';
import { EdicionesPlano } from './EdicionesPlano';
import { InspectorElemento } from './InspectorElemento';
import { almacenDelNavegador, buscarPorCodigo, elementosDe, leerVertices, recordarVariacion, variacionRecordada,
  type Elemento } from './logicaPlano';
import { leerMensaje, mensajeAlPlano } from './mensajesPlano';
import { TablaElementos } from './TablaElementos';
import { TEXTOS } from './textosPlano';

/**
 * 111: la pestaña «Plano de la red». El plano es una página del servidor en un `<iframe sandbox>` (sin origen propio)
 * y habla con la pestaña por `postMessage` con un esquema cerrado. Las ediciones van a la API, que valida, versiona y
 * decide toda regla eléctrica; estudiar es un trabajo en su carril. Todo se puede hacer con el teclado: el buscador,
 * la tabla, el inspector y los formularios sustituyen a arrastrar en el plano.
 */
export function PlanoRed() {
  const { ws, feeders, selected, run, startJob, active, jobs } = useApp();
  const opciones = useMemo(() => feeders.map((f) => f.feeder), [feeders]);
  const [alimentador, setAlimentador] = useState<string>(() => selected[0] ?? '');
  const [datos, setDatos] = useState<Plano | null>(null);
  const [busqueda, setBusqueda] = useState('');
  const [elegido, setElegido] = useState<string | null>(null);
  const [caso, setCaso] = useState('Caso base');
  const [proyecto, setProyecto] = useState('');
  const [variacion, setVariacion] = useState<VariacionPlano | null>(null);
  // Lo guardado vive en el servidor; el navegador solo recuerda cuál se miraba (si puede).
  const [lista, setLista] = useState<VariacionesPlano | null>(null);
  const [capas, setCapas] = useState<CapasPlano | null>(null);
  const [comparacion, setComparacion] = useState<ComparacionPlano | null>(null);
  const [aComparar, setAComparar] = useState<[string, string]>(['', '']);
  const [propuesta, setPropuesta] = useState<PropuestaAjuste | null>(null);
  const [anuncio, setAnuncio] = useState('');
  const [refresco, setRefresco] = useState(0);
  const marco = useRef<HTMLIFrameElement>(null);
  const actual = alimentador || opciones[0] || '';
  const ocupado = Boolean(active.engine || active.powerfactory);

  useEffect(() => {
    if (!actual) return;
    let vivo = true;
    void run(() => plano.datos(ws.id, [actual], proyecto || null)).then((d) => { if (vivo && d) setDatos(d); });
    return () => { vivo = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ws.id, actual, refresco]);

  useEffect(() => {
    if (!actual) return;
    let vivo = true;
    void run(() => plano.variaciones(ws.id, actual)).then((l) => {
      if (!vivo || !l) return;
      setLista(l);
      const recordada = variacionRecordada(almacenDelNavegador(), ws.id);
      setVariacion((v) => v ?? l.variaciones.find((x) => x.id === recordada) ?? null);
    });
    return () => { vivo = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ws.id, actual, refresco]);

  // La página del plano avisa de lo que el operador selecciona; solo se acepta de su marco y con su esquema.
  useEffect(() => {
    const oir = (e: MessageEvent) => {
      const m = leerMensaje(e, marco.current?.contentWindow);
      if (m?.tipo === 'seleccionado') { setElegido(m.codigo); setAnuncio(`${m.codigo} seleccionado.`); }
    };
    window.addEventListener('message', oir);
    return () => window.removeEventListener('message', oir);
  }, []);

  // El estudio termina en el carril de trabajos; al acabar, se piden sus capas.
  const estudio = Object.values(jobs).find((j) => j.kind === 'plano_estudiar' && j.result?.variacion === variacion?.id);
  useEffect(() => {
    if (!variacion || !estudio || estudio.status !== 'done') return;
    void run(() => plano.resultados(ws.id, variacion.id)).then((c) => {
      if (c) { setCapas(c); setAnuncio(c.pintable ? 'Resultados listos sobre el plano.' : c.motivo); }
    });
    void run(() => plano.variaciones(ws.id, variacion.alimentador)).then((l) => { if (l) setLista(l); });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [estudio?.status, estudio?.id]);

  const vista = datos?.vistas[0] ?? null;
  const elementos = useMemo(() => elementosDe(datos?.vistas ?? []), [datos]);
  const hallados = useMemo(() => buscarPorCodigo(elementos, busqueda), [elementos, busqueda]);
  const seleccion: Elemento | null = elementos.find((e) => e.codigo === elegido) ?? null;
  const enviar = (tipo: Parameters<typeof mensajeAlPlano>[0], campos: Record<string, unknown>) =>
    marco.current?.contentWindow?.postMessage(mensajeAlPlano(tipo, campos), '*');
  const elegir = (codigo: string) => {
    setElegido(codigo);
    enviar('seleccionar', { codigo });
    setAnuncio(`${codigo} seleccionado.`);
  };
  const nuevaVersion = (v: VariacionPlano | undefined, texto: string) => {
    if (!v) return;
    setVariacion(v);
    recordarVariacion(almacenDelNavegador(), ws.id, v.id);
    setAnuncio(texto);
  };
  const elegirVariacion = (id: string) => {
    const v = lista?.variaciones.find((x) => x.id === id);
    if (!v) return;
    setCapas(null);
    nuevaVersion(v, `Variación ${v.caso} abierta.`);
    if (lista?.estudiadas.includes(v.id)) void run(() => plano.resultados(ws.id, v.id)).then((c) => { if (c) setCapas(c); });
  };
  const abrir = async () => {
    if (!vista) return;
    const v = await run(() => plano.abrir(ws.id, { alimentador: vista.alimentador, caso, revision: vista.revision }));
    if (v) {
      setLista((l) => ({ variaciones: [...(l?.variaciones ?? []), v], estudiadas: l?.estudiadas ?? [] }));
      setCapas(null);
      nuevaVersion(v, `Variación abierta sobre ${vista.alimentador}.`);
    }
  };
  const editar = async (edicion: EdicionPlano, texto: string) => {
    if (!variacion) return;
    nuevaVersion(await run(() => plano.editar(ws.id, variacion.id, variacion.version, edicion)), texto);
  };
  const maniobra = seleccion?.clase === 'maniobra' ? seleccion.dato : null;
  const estadoActual = maniobra && variacion
    ? [...variacion.ediciones].reverse().find((e) => e.codigo === maniobra.codigo)?.estado ?? maniobra.estado
    : maniobra?.estado;

  return (
    <section className="card" aria-labelledby="plano-titulo">
      <h3 id="plano-titulo">{TEXTOS.titulo}</h3>
      <p className="sr-only" aria-live="polite" role="status">{anuncio}</p>
      <div className="toolbar">
        <label>{TEXTOS.alimentador}{' '}
          <select value={actual} onChange={(e) => { setAlimentador(e.target.value); setVariacion(null); setCapas(null); }}>
            {opciones.map((o) => <option key={o} value={o}>{o}</option>)}
          </select>
        </label>
        <label>{TEXTOS.buscar}{' '}
          <input type="search" value={busqueda} onChange={(e) => setBusqueda(e.target.value)} aria-controls="plano-hallados" />
        </label>
      </div>
      {busqueda && (
        <ul id="plano-hallados" className="lista-compacta" aria-live="polite">
          {hallados.length === 0 ? <li className="muted">{TEXTOS.sinResultadosBusqueda}</li> : hallados.map((h) => (
            <li key={`${h.clase}|${h.codigo}`}><button type="button" className="link" onClick={() => elegir(h.codigo)}>{h.codigo}</button>
              {' '}<span className="muted">{h.detalle}</span></li>
          ))}
        </ul>
      )}
      {datos && !datos.fondo.encendido && <p className="muted">{datos.fondo.motivo}</p>}
      {vista?.sin_coordenadas && <p className="alert alert-info">{TEXTOS.sinCoordenadas}</p>}
      {vista && vista.avisos.length > 0 && <div className="alert alert-info">{vista.avisos.slice(0, 3).map((a) => <p key={a}>{a}</p>)}</div>}
      {actual && (
        <iframe ref={marco} key={`${actual}|${refresco}|${capas?.variacion ?? ''}`} className="map-frame" title={TEXTOS.marco}
          src={plano.paginaUrl(ws.id, [actual], capas?.pintable ? capas.variacion ?? null : null)} sandbox="allow-scripts" />
      )}
      <div className="plano-columnas">
        <div>
          <h4>{TEXTOS.inspector}</h4>
          <InspectorElemento elemento={seleccion} />
          {maniobra && variacion && variacion.estado === 'abierta' && (
            <button type="button" disabled={ocupado} onClick={() => void editar(
              { tipo: 'maniobra', codigo: maniobra.codigo, estado: estadoActual === 'abierto' ? 'cerrado' : 'abierto' },
              `${maniobra.codigo}: ${estadoActual === 'abierto' ? 'cerrado' : 'abierto'}.`)}>
              {TEXTOS.maniobra}: {estadoActual === 'abierto' ? 'cerrar' : 'abrir'}
            </button>
          )}
        </div>
        <div>
          <TablaElementos filas={elementos} seleccionado={elegido} onElegir={elegir} />
        </div>
      </div>
      <h4>{TEXTOS.variacion}</h4>
      <div className="toolbar">
        <label>{TEXTOS.caso} <input value={caso} onChange={(e) => setCaso(e.target.value)} /></label>
        <label>{TEXTOS.proyecto} <input value={proyecto} onChange={(e) => setProyecto(e.target.value)} /></label>
        <button type="button" onClick={() => void abrir()} disabled={!vista || ocupado}>{TEXTOS.abrir}</button>
        {lista && lista.variaciones.length > 0 && (
          <label>{TEXTOS.variacion}{' '}
            <select value={variacion?.id ?? ''} onChange={(e) => elegirVariacion(e.target.value)}>
              <option value="">—</option>
              {lista.variaciones.map((v) => <option key={v.id} value={v.id}>{v.caso} · {v.ediciones.length} ed.</option>)}
            </select>
          </label>
        )}
        {variacion && (
          <button type="button" disabled={ocupado} onClick={() => void startJob(() => plano.estudiar(ws.id, variacion.id, proyecto || null))}>
            {TEXTOS.estudiar}
          </button>
        )}
      </div>
      {datos && <p className="muted">{datos.motor.texto}: {datos.motor.motivo}</p>}
      {variacion && vista && (
        <>
          <EdicionesPlano variacion={variacion} ocupado={ocupado}
            onDeshacer={() => void run(() => plano.deshacer(ws.id, variacion.id, variacion.version)).then((v) => nuevaVersion(v, 'Edición deshecha.'))}
            onRehacer={() => void run(() => plano.rehacer(ws.id, variacion.id, variacion.version)).then((v) => nuevaVersion(v, 'Edición rehecha.'))}
            onConfirmar={() => void run(() => plano.confirmar(ws.id, variacion.id, variacion.version)).then((v) => nuevaVersion(v, 'Variación confirmada.'))} />
          {variacion.estado === 'abierta' && (
            <FormulariosEdicion vista={vista} ocupado={ocupado} propuesta={propuesta} variacion={variacion}
              onEditar={editar} onProponer={async (punto) => {
                const p = await run(() => plano.ajuste(ws.id, variacion.id, punto));
                if (p) { setPropuesta(p); enviar('propuesta', { punto: p.punto, nodo: p.nodo }); setAnuncio(p.nodo ? `Propuesta: ${p.nodo}.` : 'Ningún nodo dentro del radio.'); }
              }} />
          )}
        </>
      )}
      <h4>{TEXTOS.resultados}</h4>
      {capas ? <CapasResultados capas={capas} onElegir={elegir} /> : <p className="muted">{TEXTOS.sinResultados}</p>}
      {lista && lista.estudiadas.length > 1 && (
        <>
          <h4>{TEXTOS.comparar}</h4>
          <div className="toolbar">
            {([0, 1] as const).map((i) => (
              <label key={i}>{i === 0 ? TEXTOS.casoA : TEXTOS.casoB}{' '}
                <select value={aComparar[i]} onChange={(e) => setAComparar(i === 0 ? [e.target.value, aComparar[1]] : [aComparar[0], e.target.value])}>
                  <option value="">—</option>
                  {lista.estudiadas.map((g) => <option key={g} value={g}>{lista.variaciones.find((v) => v.id === g)?.caso ?? g}</option>)}
                </select>
              </label>
            ))}
            <button type="button" disabled={!aComparar[0] || !aComparar[1] || aComparar[0] === aComparar[1]}
              onClick={() => void run(() => plano.comparar(ws.id, aComparar[0], aComparar[1])).then((c) => { if (c) setComparacion(c); })}>
              {TEXTOS.verComparacion}
            </button>
          </div>
          {comparacion && <Comparacion comparacion={comparacion} onElegir={elegir} />}
        </>
      )}
      <button type="button" className="link" onClick={() => setRefresco((n) => n + 1)}>Volver a leer el plano</button>
    </section>
  );
}

/** Tramo nuevo, ajuste de su extremo y equipo insertado, con el teclado: nodos de una lista y vértices escritos. */
function FormulariosEdicion({ vista, variacion, ocupado, propuesta, onEditar, onProponer }: {
  vista: Plano['vistas'][number];
  variacion: VariacionPlano;
  ocupado: boolean;
  propuesta: PropuestaAjuste | null;
  onEditar: (e: EdicionPlano, texto: string) => Promise<void>;
  onProponer: (punto: [number, number]) => Promise<void>;
}) {
  const nodos = vista.barras.map((b) => b.codigo);
  const nuevos = variacion.ediciones.filter((e) => e.tipo === 'tramo').map((e) => String(e.codigo));
  const [t, setT] = useState({ codigo: '', desde: nodos[0] ?? '', hasta: '', vertices: '', conductor: vista.tipos_de_linea[0] ?? '',
    fases: 'ABC', electrica: '' });
  const [a, setA] = useState({ tramo: '', extremo: 'hasta', punto: '' });
  const [q, setQ] = useState({ codigo: '', clase: 'seccionador', tramo: vista.tramos[0]?.codigo ?? '', extremo: 'desde',
    tension: String(vista.kv), fases: 'ABC', estado: 'cerrado' });
  const [error, setError] = useState('');
  const tramo = async () => {
    const vertices = leerVertices(t.vertices);
    if (!vertices) { setError(TEXTOS.coordenadasMal); return; }
    setError('');
    const edicion: EdicionPlano = { tipo: 'tramo', codigo: t.codigo, desde: t.desde, hasta: t.hasta || null, vertices,
      conductor: t.conductor, fases: t.fases };
    if (t.electrica.trim()) edicion.longitud_electrica_m = Number(t.electrica.replace(',', '.'));
    await onEditar(edicion, `${TEXTOS.tramoNuevo} ${t.codigo}.`);
  };
  const proponer = async () => {
    const p = leerVertices(a.punto);
    if (!p || p.length !== 1) { setError(TEXTOS.coordenadasMal); return; }
    setError('');
    await onProponer([p[0][0], p[0][1]]);
  };
  return (
    <div className="plano-columnas">
      <fieldset>
        <legend>{TEXTOS.tramoNuevo}</legend>
        <label>{TEXTOS.codigo} <input value={t.codigo} onChange={(e) => setT({ ...t, codigo: e.target.value })} /></label>
        <label>{TEXTOS.desde} <select value={t.desde} onChange={(e) => setT({ ...t, desde: e.target.value })}>
          {nodos.map((n) => <option key={n} value={n}>{n}</option>)}</select></label>
        <label>{TEXTOS.hasta} <select value={t.hasta} onChange={(e) => setT({ ...t, hasta: e.target.value })}>
          <option value="">{TEXTOS.hastaNuevo}</option>{nodos.map((n) => <option key={n} value={n}>{n}</option>)}</select></label>
        <label>{TEXTOS.vertices} <textarea rows={3} value={t.vertices} onChange={(e) => setT({ ...t, vertices: e.target.value })} /></label>
        <label>{TEXTOS.conductor} <select value={t.conductor} onChange={(e) => setT({ ...t, conductor: e.target.value })}>
          {vista.tipos_de_linea.map((c) => <option key={c} value={c}>{c}</option>)}</select></label>
        <label>{TEXTOS.fases} <input value={t.fases} onChange={(e) => setT({ ...t, fases: e.target.value.toUpperCase() })} /></label>
        <label>{TEXTOS.longitudElectrica} <input inputMode="decimal" value={t.electrica} onChange={(e) => setT({ ...t, electrica: e.target.value })} /></label>
        <button type="button" disabled={ocupado || !t.codigo} onClick={() => void tramo()}>{TEXTOS.anadirTramo}</button>
      </fieldset>
      <fieldset>
        <legend>{TEXTOS.ajuste}</legend>
        <label>{TEXTOS.tramoNuevo} <select value={a.tramo} onChange={(e) => setA({ ...a, tramo: e.target.value })}>
          <option value="">—</option>{nuevos.map((n) => <option key={n} value={n}>{n}</option>)}</select></label>
        <label>Extremo <select value={a.extremo} onChange={(e) => setA({ ...a, extremo: e.target.value })}>
          <option value="desde">{TEXTOS.desde}</option><option value="hasta">{TEXTOS.hasta}</option></select></label>
        <label>{TEXTOS.punto} <input value={a.punto} onChange={(e) => setA({ ...a, punto: e.target.value })} /></label>
        <button type="button" disabled={ocupado || !a.tramo} onClick={() => void proponer()}>{TEXTOS.proponer}</button>
        {propuesta && (
          <p>{propuesta.nodo
            ? <>{propuesta.nodo} · {propuesta.distancia_m?.toLocaleString('es-PE', { maximumFractionDigits: 1 })} m{' '}
              <button type="button" disabled={ocupado} onClick={() => void onEditar({ tipo: 'ajuste', tramo: a.tramo, extremo: a.extremo,
                nodo: propuesta.nodo, confirmado: true }, `Extremo ajustado a ${propuesta.nodo}.`)}>{TEXTOS.aplicarAjuste}</button></>
            : <span className="muted">Ningún nodo a menos de {propuesta.radio_m} m ({propuesta.radio_origen}).</span>}</p>
        )}
      </fieldset>
      <fieldset>
        <legend>{TEXTOS.equipo}</legend>
        <label>{TEXTOS.codigo} <input value={q.codigo} onChange={(e) => setQ({ ...q, codigo: e.target.value })} /></label>
        <label>{TEXTOS.clase} <input value={q.clase} onChange={(e) => setQ({ ...q, clase: e.target.value })} /></label>
        <label>Tramo <input value={q.tramo} onChange={(e) => setQ({ ...q, tramo: e.target.value })} /></label>
        <label>{TEXTOS.tension} <input inputMode="decimal" value={q.tension} onChange={(e) => setQ({ ...q, tension: e.target.value })} /></label>
        <label>{TEXTOS.fases} <input value={q.fases} onChange={(e) => setQ({ ...q, fases: e.target.value.toUpperCase() })} /></label>
        <label>{TEXTOS.estadoNormal} <select value={q.estado} onChange={(e) => setQ({ ...q, estado: e.target.value })}>
          <option value="cerrado">cerrado</option><option value="abierto">abierto</option></select></label>
        <button type="button" disabled={ocupado || !q.codigo} onClick={() => void onEditar({ tipo: 'equipo', codigo: q.codigo, clase: q.clase,
          tramo: q.tramo, extremo: q.extremo, tension_kv: Number(q.tension.replace(',', '.')), fases: q.fases, estado: q.estado },
          `Equipo ${q.codigo} añadido.`)}>{TEXTOS.anadirEquipo}</button>
      </fieldset>
      {error && <p className="alert alert-warn" role="alert">{error}</p>}
    </div>
  );
}
