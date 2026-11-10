import assert from 'node:assert/strict';
import test from 'node:test';
import { copyFileSync, existsSync, mkdirSync, mkdtempSync, readdirSync, readFileSync, renameSync, rmSync, symlinkSync, writeFileSync , realpathSync } from 'node:fs';
import { join, parse } from 'node:path';
import { tmpdir } from 'node:os';
import { fileURLToPath } from 'node:url';
import { spawn, spawnSync } from 'node:child_process';
import { once } from 'node:events';
import { publicar } from '../scripts/build.mjs';
import { estaDentro, rutasFrontend } from '../scripts/runtime-paths.mjs';

const frontend = fileURLToPath(new URL('..', import.meta.url));
const paquete = JSON.parse(readFileSync(join(frontend, 'package.json'), 'utf8'));
const entornoHijo = { ...process.env };
delete entornoHijo.NODE_TEST_CONTEXT;

function conCarpeta(nombre, comprobar) {
  const raiz = mkdtempSync(join(process.env.CSG_TEST_HOME || realpathSync.native(tmpdir()), `csg-${nombre}-`));
  try { return comprobar(raiz); }
  finally { rmSync(raiz, { recursive: true, force: true }); }
}

test('065:RF-4 — un error real al publicar restaura el directorio anterior', () => conCarpeta('rollback', raiz => {
  const destino = preparar(raiz);
  assert.throws(() => publicar(join(raiz, 'staging-inexistente'), join(destino, 'dist'), join(raiz, 'anterior')), /ENOENT/);
  assert.equal(readFileSync(join(destino, 'dist', 'assets', 'anterior.js'), 'utf8'), 'compilacion anterior completa');
  assert.equal(existsSync(join(raiz, 'anterior')), false);
}));

test('065:RF-10 — rechaza runtime y caché dentro del checkout, incluso por enlace', () => conCarpeta('raices', raiz => {
  const destino = preparar(raiz);
  const externo = { CSG_RUNTIME_HOME: join(raiz, 'runtime'), CSG_CACHE_HOME: join(raiz, 'cache') };
  assert.throws(() => rutasFrontend(destino, { ...externo, CSG_RUNTIME_HOME: join(destino, 'temporal') }), /fuera del checkout/);
  assert.throws(() => rutasFrontend(destino, { ...externo, CSG_CACHE_HOME: join(destino, 'cache') }), /fuera del checkout/);
  symlinkSync(join(raiz, 'checkout'), join(raiz, 'enlace'), 'junction');
  assert.throws(() => rutasFrontend(destino, { ...externo, CSG_CACHE_HOME: join(raiz, 'enlace', 'cache') }), /fuera del checkout/);
}));

test('065:RF-11 — una raíz en otro volumen se rechaza antes de compilar', { skip: process.platform !== 'win32' }, () => conCarpeta('volumen', raiz => {
  const destino = preparar(raiz);
  const otraUnidad = parse(destino).root.toUpperCase().startsWith('C:') ? 'D:/' : 'C:/';
  assert.throws(() => rutasFrontend(destino, { CSG_RUNTIME_HOME: join(otraUnidad, 'csg-runtime'), CSG_CACHE_HOME: join(raiz, 'cache') }), /mismo volumen/);
}));

test('065:RF-10 RF-11 — un worktree anidado usa el exterior del checkout primario', () => conCarpeta('worktrees', raiz => {
  const principal = join(raiz, 'principal');
  mkdirSync(principal);
  for (const argumentos of [['init'], ['-c', 'user.name=Prueba', '-c', 'user.email=prueba@example.invalid', 'commit', '--allow-empty', '-m', 'Prueba aislada']]) {
    const resultado = spawnSync('git', argumentos, { cwd: principal, encoding: 'utf8' });
    assert.equal(resultado.status, 0, resultado.stderr);
  }
  const checkout = join(principal, '.worktrees', 'candidato');
  const resultado = spawnSync('git', ['worktree', 'add', '-b', 'candidato', checkout], { cwd: principal, encoding: 'utf8' });
  assert.equal(resultado.status, 0, resultado.stderr);
  mkdirSync(join(checkout, 'frontend'));
  const rutas = rutasFrontend(join(checkout, 'frontend'), { LOCALAPPDATA: join(raiz, 'local') });
  assert.equal(estaDentro(principal, rutas.staging), false);
  assert.equal(estaDentro(raiz, rutas.staging), true, JSON.stringify({ raiz, rutas }));
  assert.equal(parse(rutas.staging).root, parse(checkout).root);
}));

