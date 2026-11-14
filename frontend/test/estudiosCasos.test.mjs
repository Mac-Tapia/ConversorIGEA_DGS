import assert from 'node:assert/strict';
import test from 'node:test';
import { build } from 'esbuild';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';

/**
 * 4.2 · Estudios en cualquier caso de DIgSILENT (011:RF-130, RF-131, RF-135) y su resumen ejecutivo (017:RF-142),
 * sin servidor ni DIgSILENT. Orden del usuario del 2026-11-13: «yo debería hacer esos estudios en cualquier proyecto
 * físico existente en DIgSILENT, con cualquier caso»; antes el botón se apagaba sin calibración.
 */
async function cargar() {
  const salida = await build({ stdin: { contents: `
    import { createElement } from 'react';
    import { renderToStaticMarkup } from 'react-dom/server';
    import { SelectorCasos, ResumenEjecutivo, casosPorDefecto, puedePrepararEstudios } from './src/features/powerfactory/EstudiosPF';
    export { casosPorDefecto, puedePrepararEstudios };
    export const selector = (props) => renderToStaticMarkup(createElement(SelectorCasos, { onCambio: () => undefined, ...props }));
    export const resumen = (props) => renderToStaticMarkup(createElement(ResumenEjecutivo, {
      onPedir: () => undefined, enlace: (f) => '/files/' + f, ...props }));`,
    resolveDir: fileURLToPath(new URL('..', import.meta.url)), loader: 'tsx' },
    bundle: true, write: false, format: 'cjs', platform: 'node', jsx: 'automatic' });
  const modulo = { exports: {} };
  new Function('require', 'module', 'exports', salida.outputFiles[0].text)(createRequire(import.meta.url), modulo, modulo.exports);
  return modulo.exports;
}

/** Casos sorteados del operador y, a veces, los del conversor con o sin año: ningún nombre ni tamaño fijo. */
function sorteo(semilla) {
  let s = semilla;
  const azar = () => { s = (s * 1103515245 + 12345) % 2147483648; return s / 2147483648; };
  const propios = Array.from({ length: 1 + Math.floor(azar() * 5) }, (_, i) => `Caso ${Math.floor(azar() * 900) + 100}-${i}`);
  const anio = azar() < 0.5 ? '' : ` ${2020 + Math.floor(azar() * 10)}`;
  const conversor = ['Sin proyecto', 'Cargas nuevas', 'Con proyecto'].filter(() => azar() < 0.7).map((n) => n + anio);
  return { propios, conversor, todos: [...propios, ...conversor].sort() };
}

test('011:RF-135: por defecto se marcan los casos del conversor que tenga el proyecto, ninguno de los demás', async () => {
  const { casosPorDefecto } = await cargar();
  for (const semilla of [3, 17, 29, 101]) {
    const { conversor, todos } = sorteo(semilla);
    assert.deepEqual(casosPorDefecto(todos).sort(), [...conversor].sort());
  }
  assert.deepEqual(casosPorDefecto([]), []);
});

test('011:RF-135: el selector ofrece cada caso del proyecto y marca los elegidos', async () => {
  const { selector } = await cargar();
  for (const semilla of [5, 41]) {
    const { propios, todos } = sorteo(semilla);
    const html = selector({ casos: todos, elegidos: [propios[0]] });
    for (const c of todos) assert.match(html, new RegExp(`>${c}<`));
    assert.equal((html.match(/aria-pressed="true"/g) ?? []).length, 1);
    assert.match(html, new RegExp(`1 de ${todos.length}`));
  }
  // Una lectura anterior sin casos: se dice cómo obtenerlos, sin bloquear.
  assert.match(selector({ casos: [], elegidos: [] }), /vuelva a leerlos/);
});

test('011:RF-131: sin calibración se puede preparar el estudio; solo faltan estudios, alimentadores o DIgSILENT libre', async () => {
  const { puedePrepararEstudios } = await cargar();
  assert.equal(puedePrepararEstudios({ pfBusy: false, estudios: 1, alimentadores: 1 }), true);
  assert.equal(puedePrepararEstudios({ pfBusy: true, estudios: 1, alimentadores: 1 }), false);
  assert.equal(puedePrepararEstudios({ pfBusy: false, estudios: 0, alimentadores: 1 }), false);
  assert.equal(puedePrepararEstudios({ pfBusy: false, estudios: 1, alimentadores: 0 }), false);
});

test('017:RF-142: el botón del resumen ejecutivo y sus ficheros con sus conclusiones', async () => {
  const { resumen } = await cargar();
  assert.match(resumen({ token: 'abc', resumen: null }), /Resumen ejecutivo/);
  assert.match(resumen({ token: undefined, resumen: null }), /disabled/);
  const html = resumen({ token: 'abc', resumen: { token: 'abc', project: 'P', docx: 'r.docx', xlsx: 'r.xlsx', huecos: [],
    conclusiones: ['«X»: 2 violación(es) de los límites en 1 alimentador(es) (F1).'] } });
  assert.match(html, /href="\/files\/r\.docx"/);
  assert.match(html, /href="\/files\/r\.xlsx"/);
  assert.match(html, /2 violación\(es\)/);
});
