/**
 * 112:RF-21 (T19) — el dibujo de la pantalla con las redes sintéticas de la medición de escala, en navegador real.
 *
 * Para cada tamaño (10, 50 y 200 alimentadores por omisión):
 * 1. arranca la web de prueba (`web_de_prueba.py`) en una carpeta de datos temporal, sin perfil de empresa, con la
 *    seguridad real y en un puerto libre que nunca es el de la web del operador (8765 ni 8766), con la red de la medición
 *    de escala (`CSG_E2E_ESCALA=1`: `spec_de_escala`, la misma que mide la API `tools/benchmark_escala_web.py`); la web
 *    crea el espacio, sube las tres casillas, carga la red y la convierte con su vista previa;
 * 2. abre la web en Edge (`--canal`, por omisión `msedge`) sin salida a la red y, en cada repetición, mide con
 *    `PerformanceObserver` y `performance.mark` el tiempo desde que llega la respuesta de `feeders` hasta que la tabla
 *    de alimentadores muestra su última fila ya pintada, y el del plano de la red unida con todos los alimentadores hasta
 *    su aviso «listo»;
 * 3. deja `dibujo_<N>.json` en `--salida` con el p50 y el p95 de cada magnitud, cada valor, el navegador, la red
 *    sintética y el commit (escritura atómica: un temporal y un cambio de nombre).
 * Después, `tools/benchmark_escala_web.py --salida escala.json --dibujo <salida> --solo-enlazar` enlaza el resultado de
 * la T18 con estos JSON.
 *
 * Uso (desde frontend/, con la web compilada):
 *   node e2e/escala_dibujo.mjs --salida CARPETA [--tamanos 10 50 200] [--repeticiones 10] [--escala escala.json]
 *        [--canal msedge] [--espera-s 3600]
 * `--escala` toma la semilla, los tramos y las cargas de la red del resultado de la T18; sin él, los de la medición
 * (112, 200 y 60). Sale con 0 si midió todos los tamaños, 1 si alguno falló y 2 si el uso es incorrecto.
 */
import { spawn, spawnSync } from 'node:child_process';
import { existsSync, mkdirSync, mkdtempSync, readFileSync, renameSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium } from '@playwright/test';
import { nombreDibujo, puertoPermitido, resumen } from './escala_resumen.mjs';
import { puertoLibre, python } from './preparar.mjs';

const AQUI = dirname(fileURLToPath(import.meta.url));
const FRONT = resolve(AQUI, '..');
const RAIZ = resolve(FRONT, '..');
const RED_POR_OMISION = { semilla: 112, tramos_tipicos: 200, cargas_tipicas: 60 };
const LOCALES = new Set(['127.0.0.1', 'localhost', '[::1]', '']);

function argumentos(argv) {
  const a = { tamanos: [10, 50, 200], repeticiones: 10, canal: 'msedge', esperaS: 3600, salida: null, escala: null };
  for (let i = 0; i < argv.length; i++) {
    const v = argv[i];
    if (v === '--salida') a.salida = resolve(argv[++i]);
    else if (v === '--escala') a.escala = resolve(argv[++i]);
    else if (v === '--canal') a.canal = argv[++i];
    else if (v === '--repeticiones') a.repeticiones = Number(argv[++i]);
    else if (v === '--espera-s') a.esperaS = Number(argv[++i]);
    else if (v === '--tamanos') {
      a.tamanos = [];
      while (i + 1 < argv.length && !argv[i + 1].startsWith('--')) a.tamanos.push(Number(argv[++i]));
    } else throw new Error(`opción desconocida: ${v}`);
  }
  if (!a.salida) throw new Error('falta --salida CARPETA');
  if (!a.tamanos.length || a.tamanos.some((n) => !Number.isInteger(n) || n < 1)) throw new Error('--tamanos: enteros ≥ 1');
  if (!Number.isInteger(a.repeticiones) || a.repeticiones < 2) throw new Error('--repeticiones: al menos 2');
  return a;
}

function git(...args) {
  const r = spawnSync('git', args, { cwd: RAIZ, encoding: 'utf8' });
  return r.status === 0 ? r.stdout.trim() : null;
}

/** Con qué código se midió: el commit, el árbol del índice y si había cambios sin registrar, en todo el árbol y en lo
 * que sirve la web (src/ y frontend/src/). */
function revision() {
  const todo = git('status', '--porcelain', '--untracked-files=no');
  const web = git('status', '--porcelain', '--untracked-files=no', '--', 'src', 'frontend/src');
  return { commit: git('rev-parse', 'HEAD'), arbol_indice: git('write-tree'),
    cambios_sin_registrar: todo === null ? null : Boolean(todo), cambios_en_la_web: web === null ? null : Boolean(web) };
}

