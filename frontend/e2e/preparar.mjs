/**
 * 111:RF-16 — preparación global de los recorridos: arranca la web de prueba y devuelve su cierre.
 *
 * - Semilla: `CSG_E2E_SEMILLA` o una sorteada; sale en el registro para repetir el sorteo.
 * - Alimentadores: `CSG_E2E_ALIMENTADORES` o un número sorteado con la semilla (nunca fijo).
 * - Python: `CSG_E2E_PYTHON`, o el `.venv` de la raíz del repositorio, o `python`.
 * - La web corre en una carpeta temporal propia, con la seguridad real y sin GPU; la carpeta se borra al cerrar.
 * Los datos llegan a las pruebas por variables de entorno (`CSG_E2E_*`) y por `resultados/estado.json`.
 */
import { spawn } from 'node:child_process';
import { randomInt } from 'node:crypto';
import { existsSync, mkdirSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { createServer } from 'node:net';
import { tmpdir } from 'node:os';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const AQUI = dirname(fileURLToPath(import.meta.url));
const FRONT = resolve(AQUI, '..');
const RAIZ = resolve(FRONT, '..');
const ESPERA_MS = 240_000;

function puertoLibre() {
  return new Promise((ok, mal) => {
    const s = createServer();
    s.once('error', mal);
    s.listen(0, '127.0.0.1', () => {
      const { port } = s.address();
      s.close(() => ok(port));
    });
  });
}

function python() {
  if (process.env.CSG_E2E_PYTHON) return process.env.CSG_E2E_PYTHON;
  for (const r of ['.venv/Scripts/python.exe', '.venv/bin/python']) {
    if (existsSync(join(RAIZ, r))) return join(RAIZ, r);
  }
  return 'python';
}

export default async function preparar() {
  if (!existsSync(join(FRONT, 'dist', 'index.html'))) {
    throw new Error('Falta la web compilada: ejecute «npm run build» en frontend antes de los recorridos.');
  }
  const semilla = Number(process.env.CSG_E2E_SEMILLA ?? randomInt(1, 2 ** 31 - 1));
  const alimentadores = Number(process.env.CSG_E2E_ALIMENTADORES ?? 2 + (semilla % 7));
  const puerto = await puertoLibre();
  const tmp = mkdtempSync(join(tmpdir(), 'csg-e2e-'));
  console.log(`[e2e] semilla=${semilla} alimentadores=${alimentadores} puerto=${puerto}`);

  const env = { ...process.env, CUDA_VISIBLE_DEVICES: '-1', PYTHONIOENCODING: 'utf-8' };
  const hijo = spawn(python(), ['-I', join(AQUI, 'web_de_prueba.py'), RAIZ, tmp, String(puerto), String(semilla), String(alimentadores)],
    { cwd: RAIZ, env, stdio: ['ignore', 'pipe', 'pipe'] });
  let errores = '';
  hijo.stderr.on('data', (d) => { errores = (errores + d.toString()).slice(-4000); });

  const datos = await new Promise((ok, mal) => {
    let resto = '';
    const reloj = setTimeout(() => mal(new Error(`La web de prueba no respondió en ${ESPERA_MS / 1000} s.\n${errores}`)), ESPERA_MS);
    hijo.stdout.on('data', (d) => {
      resto += d.toString();
      const linea = resto.split(/\r?\n/).find((l) => l.startsWith('LISTA '));
      if (linea) { clearTimeout(reloj); ok(JSON.parse(linea.slice(6))); }
    });
    hijo.once('exit', (rc) => { clearTimeout(reloj); mal(new Error(`La web de prueba terminó con ${rc}.\n${errores}`)); });
  });

  const estado = { ...datos, semilla, alimentadores, puerto };
  mkdirSync(join(AQUI, 'resultados'), { recursive: true });
  writeFileSync(join(AQUI, 'resultados', 'estado.json'), JSON.stringify(estado, null, 1) + '\n', 'utf8');
  process.env.CSG_E2E_BASE = datos.base;
  process.env.CSG_E2E_ENTRADA = datos.entrada;
  process.env.CSG_E2E_ESPACIO = datos.espacio;
  process.env.CSG_E2E_SEMILLA = String(semilla);

  return async () => {
    hijo.kill();
    try { rmSync(tmp, { recursive: true, force: true }); } catch { /* Windows: la carpeta puede seguir abierta un instante */ }
  };
}
