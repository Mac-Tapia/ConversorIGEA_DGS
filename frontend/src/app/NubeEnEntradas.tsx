import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { nube, type CuentaNube } from '../api/nube';
import { conectadas } from '../features/nube/logica';
import { PublicarExpediente } from '../features/nube/PublicarExpediente';
import { abrirSelector } from '../features/nube/useSelector';
import { useApp } from '../shared/context';
import { NubeEntradasCtx, type NubeEntradas } from '../shared/nubeEntradas';
import { origenesDe } from '../shared/origenes';

const TERMINADO = new Set(['done', 'failed', 'cancelled', 'parcial', 'interrumpido']);
/** Cada cuánto se mira si terminó la importación, en milisegundos. */
const INTERVALO_MS = 400;
const pausa = (ms: number) => new Promise((r) => setTimeout(r, ms));

/**
 * 109:RF-21, RF-22: da a cada `FileDrop` de la web los orígenes de la nube con cuenta conectada y la forma de traer un
 * fichero de ella: el selector del proveedor (T18), la importación como copia fija (RF-3) y su descarga al navegador,
 * para que entre por la subida propia de esa entrada (RF-4). Sin cuenta, o si la nube no responde, solo el equipo.
 */
export function NubeEnEntradas({ children }: { children: ReactNode }) {
  const { ws, startJob } = useApp();
  const [cuentas, setCuentas] = useState<CuentaNube[] | null>(null);
  useEffect(() => {
    let vivo = true;
    nube.cuentas(ws.id).then((r) => { if (vivo) setCuentas(r.cuentas); }).catch(() => { if (vivo) setCuentas(null); });
    return () => { vivo = false; };
  }, [ws.id]);

  // Un selector abierto a la vez: la ventana del proveedor se reutiliza por su nombre y un escuchador viejo, de un
  // selector que se cerró sin elegir, importaría dos veces.
  const quitar = useRef<(() => void) | null>(null);
  useEffect(() => () => quitar.current?.(), []);

  const traer = useCallback<NubeEntradas['traer']>((proveedor, entrada, varios) => new Promise<File[]>((resolver, fallar) => {
    const alElegir = async (ids: string[]) => {
      try {
        if (ids.length === 0) { resolver([]); return; }
        const elegidos = varios ? ids : ids.slice(0, 1);
        const job = await startJob(() => nube.importar(ws.id, { proveedor, ids: elegidos, entrada }));
        if (!job) { resolver([]); return; }
        let estado = job;
        while (!TERMINADO.has(estado.status)) {
          await pausa(INTERVALO_MS);
          estado = await nube.trabajo(job.id);
        }
        if (estado.status !== 'done') throw new Error(estado.error || 'No se pudo traer el fichero de la nube.');
        const copias = Array.isArray(estado.result?.copias) ? estado.result.copias as { sha256: string; nombre: string }[] : [];
        resolver(await Promise.all(copias.map(async (c) => {
          const datos = await nube.copia(ws.id, c.sha256);
          return new File([datos], c.nombre, { type: datos.type });
        })));
      } catch (e) {
        fallar(e);
      }
    };
    quitar.current?.();
    quitar.current = abrirSelector(ws.id, proveedor, 'ficheros', (ids) => { quitar.current = null; void alElegir(ids); },
      (motivo) => fallar(new Error(motivo)));
  }), [startJob, ws.id]);

  // 109:RF-24: con una cuenta conectada, cada salida se puede publicar sola con el mismo diálogo del expediente (RF-9).
  const Publicar = useMemo<NubeEntradas['Publicar']>(() => {
    const listas = conectadas(cuentas);
    if (listas.length === 0) return undefined;
    return function PublicarSalida({ seleccion, nombre }: { seleccion: string[]; nombre: string }) {
      return <PublicarExpediente cuentas={listas} seleccion={seleccion} nombreInicial={nombre} boton="Nube" />;
    };
  }, [cuentas]);
  const valor = useMemo<NubeEntradas>(() => ({ origenes: origenesDe(cuentas), traer, Publicar }),
    [cuentas, traer, Publicar]);
  return <NubeEntradasCtx.Provider value={valor}>{children}</NubeEntradasCtx.Provider>;
}
