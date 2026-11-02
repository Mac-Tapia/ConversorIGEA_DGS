/** Compila fuera del checkout y conserva la publicación anterior ante cualquier fallo. */
import { existsSync, mkdirSync, mkdtempSync, openSync, closeSync, fsyncSync, lstatSync, readdirSync, readFileSync, renameSync, rmdirSync, rmSync, statSync, unlinkSync, writeFileSync } from 'node:fs';
import { randomUUID } from 'node:crypto';
import { join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';
import { createRequire } from 'node:module';
import { estaDentro, rutasFrontend } from './runtime-paths.mjs';

export function publicar(staging, destino, respaldo) {
  const anterior = existsSync(destino);
  if (anterior) renameSync(destino, respaldo);
  try { renameSync(staging, destino); }
  catch (error) {
    if (anterior) {
      try { renameSync(respaldo, destino); }
      catch (restauracion) { throw new AggregateError([error, restauracion], `La compilación anterior se conserva en ${respaldo}; no se pudo restituir dist.`); }
    }
    throw error;
  }
}

function ejecutar(script, argumentos, frontend, entorno) {
  const resultado = spawnSync(process.execPath, [script, ...argumentos], { cwd: frontend, env: entorno, stdio: 'inherit' });
  if (resultado.error) throw resultado.error;
  if (resultado.status !== 0) throw new Error(`La compilación falló (${resultado.signal || resultado.status}): ${script}`);
}

function procesoActivo(pid) {
  if (!Number.isSafeInteger(pid) || pid <= 0) throw new Error('El bloqueo no identifica un PID válido; se conserva para revisión.');
  try { process.kill(pid, 0); return true; }
  catch (error) { if (error.code === 'ESRCH') return false; throw error; }
}

function guardarJsonPropio(ruta, datos) {
  const descriptor = openSync(ruta, 'wx');
  try { writeFileSync(descriptor, JSON.stringify(datos)); fsyncSync(descriptor); }
  finally { closeSync(descriptor); }
}

function adquirirBloqueo(rutas) {
  const bloqueo = join(rutas.staging, 'build.guard');
  const candidato = mkdtempSync(join(rutas.staging, 'lock-candidato-'));
  const nonce = randomUUID();
  const nombre = `owner-${nonce}.json`;
  const propietario = { version: 1, pid: process.pid, checkout: rutas.checkout, nonce };
  try {
    guardarJsonPropio(join(candidato, nombre), propietario);
    // Solo se publica un directorio ya completo. Un corte al escribir el candidato
    // deja scratch sin publicar, nunca un bloqueo vacío que impida recuperarse.
    for (let intento = 0; intento < 64; intento += 1) {
      try {
        renameSync(candidato, bloqueo);
        return () => {
          const marcador = join(bloqueo, nombre);
          const actual = JSON.parse(readFileSync(marcador, 'utf8'));
          if (actual.nonce !== nonce || actual.pid !== process.pid || actual.checkout !== rutas.checkout) throw new Error('El bloqueo cambió de propietario; no se retira.');
          unlinkSync(marcador);
          rmdirSync(bloqueo);
        };
      } catch (error) {
        if (!['EEXIST', 'ENOTEMPTY', 'EPERM', 'EACCES'].includes(error.code) || !existsSync(bloqueo)) throw error;
      }
      try {
        const estado = lstatSync(bloqueo);
        if (!estado.isDirectory() || estado.isSymbolicLink()) throw new Error('El bloqueo no es un directorio administrado; se conserva para revisión.');
        const entradas = readdirSync(bloqueo);
        if (entradas.length === 0) {
          // Otro recuperador pudo retirar el marcador antes de caer. rmdir nunca
          // retira el directorio completo no vacío de un propietario nuevo.
          rmdirSync(bloqueo);
          continue;
        }
        if (entradas.length !== 1 || !/^owner-[a-f0-9-]+\.json$/.test(entradas[0])) throw new Error('El bloqueo contiene archivos desconocidos; se conserva para revisión.');
        const marcador = join(bloqueo, entradas[0]);
        const anterior = JSON.parse(readFileSync(marcador, 'utf8'));
        if (anterior.checkout !== rutas.checkout || entradas[0] !== `owner-${anterior.nonce}.json`) throw new Error('El bloqueo pertenece a otro checkout; se conserva para revisión.');
        if (procesoActivo(anterior.pid)) throw new Error(`Ya existe una compilación activa: PID ${anterior.pid}.`);
        // El nonce hace que dos recuperadores no puedan borrar al nuevo dueño:
        // solo uno retira este marcador; el otro verá ENOENT y releerá la identidad.
        unlinkSync(marcador);
        rmdirSync(bloqueo);
      } catch (error) {
        if (!['ENOENT', 'ENOTEMPTY', 'EEXIST'].includes(error.code)) throw error;
      }
    }
    throw new Error('No se pudo adquirir el bloqueo tras cambios concurrentes; vuelva a intentar.');
  } finally {
    // Esta ruta aleatoria es exclusivamente nuestra; nunca se limpia build.guard
    // recursivamente ni se borra un marcador por nombre fijo.
    rmSync(candidato, { recursive: true, force: true });
  }
}

function reconciliarBloqueoHeredado(rutas) {
  const bloqueo = join(rutas.staging, 'build.lock');
  if (!existsSync(bloqueo)) return;
  const estado = lstatSync(bloqueo);
  if (!estado.isFile() || estado.isSymbolicLink()) throw new Error('El bloqueo heredado no es un archivo administrado; se conserva para revisión.');
  const contenido = readFileSync(bloqueo, 'utf8');
  let propietario;
  try { propietario = JSON.parse(contenido); }
  catch {
    // Los locks anteriores podían quedar truncados después de escribir el PID.
    // Si aún se reconoce ese dueño vivo se respeta, aunque falte el resto del JSON.
    const pid = /"pid"\s*:\s*([1-9]\d*)(?:\s*[,}]|\s*$)/.exec(contenido);
    propietario = pid ? { pid: Number(pid[1]) } : null;
  }
  if (propietario?.checkout && propietario.checkout !== rutas.checkout) throw new Error('El bloqueo heredado pertenece a otro checkout; se conserva para revisión.');
  if (propietario?.pid !== undefined && procesoActivo(propietario.pid)) throw new Error(`Ya existe una compilación activa: PID ${propietario.pid}.`);
  // La admisión nueva ya está tomada: se preserva el marcador legado completo o
  // corrupto como evidencia, sin una carrera exists→read→rm entre builders nuevos.
  renameSync(bloqueo, join(rutas.staging, `build.lock.legacy-${randomUUID()}`));
}