test('065:RF-4 — recupera la publicación interrumpida antes de otro build inválido', () => conCarpeta('recuperacion', raiz => {
  const destino = preparar(raiz);
  const entorno = { CSG_RUNTIME_HOME: join(raiz, 'runtime'), CSG_CACHE_HOME: join(raiz, 'cache') };
  const rutas = rutasFrontend(destino, entorno);
  const ejecucion = join(rutas.staging, 'build-interrumpido');
  mkdirSync(ejecucion, { recursive: true });
  const respaldo = join(ejecucion, 'anterior');
  renameSync(join(destino, 'dist'), respaldo);
  writeFileSync(join(rutas.staging, 'publicacion.json'), JSON.stringify({ destino: join(destino, 'dist'), respaldo }));
  writeFileSync(join(destino, 'src', 'main.ts'), 'const x: number = "error"; export { x };');
  const resultado = compilar(destino, raiz);
  assert.notEqual(resultado.status, 0);
  assert.match(resultado.stdout + resultado.stderr, /TS2322/);
  assert.equal(readFileSync(join(destino, 'dist', 'assets', 'anterior.js'), 'utf8'), 'compilacion anterior completa');
}));

for (const tipo of ['vacio', 'truncado']) {
  test(`065:RF-4 — recupera respaldo con lock heredado ${tipo}`, () => conCarpeta(`lock-${tipo}`, raiz => {
    const destino = preparar(raiz);
    const rutas = rutasFrontend(destino, { CSG_RUNTIME_HOME: join(raiz, 'runtime'), CSG_CACHE_HOME: join(raiz, 'cache') });
    const respaldo = join(rutas.staging, 'build-interrumpido', 'anterior');
    mkdirSync(join(rutas.staging, 'build-interrumpido'), { recursive: true });
    renameSync(join(destino, 'dist'), respaldo);
    writeFileSync(join(rutas.staging, 'publicacion.json'), JSON.stringify({ destino: join(destino, 'dist'), respaldo }));
    const terminado = spawnSync(process.execPath, ['-e', ''], { env: entornoHijo });
    assert.equal(terminado.status, 0);
    const contenido = tipo === 'vacio' ? '' : `{"pid":${terminado.pid},"checkout":`;
    writeFileSync(join(rutas.staging, 'build.lock'), contenido);
    writeFileSync(join(destino, 'src', 'main.ts'), 'const x: number = "error"; export { x };');
    const resultado = compilar(destino, raiz);
    assert.notEqual(resultado.status, 0);
    assert.match(resultado.stdout + resultado.stderr, /TS2322/, 'Debe recuperar y llegar al compilador real.');
    assert.equal(readFileSync(join(destino, 'dist', 'assets', 'anterior.js'), 'utf8'), 'compilacion anterior completa');
  }));
}

test('065:RF-4 — el lock heredado de un proceso vivo se conserva intacto', async () => {
  const raiz = mkdtempSync(join(process.env.CSG_TEST_HOME || realpathSync.native(tmpdir()), 'csg-lock-vivo-'));
  const propietario = spawn(process.execPath, ['-e', 'process.stdout.write("listo"); setInterval(() => {}, 1000);'], { env: entornoHijo, stdio: ['ignore', 'pipe', 'pipe'] });
  const fin = once(propietario, 'exit');
  try {
    await once(propietario.stdout, 'data');
    const destino = preparar(raiz);
    const rutas = rutasFrontend(destino, { CSG_RUNTIME_HOME: join(raiz, 'runtime'), CSG_CACHE_HOME: join(raiz, 'cache') });
    mkdirSync(rutas.staging, { recursive: true });
    writeFileSync(join(destino, 'src', 'main.ts'), 'document.body.textContent = "correcto";');
    for (const contenido of [JSON.stringify({ pid: propietario.pid, checkout: rutas.checkout }), `{"pid":${propietario.pid},"checkout":`]) {
      writeFileSync(join(rutas.staging, 'build.lock'), contenido);
      const resultado = compilar(destino, raiz);
      assert.notEqual(resultado.status, 0);
      assert.match(resultado.stdout + resultado.stderr, /compilación activa/);
      assert.equal(readFileSync(join(rutas.staging, 'build.lock'), 'utf8'), contenido);
    }
    assert.equal(readFileSync(join(destino, 'dist', 'assets', 'anterior.js'), 'utf8'), 'compilacion anterior completa');
  } finally {
    propietario.kill();
    await fin;
    rmSync(raiz, { recursive: true, force: true });
  }
});

