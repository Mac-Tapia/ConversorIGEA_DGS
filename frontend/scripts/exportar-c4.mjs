// Exporta el C4 interactivo a una PNG por vista y al plano PDF (spec 090, RF-26).
//
// Uso, desde la raíz del repositorio:  node frontend/scripts/exportar-c4.mjs [--salida docs/architecture]
//
// Hasta el 25-11 las PNG y el PDF se sacaban a mano desde la página, y el PDF del 17-11 se quedó sin las vistas del PIT,
// de los motores abiertos y de los carriles. Ahora salen de la misma página que se versiona: se compila con
// tools/build_interactive_architecture.py, se abre en Chromium (el Playwright fijado en frontend/) y se fotografía cada
// pestaña. El PDF lleva una portada, una página por vista y otra por bloque de pseudocódigo. Si una pestaña no dibuja su
// vista, la orden falla y la nombra.
import { spawnSync } from 'node:child_process';
import { existsSync, mkdtempSync, readFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { chromium } from 'playwright-core';

const RAIZ = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..');
const argumentos = process.argv.slice(2);
if (argumentos.includes('--help') || argumentos.includes('-h')) {
  console.log('Uso: node frontend/scripts/exportar-c4.mjs [--salida docs/architecture]\n'
    + 'Una PNG por vista (c4_vista_<vista>.png) y plano_flujo_arquitectura_converter_smart_grid.pdf (090:RF-26).');
  process.exit(0);
}
const i = argumentos.indexOf('--salida');
const SALIDA = path.resolve(RAIZ, i >= 0 ? argumentos[i + 1] : 'docs/architecture');
const PDF = path.join(SALIDA, 'plano_flujo_arquitectura_converter_smart_grid.pdf');

function python() {
  const venv = path.join(RAIZ, '.venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python');
  return existsSync(venv) ? venv : 'python';
}

function escapar(texto) {
  return texto.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

const temporal = mkdtempSync(path.join(tmpdir(), 'c4-'));
try {
  const compilado = spawnSync(python(), ['tools/build_interactive_architecture.py', '--output-dir', temporal],
    { cwd: RAIZ, encoding: 'utf-8' });
  if (compilado.status !== 0) {
    console.error(`no se pudo compilar la página: ${compilado.stderr || compilado.stdout}`);
    process.exit(1);
  }
  const navegador = await chromium.launch();
  try {
    const pagina = await navegador.newPage({ viewport: { width: 2000, height: 1300 }, deviceScaleFactor: 1 });
    await pagina.emulateMedia({ reducedMotion: 'reduce' });
    await pagina.goto(pathToFileURL(path.join(temporal, 'index.html')).href);
    const vistas = await pagina.$$eval('[data-view]', botones => botones.map(b => ({ id: b.dataset.view, nombre: b.textContent.trim() })));
    const fotos = [];
    for (const vista of vistas) {
      await pagina.click(`[data-view="${vista.id}"]`);
      const cajas = await pagina.$$eval('#c4-nodes > g', g => g.length);
      if (!cajas) {
        console.error(`la pestaña «${vista.nombre}» (${vista.id}) no dibuja ninguna caja: falta su vista en «views»`);
        process.exit(1);
      }
      const titulo = await pagina.$eval('#c4-detail-title', el => el.textContent.trim());
      const png = path.join(SALIDA, `c4_vista_${vista.id}.png`);
      await pagina.locator('.c4-canvas').screenshot({ path: png });
      fotos.push({ ...vista, titulo, png });
      console.log(`vista ${vista.id}: ${path.relative(RAIZ, png)}`);
    }
    const bloques = await pagina.$$eval('.c4-pseudo-block', ds => ds.map(d => ({
      titulo: d.querySelector('summary').textContent.trim(), codigo: d.querySelector('pre').textContent })));
    if (!bloques.length) {
      console.error('la página no trae el pseudocódigo: python tools/generar_c4.py --escribir');
      process.exit(1);
    }
    const leyenda = await pagina.$eval('.c4-legend', el => el.textContent.trim());
    const revision = (readFileSync(path.join(RAIZ, 'docs/architecture/workspace.dsl'), 'utf-8').match(/revisión (\w+)/) || [])[1] || '';
    const hojas = [
      `<section class="hoja portada"><h1>Arquitectura C4 — ConverterSmartGrid</h1><p>${escapar(leyenda)}</p>`
        + `<p>Revisión del C4: ${escapar(revision)}. Vistas: ${fotos.map(f => escapar(f.nombre)).join(', ')}.</p>`
        + '<p>Fuente: docs/architecture/workspace.dsl, arquitectura-interactiva-c4.html y pseudocodigo.md (spec 090).</p></section>',
      ...fotos.map(f => `<section class="hoja"><h2>${escapar(f.nombre)} — ${escapar(f.titulo)}</h2>`
        // Incrustada: una página creada con setContent no carga file://, y el PDF del 25-11 salió con las vistas en blanco.
        + `<img src="data:image/png;base64,${readFileSync(f.png).toString('base64')}" alt="${escapar(f.titulo)}"></section>`),
      ...bloques.map(b => `<section class="hoja"><h2>Pseudocódigo — ${escapar(b.titulo)}</h2><pre>${escapar(b.codigo)}</pre></section>`),
    ];
    const impresion = await navegador.newPage();
    await impresion.setContent(`<!doctype html><html lang="es"><head><meta charset="utf-8"><style>
      @page { size: A3 landscape; margin: 12mm; }
      body { font-family: Inter, ui-sans-serif, system-ui, sans-serif; color: #17202a; margin: 0; }
      .hoja { page-break-after: always; break-after: page; height: 100%; }
      .hoja:last-child { page-break-after: auto; break-after: auto; }
      h1 { font-size: 28px; margin: 40mm 0 8mm; } h2 { font-size: 18px; margin: 0 0 4mm; }
      img { display: block; max-width: 100%; max-height: 245mm; margin: 0 auto; }
      pre { font-size: 14px; line-height: 1.45; white-space: pre-wrap; }
    </style></head><body>${hojas.join('\n')}</body></html>`, { waitUntil: 'load' });
    const rotas = await impresion.$$eval('img', imgs => imgs.filter(i => !i.complete || !i.naturalWidth).map(i => i.alt));
    if (rotas.length) {
      console.error(`el plano saldría con vistas en blanco: ${rotas.join(', ')}`);
      process.exit(1);
    }
    await impresion.pdf({ path: PDF, format: 'A3', landscape: true, printBackground: true });
    console.log(`plano: ${path.relative(RAIZ, PDF)} (${hojas.length} páginas)`);
  } finally {
    await navegador.close();
  }
} finally {
  rmSync(temporal, { recursive: true, force: true });
}
