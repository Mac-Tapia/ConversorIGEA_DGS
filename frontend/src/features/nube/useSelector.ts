import { useCallback, useEffect, useRef } from 'react';
import { nube, type ProveedorNube } from '../../api/nube';
import { seleccionDelSelector } from './logica';

/**
 * 109:RF-1, RF-3: abre la página del selector del proveedor en una ventana aparte y espera sus ids por `postMessage`.
 * Solo se aceptan los mensajes del propio origen, de ese proveedor y de ese modo (`seleccionDelSelector`).
 * Devuelve la función que deja de escuchar. La usan `useSelector` y el campo único de cada entrada (109:RF-22).
 */
export function abrirSelector(wsId: string, proveedor: ProveedorNube, modo: 'ficheros' | 'carpeta',
  onIds: (ids: string[]) => void, onError: (motivo: string) => void): (() => void) | null {
  const ventana = window.open(nube.urlSelector(wsId, proveedor, modo), 'csg-nube-selector', 'popup,width=960,height=680');
  if (!ventana) {
    onError('El navegador bloqueó la ventana del selector: permita las ventanas emergentes de esta página.');
    return null;
  }
  const quitar = () => window.removeEventListener('message', escuchar);
  function escuchar(ev: MessageEvent) {
    if (ev.source !== ventana) return;
    const ids = seleccionDelSelector(ev, window.location.origin, proveedor, modo);
    if (ids === null) return;
    quitar();
    onIds(ids);
  }
  window.addEventListener('message', escuchar);
  return quitar;
}

export function useSelector(wsId: string, onIds: (ids: string[], proveedor: ProveedorNube) => void,
  onError: (motivo: string) => void) {
  const quitar = useRef<(() => void) | null>(null);
  useEffect(() => () => quitar.current?.(), []);
  return useCallback((proveedor: ProveedorNube, modo: 'ficheros' | 'carpeta') => {
    quitar.current?.();
    quitar.current = abrirSelector(wsId, proveedor, modo, (ids) => {
      quitar.current = null;
      onIds(ids, proveedor);
    }, onError);
  }, [wsId, onIds, onError]);
}
