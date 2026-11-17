import { useEffect, useState } from 'react';
import { api } from '../../api/client';
import { LIBROS_RED, leerAnios, pit, type AreaPit, type CapacidadesPit } from '../../api/pit';
import type { Job } from '../../api/types';
import { AvisosTrabajo } from '../../shared/AvisosTrabajo';
import { useApp } from '../../shared/context';
import { FileDrop, GuardarSalida } from '../../shared/ui';

interface ResultadoDiagnostico { salida_relativa?: string | null; completo?: boolean; avisos?: string[] }
interface ResultadoExpediente {
  tipo?: string; estado?: string; carpeta_relativa?: string | null; salidas_relativas?: Record<string, string>;
  pendientes?: { causa?: string }[]; libro_f000?: { motivo?: string };
}

const nombre = (rel: string) => rel.split('/').pop() ?? rel;

/** El último trabajo terminado de un tipo en este espacio. */
function ultimo<R>(jobs: Record<string, Job>, wsId: string, kind: string): Job<R> | undefined {
  return Object.values(jobs).filter((j) => j.kind === kind && j.workspace_id === wsId && j.status === 'done').pop();
}

/**
 * Pestaña «Estudio PIT» (107 T13): el diagnóstico de la red del área y el expediente del Plan de Inversiones en
 * Transmisión, como trabajos del carril engine, y el registro de las observaciones de Osinergmin.
 */
