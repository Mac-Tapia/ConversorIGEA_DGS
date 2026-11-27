import assert from 'node:assert/strict';
import test from 'node:test';
import { build } from 'esbuild';
import { fileURLToPath } from 'node:url';

// Empresa B NJA292 (T32, 2026-11-12): calibrado a 0,568 p.u. y sin cargas nuevas, la web no ofrecía ninguna obra.
const entry = fileURLToPath(new URL('../src/features/powerfactory/obrasEstadoActual.ts', import.meta.url));

async function cargar() {
  const salida = await build({ entryPoints: [entry], bundle: true, write: false, format: 'esm', platform: 'node' });
  const codigo = Buffer.from(salida.outputFiles[0].contents).toString('base64');
  return import(`data:text/javascript;base64,${codigo}`);
}

const BASE = { proyecto: 'NJA292', alimentadores: ['NJA292'], calibrado: true, proyectoDeCargas: null };

test('086:RF-77: calibrado, con alimentadores y sin cargas nuevas integradas, se ofrecen las obras del estado actual', async () => {
  const { ofrecerObrasEstadoActual } = await cargar();
  assert.equal(ofrecerObrasEstadoActual(BASE), true);
  assert.equal(ofrecerObrasEstadoActual({ ...BASE, proyectoDeCargas: 'OTRO' }), true);
});

test('086:RF-77: sin proyecto, sin alimentadores, sin calibrar o con cargas integradas, no', async () => {
  const { ofrecerObrasEstadoActual } = await cargar();
  assert.equal(ofrecerObrasEstadoActual({ ...BASE, proyecto: null }), false);
  assert.equal(ofrecerObrasEstadoActual({ ...BASE, alimentadores: [] }), false);
  assert.equal(ofrecerObrasEstadoActual({ ...BASE, calibrado: false }), false);
  // Con cargas integradas, la escalera va en su informe, como siempre (042:RF-81).
  assert.equal(ofrecerObrasEstadoActual({ ...BASE, proyectoDeCargas: 'NJA292' }), false);
});

test('086:RF-77: el resultado dice que lo medido es el estado actual', async () => {
  const { RESUMEN_SIN_CARGAS } = await cargar();
  assert.match(RESUMEN_SIN_CARGAS, /estado actual/);
  assert.match(RESUMEN_SIN_CARGAS, /violan límites/);
});

test('086:RF-77: con cargas nuevas aplicadas en disco, el bloque las nombra y propone las obras automáticamente', async () => {
  const { textosObras } = await cargar();
  const cargas = [{ sed: 'SECA001', alimentador: 'CA191', sola: true }, { sed: 'B1', alimentador: 'CHN192', sola: false }];
  const t = textosObras(cargas, ['CA191', 'CHN192']);
  assert.equal(t.titulo, 'Obras en «Con proyecto» con las cargas nuevas');
  assert.equal(t.boton, 'Proponer obras automáticamente');
  assert.match(t.ayuda, /SECA001 \(CA191\), B1 \(CHN192, en bloque\)/);
  assert.match(t.ayuda, /hasta 3 alternativas/);
  // Solo cuentan las de los alimentadores marcados; sin ninguna, es el estado actual, como antes.
  const sin = textosObras(cargas, ['PA297']);
  assert.equal(sin.titulo, 'Obras para el estado actual');
  assert.equal(sin.boton, 'Corregir el estado actual en «Con proyecto»');
});

test('018:RF-19: 4 y 5 trabajan con el proyecto elegido en su desplegable, o con el del paso 1', async () => {
  const { proyectoDeEstudio } = await cargar();
  assert.deepEqual(proyectoDeEstudio('', [], 'P1', ['A']), { proyecto: 'P1', feeders: ['A'], propio: false });
  assert.deepEqual(proyectoDeEstudio('P1', ['X'], 'P1', ['A']), { proyecto: 'P1', feeders: ['A'], propio: false });
  assert.deepEqual(proyectoDeEstudio('OTRO', ['B', 'C'], 'P1', ['A']), { proyecto: 'OTRO', feeders: ['B', 'C'], propio: true });
  assert.deepEqual(proyectoDeEstudio('OTRO', [], '', []), { proyecto: 'OTRO', feeders: [], propio: true });
});