function escribirAtomico(ruta, datos) {
  mkdirSync(dirname(ruta), { recursive: true });
  const temporal = `${ruta}.${process.pid}.tmp`;
  writeFileSync(temporal, JSON.stringify(datos, null, 1) + '\n', 'utf8');
  renameSync(temporal, ruta);
}

async function puertoDeLaMedicion() {
  for (;;) {
    const p = await puertoLibre();
    if (puertoPermitido(p)) return p;
  }
}

/** La web de prueba con la red de escala; devuelve sus datos («LISTA») y su cierre. */
async function arrancarWeb(n, red, esperaS) {
  const puerto = await puertoDeLaMedicion();
  const tmp = mkdtempSync(join(tmpdir(), 'csg-escala-'));
  const env = { ...process.env, CUDA_VISIBLE_DEVICES: '-1', PYTHONIOENCODING: 'utf-8', CSG_E2E_SIN_MODELO: '1',
    CSG_E2E_ESCALA: '1', CSG_E2E_TRAMOS: String(red.tramos_tipicos), CSG_E2E_CARGAS: String(red.cargas_tipicas) };
  const hijo = spawn(python(), ['-I', join(AQUI, 'web_de_prueba.py'), RAIZ, tmp, String(puerto), String(red.semilla),
    String(n)], { cwd: RAIZ, env, stdio: ['ignore', 'pipe', 'pipe'] });
  let errores = '';
  hijo.stderr.on('data', (d) => { errores = (errores + d.toString()).slice(-4000); });
  const cerrar = () => {
    hijo.kill();
    try { rmSync(tmp, { recursive: true, force: true }); } catch { /* Windows: la carpeta puede seguir abierta */ }
  };
  try {
    const datos = await new Promise((ok, mal) => {
      let resto = '';
      const reloj = setTimeout(() => mal(new Error(`la web de ${n} alimentadores no estuvo lista en ${esperaS} s\n${errores}`)),
        esperaS * 1000);
      hijo.stdout.on('data', (d) => {
        resto += d.toString();
        const linea = resto.split(/\r?\n/).find((l) => l.startsWith('LISTA '));
        if (linea) { clearTimeout(reloj); ok(JSON.parse(linea.slice(6))); }
      });
      hijo.once('exit', (rc) => { clearTimeout(reloj); mal(new Error(`la web de prueba terminó con ${rc}\n${errores}`)); });
    });
    return { datos, puerto, cerrar };
  } catch (e) {
    cerrar();
    throw e;
  }
}

/** Se instala antes de cargar la página: la marca de la última fila pintada de la tabla de alimentadores, medida desde
 * el final de la respuesta de `feeders`. */
function medidorDeLaTabla(n) {
  const estado = { n, tabla_ms: null };
  window.__csgEscala = estado;
  performance.setResourceTimingBufferSize(100000);
  const filas = () => document.querySelectorAll(
    'table input[type="checkbox"][aria-label^="Seleccionar "]:not([aria-label="Seleccionar visibles"])').length;
  const respuesta = () => {
    const r = performance.getEntriesByType('resource').filter((e) => /\/api\/workspaces\/[^/?]+\/feeders(\?|$)/.test(e.name));
    return r.length ? r[r.length - 1] : null;
  };
  let pendiente = false;
  const comprobar = () => {
    if (estado.tabla_ms !== null || pendiente || !document.body || filas() < n || !respuesta()) return;
    pendiente = true;
    // Dos cuadros: el primero se dibuja con la fila ya en el DOM; la marca va cuando ese cuadro está pintado.
    requestAnimationFrame(() => requestAnimationFrame(() => {
      const r = respuesta();
      const marca = performance.mark('csg-escala-ultima-fila');
      estado.tabla_ms = marca.startTime - r.responseEnd;
      estado.respuesta_fin_ms = r.responseEnd;
    }));
  };
  new PerformanceObserver(comprobar).observe({ type: 'resource', buffered: true });
  const mirar = () => new MutationObserver(comprobar).observe(document.documentElement, { childList: true, subtree: true });
  if (document.documentElement) mirar(); else document.addEventListener('readystatechange', mirar, { once: true });
}

