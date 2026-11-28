import assert from 'node:assert/strict';
import test from 'node:test';
import { build } from 'esbuild';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

// Spec 114, T4 (2026-11-27): el usuario pidió la parte web del agente MASAC: que proponga junto a las obras
// automáticas, en sombra y sin aplicar, y que el operador confirme o deshaga.
const entry = fileURLToPath(new URL('../src/features/powerfactory/textosAgente.ts', import.meta.url));
const fuente = (rel) => readFileSync(fileURLToPath(new URL(`../src/${rel}`, import.meta.url)), 'utf-8');

async function cargar() {
  const salida = await build({ entryPoints: [entry], bundle: true, write: false, format: 'esm', platform: 'node' });
  return import(`data:text/javascript;base64,${Buffer.from(salida.outputFiles[0].contents).toString('base64')}`);
}

test('114:RF-7: el bloque dice que es una propuesta en sombra que no se aplica, y el marcador frente a la regla', async () => {
  const { TITULO_AGENTE, textoMarcador, textoAcierta } = await cargar();
  assert.equal(TITULO_AGENTE, 'Propuesta del agente (en sombra, no se aplica)');
  assert.equal(textoMarcador({ agente: 0, regla: 0, empate: 0 }), 'Aún no hay propuestas en este proyecto.');
  assert.equal(textoMarcador({ agente: 1, regla: 3, empate: 0 }),
    'Frente a la regla actual: acierta el agente 1 vez, la regla 3 veces, 0 empates (4 propuestas).');
  assert.equal(textoAcierta('regla'), 'Esta vez acierta la regla actual.');
  assert.equal(textoAcierta('agente'), 'Esta vez acierta el agente.');
});

test('114:RF-7: cómo queda la red con cada propuesta, con las mismas palabras', async () => {
  const { textoResultado } = await cargar();
  assert.equal(textoResultado({ en_norma: true, costo: 20, costo_maniobras: 0, vm_min: 0.9512, perdidas_mw: 0.08, obras: [] }),
    'en norma, obras 20, mínima 0.951 p.u.');
  assert.equal(textoResultado({ en_norma: false, costo: 0, costo_maniobras: 2, vm_min: null, perdidas_mw: null, obras: [] }),
    'fuera de norma, sin obras, maniobras 2');
});

test('114:RF-11: solo una propuesta sin decidir se confirma o deshace; después dice cómo quedó', async () => {
  const { puedeDecidir, textoEstado } = await cargar();
  const d = { id: 'a', agente: 'x', tipo: 'banco', elemento: 'B', explicacion: 'Propone…', confirmo: null };
  assert.equal(puedeDecidir({ ...d, estado: 'propuesta' }), true);
  assert.equal(puedeDecidir({ ...d, estado: 'confirmada' }), false);
  assert.equal(textoEstado({ ...d, estado: 'deshecha', confirmo: 'operador' }), 'Deshecha');
  assert.equal(textoEstado({ ...d, estado: 'confirmada', confirmo: 'operador' }), 'Confirmada');
});

test('114:RF-9: el bloque vive junto a las obras automáticas y no aplica nada en DIgSILENT', () => {
  const cargas = fuente('features/powerfactory/CargasTab.tsx');
  const obras = cargas.slice(cargas.indexOf('function ObrasEstadoActual('), cargas.indexOf('type AplicarAparte'));
  assert.match(obras, /<PropuestaAgente project=\{project\} feeders=\{feeders\} \/>/);
  assert.match(cargas, /<ObrasEstadoActual project=\{project\}/);
  const bloque = fuente('features/powerfactory/PropuestaAgente.tsx');
  const llamadas = [...bloque.matchAll(/api\.(\w+)\(/g)].map((m) => m[1]).sort();
  assert.deepEqual([...new Set(llamadas)], ['agenteSombra', 'agenteSombraDecidir', 'agenteSombraPedir']);
  assert.doesNotMatch(bloque, /RF-\d+</);
  const cliente = fuente('api/client.ts');
  assert.match(cliente, /agente\/sombra\/decisiones\/\$\{enc\(decision\)\}`, json\('POST', \{ accion \}\)/);
});
