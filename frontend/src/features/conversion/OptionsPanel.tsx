import { useEffect, useState } from 'react';
import { api } from '../../api/client';
import { useApp } from '../../shared/context';
import type { Options, SalidaRed, SalidasRed } from '../../api/types';
import { Toggle } from '../../shared/ui';

export const ETIQUETA_FONDO_MAPA = 'Fondo de mapa (calles y satélite; pide las teselas a internet)';

/** 086:RF-67, RF-68: lo que se explica bajo el interruptor; sin la salida leída, nada. */
export function ayudaFondoMapa(salida: SalidaRed | null): string {
  if (!salida) return '';
  if (salida.origen === 'variable') {
    return `Lo fija ${salida.variable} al arrancar el programa: no se cambia desde aquí.`;
  }
  return `Fondo de mapa: pide las teselas a ${salida.destino}. Se recuerda en este equipo y vale para las `
    + 'conversiones siguientes; los mapas ya generados no cambian.';
}

/** 086:RF-67: guarda la elección en el servidor y devuelve la salida de las teselas como quedó. */
export async function cambiarFondoMapa(llamada: (encendida: boolean) => Promise<SalidasRed | undefined>,
  encendida: boolean, poner: (s: SalidaRed) => void): Promise<SalidaRed | undefined> {
  const r = await llamada(encendida);
  const teselas = r?.salidas.find((s) => s.nombre === 'teselas');
  if (teselas) poner(teselas);
  return teselas;
}

/** 086:RF-67, RF-68: el interruptor del fondo de mapa; bloqueado si lo fija la variable o mientras se lee. */
export function FondoMapa({ salida, locked, onChange }: {
  salida: SalidaRed | null; locked: boolean; onChange: (v: boolean) => void;
}) {
  const fijada = salida?.origen === 'variable';
  return (
    <Toggle label={ETIQUETA_FONDO_MAPA} checked={Boolean(salida?.encendida)}
      disabled={locked || !salida || !salida.cambiable}
      hint={fijada ? ayudaFondoMapa(salida) : ''} onChange={onChange} />
  );
}

