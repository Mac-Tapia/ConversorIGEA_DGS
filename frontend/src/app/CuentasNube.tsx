import { useCallback, useEffect, useState, type ReactNode } from 'react';
import { nube, type CuentaNube, type ProveedorNube } from '../api/nube';
import { useApp } from '../shared/context';
import { useConfirm } from '../shared/ui';
import { ElegirDeLaNube } from '../features/nube/ElegirDeLaNube';
import { PublicarExpediente } from '../features/nube/PublicarExpediente';
import { VersionesNuevas } from '../features/nube/VersionesNuevas';
import { conectadas, leerRetorno, permisosDeCuenta, SIN_CUENTA, sinRegistro, type Tono } from '../features/nube/logica';

type Aviso = { tono: Tono; texto: string } | null;

/** 109:RF-1, RF-14, RF-19: las cuentas de Google Drive y OneDrive de este espacio, sin datos de la API en la vista. */
export function TarjetaCuentas({ cuentas, error, aviso, ocupado, onConectar, onDesconectar, children }: {
  cuentas: CuentaNube[] | null;
  error: string | null;
  aviso: Aviso;
  ocupado: boolean;
  onConectar: (p: ProveedorNube) => void;
  onDesconectar: (p: ProveedorNube) => void;
  children?: ReactNode;
}) {
  return (
    <section className="card" aria-labelledby="nube-titulo">
      <header className="card-head"><h2 id="nube-titulo">Cuentas en la nube</h2></header>
      <div aria-live="polite">{aviso && <p className={`alert alert-${aviso.tono === 'muted' ? 'info' : aviso.tono}`}>{aviso.texto}</p>}</div>
      {sinRegistro(cuentas) ? <p className="muted">{SIN_CUENTA}</p> : (
        <ul className="stack">
          {cuentas!.map((c) => (
            <li key={c.nombre} className="row">
              <strong>{c.visible}</strong>
              {c.conectada && c.cuenta ? (
                <>
                  <span className="muted small">{c.cuenta}</span>
                  {permisosDeCuenta(c) && <small className="muted">{permisosDeCuenta(c)}</small>}
                  <button className="btn btn-sm btn-ghost" disabled={ocupado} aria-label={`Desconectar ${c.visible}`}
                    onClick={() => onDesconectar(c.nombre)}>Desconectar</button>
                </>
              ) : c.se_puede_conectar ? (
                <button className="btn btn-sm" disabled={ocupado} aria-label={`Conectar ${c.visible}`} title={c.permisos}
                  onClick={() => onConectar(c.nombre)}>Conectar</button>
              ) : (
                <small className="muted">{c.registrado ? c.motivo : 'Sin registrar en este equipo.'}</small>
              )}
            </li>
          ))}
        </ul>
      )}
      {error && <p className="alert alert-error" role="alert">{error}</p>}
      {children}
    </section>
  );
}

/** La tarjeta con sus datos: lee las cuentas, conecta (va al proveedor y vuelve) y desconecta con confirmación. */
export function CuentasNube() {
  const { ws } = useApp();
  const confirm = useConfirm();
  const [cuentas, setCuentas] = useState<CuentaNube[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [aviso, setAviso] = useState<Aviso>(() => leerRetorno(window.location.search));
  const [ocupado, setOcupado] = useState(false);

  const leer = useCallback(async () => {
    try {
      setCuentas((await nube.cuentas(ws.id)).cuentas);
      setError(null);
    } catch (e) {
      // La web nunca falla por la nube: sin respuesta, no hay cuenta, y se dice el motivo.
      setCuentas(null);
      setError(e instanceof Error ? e.message : String(e));
    }
  }, [ws.id]);
  useEffect(() => { void leer(); }, [leer]);
  // La vuelta del proveedor deja «?nube=…» en la dirección: se dice una vez y se quita.
  useEffect(() => {
    const q = new URLSearchParams(window.location.search);
    if (!q.has('nube')) return;
    q.delete('nube');
    q.delete('proveedor');
    const resto = q.toString();
    window.history.replaceState(null, '', `${window.location.pathname}${resto ? `?${resto}` : ''}${window.location.hash}`);
  }, []);

  const conectar = async (p: ProveedorNube) => {
    setOcupado(true);
    setError(null);
    try {
      window.location.assign((await nube.conectar(ws.id, p)).url);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setOcupado(false);
    }
  };
  const desconectar = async (p: ProveedorNube) => {
    const c = cuentas?.find((x) => x.nombre === p);
    if (!await confirm(`Desconectar ${c?.visible ?? p}`, <p>Las copias ya importadas y los recibos se conservan.</p>, 'Desconectar')) return;
    setOcupado(true);
    try {
      const r = await nube.desconectar(ws.id, p);
      setAviso(r.aviso ? { tono: 'warn', texto: r.aviso } : { tono: 'ok', texto: `${c?.visible ?? p} desconectado.` });
      await leer();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setOcupado(false);
    }
  };
  const listas = conectadas(cuentas);

  return (
    <TarjetaCuentas cuentas={cuentas} error={error} aviso={aviso} ocupado={ocupado}
      onConectar={(p) => void conectar(p)} onDesconectar={(p) => void desconectar(p)}>
      {listas.length > 0 && (
        <div className="row">
          <ElegirDeLaNube cuentas={listas} />
          <VersionesNuevas />
          <PublicarExpediente cuentas={listas} />
        </div>
      )}
    </TarjetaCuentas>
  );
}