/** El plano de la red unida con todos los alimentadores, como la pestaña: en un iframe sandbox hasta su «listo». */
function dibujarPlano(src) {
  return new Promise((ok, mal) => {
    const marco = document.createElement('iframe');
    marco.setAttribute('sandbox', 'allow-scripts');
    marco.style.width = '1200px';
    marco.style.height = '800px';
    performance.mark('csg-escala-plano-inicio');
    const reloj = setTimeout(() => mal(new Error('el plano no avisó «listo» en 600 s')), 600_000);
    window.addEventListener('message', (e) => {
      if (e.source === marco.contentWindow && e.data && e.data.tipo === 'listo') {
        clearTimeout(reloj);
        const m = performance.measure('csg-escala-plano', 'csg-escala-plano-inicio');
        marco.remove();
        ok(m.duration);
      }
    });
    marco.src = src;
    document.body.appendChild(marco);
  });
}

async function medirTamano(navegador, n, a, red) {
  const { datos, puerto, cerrar } = await arrancarWeb(n, red, a.esperaS);
  try {
    if (datos.alimentadores.length !== n) throw new Error(`la web lista ${datos.alimentadores.length} alimentadores, no ${n}`);
    const contexto = await navegador.newContext({ viewport: { width: 1440, height: 1000 }, locale: 'es-PE' });
    const fuera = [];
    await contexto.route('**/*', async (ruta) => {
      const url = new URL(ruta.request().url());
      if (['data:', 'blob:', 'about:'].includes(url.protocol) || LOCALES.has(url.hostname)) await ruta.continue();
      else { fuera.push(url.hostname); await ruta.abort(); }
    });
    await contexto.addInitScript(medidorDeLaTabla, n);
    const q = new URLSearchParams();
    for (const al of datos.alimentadores) q.append('alimentador', al);
    const plano = `${datos.base}/api/workspaces/${encodeURIComponent(datos.espacio)}/plano/pagina?${q}`;
    const tabla = [];
    const planos = [];
    for (let i = 0; i < a.repeticiones; i++) {
      const pagina = await contexto.newPage();
      await pagina.goto(datos.entrada, { waitUntil: 'domcontentloaded' });
      await pagina.waitForFunction(() => window.__csgEscala && window.__csgEscala.tabla_ms !== null, null,
        { timeout: a.esperaS * 1000, polling: 100 });
      tabla.push(await pagina.evaluate(() => window.__csgEscala.tabla_ms));
      planos.push(await pagina.evaluate(dibujarPlano, plano));
      await pagina.close();
      console.error(`[escala] ${n} alimentadores, repetición ${i + 1}/${a.repeticiones}: tabla ${tabla.at(-1).toFixed(1)} ms, `
        + `plano ${planos.at(-1).toFixed(1)} ms`);
    }
    await contexto.close();
    return { formato: 1, herramienta: 'frontend/e2e/escala_dibujo.mjs', medido: new Date().toISOString(),
      revision: revision(), navegador: { canal: a.canal, version: navegador.version() },
      red_sintetica: { ...red, generador: 'convertersmartgrid.dominio.benchmarks.sintetico.spec_de_escala' },
      alimentadores: n, puerto, repeticiones: a.repeticiones, conversion: datos.conversion,
      salidas_bloqueadas: [...new Set(fuera)], tabla: resumen(tabla), plano: resumen(planos) };
  } finally {
    cerrar();
  }
}

async function main() {
  let a;
  try {
    a = argumentos(process.argv.slice(2));
  } catch (e) {
    console.error(`Uso: ${e.message}`);
    return 2;
  }
  if (!existsSync(join(FRONT, 'dist', 'index.html'))) {
    console.error('Falta la web compilada: ejecute «npm run build» en frontend antes de medir.');
    return 2;
  }
  const red = { ...RED_POR_OMISION };
  if (a.escala) {
    const suya = JSON.parse(readFileSync(a.escala, 'utf8')).red_sintetica || {};
    for (const clave of Object.keys(RED_POR_OMISION)) if (Number.isInteger(suya[clave])) red[clave] = suya[clave];
  }
  const navegador = await chromium.launch({ channel: a.canal });
  let rc = 0;
  try {
    for (const n of a.tamanos) {
      try {
        const medida = await medirTamano(navegador, n, a, red);
        escribirAtomico(join(a.salida, nombreDibujo(n)), medida);
        console.error(`[escala] ${n} alimentadores: tabla p50 ${medida.tabla.p50_ms} ms, p95 ${medida.tabla.p95_ms} ms; `
          + `plano p50 ${medida.plano.p50_ms} ms, p95 ${medida.plano.p95_ms} ms`);
      } catch (e) {
        console.error(`[escala] ${n} alimentadores: no se pudo medir: ${e.message}`);
        rc = 1;
      }
    }
  } finally {
    await navegador.close();
  }
  return rc;
}

process.exit(await main());
