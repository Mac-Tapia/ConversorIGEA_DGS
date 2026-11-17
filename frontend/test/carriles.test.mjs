import assert from 'node:assert/strict';
import test from 'node:test';
import { build } from 'esbuild';
import { createRequire } from 'node:module';
import { readFileSync } from 'node:fs';

// 080:RF-61: la búsqueda de publicaciones va en el carril «red» para no ocupar el motor; la barra de trabajos y el
// monitor del asistente decían «Motor» de todo carril que no fuera DIgSILENT (auditoría de f7, 17-11).
// Los carriles del servidor, del contrato que genera tools/generar_contrato_api.py (el Literal de JobRespuesta.lane):
// queda dentro de frontend/, que es lo que estas pruebas tienen (test_frontend_rutas las copia solas a otra carpeta).
const lanesDelServidor = () => {
  const esquema = readFileSync('src/api/esquema.ts', 'utf8');
  const m = esquema.match(/^\s+lane\??: ((?:"[a-z_]+"(?: \| )?)+);/m);
  assert.ok(m, 'no se encuentra el tipo de lane en src/api/esquema.ts');
  return [...m[1].matchAll(/"([a-z_]+)"/g)].map((x) => x[1]);
};

async function carriles() {
  const salida = await build({ entryPoints: ['src/shared/carriles.ts'], bundle: true, write: false, format: 'cjs', platform: 'node' });
  const mod = { exports: {} };
  new Function('module', 'exports', 'require', salida.outputFiles[0].text)(mod, mod.exports, createRequire(import.meta.url));
  return mod.exports;
}

test('080:RF-61 cada carril del servidor tiene su nombre y solo el motor se llama «Motor»', async () => {
  const { NOMBRE_CARRIL, nombreCarril } = await carriles();
  for (const lane of lanesDelServidor()) {
    assert.ok(NOMBRE_CARRIL[lane], `el carril ${lane} no tiene nombre para el operador`);
    if (lane !== 'engine') assert.notEqual(nombreCarril(lane), 'Motor', lane);
  }
  assert.equal(nombreCarril('red'), 'Red');
  assert.equal(nombreCarril('carril_nuevo'), 'carril_nuevo');
});

test('080:RF-61 la barra de trabajos y el monitor nombran el carril con nombreCarril, y cada carril tiene su estilo', () => {
  for (const f of ['src/app/JobBar.tsx', 'src/features/asistente/MonitorAgente.tsx']) {
    const t = readFileSync(f, 'utf8');
    assert.match(t, /nombreCarril\(j\.lane\)/, f);
    assert.doesNotMatch(t, /'Motor'/, `${f} no escribe «Motor» por su cuenta`);
  }
  const css = readFileSync('src/shared/styles.css', 'utf8');
  for (const lane of lanesDelServidor()) assert.match(css, new RegExp(String.raw`\.lane-${lane}\b`), `sin estilo .lane-${lane}`);
});
