import { useCallback, useEffect, useRef, useState } from 'react';
import { nube, type CompartirPreviaRespuesta, type CuentaNube, type ProveedorNube, type PublicarPreviaRespuesta,
  type ReciboNube } from '../../api/nube';
import { useApp } from '../../shared/context';
import { separarDirecciones } from '../../shared/direcciones';
import { Modal } from '../../shared/ui';
import { faltaPermiso, publicacionesDe, puedeConfirmarCompartir, VISIBLE } from './logica';
import { useSelector } from './useSelector';

const TERMINADO = new Set(['done', 'failed', 'cancelled', 'parcial', 'interrumpido']);
const DE_PUBLICAR = new Set(['nube_publicar', 'nube_compartir']);
const motivo = (e: unknown) => (e instanceof Error ? e.message : String(e));

/** 109:RF-10, RF-11, RF-20: quién tendrá acceso, el aviso del enlace público y lo que impide compartir. */
export function VistaCompartir({ previa, autorizo, onAutorizo, ocupado, onConfirmar }: {
  previa: CompartirPreviaRespuesta;
  autorizo: boolean;
  onAutorizo: (v: boolean) => void;
  ocupado: boolean;
  onConfirmar: () => void;
}) {
  return (
    <div className="stack">
      <strong>Tendrán acceso de solo lectura</strong>
      <ul>{previa.acceso.map((a) => <li key={a.destinatario}>{a.destinatario}</li>)}</ul>
      {previa.bloqueo.length > 0 && (
        <p className="alert alert-error" role="alert">
          {`No se comparte: lleva datos de la distribuidora sin procesar (${previa.bloqueo.join(', ')}).`}</p>
      )}
      {previa.publico && previa.aviso_publico && (
        <>
          <p className="alert alert-warn">{previa.aviso_publico}</p>
          <label className="row">
            <input type="checkbox" checked={autorizo} onChange={(e) => onAutorizo(e.target.checked)} />
            <span>Autorizo el enlace público en este envío</span>
          </label>
        </>
      )}
      <div>
        <button className="btn btn-primary" disabled={ocupado || !puedeConfirmarCompartir(previa, autorizo)}
          onClick={onConfirmar}>Compartir</button>
      </div>
    </div>
  );
}

