import assert from 'node:assert/strict';
import test from 'node:test';
import { build } from 'esbuild';
import { fileURLToPath } from 'node:url';

const entry = fileURLToPath(new URL('../src/features/powerfactory/entradasEstudiosLogica.ts', import.meta.url));

async function cargar() {
  const salida = await build({ entryPoints: [entry], bundle: true, write: false, format: 'esm', platform: 'node' });
  return import(`data:text/javascript;base64,${Buffer.from(salida.outputFiles[0].contents).toString('base64')}`);
}

const PCC = 'Potencia e impedancia de cortocircuito de cada subestación de cabecera';
const PERFILES = 'Perfiles de carga horarios o curvas típicas por tipo de cliente';
const esquema = (clave, nombre) => ({ clave, nombre, titulo: clave, ayuda: '', estudios: [],
  columnas: [{ clave: 'a', titulo: 'A', unidad: '-', obligatoria: true, numero: false },
    { clave: 'b', titulo: 'B', unidad: 'MVA', obligatoria: false, numero: true }] });
const ESTADO = { project: 'P', esquemas: [esquema('impedancia', PCC), esquema('perfiles', PERFILES), esquema('espectros', 'Espectros')],
  guardadas: {}, borradores: {}, cumplidas: [] };

test('012:RF-80 cada entrada que falta sale una vez, con los estudios que la piden', async () => {
  const { entradasQueFaltan } = await cargar();
  const no = [{ clave: 'cortocircuito', nombre: 'Cortocircuito', falta: [PCC], motivo: 'faltan datos' },
    { clave: 'protecciones', nombre: 'Protecciones', falta: [PCC, 'curvas'], motivo: 'faltan datos' },
    { clave: 'cuasi_dinamica', nombre: 'Cuasi-dinámica', falta: [PERFILES], motivo: 'faltan datos' }];
  const lista = entradasQueFaltan(no, ESTADO);
  assert.deepEqual(lista.map((x) => x.esquema.clave), ['impedancia', 'perfiles']);
  assert.deepEqual(lista[0].estudios, ['Cortocircuito', 'Protecciones']);
  // Lo ya guardado sigue a la vista para poder reemplazarlo, aunque ningún estudio lo pida ya.
  const guardado = { ...ESTADO, guardadas: { espectros: { fichero: 'x.txt', confirmado: null, faltan: [], completa: true, filas: [] } } };
  assert.ok(entradasQueFaltan([], guardado).some((x) => x.esquema.clave === 'espectros' && x.guardada));
});

test('012:RF-80 los estudios con sus datos y sin ejecución se nombran aparte', async () => {
  const { conDatosSinEjecucion } = await cargar();
  const no = [{ clave: 'armonicos', nombre: 'Flujo armónico', falta: [], motivo: 'datos cargados; su ejecución…' },
    { clave: 'flujo_optimo', nombre: 'Flujo óptimo', falta: [], motivo: 'fuera de esta iteración' }];
  assert.deepEqual(conDatosSinEjecucion(no).map((e) => e.clave), ['armonicos']);
});

test('012:RF-75, RF-77 la tabla se edita sin mutar y marca las filas con error', async () => {
  const { editarCelda, quitarFila, filaVacia, filasConError, pagina, textoCelda } = await cargar();
  const filas = [{ a: 'X', b: 1 }, { a: 'Y', b: null }];
  const otra = editarCelda(filas, 1, 'b', '2,5');
  assert.equal(filas[1].b, null);
  assert.equal(otra[1].b, '2,5');
  assert.equal(editarCelda(filas, 0, 'a', '  ')[0].a, null);
  assert.deepEqual(quitarFila(filas, 0), [{ a: 'Y', b: null }]);
  assert.deepEqual(filaVacia(esquema('impedancia', PCC)), { a: null, b: null });
  assert.deepEqual([...filasConError(['Fila 2, «B»: falta', 'CA101: mezcla p.u. y kW'])], [1]);
  const muchas = Array.from({ length: 250 }, (_, i) => ({ a: String(i) }));
  const p = pagina(muchas, 9);
  assert.equal(p.paginas, 3);
  assert.equal(p.desde, 200);
  assert.equal(p.filas.length, 50);
  assert.equal(textoCelda(0), '0');
  assert.equal(textoCelda(null), '');
});