export function EstudioPit() {
  const { ws, jobs, active, startJob, run } = useApp();
  const [areas, setAreas] = useState<AreaPit[]>([]);
  const [caps, setCaps] = useState<CapacidadesPit | null>(null);
  const [area, setArea] = useState('');
  const [periodo, setPeriodo] = useState('');
  const [aniosTexto, setAniosTexto] = useState('');
  const [motor, setMotor] = useState('abierto');
  const [libro, setLibro] = useState<File | null>(null);
  const [proyeccion, setProyeccion] = useState<File | null>(null);
  const [alternativas, setAlternativas] = useState<File | null>(null);
  const [elegida, setElegida] = useState('');
  const [obs, setObs] = useState<File | null>(null);

  useEffect(() => {
    void run(() => pit.areas()).then((r) => {
      if (!r) return;
      setAreas(r.areas);
      setArea((a) => a || r.areas[0]?.codigo || '');
    });
    void run(() => pit.capacidades()).then((r) => { if (r) setCaps(r); });
  }, [run]);

  const ocupado = Boolean(active.engine);
  const anios = leerAnios(aniosTexto);
  const listo = Boolean(area && anios && libro && proyeccion);
  const listoExpediente = listo && Boolean(periodo.trim()) && (!alternativas || Boolean(elegida.trim()));

  /** Sube lo elegido al espacio y devuelve sus rutas: libro, proyección y, si hay, alternativas. */
  const subir = async () => {
    const files = [libro!, proyeccion!, ...(alternativas ? [alternativas] : [])];
    return (await pit.entradas(ws.id, files)).rutas;
  };
  const diagnosticar = () => startJob(async () => {
    const [libroRed, proy] = await subir();
    return pit.diagnostico({ workspace_id: ws.id, area, anios: anios!, libro_red: libroRed, proyeccion: proy, motor });
  });
  const armar = () => startJob(async () => {
    const [libroRed, proy, alt] = await subir();
    return pit.expediente({
      workspace_id: ws.id, area, periodo: periodo.trim(), anios: anios!, libro_red: libroRed, proyeccion: proy,
      alternativas: alt ?? null, alternativa_elegida: alt ? elegida.trim() : null, motor,
    });
  });

  const diag = ultimo<ResultadoDiagnostico>(jobs, ws.id, 'pit_diagnostico')?.result;
  const exp = ultimo<ResultadoExpediente>(jobs, ws.id, 'pit_expediente')?.result;
  const registrar = () => obs && exp?.carpeta_relativa && run(async () => {
    const datos = JSON.parse(await obs.text()) as { observaciones: Record<string, unknown>[];
      referencias: Record<string, Record<string, unknown>> };
    return pit.observaciones({ workspace_id: ws.id, expediente: exp.carpeta_relativa!, ...datos });
  });

  return (
    <div className="estudio-pit">
      <AvisosTrabajo paso="pit" />
      <div className="form-grid">
        <label className="field">
          <span>Área de demanda</span>
          <select value={area} disabled={ocupado} onChange={(e) => setArea(e.target.value)}>
            {areas.map((a) => <option key={a.codigo} value={a.codigo}>{a.codigo}</option>)}
          </select>
        </label>
        <label className="field">
          <span>Años</span>
          <input value={aniosTexto} placeholder="2027-2031" disabled={ocupado} aria-invalid={Boolean(aniosTexto) && !anios}
            onChange={(e) => setAniosTexto(e.target.value)} />
        </label>
        <label className="field">
          <span>Periodo del plan</span>
          <input value={periodo} placeholder="2025-2029" disabled={ocupado} onChange={(e) => setPeriodo(e.target.value)} />
        </label>
        <label className="field">
          <span>Motor</span>
          <select value={motor} disabled={ocupado} onChange={(e) => setMotor(e.target.value)}>
            {(caps?.motores ?? ['abierto']).map((m) => (
              <option key={m} value={m} disabled={m === 'digsilent'}>{m}</option>
            ))}
          </select>
        </label>
        <div className="field">
          <span>Libro de la red</span>
          <FileDrop entrada="pit-libro-red" compact accept={LIBROS_RED} disabled={ocupado}
            onFiles={(f) => setLibro(f[0] ?? null)}>{libro ? libro.name : 'Suelte o elija el libro'}</FileDrop>
        </div>
        <div className="field">
          <span>Proyección de la demanda</span>
          <FileDrop entrada="pit-proyeccion" compact accept=".json" disabled={ocupado}
            onFiles={(f) => setProyeccion(f[0] ?? null)}>{proyeccion ? proyeccion.name : 'Suelte o elija el JSON'}</FileDrop>
        </div>
        <div className="field">
          <span>Alternativas (opcional)</span>
          <FileDrop entrada="pit-alternativas" compact accept=".json" disabled={ocupado}
            onFiles={(f) => setAlternativas(f[0] ?? null)}>{alternativas ? alternativas.name : 'Suelte o elija el JSON'}</FileDrop>
        </div>
        {alternativas && (
          <label className="field">
            <span>Alternativa elegida</span>
            <input value={elegida} disabled={ocupado} onChange={(e) => setElegida(e.target.value)} />
          </label>
        )}
      </div>
      <div className="row">
        <button className="btn" onClick={diagnosticar} disabled={ocupado || !listo}>Diagnosticar</button>
        <button className="btn btn-primary" onClick={armar} disabled={ocupado || !listoExpediente}>Armar el expediente</button>
        {ocupado && <small className="muted">Hay otro trabajo del motor en curso.</small>}
      </div>
      {caps && (
        <details>
          <summary>Qué calcula cada motor</summary>
          <table className="small" aria-label="Alcance de cada motor">
            <thead><tr><th>Motor</th><th>Estudio</th><th>Alcance</th></tr></thead>
            <tbody>{caps.matriz.map((c) => (
              <tr key={`${c.motor}-${c.estudio}`}><td>{c.motor}</td><td>{c.estudio}</td><td>{c.alcance}</td></tr>
            ))}</tbody>
          </table>
        </details>
      )}
      {diag && (
        <section className="resultado-pit" aria-label="Diagnóstico del PIT">
          <p><strong>Diagnóstico {diag.completo ? 'completo' : 'incompleto'}</strong>
            {diag.avisos?.length ? ` · ${diag.avisos.length} avisos` : ''}</p>
          {diag.salida_relativa && (
            <GuardarSalida url={api.fileUrl(ws.id, diag.salida_relativa, true)} nombre={nombre(diag.salida_relativa)}
              rel={diag.salida_relativa} />
          )}
        </section>
      )}
      {exp && (
        <section className="resultado-pit" aria-label="Expediente del PIT">
          <p><strong>{exp.tipo}</strong> · {exp.estado}</p>
          {Object.entries(exp.salidas_relativas ?? {}).map(([k, rel]) => (
            <GuardarSalida key={k} url={api.fileUrl(ws.id, rel, true)} nombre={nombre(rel)} rel={rel} />
          ))}
          {exp.libro_f000?.motivo && <p className="muted">F-000: {exp.libro_f000.motivo}</p>}
          {(exp.pendientes?.length ?? 0) > 0 && (
            <details>
              <summary>Pendientes ({exp.pendientes!.length})</summary>
              <ul>{exp.pendientes!.map((p, i) => <li key={i}>{p.causa}</li>)}</ul>
            </details>
          )}
          {exp.carpeta_relativa && (
            <div className="row">
              <FileDrop entrada="pit-observaciones" compact accept=".json"
                onFiles={(f) => setObs(f[0] ?? null)}>{obs ? obs.name : 'Observaciones (JSON)'}</FileDrop>
              <button className="btn" onClick={registrar} disabled={!obs}>Registrar observaciones</button>
            </div>
          )}
        </section>
      )}
    </div>
  );
}
