import { useCallback, useEffect, useState } from 'react';
import { ApiError } from '../../api/client';
import { correo, type Adjuntable, type CorreoEnvio, type CorreoPeticion, type CorreoVistaPrevia } from '../../api/correo';
import { nube, type CuentaNube } from '../../api/nube';
import { useApp } from '../../shared/context';
import { fmtBytes } from '../../shared/formato';
import { Modal, Pill } from '../../shared/ui';
import { cuentaElegida, cuentasDeCorreo, mismaPeticion, motivoSinCuenta, peticionVistaPrevia, textoEstado,
  type CamposCorreo, type CuentaDeCorreo } from './enviarInformeLogica';

const EN_CURSO = new Set(['queued', 'running']);
const ADJUNTOS: { clave: Adjuntable; etiqueta: string }[] = [
  { clave: 'docx', etiqueta: 'Word' }, { clave: 'pdf', etiqueta: 'PDF' }, { clave: 'xlsx', etiqueta: 'Libro' }];
const motivo = (e: unknown) => (e instanceof Error ? e.message : String(e));

/** 110:RF-1: el botón junto a «Descargar Word»; sin cuenta, desactivado y con su motivo. */
export function BotonEnviar({ motivo: porQue, onAbrir }: { motivo: string | null; onAbrir: () => void }) {
  return (
    <>
      <button className="btn btn-sm" disabled={Boolean(porQue)} title={porQue ?? undefined} onClick={onAbrir}>
        Enviar por correo</button>
      {porQue && <> <small className="muted">{porQue}</small></>}
    </>
  );
}

/** 110:RF-1, RF-3, RF-10, RF-12, RF-14: lo que saldrá, tal como lo devolvió el servidor, y el botón de confirmar. */
export function VistaPrevia({ previa, ocupado, onConfirmar }: {
  previa: CorreoVistaPrevia;
  ocupado: boolean;
  onConfirmar: () => void;
}) {
  const filas: [string, string[]][] = [['Para', previa.para], ['CC', previa.cc], ['CCO', previa.cco]];
  return (
    <div className="stack">
      {!previa.validez.valido && <p className="alert alert-warn">{`No válido como estudio: ${previa.validez.motivo}`}</p>}
      <p className="small">{`De: ${previa.cuenta}`}</p>
      {filas.filter(([, ds]) => ds.length > 0).map(([titulo, ds]) => (
        <div key={titulo} className="stack">
          <strong className="small">{titulo}</strong>
          <ul>{ds.map((d) => {
            const a = previa.avisos[d];
            return (
              <li key={d}>{d}{a && <> <small className="alert alert-warn">
                {a.sugerencia ? `${a.aviso} ¿Quiso decir ${a.sugerencia}?` : a.aviso}</small></>}</li>
            );
          })}</ul>
        </div>
      ))}
      <p><strong>{previa.asunto}</strong></p>
      <p className="small" style={{ whiteSpace: 'pre-wrap' }}>{previa.cuerpo}</p>
      {previa.enlace ? <p className="small">{`Enlace: ${previa.enlace}`}</p> : (
        <ul>{previa.adjuntos.map((a) => <li key={a.nombre}>{a.nombre} <span className="muted small">{fmtBytes(a.tamano)}</span></li>)}</ul>
      )}
      {previa.excede_limite && (
        <p className="alert alert-warn">{`Los adjuntos pasan de ${fmtBytes(previa.limite_bytes)}: envíe mejor un enlace al expediente.`}</p>
      )}
      <div>
        <button className="btn btn-primary" disabled={ocupado} onClick={onConfirmar}>Confirmar y enviar</button>
      </div>
    </div>
  );
}

/** 110:RF-8, RF-9, RF-13: los envíos de este informe; un resultado desconocido lo resuelve el operador. */
export function HistorialEnvios({ envios, ocupado, onResolver }: {
  envios: CorreoEnvio[];
  ocupado: boolean;
  onResolver: (clave: string, llego: boolean) => void;
}) {
  if (envios.length === 0) return <p className="muted small">Sin envíos de este informe.</p>;
  return (
    <ul className="stack">
      {envios.map((e) => {
        const t = textoEstado(e.estado);
        return (
          <li key={e.clave} className="stack">
            <div className="row">
              <Pill tone={t.tono}>{t.texto}</Pill>
              <span className="small">{(e.destinatarios.para ?? []).join(', ')}</span>
              <span className="muted small">{e.hora.replace('T', ' ').slice(0, 16)}</span>
            </div>
            {e.motivo && <small className="muted">{e.motivo}</small>}
            {e.estado === 'desconocido' && !e.resolucion && (
              <div className="row">
                <button className="btn btn-sm" disabled={ocupado} onClick={() => onResolver(e.clave, true)}>Llegó</button>
                <button className="btn btn-sm btn-ghost" disabled={ocupado} onClick={() => onResolver(e.clave, false)}>No llegó</button>
              </div>
            )}
          </li>
        );
      })}
    </ul>
  );
}

