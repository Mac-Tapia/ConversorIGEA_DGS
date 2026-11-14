import { useEffect, useState } from 'react';

import { mapaCargas, type ConfirmacionMapa, type DatosMapa, type DiferenciaMapa, type LecturaMapa } from '../../api/mapaCargas';
import { useApp } from '../../shared/context';
import { Ayuda, Pill } from '../../shared/ui';
import { filasOrdenadas, rotuloCarga, sePuedeUsar, textoCoordenadas, textoDiferencia, ultimaLectura } from './puntosDeDiseno';

/**
 * 017:RF-109, RF-124: dónde se conectó cada carga nueva, sola o en bloque, sobre la red del alimentador.
 *
 * Usuario, 2026-11-13: «en la web se debe ver la ubicación en Google Maps o similar de dónde se conectó y la
 * ubicación de la carga nueva o de los bloques»; y «un botón para actualizar la imagen de la ubicación y el punto de
 * fijación de diseño cuando el usuario verificó en DIgSILENT, corrigió o asignó otro punto». El mapa es una página
 * generada por el servidor con Leaflet dentro, como la vista previa (086:RF-21): ni CDN ni dependencia nueva, y los
 * fondos de calles y satélite solo con la salida de las teselas encendida (086:RF-63). «Actualizar desde DIgSILENT»
 * solo lee el proyecto; «Usar este punto» guarda en el espacio, nunca en DIgSILENT.
 */
export function MapaCargas({ project, alimentadores = [], anio = null }: {
  project: string;
  alimentadores?: string[];
  anio?: number | null;
}) {
  const { ws, run, startJob, jobs, active } = useApp();
  const [datos, setDatos] = useState<DatosMapa | null>(null);
  const [refresco, setRefresco] = useState(0);
  const [confirmado, setConfirmado] = useState<ConfirmacionMapa | null>(null);
  const [alta, setAlta] = useState('');
  const clave = alimentadores.join('|');
  const lectura = ultimaLectura<LecturaMapa>(Object.values(jobs), project);

  useEffect(() => {
    if (!project) return;
    let vivo = true;
    void run(() => mapaCargas.datos(ws.id, project, alimentadores)).then((d) => { if (vivo && d) setDatos(d); });
    return () => { vivo = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ws.id, project, clave, refresco]);

  if (!project) return null;
  const ocupado = Boolean(active.powerfactory);
  const actualizar = () => void startJob(() => mapaCargas.actualizar(ws.id, project, alimentadores, anio));
  // 017:RF-124 ampliada: la carga aplicada desde otro espacio (SECA0001, 2026-11-13) se da de alta aquí.
  const darDeAlta = async (d: DiferenciaMapa) => {
    if (!lectura) return;
    const r = await run(() => mapaCargas.alta(ws.id, project, lectura.lectura, [{ alimentador: d.alimentador, sed: d.sed }]));
    if (r) {
      setAlta(r.aviso);
      setRefresco((n) => n + 1);
    }
  };
  const usar = async (filas: DiferenciaMapa[]) => {
    if (!lectura || !filas.length) return;
    const r = await run(() => mapaCargas.confirmar(ws.id, project, lectura.lectura,
      filas.map((d) => ({ alimentador: d.alimentador, sed: d.sed }))));
    if (r) {
      setConfirmado(r);
      setRefresco((n) => n + 1);
    }
  };
  const filas = lectura ? filasOrdenadas(lectura.diferencias) : [];
  const usables = filas.filter(sePuedeUsar);

  return (
    <section className="card">
      <h3>Ubicación de las cargas nuevas</h3>
      <Ayuda>
        Rombo rojo: la carga nueva en su punto; círculo azul: el nodo donde se conectó; línea discontinua: la línea de
        enlace. Si corrigió la conexión en DIgSILENT, pulse «Actualizar desde DIgSILENT» y elija el punto que vale.
      </Ayuda>
      <iframe key={refresco} className="map-frame" title={`Cargas nuevas de ${project}`}
        src={mapaCargas.paginaUrl(ws.id, project, alimentadores)} sandbox="allow-scripts allow-popups" />
      {datos && !datos.fondo.encendido && <p className="muted">Sin fondo de mapa: {datos.fondo.motivo}</p>}
      {datos && datos.avisos.length > 0 && <div className="alert alert-info">{datos.avisos.map((a) => <p key={a}>{a}</p>)}</div>}
      {datos && datos.cargas.length > 0 && (
        <div className="table-wrap table-short">
          <table className="table">
            <thead>
              <tr><th>Carga</th><th>Alimentador</th><th>Nodo de conexión</th><th>Punto de la carga</th>
                <th className="num">Enlace (km)</th><th /></tr>
            </thead>
            <tbody>
              {datos.cargas.map((c) => (
                <tr key={`${c.alimentador}|${c.sed}`}>
                  <td>{rotuloCarga(c)}</td>
                  <td>{c.alimentador}</td>
                  <td className="mono">{c.nodo.nombre ?? '—'} <span className="muted">{textoCoordenadas(c.nodo)}</span></td>
                  <td className="muted">{textoCoordenadas(c.punto)}</td>
                  <td className="num">{c.enlace?.km == null ? '—' : c.enlace.km.toFixed(3)}</td>
                  <td>{c.corregida && <Pill tone="info" title={`Confirmado el ${c.confirmado ?? ''}; aplicada en ${c.barra_aplicada ?? '—'}`}>corregido en DIgSILENT</Pill>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <div className="toolbar">
        <button type="button" onClick={actualizar} disabled={ocupado}
          title={ocupado ? 'Hay un trabajo de DIgSILENT en curso' : 'Lee el proyecto sin escribir nada en él'}>
          Actualizar desde DIgSILENT
        </button>
        {usables.length > 1 && (
          <button type="button" onClick={() => void usar(usables)}>Usar los {usables.length} puntos leídos</button>
        )}
      </div>
      {confirmado && <div className="alert alert-warn">{confirmado.aviso}</div>}
      {alta && <div className="alert alert-ok">{alta}</div>}
      {lectura && (
        <div className="table-wrap table-short">
          <table className="table">
            <thead>
              <tr><th>Carga</th><th>Alimentador</th><th>Guardado</th><th>En DIgSILENT ({lectura.caso ?? 'caso activo'})</th>
                <th>Diferencia</th><th /></tr>
            </thead>
            <tbody>
              {filas.map((d) => (
                <tr key={`${d.alimentador}|${d.sed}`}>
                  <td>{d.sed}</td>
                  <td>{d.alimentador ?? '—'}</td>
                  <td className="mono">{d.guardado?.barra ?? '—'}</td>
                  <td className="mono">{d.leido?.barra ?? '—'}{d.leido?.enlace ? ` · ${d.leido.enlace.nombre}` : ''}</td>
                  <td>{textoDiferencia(d)}</td>
                  <td>{sePuedeUsar(d) && <button type="button" onClick={() => void usar([d])}>Usar este punto</button>}
                    {d.estado === 'solo_en_digsilent' && (
                      <button type="button" className="btn btn-sm" onClick={() => void darDeAlta(d)}
                        title="La carga está en DIgSILENT pero no en esta web: se da de alta como carga sola, con su potencia y su punto">
                        Dar de alta</button>)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {lectura.avisos.map((a) => <p key={a} className="muted">{a}</p>)}
        </div>
      )}
    </section>
  );
}
