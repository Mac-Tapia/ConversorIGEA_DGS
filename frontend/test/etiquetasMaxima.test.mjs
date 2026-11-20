import assert from 'node:assert/strict';
import test from 'node:test';
import { build } from 'esbuild';
import { createRequire } from 'node:module';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';

// 086:RF-123: con varias curvas de cabecera, cada máxima lleva su etiqueta (alimentador, kW y fecha) junto a su punto,
// sin taparse unas a otras.
const FRONT = fileURLToPath(new URL('../', import.meta.url));

async function graficos() {
  const salida = await build({
    stdin: { contents: `export * from './src/shared/graficos';`, resolveDir: FRONT, loader: 'ts' },
    bundle: true, format: 'cjs', platform: 'node', write: false, external: ['react'],
  });
  const require = createRequire(import.meta.url);
  const m = { exports: {} };
  new Function('module', 'exports', 'require', salida.outputFiles[0].text)(m, m.exports, require);
  return m.exports;
}

test('086:RF-123 las etiquetas quedan separadas, dentro del gráfico y en el orden de entrada', async () => {
  const { separarEtiquetas } = await graficos();
  assert.equal(typeof separarEtiquetas, 'function', 'falta separarEtiquetas');
  // Lección B6: la semilla del sorteo sale en el registro para repetir el caso; CSG_SEMILLA la fija.
  const semilla = Number(process.env.CSG_SEMILLA) || Math.floor(Math.random() * 2 ** 31);
  console.log(`separarEtiquetas: semilla ${semilla}`);
  let x = semilla;
  const azar = () => ((x = (x * 1103515245 + 12345) % 2 ** 31) / 2 ** 31);
  for (let caso = 0; caso < 200; caso++) {
    const n = 1 + Math.floor(azar() * 8);
    const ys = Array.from({ length: n }, () => 5 + azar() * 260);
    const r = separarEtiquetas(ys, 24, 244, 14);
    assert.equal(r.length, n, `semilla ${semilla}`);
    const orden = r.map((y, i) => ({ y, i })).sort((a, b) => a.y - b.y);
    for (const o of orden) assert.ok(o.y >= 24 - 1e-9 && o.y <= 244 + 1e-9, `fuera del gráfico (semilla ${semilla})`);
    for (let k = 1; k < orden.length; k++) assert.ok(orden[k].y - orden[k - 1].y >= 14 - 1e-9, `se tapan (semilla ${semilla})`);
  }
  // Un punto solo, dentro: su etiqueta a su altura.
  assert.deepEqual(separarEtiquetas([100], 24, 244, 14), [100]);
});

test('086:RF-123 la gráfica con varias curvas pinta la etiqueta de cada máxima con su alimentador, kW y fecha', () => {
  const fuente = readFileSync(join(FRONT, 'src', 'features', 'powerfactory', 'CurvaCabecera.tsx'), 'utf8');
  assert.match(fuente, /separarEtiquetas\(/, 'las etiquetas no se separan');
  assert.match(fuente, /texto: `\$\{t\.etiqueta\} · \$\{fmtNum\(t\.kwMax, 1\)\} kW · \$\{diaHora\(t\.fm\)\}`/);
  assert.match(fuente, /g\.etiquetas\.map\(\(e\) =>/, 'las etiquetas no se pintan');
});