test('065:RF-4 — recupera guard propio muerto o vacío y preserva archivos desconocidos', () => conCarpeta('guard-recuperable', raiz => {
  const destino = preparar(raiz);
  const rutas = rutasFrontend(destino, { CSG_RUNTIME_HOME: join(raiz, 'runtime'), CSG_CACHE_HOME: join(raiz, 'cache') });
  const guard = join(rutas.staging, 'build.guard');
  const muerto = spawnSync(process.execPath, ['-e', ''], { env: entornoHijo });
  const nonce = '11111111-1111-4111-8111-111111111111';
  writeFileSync(join(destino, 'src', 'main.ts'), 'const x: number = "error"; export { x };');
  for (const conPropietario of [true, false]) {
    mkdirSync(guard, { recursive: true });
    if (conPropietario) writeFileSync(join(guard, `owner-${nonce}.json`), JSON.stringify({ pid: muerto.pid, checkout: rutas.checkout, nonce }));
    const resultado = compilar(destino, raiz);
    assert.notEqual(resultado.status, 0);
    assert.match(resultado.stdout + resultado.stderr, /TS2322/);
    assert.equal(existsSync(guard), false);
  }
  mkdirSync(guard);
  writeFileSync(join(guard, 'ajeno.txt'), 'conservar');
  const resultado = compilar(destino, raiz);
  assert.notEqual(resultado.status, 0);
  assert.match(resultado.stdout + resultado.stderr, /archivos desconocidos/);
  assert.equal(readFileSync(join(guard, 'ajeno.txt'), 'utf8'), 'conservar');
}));

function compilarEnProceso(destino, raiz) {
  const proceso = spawn(process.execPath, [join(destino, 'scripts', 'build.mjs')], { cwd: destino, env: { ...entornoHijo, CSG_RUNTIME_HOME: join(raiz, 'runtime'), CSG_CACHE_HOME: join(raiz, 'cache') }, stdio: ['ignore', 'pipe', 'pipe'] });
  let salida = '';
  proceso.stdout.on('data', dato => { salida += dato; });
  proceso.stderr.on('data', dato => { salida += dato; });
  const terminado = once(proceso, 'exit').then(([codigo]) => ({ codigo, salida }));
  return { proceso, terminado };
}

async function esperarArchivo(ruta) {
  const limite = Date.now() + 15000;
  while (!existsSync(ruta)) {
    assert.ok(Date.now() < limite, `No apareció el marcador del build real: ${ruta}`);
    await new Promise(resolver => setTimeout(resolver, 20));
  }
}