/** 109:RF-9 a RF-13: publicar el expediente (la salida del espacio) en una carpeta de la nube y compartirlo. */
export function PublicarExpediente({ cuentas, seleccion, nombreInicial = '', paraInicial = '', boton = 'Publicar' }: {
  cuentas: CuentaNube[];
  /** 109:RF-24: publicar solo esta salida (su ruta en la salida del espacio) en lugar del expediente entero. */
  seleccion?: string[];
  nombreInicial?: string;
  /** Spec 070, RF-80: las direcciones que dijo la orden al asistente; el operador las revisa antes de compartir. */
  paraInicial?: string;
  boton?: string;
}) {
  const { ws, jobs, active, startJob } = useApp();
  const [abierto, setAbierto] = useState(false);
  const [proveedor, setProveedor] = useState<ProveedorNube>(cuentas[0]?.nombre ?? 'google');
  const [carpeta, setCarpeta] = useState('');
  const [nombre, setNombre] = useState(nombreInicial);
  const [previa, setPrevia] = useState<PublicarPreviaRespuesta | null>(null);
  const [recibos, setRecibos] = useState<ReciboNube[]>([]);
  const [publicacion, setPublicacion] = useState('');
  const [para, setPara] = useState(paraInicial);
  const [publico, setPublico] = useState(false);
  const [previaC, setPreviaC] = useState<CompartirPreviaRespuesta | null>(null);
  const [autorizo, setAutorizo] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [estado, setEstado] = useState<string | null>(null);
  const vistos = useRef(new Set<string>());
  const ocupado = Boolean(active.engine);

  const leerRecibos = useCallback(async () => {
    try {
      setRecibos((await nube.recibos(ws.id)).recibos);
    } catch (e) {
      setError(motivo(e));
    }
  }, [ws.id]);
  useEffect(() => { if (abierto) void leerRecibos(); }, [abierto, leerRecibos]);
  useEffect(() => {
    for (const j of Object.values(jobs)) {
      if (j.workspace_id === ws.id && DE_PUBLICAR.has(j.kind) && TERMINADO.has(j.status) && !vistos.current.has(j.id)) {
        vistos.current.add(j.id);
        if (j.status === 'done') setEstado(j.kind === 'nube_publicar' ? 'Expediente publicado.' : 'Acceso concedido.');
        else if (j.error) setError(j.error);
        void leerRecibos();
      }
    }
  }, [jobs, ws.id, leerRecibos]);

  const elegirCarpeta = useSelector(ws.id, (ids) => { if (ids[0]) { setCarpeta(ids[0]); setPrevia(null); } }, setError);
  const cuerpo = { proveedor, carpeta_destino: carpeta, nombre: nombre.trim(), ...(seleccion?.length ? { seleccion } : {}) };
  const revisar = async () => {
    setError(null);
    try { setPrevia(await nube.publicarPrevia(ws.id, cuerpo)); } catch (e) { setError(motivo(e)); }
  };
  const publicar = async () => {
    if (!previa) return;
    setPrevia(null);
    setEstado('Publicando…');
    await startJob(() => nube.publicar(ws.id, cuerpo, previa.confirmacion));
  };
  const revisarAcceso = async () => {
    setError(null);
    setAutorizo(false);
    const d = separarDirecciones(para);
    if (d.invalidas.length) { setError(`Revise: ${d.invalidas.join(', ')}`); return; }
    try { setPreviaC(await nube.compartirPrevia(ws.id, { publicacion, destinatarios: d.validas, publico })); }
    catch (e) { setError(motivo(e)); }
  };
  const compartir = async () => {
    const c = previaC;
    const confirmacion = c?.confirmacion;
    if (!c || !confirmacion) return;
    setPreviaC(null);
    setEstado('Compartiendo…');
    await startJob(() => nube.compartir(ws.id, { publicacion: c.publicacion, destinatarios: c.destinatarios,
      publico: c.publico }, autorizo, confirmacion));
  };
  const publicaciones = publicacionesDe(recibos);
  const cuenta = cuentas.find((c) => c.nombre === proveedor);

  return (
    <>
      <button className="btn btn-sm" onClick={() => { setError(null); setEstado(null); setAbierto(true); }}>{boton}</button>
      {abierto && (
        <Modal title="Publicar y compartir" wide onClose={() => setAbierto(false)}>
          <div className="stack">
            <h3>Publicar el expediente</h3>
            <div className="form-grid">
              <label className="field"><span>Cuenta</span>
                <select value={proveedor} onChange={(e) => { setProveedor(e.target.value as ProveedorNube); setCarpeta(''); setPrevia(null); }}>
                  {cuentas.map((c) => <option key={c.nombre} value={c.nombre}>{`${c.visible} · ${c.cuenta ?? ''}`}</option>)}
                </select>
              </label>
              <label className="field"><span>Nombre</span>
                <input value={nombre} maxLength={120} onChange={(e) => { setNombre(e.target.value); setPrevia(null); }} />
              </label>
            </div>
            <div className="row">
              <button className="btn btn-sm" onClick={() => elegirCarpeta(proveedor, 'carpeta')}>Elegir carpeta</button>
              <small className="muted">{carpeta ? 'Carpeta elegida.' : 'Sin carpeta.'}</small>
              {faltaPermiso(cuenta, 'publicar') && (
                <button className="btn btn-sm btn-ghost" aria-label={`Permitir publicar en ${VISIBLE[proveedor]}`}
                  onClick={async () => {
                    try { window.location.assign((await nube.conectar(ws.id, proveedor, 'publicar')).url); }
                    catch (e) { setError(motivo(e)); }
                  }}>Permitir publicar</button>
              )}
            </div>
            {!previa ? (
              <div><button className="btn" disabled={ocupado || !carpeta || !nombre.trim()} onClick={() => void revisar()}>
                Revisar</button></div>
            ) : (
              <div className="stack">
                <p>{`Se suben ${previa.ficheros} ficheros en un ZIP cerrado a ${VISIBLE[previa.proveedor]}. No se sobrescribe nada.`}</p>
                <div><button className="btn btn-primary" disabled={ocupado} onClick={() => void publicar()}>Publicar</button></div>
              </div>
            )}

            <h3>Compartir</h3>
            {publicaciones.length === 0 ? <p className="muted">Publique antes un expediente.</p> : (
              <>
                <label className="field"><span>Expediente</span>
                  <select value={publicacion} onChange={(e) => { setPublicacion(e.target.value); setPreviaC(null); }}>
                    <option value="">Elija…</option>
                    {publicaciones.map((r) => <option key={r.clave} value={r.clave}>{r.etiqueta}</option>)}
                  </select>
                </label>
                <label className="field"><span>Para</span>
                  <input value={para} placeholder="Una o varias direcciones"
                    onChange={(e) => { setPara(e.target.value); setPreviaC(null); }} />
                </label>
                <label className="row">
                  <input type="checkbox" checked={publico} onChange={(e) => { setPublico(e.target.checked); setPreviaC(null); }} />
                  <span>Cualquiera con el enlace</span>
                </label>
                {!previaC ? (
                  <div><button className="btn" disabled={ocupado || !publicacion || (!para.trim() && !publico)}
                    onClick={() => void revisarAcceso()}>Revisar acceso</button></div>
                ) : (
                  <VistaCompartir previa={previaC} autorizo={autorizo} onAutorizo={setAutorizo} ocupado={ocupado}
                    onConfirmar={() => void compartir()} />
                )}
              </>
            )}
            <div aria-live="polite">
              {estado && <p className="muted">{estado}</p>}
              {error && <p className="alert alert-error" role="alert">{error}</p>}
            </div>
          </div>
        </Modal>
      )}
    </>
  );
}
