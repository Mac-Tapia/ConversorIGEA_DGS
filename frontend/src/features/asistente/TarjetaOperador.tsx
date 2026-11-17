import { useEffect, useState } from 'react';
import { ApiError } from '../../api/client';
import { correo, type CorreoEnvio } from '../../api/correo';
import { nube, type CuentaNube } from '../../api/nube';
import { useAccionesOperador } from '../../shared/accionesOperador';
import { useApp } from '../../shared/context';
import { proveedoresParaConectar, type Tarjeta } from './tarjetaOperadorLogica';

const EN_CURSO = new Set(['queued', 'running']);
const motivo = (e: unknown) => (e instanceof Error ? e.message : String(e));

/** Spec 070, RF-80 a RF-82: el correo que preparó el asistente, con «Confirmar y enviar». El clic lo manda el navegador
 * con la firma que el operador ve; después se sigue el envío hasta su recibo. */
function TarjetaCorreo({ tarjeta }: { tarjeta: Tarjeta }) {
  const { ws, jobs, startJob } = useApp();
  const { VistaPrevia, textoEstado } = useAccionesOperador();
  const previa = tarjeta.previa!;
  const [envio, setEnvio] = useState<{ clave: string; job: string | null; recibo: CorreoEnvio | null } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);
  const trabajo = envio?.job ? jobs[envio.job] : undefined;
  useEffect(() => {
    if (!envio?.job || !trabajo || EN_CURSO.has(trabajo.status) || envio.recibo) return;
    correo.envio(ws.id, envio.clave).then((r) => setEnvio((v) => (v ? { ...v, recibo: r } : v)))
      .catch((e) => setError(motivo(e)));
  }, [trabajo, envio, ws.id]);

  const confirmar = async () => {
    setEnviando(true);
    setError(null);
    try {
      const r = await correo.confirmar(ws.id, previa.borrador, previa.firma);
      const job = r.trabajo ? await startJob(async () => r.trabajo!) : undefined;
      setEnvio({ clave: r.clave, job: job?.id ?? null, recibo: r.recibo });
    } catch (e) {
      setError(e instanceof ApiError && e.status === 409
        ? 'El informe o un adjunto cambió desde el borrador: pida otra vez el envío al asistente.' : motivo(e));
    } finally {
      setEnviando(false);
    }
  };

  if (envio) {
    const estado = envio.recibo ? textoEstado(envio.recibo.estado) : { tono: 'muted', texto: 'Enviando…' };
    return (
      <div className="stack" aria-live="polite">
        <p className={estado.tono === 'error' ? 'alert alert-error' : 'small'}>{estado.texto}</p>
        {error && <p className="alert alert-error" role="alert">{error}</p>}
      </div>
    );
  }
  return (
    <div className="stack">
      <VistaPrevia previa={previa} ocupado={enviando} onConfirmar={() => void confirmar()} />
      {error && <p className="alert alert-error" role="alert">{error}</p>}
    </div>
  );
}

/** Spec 070, RF-80: conectar la cuenta; la contraseña se escribe en la página del proveedor, nunca aquí. */
function TarjetaConectar({ tarjeta }: { tarjeta: Tarjeta }) {
  const { ws } = useApp();
  const [error, setError] = useState<string | null>(null);
  const opciones = proveedoresParaConectar(tarjeta);
  if (opciones.length === 0) {
    return <p className="alert alert-warn">Sin proveedor registrado en este equipo: configure config/nube.json.</p>;
  }
  return (
    <div className="stack">
      <div className="row">
        {opciones.map((p) => (
          <button key={p.nombre} className="btn btn-primary" disabled={!p.se_puede_conectar} title={p.motivo ?? undefined}
            onClick={async () => {
              try { window.location.assign((await nube.conectar(ws.id, p.nombre)).url); }
              catch (e) { setError(motivo(e)); }
            }}>{`Conectar ${p.visible}`}</button>
        ))}
      </div>
      {error && <p className="alert alert-error" role="alert">{error}</p>}
    </div>
  );
}

/** Spec 070, RF-80: publicar, compartir e importar con las ventanas de siempre, ya abiertas con lo que dijo la orden. */
function TarjetaNube({ tarjeta }: { tarjeta: Tarjeta }) {
  const { ws } = useApp();
  const { ElegirDeLaNube, PublicarExpediente, conectadas } = useAccionesOperador();
  const [cuentas, setCuentas] = useState<CuentaNube[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    nube.cuentas(ws.id).then((r) => setCuentas(r.cuentas)).catch((e) => setError(motivo(e)));
  }, [ws.id]);
  if (error) return <p className="alert alert-error" role="alert">{error}</p>;
  if (!cuentas) return <p className="small muted">Leyendo las cuentas…</p>;
  const listas = conectadas(cuentas).filter((c) => !tarjeta.proveedor || c.nombre === tarjeta.proveedor);
  if (listas.length === 0) {
    return <p className="alert alert-warn">Sin cuenta conectada: pida antes al asistente «conecta mi cuenta de google».</p>;
  }
  if (tarjeta.tipo === 'importar_nube') return <ElegirDeLaNube cuentas={listas} />;
  return (
    <PublicarExpediente cuentas={listas} seleccion={tarjeta.salida ? [tarjeta.salida] : undefined}
      paraInicial={tarjeta.para.join(', ')} boton={tarjeta.tipo === 'compartir_nube' ? 'Compartir' : 'Publicar'} />
  );
}

export function TarjetaOperador({ tarjeta }: { tarjeta: Tarjeta }) {
  return (
    <div className="card stack">
      {tarjeta.tipo === 'enviar_informe' ? <TarjetaCorreo tarjeta={tarjeta} />
        : tarjeta.tipo === 'conectar_nube' ? <TarjetaConectar tarjeta={tarjeta} />
          : <TarjetaNube tarjeta={tarjeta} />}
    </div>
  );
}