test('065:RF-4 — builds concurrentes reclaman un lock roto sin robar el build activo', async () => {
  const raiz = mkdtempSync(join(process.env.CSG_TEST_HOME || realpathSync.native(tmpdir()), 'csg-lock-concurrente-'));
  const procesos = [];
  const liberar = join(raiz, 'continuar');
  try {
    const destino = preparar(raiz);
    const rutas = rutasFrontend(destino, { CSG_RUNTIME_HOME: join(raiz, 'runtime'), CSG_CACHE_HOME: join(raiz, 'cache') });
    mkdirSync(rutas.staging, { recursive: true });
    writeFileSync(join(rutas.staging, 'build.lock'), '');
    writeFileSync(join(destino, 'src', 'main.ts'), 'document.body.textContent = "correcto";');
    const marcador = join(raiz, 'vite-en-marcha');
    writeFileSync(join(destino, 'vite.config.mjs'), `import { existsSync, writeFileSync } from "node:fs"; export default { plugins: [{ name: "pausa-real", async buildStart() { writeFileSync(${JSON.stringify(marcador)}, "listo"); while (!existsSync(${JSON.stringify(liberar)})) await new Promise(resolver => setTimeout(resolver, 20)); } }] };`);
    procesos.push(compilarEnProceso(destino, raiz), compilarEnProceso(destino, raiz));
    await esperarArchivo(marcador);
    const guard = join(rutas.staging, 'build.guard');
    const entradas = readdirSync(guard);
    assert.equal(entradas.length, 1);
    const contenido = readFileSync(join(guard, entradas[0]), 'utf8');
    const propietario = JSON.parse(contenido);
    assert.equal(entradas[0], `owner-${propietario.nonce}.json`);
    assert.equal(procesos.some(proceso => proceso.proceso.pid === propietario.pid), true);
    const tercero = compilar(destino, raiz);
    assert.notEqual(tercero.status, 0, tercero.stdout + tercero.stderr);
    assert.match(tercero.stdout + tercero.stderr, /compilación activa/);
    assert.equal(readFileSync(join(guard, entradas[0]), 'utf8'), contenido);
    writeFileSync(liberar, 'continuar');
    const resultados = await Promise.all(procesos.map(proceso => proceso.terminado));
    assert.deepEqual(resultados.map(resultado => resultado.codigo).sort(), [0, 1], JSON.stringify(resultados));
    assert.match(resultados.find(resultado => resultado.codigo !== 0).salida, /compilación activa/);
    assert.match(readFileSync(join(destino, 'dist', 'index.html'), 'utf8'), /assets\/index-/);
  } finally {
    writeFileSync(liberar, 'continuar');
    await Promise.all(procesos.map(proceso => proceso.terminado));
    rmSync(raiz, { recursive: true, force: true });
  }
});

// cpSync recursivo de Node 22.23 en Windows no copiaba a una carpeta con «ñ» (GitHub Actions, 2026-11-10: «Cannot
// find module …\csg-con espacios y ñ-…\scripts\build.mjs»). Con readdirSync y copyFileSync la ruta llega entera.
function copiarArbol(origen, destino) {
  mkdirSync(destino, { recursive: true });
  for (const entrada of readdirSync(origen, { withFileTypes: true })) {
    const desde = join(origen, entrada.name);
    const hasta = join(destino, entrada.name);
    if (entrada.isDirectory()) copiarArbol(desde, hasta);
    else copyFileSync(desde, hasta);
  }
}
function preparar(raiz) {
  const destino = join(raiz, 'checkout', 'frontend');
  mkdirSync(join(destino, 'src'), { recursive: true });
  writeFileSync(join(destino, 'package.json'), JSON.stringify(paquete));
  copyFileSync(join(frontend, 'tsconfig.json'), join(destino, 'tsconfig.json'));
  if (existsSync(join(frontend, 'scripts'))) copiarArbol(join(frontend, 'scripts'), join(destino, 'scripts'));
  const backend = join(raiz, 'checkout', 'src', 'convertersmartgrid', 'web');
  mkdirSync(backend, { recursive: true });
  copyFileSync(join(frontend, '..', 'src', 'convertersmartgrid', 'web', 'runtime.py'), join(backend, 'runtime.py'));
  symlinkSync(join(frontend, 'node_modules'), join(destino, 'node_modules'), 'junction');
  writeFileSync(join(destino, 'index.html'), '<div id="root"></div><script type="module" src="/src/main.ts"></script>');
  mkdirSync(join(destino, 'dist', 'assets'), { recursive: true });
  writeFileSync(join(destino, 'dist', 'index.html'), '<script src="/assets/anterior.js"></script>');
  writeFileSync(join(destino, 'dist', 'assets', 'anterior.js'), 'compilacion anterior completa');
  return destino;
}