/** 110:RF-1: «Enviar desde» lista las cuentas conectadas en la nube; la que aún no envía ofrece su permiso. */
export function EnviarDesde({ opciones, valor, onCambio, onPedirPermiso }: {
  opciones: CuentaDeCorreo[];
  valor: string;
  onCambio: (valor: string) => void;
  onPedirPermiso: () => void;
}) {
  const elegida = cuentaElegida(opciones, valor);
  return (
    <div className="stack">
      <label className="field"><span>Enviar desde</span>
        <select value={valor} onChange={(e) => onCambio(e.target.value)}>
          {opciones.map((o) => <option key={`${o.proveedor}|${o.cuenta}`} value={`${o.proveedor}|${o.cuenta}`}>{o.etiqueta}</option>)}
        </select>
      </label>
      {elegida && !elegida.puedeEnviar && (
        <div className="row">
          <small className="muted">Esta cuenta aún no envía correo.</small>
          <button className="btn btn-sm btn-ghost" onClick={onPedirPermiso}>Dar permiso para enviar</button>
        </div>
      )}
    </div>
  );
}

const VACIOS: CamposCorreo = { cuenta: '', para: '', cc: '', cco: '', asunto: '', cuerpo: '', adjuntar: ['docx', 'pdf', 'xlsx'] };

