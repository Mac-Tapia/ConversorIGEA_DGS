/** Lo común a la configuración y a los recorridos E2E: el puerto aislado y la carpeta de evidencia por SHA. */
import { execFileSync } from 'node:child_process';
import { existsSync, readFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';

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

/** 109 T19: la web con la nube simulada va en el puerto siguiente, nunca en el del operador. */
export function puertoNubeE2E() {
  const puerto = puertoE2E() + 1;
  if (puerto === PUERTO_OPERADOR || puerto > 65535) throw new Error(`No hay un puerto libre junto al ${puertoE2E()}.`);
  return puerto;
}

/** Sus espacios y sesiones, aparte de los de la web de los demás recorridos. */
export function carpetaNubeE2E() {
  return process.env.CSG_E2E_DIR ? `${process.env.CSG_E2E_DIR}-nube` : join(tmpdir(), `csg-e2e-nube-${puertoNubeE2E()}`);
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

/**
 * El python del servidor y de los ayudantes de los recorridos: CSG_E2E_PYTHON, el del checkout o, en un worktree sin
 * .venv, el del checkout primario.
 */
export function pythonServidor(RAIZ) {
  if (process.env.CSG_E2E_PYTHON) return process.env.CSG_E2E_PYTHON;
  const exe = process.platform === 'win32' ? join('Scripts', 'python.exe') : join('bin', 'python');
  const candidatas = [join(RAIZ, '.venv', exe)];
  const marca = join(RAIZ, '.git');
  if (existsSync(marca) && !existsSync(join(marca, 'HEAD'))) {
    // .git de un worktree: «gitdir: <primario>/.git/worktrees/<nombre>».
    const gitdir = readFileSync(marca, 'utf8').split(':').slice(1).join(':').trim();
    candidatas.push(join(resolve(gitdir, '..', '..', '..'), '.venv', exe));
  }
  const elegida = candidatas.find((c) => existsSync(c));
  if (!elegida) throw new Error(`No hay python para la web en ${candidatas.join(' ni en ')}: indique CSG_E2E_PYTHON.`);
  return elegida;
}
