import { useCallback, useEffect, useState } from 'react';
import { api } from '../../api/client';
import { vad, type DestinoVad, type DetalleVad, type EstudioVadFila, type ObservacionVadDetalle } from '../../api/vad';
import { AvisosTrabajo } from '../../shared/AvisosTrabajo';
import { useApp } from '../../shared/context';
import { ElegirFuente } from '../../shared/ElegirFuente';
import { GuardarSalida } from '../../shared/ui';

const TIPOS = ['vad_empresa_modelo', 'vad_informe_definitivo'];
const nombre = (rel: string) => rel.split('/').pop() ?? rel;
const destinoTexto = (d: DestinoVad) => `${d.tipo} ${d.id}`;

/** La respuesta de una observación pendiente: texto, sustento y qué cambió en cada destino que afecta. */
function Responder({ o, onResponder }: { o: ObservacionVadDetalle; onResponder: (r: { respuesta: string; sustento: string;
  cambios: Record<string, string> }) => void }) {
  const [respuesta, setRespuesta] = useState('');
  const [sustento, setSustento] = useState('');
  const [cambios, setCambios] = useState<Record<string, string>>({});
  const completa = respuesta.trim() && sustento.trim() && o.afecta.every((d) => cambios[destinoTexto(d)]?.trim());
  return (
    <div className="form-grid">
      <label className="field"><span>Respuesta</span>
        <textarea value={respuesta} onChange={(e) => setRespuesta(e.target.value)} /></label>
      <label className="field"><span>Sustento</span>
        <input value={sustento} onChange={(e) => setSustento(e.target.value)} /></label>
      {o.afecta.map((d) => (
        <label key={destinoTexto(d)} className="field"><span>Qué cambió en {destinoTexto(d)}</span>
          <input value={cambios[destinoTexto(d)] ?? ''} placeholder="o «no cambia: …»"
            onChange={(e) => setCambios({ ...cambios, [destinoTexto(d)]: e.target.value })} /></label>
      ))}
      <button className="btn" disabled={!completa} onClick={() => onResponder({ respuesta, sustento, cambios })}>
        Responder
      </button>
    </div>
  );
}

/**
 * Pestaña «Estudio VAD» (108 T29): el estudio de costos con la empresa modelo eficiente. Crear el estudio, subir el caso y
 * armar la empresa modelo, registrar y responder las observaciones del regulador, y armar el Informe Definitivo.
 */