// 086:RF-141: el 2026-11-27, con SEN0001 de LL202 simulada, el operador no encontraba cómo proponer las obras: la
// simulación tapaba el bloque de obras automáticas y su resultado no trae la escalera.
test('086:RF-141 una simulación no tapa las obras automáticas y el paso 4 dice dónde están o qué falta', async () => {
  const { porQueSinObrasAutomaticas } = await cargar();
  const { readFileSync } = await import('node:fs');
  const pantalla = readFileSync(fileURLToPath(new URL('../src/features/powerfactory/CargasTab.tsx', import.meta.url)), 'utf8');
  assert.match(pantalla, /proyectoDeCargas: resultado && resultado\.informe\.modo !== 'simular'/,
    'una simulación sigue tapando el bloque de obras automáticas');
  assert.match(pantalla, /Ir a «Proponer obras automáticamente»/);
  assert.equal(porQueSinObrasAutomaticas(BASE), null);
  assert.match(porQueSinObrasAutomaticas({ ...BASE, proyecto: null }), /paso 1/);
  assert.match(porQueSinObrasAutomaticas({ ...BASE, alimentadores: [] }), /paso 2/);
  assert.match(porQueSinObrasAutomaticas({ ...BASE, calibrado: false }), /calibre/);
  assert.match(porQueSinObrasAutomaticas({ ...BASE, proyectoDeCargas: 'NJA292' }), /Proponer obras en escalera/);
});

// 042:RF-113: el botón de las obras automáticas en color, y la casilla del CAPEX nombra el libro vigente.
test('042:RF-113 la casilla del CAPEX nombra el vigente y el botón de las obras va en color', async () => {
  const { readFileSync } = await import('node:fs');
  const pantalla = readFileSync(fileURLToPath(new URL('../src/features/powerfactory/CargasTab.tsx', import.meta.url)), 'utf8');
  assert.match(pantalla, /placeholder=\{textoCapexVigente\(capexVigente\)\}/);
  assert.doesNotMatch(pantalla, /placeholder="ruta del \.xlsx en este equipo"/);
  assert.match(pantalla, /<button className="btn btn-sm btn-primary" disabled=\{ocupado \|\| \(tipoCambio\.trim\(\) !== '' && !tcValido\)\}\r?\n\s+onClick=\{\(\) => onCorregir/);
  const salida = await build({ entryPoints: [fileURLToPath(new URL('../src/features/powerfactory/capexVigente.ts', import.meta.url))],
    bundle: true, write: false, format: 'esm', platform: 'node' });
  const { textoCapexVigente } = await import(`data:text/javascript;base64,${Buffer.from(salida.outputFiles[0].contents).toString('base64')}`);
  assert.equal(textoCapexVigente({ ruta: 'X/libro.xlsx', nombre: 'libro.xlsx', origen: 'referencias' }),
    'en blanco: libro.xlsx (de las referencias)');
  assert.match(textoCapexVigente(null), /no hay uno/);
});

// 042:RF-114: el 2026-11-27 los bancos del déficit previo de LL202 estaban medidos y no había cómo aplicarlos.
test('042:RF-114 las obras aparte se aplican con su botón y su columna dice «Recomendada»', async () => {
  const { readFileSync } = await import('node:fs');
  const pantalla = readFileSync(fileURLToPath(new URL('../src/features/powerfactory/CargasTab.tsx', import.meta.url)), 'utf8');
  const cliente = readFileSync(fileURLToPath(new URL('../src/api/client.ts', import.meta.url)), 'utf8');
  assert.match(cliente, /obrasAparte: .*\r?\n.*\/pf\/obras\/aparte/);
  assert.match(pantalla, /<TablaAlternativas lista=\{d\.alternativas\} moneda=\{moneda\} onAplicar=\{onAplicar\}/);
  assert.match(pantalla, /onAplicar \? <><th>Recomendada<\/th>/);
  assert.match(pantalla, /Aplicar en «Con proyecto»/);
  assert.equal((pantalla.match(/onAplicarAparte=\{\(feeder, nombre\) => startJob\(\(\) => api\.obrasAparte/g) ?? []).length, 2,
    'los dos sitios que pintan «Con proyecto» llevan el botón');
});

// 017:RF-156: el cuadro de pérdidas por alimentador y caso, en «Estudios», con cargabilidad y caída en MT.
test('017:RF-156 «Estudios» muestra el cuadro de pérdidas con el tramo más cargado y la caída en MT', async () => {
  const { readFileSync } = await import('node:fs');
  const estudios = readFileSync(fileURLToPath(new URL('../src/features/powerfactory/EstudiosPF.tsx', import.meta.url)), 'utf8');
  assert.match(estudios, /<CuadroDePerdidas project=\{project\} \/>/);
  assert.match(estudios, /api\.cuadroPerdidas\(ws\.id, todos \? '' : project\)/);
  for (const col of ['Pérdidas</th>', 'Tramo más cargado', 'Cargabilidad</th>', 'Caída en MT</th>']) {
    assert.ok(estudios.includes(col), col);
  }
});