export function OptionsPanel() {
  const { ws, setWs, health, run, active } = useApp();
  const o = ws.options;
  const caps = health.capabilities;
  const [crs, setCrs] = useState(o.source_crs ?? '');
  const [target, setTarget] = useState(o.target_crs);
  const [crsWarning, setCrsWarning] = useState('');
  const locked = Boolean(active.engine);
  const [fondo, setFondo] = useState<SalidaRed | null>(null);

  useEffect(() => {
    api.salidas().then((r) => setFondo(r.salidas.find((s) => s.nombre === 'teselas') ?? null)).catch(() => setFondo(null));
  }, []);

  useEffect(() => setCrs(o.source_crs ?? ''), [o.source_crs]);
  const perfil = health.perfil_empresa;
  const crsPerfil = perfil.crs_origen ?? '';
  const sinCrs = o.include_geography && !o.source_crs && !crsPerfil;
  useEffect(() => setTarget(o.target_crs), [o.target_crs]);

  const save = async (patch: Partial<Options>) => {
    const r = await run(() => api.setOptions(ws.id, patch));
    if (r) {
      setWs(r);
      if ('source_crs' in patch) setCrsWarning(r.warning ?? '');
    }
  };

  return (
    <section className="card">
      <header className="card-head"><h2>Opciones de conversión</h2></header>
      <div className="options-grid">
        <label className="field">
          <span>CRS de origen (el de su empresa o región)</span>
          <input list="crs-presets" value={crs} disabled={locked}
            placeholder={crsPerfil ? `${crsPerfil} (del perfil de empresa)` : 'Elija un EPSG en metros'}
            onChange={(e) => setCrs(e.target.value)}
            onBlur={() => crs !== (o.source_crs ?? '') && save({ source_crs: crs })}
            onKeyDown={(e) => e.key === 'Enter' && (e.target as HTMLInputElement).blur()} />
          <datalist id="crs-presets">
            {health.crs_presets.map((p) => <option key={p.code} value={p.code}>{p.label}</option>)}
          </datalist>
          <small className="muted">
            Cualquier EPSG <b>proyectado en metros</b>. Uno en grados (p. ej. EPSG:4326) falsearía las
            longitudes unas 100.000 veces y se rechaza al convertir.
          </small>
          {crsWarning && <small className="alert alert-error">{crsWarning}</small>}
          {perfil.error && <small className="alert alert-error">Perfil de empresa: {perfil.error}</small>}
          {sinCrs && (
            <small className="alert alert-warn">
              Sin perfil de empresa no se supone ningún CRS: elíjalo aquí, cargue un perfil con <code>crs_origen</code>
              {' '}en «Perfil de la empresa» o desactive la georreferenciación.
            </small>
          )}
        </label>
        <label className="field">
          <span>CRS de destino GPS</span>
          <input list="crs-target" value={target} disabled={locked}
            onChange={(e) => setTarget(e.target.value)}
            onBlur={() => target !== o.target_crs && save({ target_crs: target })} />
          <datalist id="crs-target"><option value="EPSG:4326">WGS 84</option></datalist>
        </label>
        <label className="field">
          <span>Hoja del diagrama en PowerFactory</span>
          <select value={o.hoja ?? 'AUTO'} disabled={locked}
            onChange={(e) => save({ hoja: e.target.value === 'AUTO' ? null : e.target.value as typeof o.hoja })}>
            <option value="AUTO">Ajustada a la red (escala real)</option>
            {['A0', 'A1', 'A2', 'A3', 'A4'].map((h) => <option key={h} value={h}>{h}</option>)}
          </select>
          <small className="muted">
            La opción automática mantiene la escala geográfica y ajusta el lienzo al tamaño de la red.
          </small>
        </label>
        <label className="field">
          <span>Procesos en paralelo</span>
          <select value={o.workers ?? 0} disabled={locked}
            onChange={(e) => save({ workers: Number(e.target.value) })}>
            <option value={0}>Automático ({health.parallel.auto})</option>
            <option value={1}>1 (en serie)</option>
            {[2, 4, 8].filter((n) => n <= health.parallel.cpus).map((n) => (
              <option key={n} value={n}>{n}</option>
            ))}
          </select>
          <small className="muted">
            Convierte varios alimentadores a la vez. El resultado es idéntico; con muchos
            procesos cada uno ocupa memoria y compiten por el disco, así que más no siempre es
            más rápido.
          </small>
        </label>
      </div>
      <div className="toggles">
        <Toggle label="Georreferenciación (GPS + diagrama)" checked={o.include_geography} disabled={locked}
          hint={caps.geography ? '' : 'Falta pyproj en el servidor'}
          onChange={(v) => save(v ? { include_geography: true } : { include_geography: false, write_preview: false })} />
        <Toggle label="Modo estricto (topología)" checked={o.strict} disabled={locked}
          onChange={(v) => save({ strict: v })} />
        <Toggle label="Vista previa en mapa (HTML)" checked={o.write_preview} disabled={locked || !o.include_geography}
          hint={!o.include_geography ? 'Requiere georreferenciación' : ''}
          onChange={(v) => save({ write_preview: v })} />
        <FondoMapa salida={fondo} locked={locked}
          onChange={(v) => void cambiarFondoMapa((e) => run(() => api.fondoMapa(e)), v, setFondo)} />
        <Toggle label="Exportar Excel (.xlsx)" checked={o.export_xlsx} disabled={locked || !caps.xlsx}
          hint={caps.xlsx ? '' : 'Falta pandas/openpyxl en el servidor'}
          onChange={(v) => save({ export_xlsx: v })} />
        <Toggle label="Exportar TSV por tabla" checked={o.export_tsv} disabled={locked}
          onChange={(v) => save({ export_tsv: v })} />
      </div>
      {fondo && <p className="muted small">{ayudaFondoMapa(fondo)}</p>}
      {o.include_geography && !caps.geography && (
        <p className="alert alert-warn">El servidor no tiene <code>pyproj</code>: desactive la georreferenciación o instálelo.</p>
      )}
    </section>
  );
}
