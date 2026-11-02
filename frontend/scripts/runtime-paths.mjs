/** 065:RF-10 RF-11 — contrato equivalente a convertersmartgrid.runtime_paths. */
import { createHash } from 'node:crypto';
import { existsSync, realpathSync } from 'node:fs';
import { dirname, isAbsolute, join, parse, relative, resolve, sep } from 'node:path';
import { homedir } from 'node:os';
import { execFileSync } from 'node:child_process';

export function rutaReal(ruta) {
  const absoluta = resolve(ruta);
  if (existsSync(absoluta)) return realpathSync.native(absoluta);
  return join(rutaReal(dirname(absoluta)), absoluta.slice(dirname(absoluta).length + 1));
}

export function estaDentro(raiz, ruta) {
  const resto = relative(rutaReal(raiz), rutaReal(ruta));
  return resto === '' || (!resto.startsWith(`..${sep}`) && resto !== '..' && !isAbsolute(resto));
}

export function rutasFrontend(frontend, entorno = process.env) {
  const checkout = rutaReal(dirname(frontend));
  const normalizada = process.platform === 'win32' ? checkout.replaceAll('\\', '/').toLowerCase() : checkout;
  const identidad = createHash('sha256').update(normalizada).digest('hex').slice(0, 16);
  let principal;
  try {
    const comun = execFileSync('git', ['rev-parse', '--path-format=absolute', '--git-common-dir'], { cwd: checkout, encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore'] }).trim();
    principal = dirname(rutaReal(comun));
  } catch {
    if (!entorno.CSG_RUNTIME_HOME) throw new Error('Sin Git, indique CSG_RUNTIME_HOME externo en el volumen del frontend.');
    principal = checkout;
  }
  const runtime = rutaReal(entorno.CSG_RUNTIME_HOME || join(dirname(principal), '.convertersmartgrid-runtime', identidad));
  const cache = rutaReal(entorno.CSG_CACHE_HOME || join(entorno.LOCALAPPDATA || entorno.XDG_CACHE_HOME || join(homedir(), '.cache'), 'ConverterSmartGrid', identidad, 'cache'));
  for (const ruta of [runtime, cache]) {
    if (estaDentro(principal, ruta) || estaDentro(checkout, ruta)) throw new Error(`La raíz administrada debe estar fuera del checkout: ${ruta}`);
  }
  if (parse(runtime).root.toLowerCase() !== parse(rutaReal(frontend)).root.toLowerCase()) {
    throw new Error('CSG_RUNTIME_HOME debe estar en el mismo volumen que frontend/dist.');
  }
  return { identidad, checkout, principal, runtime, cache, staging: join(runtime, 'staging', `frontend-${identidad}`) };
}
