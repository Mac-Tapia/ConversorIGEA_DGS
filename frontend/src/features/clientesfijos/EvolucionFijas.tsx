import { useCallback, useEffect, useMemo, useState } from 'react';
import { api } from '../../api/client';
import { EVENTO_ARCHIVO, evolucionFijas, type EvolucionEstado } from '../../api/evolucionFijas';
import { AvisosTrabajo } from '../../shared/AvisosTrabajo';
import { useApp } from '../../shared/context';
import { Tablero } from './Tablero';
import { nombreMes } from './datosTablero';

const TIPO = 'clientes_fijos_evolucion';

/**
 * Pestaña «Evolución de clientes fijos» (105:RF-21): elige alimentadores y meses, lanza el trabajo y muestra el tablero;
 * su prueba de render está en frontend/test/evolucionFijas.test.mjs.
 * Usa los libros ya asignados en «2.1 · Libros de medición» (RF-1): aquí no se pide ninguna ruta.
 */
export function EvolucionFijas() {
  const { ws, jobs, active, startJob, run } = useApp();
  const [estado, setEstado] = useState<EvolucionEstado | null>(null);
  const [elegidos, setElegidos] = useState<string[]>([]);
  const [filtro, setFiltro] = useState('');
  const [desde, setDesde] = useState('');
  const [hasta, setHasta] = useState('');
  const [conCabecera, setConCabecera] = useState(false);

  const leer = useCallback(() => {
    void run(() => evolucionFijas.estado(ws.id)).then((e) => { if (e) setEstado(e); });
  }, [run, ws.id]);
  // Se vuelve a leer al cambiar los libros del espacio y al terminar un trabajo de esta pestaña.
  const firmaLibros = JSON.stringify(ws.demanda ?? {});
  const terminado = Object.values(jobs)
    .filter((j) => j.kind === TIPO && j.workspace_id === ws.id && !['queued', 'running'].includes(j.status))
    .map((j) => j.id).pop();
  useEffect(leer, [leer, firmaLibros, terminado]);
  useEffect(() => {
    window.addEventListener(EVENTO_ARCHIVO, leer);
    return () => window.removeEventListener(EVENTO_ARCHIVO, leer);
  }, [leer]);

  useEffect(() => {
    const r = estado?.resultado;
    if (!estado) return;
    if (r) {
      setElegidos((x) => (x.length ? x : r.alimentadores));
      setDesde((d) => d || r.desde);
      setHasta((h) => h || r.hasta);
    } else if (estado.meses.length) {
      setDesde((d) => d || estado.meses[0]);
      setHasta((h) => h || estado.meses[estado.meses.length - 1]);
    }
  }, [estado]);

  const visibles = useMemo(() => {
    const f = filtro.trim().toLowerCase();
    const xs = estado?.alimentadores ?? [];
    return f ? xs.filter((a) => a.toLowerCase().includes(f)) : xs;
  }, [estado, filtro]);
  const enCurso = Object.values(jobs).find((j) => j.kind === TIPO && j.workspace_id === ws.id
    && ['queued', 'running'].includes(j.status));
  const ocupado = Boolean(active.engine);
  const rangoMal = Boolean(desde && hasta && hasta < desde);
  const conmutar = (a: string) => setElegidos((x) => (x.includes(a) ? x.filter((y) => y !== a) : [...x, a]));
  const lanzar = () => startJob(() => evolucionFijas.lanzar(ws.id, {
    alimentadores: elegidos, desde, hasta, con_cabecera: conCabecera }));
  const r = estado?.resultado;
  const meses = estado?.meses ?? [];

  return (
    <div className="evolucion-fijas">
      {/* 086:RF-70: el aviso de un cálculo interrumpido o fallido, en su propio paso. */}
      <AvisosTrabajo paso="clientes-fijos" />
      <p className="muted">Máximas, crecimiento, variaciones y tendencia de los clientes fijos de cada alimentador, con los
        libros de clientes importantes y de suministros asignados en «Cargas en DIgSILENT» › 2.1 · Libros de medición.</p>
      {estado && estado.faltan.length > 0 && (
        <p className="alert alert-warn">Falta {estado.faltan.join(' y ')}: asígnelo en «2.1 · Libros de medición».</p>
      )}
      <div className="form-grid">
        <div className="field">
          <span>Alimentadores ({elegidos.length} de {estado?.alimentadores.length ?? 0})</span>
          <input className="search" placeholder="filtrar" value={filtro} onChange={(e) => setFiltro(e.target.value)}
            aria-label="Filtrar alimentadores" />
          <div className="chips chips-scroll" role="group" aria-label="Alimentadores con clientes fijos">
            {visibles.map((a) => (
              <button key={a} type="button" className={`chip ${elegidos.includes(a) ? 'on' : ''}`} aria-pressed={elegidos.includes(a)}
                disabled={ocupado} onClick={() => conmutar(a)}>{a}</button>
            ))}
          </div>
        </div>
        <label className="field">
          <span>Desde</span>
          {meses.length
            ? <select value={desde} disabled={ocupado} onChange={(e) => setDesde(e.target.value)}>
                {meses.map((m) => <option key={m} value={m}>{nombreMes(m)}</option>)}</select>
            : <input type="month" value={desde} disabled={ocupado} onChange={(e) => setDesde(e.target.value)} />}
        </label>
        <label className="field">
          <span>Hasta</span>
          {meses.length
            ? <select value={hasta} disabled={ocupado} onChange={(e) => setHasta(e.target.value)}>
                {meses.map((m) => <option key={m} value={m}>{nombreMes(m)}</option>)}</select>
            : <input type="month" value={hasta} disabled={ocupado} onChange={(e) => setHasta(e.target.value)} />}
        </label>
      </div>
      {estado?.cabecera && (
        <label className="curva-check" title="Lee los libros de cabecera del rango, que pueden pesar cientos de MB">
          <input type="checkbox" checked={conCabecera} disabled={ocupado} onChange={(e) => setConCabecera(e.target.checked)} />
          {' '}Con la participación de los fijos en la máxima de cabecera (tarda más)
        </label>
      )}
      <div className="row">
        <button className="btn btn-primary" onClick={lanzar}
          disabled={ocupado || !elegidos.length || !desde || !hasta || rangoMal || Boolean(estado?.faltan.length)}>
          {enCurso ? 'Calculando…' : 'Calcular la evolución'}
        </button>
        {rangoMal && <small className="alert alert-warn">El mes «hasta» es anterior a «desde».</small>}
        {ocupado && !enCurso && <small className="muted">Hay otro trabajo del motor en curso.</small>}
        {estado?.archivo
          ? <small className="muted">El libro se archivará en {estado.archivo}.</small>
          : <small className="muted">Sin carpeta de archivo: el libro queda solo en «Resultados».</small>}
      </div>
      {r && <Tablero r={r} wsId={ws.id} enlace={api.fileUrl(ws.id, r.libro, true)} />}
      {estado && !r && <p className="muted">Aún no hay una evolución calculada en este espacio.</p>}
    </div>
  );
}