export function construir(frontend, entorno = process.env) {
  const rutas = rutasFrontend(frontend, entorno);
  mkdirSync(rutas.staging, { recursive: true });
  mkdirSync(rutas.cache, { recursive: true });
  if (statSync(rutas.staging).dev !== statSync(frontend).dev) throw new Error('El staging y frontend/dist deben compartir sistema de archivos.');
  // Serializar solo builds del mismo checkout; no se toma el turno de PowerFactory.
  const liberarBloqueo = adquirirBloqueo(rutas);
  const diario = join(rutas.staging, 'publicacion.json');
  const destino = join(frontend, 'dist');
  let ejecucion;
  let conservar = existsSync(diario);
  try {
    reconciliarBloqueoHeredado(rutas);
    if (existsSync(diario)) {
      conservar = true;
      const pendiente = JSON.parse(readFileSync(diario, 'utf8'));
      if (pendiente.destino !== destino || !estaDentro(rutas.staging, pendiente.respaldo)) throw new Error('Diario de publicación ajeno; requiere revisión.');
      if (!existsSync(destino) && existsSync(pendiente.respaldo)) renameSync(pendiente.respaldo, destino);
      rmSync(diario);
      conservar = false;
    }
    ejecucion = mkdtempSync(join(rutas.staging, 'build-'));
    writeFileSync(join(ejecucion, 'propietario.json'), JSON.stringify({ pid: process.pid, checkout: rutas.checkout, estado: 'en_curso' }));
    const temporal = join(ejecucion, 'dist');
    const respaldo = join(ejecucion, 'anterior');
    const requerir = createRequire(join(frontend, 'package.json'));
    const env = { ...entorno, CSG_CACHE_HOME: rutas.cache, TMP: ejecucion, TEMP: ejecucion, TMPDIR: ejecucion };
    ejecutar(requerir.resolve('typescript/bin/tsc'), ['--noEmit', '--incremental', 'false', '-p', 'tsconfig.json'], frontend, env);
    ejecutar(join(requerir.resolve('vite/package.json'), '..', 'bin', 'vite.js'), ['build', '--configLoader', 'runner', '--outDir', temporal, '--emptyOutDir'], frontend, env);
    if (!existsSync(join(temporal, 'index.html'))) throw new Error('La compilación no produjo index.html; se conserva dist anterior.');
    const pythonLocal = process.platform === 'win32' ? join(rutas.principal, '.venv', 'Scripts', 'python.exe') : join(rutas.principal, '.venv', 'bin', 'python');
    const python = entorno.CSG_PYTHON || (existsSync(pythonLocal) ? pythonLocal : 'python');
    const validacion = spawnSync(python, ['-I', '-B', join(rutas.checkout, 'src', 'convertersmartgrid', 'web', 'runtime.py'), '--validate-dist', temporal], { cwd: frontend, env, stdio: 'inherit' });
    if (validacion.error) throw validacion.error;
    if (validacion.status !== 0) throw new Error('La salida contiene una referencia local faltante o inválida; se conserva dist anterior.');
    const diarioCompleto = join(ejecucion, 'publicacion.json');
    guardarJsonPropio(diarioCompleto, { destino, respaldo });
    renameSync(diarioCompleto, diario);
    try { publicar(temporal, destino, respaldo); }
    catch (error) { conservar = existsSync(respaldo); throw error; }
    console.log(`Frontend completo publicado en ${destino}`);
  } finally {
    // Un fallo de limpieza no convierte una publicación válida en un build fallido.
    // En error se conserva el diagnóstico original y se informa cualquier resto propio.
    if (!conservar) {
      for (const ruta of [ejecucion, diario]) {
        if (!ruta) continue;
        try { rmSync(ruta, { recursive: ruta === ejecucion, force: true }); }
        catch (error) { console.warn(`No se pudo retirar el temporal propio ${ruta}: ${error.message}`); }
      }
    }
    try { liberarBloqueo(); }
    catch (error) { console.warn(`No se pudo retirar el bloqueo propio: ${error.message}`); }
  }
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  try { construir(fileURLToPath(new URL('..', import.meta.url))); }
  catch (error) { console.error(error); process.exitCode = 1; }
}
