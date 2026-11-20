import { useCallback, useEffect, useState } from 'react';
import { api } from '../../api/client';
import { vnr, type VnrEstudio } from '../../api/vnr';
import { AvisosTrabajo } from '../../shared/AvisosTrabajo';
import { useApp } from '../../shared/context';
import { ElegirFuente } from '../../shared/ElegirFuente';
import { FileDrop, GuardarSalida } from '../../shared/ui';
import { fuentes, type Fuente, type RedDelEspacio } from '../../api/fuentes';

const TIPO = 'vnr_estudio';
const SECTORES: [string, string][] = [
  ['urbano_alta', 'Urbano de alta densidad (cap. 6)'],
  ['urbano_media_baja', 'Urbano de media y baja densidad (cap. 7)'],
  ['urbano_rural', 'Urbano-rural (cap. 8)'],
  ['rural_ser', 'Rural y SER (cap. 9)'],
];
const miles = (v?: number | null) => (v == null ? '—' : v.toLocaleString('es-PE', { maximumFractionDigits: 2 }));

/**
 * Pestaña «Estudio VNR» (108 T28): el VNR adaptado según la Guía del VNR (RCD 232-2017-OS/CD) desde el inventario
 * VNR-GIS (canonical.json del conversor) y el SICODI de la última fijación; deja el libro de los formatos del Anexo 5.
 */
export function EstudioVnr() {
  const { ws, jobs, active, startJob, run } = useApp();
  const [estado, setEstado] = useState<VnrEstudio | null>(null);
  const [canonical, setCanonical] = useState<File | null>(null);
  const [sicodi, setSicodi] = useState<Fuente | File | null>(null);
  const [red, setRed] = useState<RedDelEspacio | null>(null);
  useEffect(() => { void fuentes.red(ws.id).then((r) => setRed(r.disponible === false ? null : r)).catch(() => setRed(null)); }, [ws.id]);
  const [sector, setSector] = useState('urbano_media_baja');
  const [sectorSicodi, setSectorSicodi] = useState('');
  const [resolucion, setResolucion] = useState('');
  const [anio, setAnio] = useState('');
  const [moneda, setMoneda] = useState('USD');  // el SICODI está en US$ (cotejado con el Anexo 8 de la empresa)

  const leer = useCallback(() => {
    void run(() => vnr.estado(ws.id)).then((e) => { if (e) setEstado(e); });
  }, [run, ws.id]);
  const terminado = Object.values(jobs)
    .filter((j) => j.kind === TIPO && j.workspace_id === ws.id && !['queued', 'running'].includes(j.status))
    .map((j) => j.id).pop();
  useEffect(leer, [leer, terminado]);

  const enCurso = Object.values(jobs).some((j) => j.kind === TIPO && j.workspace_id === ws.id
    && ['queued', 'running'].includes(j.status));
  const ocupado = Boolean(active.engine);
  const conRed = Boolean(canonical || red?.canonical);
  const listo = Boolean(conRed && sicodi && sectorSicodi.trim() && resolucion.trim() && Number(anio) > 1990
    && moneda.trim());
  const lanzar = () => conRed && sicodi && startJob(() => vnr.lanzar(ws.id, {
    sector, sector_sicodi: sectorSicodi.trim(), resolucion: resolucion.trim(), anio: Number(anio),
    moneda: moneda.trim(), canonical, sicodi: sicodi instanceof File ? sicodi : sicodi.id }));
  const r = estado && estado.libro ? estado : null;

  return (
    <div className="estudio-vnr">
      <AvisosTrabajo paso="vnr" />
      <p className="muted">VNR = MIE × CEIE + MINE × CINE (Guía del VNR, art. 17.2): zonificación, adaptación y
        valorización del inventario con los costos estándar del SICODI.</p>
      <div className="form-grid">
        <div className="field">
          <span>Inventario VNR-GIS</span>
          {red?.canonical && !canonical && <p className="muted">La red cargada en el espacio ({red.alimentadores?.length ?? 0} alimentadores{red.empresa ? `, ${red.empresa}` : ''}).</p>}
          <FileDrop entrada="vnr-inventario" compact accept=".json" disabled={ocupado}
            onFiles={(f) => setCanonical(f[0] ?? null)}>{canonical ? canonical.name : red?.canonical ? 'O suba otro canonical.json' : 'Suelte o elija el canonical.json'}</FileDrop>
        </div>
        <ElegirFuente clase="sicodi" etiqueta="SICODI de la última fijación" accept=".xlsx,.xlsm,.xls,.xlsb,.zip"
          disabled={ocupado} onElegir={setSicodi} />
        <label className="field">
          <span>Sector típico (Guía)</span>
          <select value={sector} disabled={ocupado} onChange={(e) => setSector(e.target.value)}>
            {SECTORES.map(([v, t]) => <option key={v} value={v}>{t}</option>)}
          </select>
        </label>
        <label className="field">
          <span>Sector del SICODI</span>
          <input value={sectorSicodi} placeholder="ST1…ST4, SER" disabled={ocupado}
            onChange={(e) => setSectorSicodi(e.target.value)} />
        </label>
        <label className="field">
          <span>Resolución de los costos</span>
          <input value={resolucion} disabled={ocupado} onChange={(e) => setResolucion(e.target.value)} />
        </label>
        <label className="field">
          <span>Año</span>
          <input type="number" value={anio} disabled={ocupado} onChange={(e) => setAnio(e.target.value)} />
        </label>
        <label className="field">
          <span>Moneda</span>
          <input value={moneda} disabled={ocupado} onChange={(e) => setMoneda(e.target.value)} />
        </label>
      </div>
      <div className="row">
        <button className="btn btn-primary" onClick={lanzar} disabled={ocupado || !listo}>
          {enCurso ? 'Calculando…' : 'Calcular el VNR'}
        </button>
        {ocupado && !enCurso && <small className="muted">Hay otro trabajo del motor en curso.</small>}
      </div>
      {r && (
        <section className="resultado-vnr" aria-label="Resultado del estudio VNR">
          <p>
            <strong>VNR {r.completo ? '' : '(incompleto) '}</strong>
            {miles(r.completo ? r.vnr_total : r.vnr_ie)} {r.moneda} · sector {r.sector_sicodi}
            {r.anualidad_vnr_real && typeof r.anualidad_vnr_real.anualidad === 'number'
              && <> · anualidad {miles(r.anualidad_vnr_real.anualidad)}</>}
          </p>
          <GuardarSalida url={api.fileUrl(ws.id, r.libro!, true)} nombre="formatos_vnr.xlsx" rel={r.libro!} />
          {(r.partidas_sin_costo?.length ?? 0) + (r.huecos?.length ?? 0) > 0 && (
            <details>
              <summary>Huecos ({(r.partidas_sin_costo?.length ?? 0) + (r.huecos?.length ?? 0)})</summary>
              <ul>{[...(r.partidas_sin_costo ?? []), ...(r.huecos ?? [])].map((h) => <li key={h}>{h}</li>)}</ul>
            </details>
          )}
        </section>
      )}
      {estado && !r && <p className="muted">Aún no hay un estudio VNR en este espacio.</p>}
    </div>
  );
}
