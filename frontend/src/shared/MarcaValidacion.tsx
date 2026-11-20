import { useEffect, useState } from 'react';
import { matrizEstudios, type MatrizEstudios } from '../api/matrizEstudios';
import { marcaDe, type Marca, type RefMatriz } from './matrizEstudios';
import { Pill } from './ui';

// Una sola petición para toda la página: la matriz cambia solo cuando cambia el estado de las specs del servidor.
let enCurso: Promise<MatrizEstudios | null> | null = null;

/** 100:RF-10: la matriz estudio × motor del servidor; `null` mientras llega o si no se pudo leer. */
export function useMatrizEstudios(): MatrizEstudios | null {
  const [matriz, setMatriz] = useState<MatrizEstudios | null>(null);
  useEffect(() => {
    let vivo = true;
    enCurso ??= matrizEstudios.leer().catch(() => { enCurso = null; return null; });
    void enCurso.then((m) => { if (vivo) setMatriz(m); });
    return () => { vivo = false; };
  }, []);
  return matriz;
}

/** La marca ya calculada; sin marca no se pinta nada. */
export function MarcaDeCelda({ marca }: { marca: Marca | null }) {
  return marca ? <Pill tone={marca.tono} title={marca.titulo}>{marca.texto}</Pill> : null;
}

/** 100:RF-12: junto al nombre de un estudio, si está sin validar o no disponible con el motor que usa. */
export function MarcaValidacion(ref: RefMatriz) {
  const matriz = useMatrizEstudios();
  return <MarcaDeCelda marca={marcaDe(matriz, ref)} />;
}