/** La ventana de envío de un informe cerrado (`informe` es el Word de la salida del espacio). */
export function EnviarInforme({ informe, proyecto, escenario }: { informe: string; proyecto?: string | null;
  escenario?: string | null }) {
  const { ws, jobs, startJob } = useApp();
  const [cuentas, setCuentas] = useState<CuentaNube[] | null>(null);
  const [errorCuentas, setErrorCuentas] = useState<string | null>(null);
  const [abierto, setAbierto] = useState(false);
  const [campos, setCampos] = useState<CamposCorreo>(VACIOS);
  const [previa, setPrevia] = useState<{ peticion: CorreoPeticion; respuesta: CorreoVistaPrevia } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);
  const [envio, setEnvio] = useState<{ clave: string; job: string | null; recibo: CorreoEnvio | null } | null>(null);
  const [historial, setHistorial] = useState<CorreoEnvio[]>([]);

  useEffect(() => {
    nube.cuentas(ws.id).then((r) => { setCuentas(r.cuentas); setErrorCuentas(null); })
      .catch((e) => { setCuentas(null); setErrorCuentas(motivo(e)); });
  }, [ws.id]);
  const leerHistorial = useCallback(async () => {
    try { setHistorial((await correo.historial(ws.id, informe)).envios); } catch (e) { setError(motivo(e)); }
  }, [ws.id, informe]);
  useEffect(() => { if (abierto) void leerHistorial(); }, [abierto, leerHistorial]);

  // El trabajo del envío terminó: su recibo y el historial, sin sondeo (llega por el WebSocket de los trabajos).
  const trabajo = envio?.job ? jobs[envio.job] : undefined;
  const enCurso = Boolean(trabajo && EN_CURSO.has(trabajo.status));
  useEffect(() => {
    if (!envio?.job || !trabajo || EN_CURSO.has(trabajo.status) || envio.recibo) return;
    correo.envio(ws.id, envio.clave).then((r) => setEnvio((v) => (v ? { ...v, recibo: r } : v)))
      .catch((e) => setError(motivo(e)));
    void leerHistorial();
  }, [trabajo, envio, ws.id, leerHistorial]);

  const porQue = motivoSinCuenta(cuentas, errorCuentas);
  const opciones = cuentasDeCorreo(cuentas);
  const ctx = { informe, proyecto, escenario };
  let actual: CorreoPeticion | null = null;
  try { actual = peticionVistaPrevia(campos, ctx); } catch { actual = null; }
  const vigente = previa && mismaPeticion(previa.peticion, actual) ? previa.respuesta : null;
  const ocupado = enviando || enCurso;
  const fijar = (p: Partial<CamposCorreo>) => { setCampos((c) => ({ ...c, ...p })); setError(null); };
  const elegida = cuentaElegida(opciones, campos.cuenta);
  // 110:RF-1: la misma cuenta de la nube pide el permiso de envío (incremental); vuelve por el retorno de la nube.
  const pedirEnvio = async () => {
    if (!elegida) return;
    try { window.location.assign((await nube.conectar(ws.id, elegida.proveedor, 'enviar')).url); }
    catch (e) { setError(motivo(e)); }
  };

  const abrir = () => {
    setCampos({ ...VACIOS, cuenta: opciones[0] ? `${opciones[0].proveedor}|${opciones[0].cuenta}` : '' });
    setPrevia(null);
    setEnvio(null);
    setError(null);
    setAbierto(true);
  };
  const verPrevia = async () => {
    setError(null);
    try {
      const peticion = peticionVistaPrevia(campos, ctx);
      setPrevia({ peticion, respuesta: await correo.vistaPrevia(ws.id, peticion) });
    } catch (e) { setError(motivo(e)); }
  };
  const confirmar = async () => {
    if (!vigente) return;
    setEnviando(true);
    setError(null);
    try {
      const r = await correo.confirmar(ws.id, vigente.borrador, vigente.firma);
      const job = r.trabajo ? await startJob(async () => r.trabajo!) : undefined;
      setEnvio({ clave: r.clave, job: job?.id ?? null, recibo: r.recibo });
      setPrevia(null);
      if (r.recibo) void leerHistorial();
    } catch (e) {
      // 409: el informe o un adjunto cambió desde la vista previa (110:RF-4): hay que revisarlo otra vez.
      if (e instanceof ApiError && e.status === 409) setPrevia(null);
      setError(motivo(e));
    } finally {
      setEnviando(false);
    }
  };
  const resolver = async (clave: string, llego: boolean) => {
    try { await correo.resolver(ws.id, clave, llego); await leerHistorial(); } catch (e) { setError(motivo(e)); }
  };
  const estado = envio?.recibo ? textoEstado(envio.recibo.estado) : enCurso ? textoEstado('enviando') : null;

  return (
    <>
      <BotonEnviar motivo={porQue} onAbrir={abrir} />
      {abierto && (
        <Modal title="Enviar por correo" wide onClose={() => setAbierto(false)}>
          <div className="stack">
            <div className="form-grid">
              <EnviarDesde opciones={opciones} valor={campos.cuenta} onCambio={(v) => fijar({ cuenta: v })}
                onPedirPermiso={() => void pedirEnvio()} />
              <label className="field"><span>Para</span>
                <input value={campos.para} placeholder="Una o varias direcciones" onChange={(e) => fijar({ para: e.target.value })} />
              </label>
              <label className="field"><span>CC</span>
                <input value={campos.cc} onChange={(e) => fijar({ cc: e.target.value })} />
              </label>
              <label className="field"><span>CCO</span>
                <input value={campos.cco} onChange={(e) => fijar({ cco: e.target.value })} />
              </label>
              <label className="field span-2"><span>Asunto</span>
                <input value={campos.asunto} placeholder="Se propone el del informe" onChange={(e) => fijar({ asunto: e.target.value })} />
              </label>
              <label className="field span-2"><span>Mensaje</span>
                <textarea rows={4} value={campos.cuerpo} placeholder="Se propone uno si lo deja vacío"
                  onChange={(e) => fijar({ cuerpo: e.target.value })} />
              </label>
            </div>
            <fieldset className="row">
              <legend className="small">Adjuntos</legend>
              {ADJUNTOS.map((a) => (
                <label key={a.clave} className="row">
                  <input type="checkbox" checked={campos.adjuntar.includes(a.clave)} onChange={(e) => fijar({
                    adjuntar: e.target.checked ? [...campos.adjuntar, a.clave] : campos.adjuntar.filter((x) => x !== a.clave) })} />
                  <span>{a.etiqueta}</span>
                </label>
              ))}
            </fieldset>
            {!vigente && <div><button className="btn" disabled={ocupado} onClick={() => void verPrevia()}>Vista previa</button></div>}
            {vigente && <VistaPrevia previa={vigente} ocupado={ocupado} onConfirmar={() => void confirmar()} />}
            <div aria-live="polite">
              {estado && <p><Pill tone={estado.tono}>{estado.texto}</Pill>{envio?.recibo?.motivo ? <> <small className="muted">{envio.recibo.motivo}</small></> : null}</p>}
              {error && <p className="alert alert-error" role="alert">{error}</p>}
            </div>
            <h3>Envíos de este informe</h3>
            <HistorialEnvios envios={historial} ocupado={ocupado} onResolver={(c, l) => void resolver(c, l)} />
          </div>
        </Modal>
      )}
    </>
  );
}