test('065:RF-3 RF-4 — una salida Vite incompleta nunca reemplaza dist anterior', () => conCarpeta('integridad', raiz => {
  const destino = preparar(raiz);
  writeFileSync(join(destino, 'src', 'main.ts'), 'document.body.textContent = "correcto";');
  writeFileSync(join(destino, 'vite.config.mjs'), 'import { unlinkSync } from "node:fs"; import { join } from "node:path"; export default { plugins: [{ name: "salida-incompleta", writeBundle(options, bundle) { for (const archivo of Object.keys(bundle)) if (archivo.endsWith(".js")) unlinkSync(join(options.dir, archivo)); } }] };');
  const resultado = compilar(destino, raiz);
  assert.notEqual(resultado.status, 0, resultado.stdout + resultado.stderr);
  assert.match(resultado.stdout + resultado.stderr, /no existe|faltante|referencia/i);
  assert.equal(readFileSync(join(destino, 'dist', 'assets', 'anterior.js'), 'utf8'), 'compilacion anterior completa');
}));

function compilar(destino, raiz) {
  assert.ok(process.env.npm_execpath, 'Ejecutar mediante npm test para usar el mismo npm.');
  return spawnSync(process.execPath, [process.env.npm_execpath, 'run', 'build'], {
    cwd: destino, encoding: 'utf8', env: { ...entornoHijo,
      CSG_RUNTIME_HOME: join(raiz, 'runtime'), CSG_CACHE_HOME: join(raiz, 'cache') },
  });
}

for (const nombre of ['sin-espacios', 'con espacios y ñ']) {
  test(`065:RF-9 — pruebas existentes funcionan ${nombre}`, () => conCarpeta(nombre, raiz => {
    const destino = preparar(raiz);
    // 081:RF-51: el render de Entrada consume sus componentes reales y su contexto.
    copiarArbol(join(frontend, 'src'), join(destino, 'src'));
    mkdirSync(join(destino, 'test'));
    for (const archivo of ['clientesCatalogo.test.mjs', 'projectBinding.test.mjs']) {
      copyFileSync(join(frontend, 'test', archivo), join(destino, 'test', archivo));
    }
    const resultado = spawnSync(process.execPath, ['--test', 'test/clientesCatalogo.test.mjs', 'test/projectBinding.test.mjs'], { cwd: destino, encoding: 'utf8', env: entornoHijo });
    assert.equal(resultado.status, 0, resultado.stdout + resultado.stderr);
  }));

  for (const fallo of ['typescript', 'vite']) {
    test(`065:RF-4 — fallo ${fallo} conserva dist completo ${nombre}`, () => conCarpeta(nombre, raiz => {
      const destino = preparar(raiz);
      writeFileSync(join(destino, 'src', 'main.ts'), fallo === 'typescript' ? 'const x: number = "error"; export { x };' : 'document.body.textContent = "correcto";');
      if (fallo === 'vite') writeFileSync(join(destino, 'vite.config.mjs'), 'export default { plugins: [{ name: "fallo-real", writeBundle() { throw new Error("vite-falla-publicando"); } }] };');
      const resultado = compilar(destino, raiz);
      assert.notEqual(resultado.status, 0, 'La compilación inválida debe fallar.');
      assert.match(resultado.stdout + resultado.stderr, fallo === 'typescript' ? /TS2322/ : /vite-falla-publicando/);
      assert.equal(readFileSync(join(destino, 'dist', 'index.html'), 'utf8'), '<script src="/assets/anterior.js"></script>');
      assert.equal(readFileSync(join(destino, 'dist', 'assets', 'anterior.js'), 'utf8'), 'compilacion anterior completa');
      assert.equal(existsSync(join(destino, 'tsconfig.tsbuildinfo')), false, 'No se crean cachés en el checkout.');
    }));
  }

  test(`065:RF-4 RF-10 RF-11 — publica build completo ${nombre}`, () => conCarpeta(nombre, raiz => {
    const destino = preparar(raiz);
    writeFileSync(join(destino, 'src', 'main.ts'), 'document.body.textContent = "correcto";');
    const resultado = compilar(destino, raiz);
    assert.equal(resultado.status, 0, resultado.stdout + resultado.stderr);
    assert.match(readFileSync(join(destino, 'dist', 'index.html'), 'utf8'), /assets\/index-/);
    assert.equal(existsSync(join(destino, 'dist', 'assets', 'anterior.js')), false);
    assert.equal(existsSync(join(destino, 'tsconfig.tsbuildinfo')), false);
  }));
}