export function EstudioVad() {
  const { ws, jobs, active, startJob, run } = useApp();
  const [estudios, setEstudios] = useState<EstudioVadFila[]>([]);
  const [elegido, setElegido] = useState('');
  const [detalle, setDetalle] = useState<DetalleVad | null>(null);
  const [grupo, setGrupo] = useState('1');
  const [periodo, setPeriodo] = useState('');
  const [tdr, setTdr] = useState('');
  // 109:RF-25: el caso de la empresa (clase «vad_caso»): el vigente, otro de la lista o uno subido.
  const [caso, setCaso] = useState<File | { id: string } | null>(null);
  const [obs, setObs] = useState({ numero: '', fecha: '', texto: '', destino: '' });

  const leer = useCallback(() => {
    void run(() => vad.estudios(ws.id)).then((r) => {
      if (!r) return;
      setEstudios(r.estudios);
      setElegido((e) => e || r.estudios[0]?.id || '');
    });
  }, [run, ws.id]);
  const leerDetalle = useCallback(() => {
    if (elegido) void run(() => vad.detalle(ws.id, elegido)).then((d) => { if (d) setDetalle(d); });
  }, [run, ws.id, elegido]);
  const terminado = Object.values(jobs)
    .filter((j) => TIPOS.includes(j.kind) && j.workspace_id === ws.id && !['queued', 'running'].includes(j.status))
    .map((j) => j.id).pop();
  useEffect(leer, [leer, terminado]);
  useEffect(leerDetalle, [leerDetalle, terminado]);

  const ocupado = Boolean(active.engine);
  const crear = () => run(async () => {
    const e = await vad.crear(ws.id, { grupo: Number(grupo), periodo: periodo.trim(), version_tdr: tdr.trim() });
    setElegido(e.id);
    leer();
  });
  const registrar = () => {
    const [tipo, ...resto] = obs.destino.split(' ');
    void run(async () => {
      await vad.observar(ws.id, elegido, { numero: obs.numero.trim(), fecha: obs.fecha, texto: obs.texto.trim(),
        afecta: [{ tipo, id: resto.join(' ') }] });
      setObs({ numero: '', fecha: '', texto: '', destino: '' });
      leerDetalle();
    });
  };
  const d = detalle && detalle.estudio.id === elegido ? detalle : null;
  const inf = d?.informe_definitivo;

  return (
    <div className="estudio-vad">
      <AvisosTrabajo paso="vad" />
      <div className="form-grid">
        <label className="field"><span>Estudio</span>
          <select value={elegido} onChange={(e) => setElegido(e.target.value)}>
            {estudios.map((e) => <option key={e.id} value={e.id}>{`G${e.grupo} ${e.periodo} · ${e.estado}`}</option>)}
          </select></label>
        <label className="field"><span>Grupo</span>
          <input type="number" min={1} max={9} value={grupo} onChange={(e) => setGrupo(e.target.value)} /></label>
        <label className="field"><span>Periodo</span>
          <input value={periodo} placeholder="2027-2031" onChange={(e) => setPeriodo(e.target.value)} /></label>
        <label className="field"><span>Versión del TdR</span>
          <input value={tdr} onChange={(e) => setTdr(e.target.value)} /></label>
      </div>
      <div className="row">
        <button className="btn" onClick={crear} disabled={!/^\d{4}-\d{4}$/.test(periodo.trim()) || !tdr.trim()}>
          Crear estudio</button>
      </div>

      {d && (
        <>
          <section aria-label="Empresa modelo">
            <ElegirFuente clase="vad_caso" etiqueta="Caso (zip con sistemas.json y sus tablas)" accept=".zip"
              disabled={ocupado} onElegir={setCaso} />
            <div className="row">
              <button className="btn btn-primary" disabled={ocupado || !caso}
                onClick={() => startJob(() => vad.armar(ws.id, elegido, caso))}>Armar la empresa modelo</button>
              {ocupado && <small className="muted">Hay otro trabajo del motor en curso.</small>}
            </div>
            {d.armado && (
              <ul className="small">
                {Object.entries(d.armado.sistemas).map(([s, r]) => (
                  <li key={s}><strong>{s}</strong> · {r.estado}
                    {r.error ? ` · ${r.error}` : ''}
                    {Object.values(r.pasos ?? {}).some((p) => p.huecos?.length)
                      ? ` · ${Object.values(r.pasos ?? {}).reduce((n, p) => n + (p.huecos?.length ?? 0), 0)} huecos` : ''}</li>
                ))}
              </ul>
            )}
          </section>

          {d.linea && (
            <section aria-label="Línea del VAD">
              <h3>Línea del VAD</h3>
              <ul className="small">
                {Object.entries(d.linea.pasos).map(([p, r]) => (
                  <li key={p}><strong>{p}</strong> · {r.estado}{r.motivo || r.error ? ` · ${r.motivo || r.error}` : ''}</li>
                ))}
              </ul>
            </section>
          )}

          <section aria-label="Observaciones del regulador">
            <h3>Observaciones ({d.pendientes.length} pendientes)</h3>
            {d.aviso_destinos && <p className="muted">{d.aviso_destinos}</p>}
            <div className="form-grid">
              <label className="field"><span>Número</span>
                <input value={obs.numero} onChange={(e) => setObs({ ...obs, numero: e.target.value })} /></label>
              <label className="field"><span>Fecha</span>
                <input type="date" value={obs.fecha} onChange={(e) => setObs({ ...obs, fecha: e.target.value })} /></label>
              <label className="field"><span>Afecta a</span>
                <select value={obs.destino} onChange={(e) => setObs({ ...obs, destino: e.target.value })}>
                  <option value="">—</option>
                  {d.destinos.map((x) => <option key={destinoTexto(x)} value={destinoTexto(x)}>{destinoTexto(x)}</option>)}
                </select></label>
              <label className="field"><span>Texto</span>
                <textarea value={obs.texto} onChange={(e) => setObs({ ...obs, texto: e.target.value })} /></label>
            </div>
            <button className="btn" onClick={registrar}
              disabled={!obs.numero.trim() || !obs.fecha || !obs.texto.trim() || !obs.destino}>Registrar observación</button>
            {d.observaciones.map((o) => (
              <details key={o.numero}>
                <summary>{o.numero} · {o.estado} · {o.afecta.map(destinoTexto).join(', ')}</summary>
                <p>{o.texto}</p>
                {o.estado === 'pendiente'
                  ? <Responder o={o} onResponder={(r) => void run(async () => {
                    await vad.responder(ws.id, elegido, o.numero, r);
                    leerDetalle();
                  })} />
                  : <p className="muted">{o.respuesta} ({o.sustento})</p>}
              </details>
            ))}
          </section>

          <section aria-label="Informe Definitivo">
            <div className="row">
              <button className="btn btn-primary" disabled={ocupado || d.pendientes.length > 0}
                onClick={() => startJob(() => vad.informeDefinitivo(ws.id, elegido))}>Armar el Informe Definitivo</button>
              {d.pendientes.length > 0 && <small className="muted">Antes, responda las observaciones.</small>}
            </div>
            {inf && (
              <ul className="small">
                {inf.documentos.map((doc) => (
                  <li key={doc.documento}>
                    {doc.ruta_relativa
                      ? <GuardarSalida url={api.fileUrl(ws.id, doc.ruta_relativa, true)} nombre={nombre(doc.ruta_relativa)}
                        rel={doc.ruta_relativa} />
                      : <span>{doc.documento}: <span className="muted">{doc.motivo}</span></span>}
                  </li>
                ))}
              </ul>
            )}
            {inf && inf.huecos.length > 0 && (
              <details><summary>Huecos ({inf.huecos.length})</summary>
                <ul>{inf.huecos.map((h) => <li key={h}>{h}</li>)}</ul></details>
            )}
          </section>

          {d.salidas.length > 0 && (
            <details>
              <summary>Salidas ({d.salidas.length})</summary>
              {d.salidas.map((s) => <GuardarSalida key={s} url={api.fileUrl(ws.id, s, true)} nombre={nombre(s)} rel={s} />)}
            </details>
          )}
        </>
      )}
      {!estudios.length && <p className="muted">Aún no hay un estudio del VAD en este espacio.</p>}
    </div>
  );
}
