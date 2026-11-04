import { useApp } from '../context';
import { avisoBeta, type ClaveBeta } from '../edicion';
import { Pill } from './ui';

/** 086:RF-16: la marca junto al nombre de una función en beta; en desarrollo no se ve. */
export function MarcaBeta({ clave }: { clave: ClaveBeta }) {
  const { health } = useApp();
  const aviso = avisoBeta(health, clave);
  return aviso ? <Pill tone="warn" title={aviso}>Beta</Pill> : null;
}

/** Lo mismo con sus palabras, para el comienzo de la sección: la marca sola no dice qué hay que revisar. */
export function AvisoBeta({ clave }: { clave: ClaveBeta }) {
  const { health } = useApp();
  const aviso = avisoBeta(health, clave);
  return aviso ? <p className="alert alert-warn small">{aviso}</p> : null;
}
