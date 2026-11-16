/** Lo común a la configuración y a los recorridos E2E: el puerto aislado y la carpeta de evidencia por SHA. */
import { execFileSync } from 'node:child_process';
import { join } from 'node:path';

/** El puerto del operador: los recorridos nunca lo usan, para no tocar su web ni sus espacios. */
export const PUERTO_OPERADOR = 8765;

export function puertoE2E() {
  const texto = process.env.CSG_E2E_PUERTO || '8799';
  const puerto = Number(texto);
  if (!Number.isInteger(puerto) || puerto < 1024 || puerto > 65535) {
    throw new Error(`CSG_E2E_PUERTO no es un puerto válido (1024–65535): «${texto}».`);
  }
  if (puerto === PUERTO_OPERADOR) {
    throw new Error(`El ${PUERTO_OPERADOR} es la web del operador: los recorridos usan otro puerto.`);
  }
  return puerto;
}

/**
 * La revisión que se prueba: el SHA de HEAD y, si el árbol tiene cambios sin commit, «-sucio», para que la
 * evidencia nunca se atribuya a un commit que no es lo que corrió.
 */
export function revision(frontend) {
  try {
    const sha = execFileSync('git', ['rev-parse', 'HEAD'], { cwd: frontend, encoding: 'utf8' }).trim();
    const cambios = execFileSync('git', ['status', '--porcelain', '--untracked-files=no'], { cwd: frontend, encoding: 'utf8' }).trim();
    return cambios ? `${sha}-sucio` : sha;
  } catch {
    return 'sin-git';
  }
}

export function evidenciaDe(frontend) {
  // Por defecto en output/e2e del checkout, que git ignora; CSG_E2E_EVIDENCIA la lleva a otra carpeta.
  return join(process.env.CSG_E2E_EVIDENCIA || join(frontend, '..', 'output', 'e2e'), revision(frontend));
}
