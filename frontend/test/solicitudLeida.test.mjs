import assert from 'node:assert/strict';
import test from 'node:test';
import { build } from 'esbuild';
import { fileURLToPath } from 'node:url';

// 065:RF-9: `URL.pathname` deja «%20» y la prueba fallaba en una ruta con espacios.
const entry = fileURLToPath(new URL('../src/features/powerfactory/solicitudLeida.ts', import.meta.url));

async function cargar() {
  const salida = await build({
    entryPoints: [entry], bundle: true, write: false, format: 'esm', platform: 'node',
  });
  const codigo = Buffer.from(salida.outputFiles[0].contents).toString('base64');
  return import(`data:text/javascript;base64,${codigo}`);
}

test('063:RF-20 las fechas de varios documentos leídos de uno en uno se acumulan', async () => {
  const { acumularLeidos } = await cargar();
  let lista = acumularLeidos([], 'carta.pdf', [{ valor: '2026-10-22', fichero: 'carta.pdf' }]);
  lista = acumularLeidos(lista, 'ficha.pdf', [{ valor: '2025-11-04', fichero: 'ficha.pdf' }]);
  assert.deepEqual(lista.map((x) => x.fichero), ['carta.pdf', 'ficha.pdf']);
  // Releer un documento no repite sus filas, y uno sin fecha no borra las de los demás.
  lista = acumularLeidos(lista, 'carta.pdf', [{ valor: '2026-10-23', fichero: 'carta.pdf' }]);
  assert.deepEqual(lista.map((x) => x.valor).sort(), ['2025-11-04', '2026-10-23']);
  assert.equal(acumularLeidos(lista, 'otro.pdf', undefined).length, 2);
});

test('063:RF-19 avisa solo del alimentador de los PDF que no es el de la carga', async () => {
  const { alimentadoresDistintos } = await cargar();
  const leidos = [{ valor: 'AB123', fichero: 'ficha.pdf' }, { valor: ' cd456 ', fichero: 'carta.pdf' }];
  assert.deepEqual(alimentadoresDistintos(leidos, 'CD456').map((x) => x.fichero), ['ficha.pdf']);
  assert.deepEqual(alimentadoresDistintos(leidos, null), []);
  assert.deepEqual(alimentadoresDistintos([], 'CD456'), []);
});

test('063:RF-49 el cliente de otra carga se detecta y el código no afirma nada', async () => {
  const { clienteAjeno } = await cargar();
  assert.equal(clienteAjeno("AMPC INKA'S BERRIES S.A.C.", 'Minera Santa María S.A.C.'), true);
  assert.equal(clienteAjeno("AMPC INKA'S BERRIES S.A.C.", 'Incas Berries S.A.C.'), false);
  assert.equal(clienteAjeno('SN1', 'Minera Santa María S.A.C.'), false);
  assert.equal(clienteAjeno("AMPC INKA'S BERRIES S.A.C.", ''), false);
});

test('063:RF-48 elegir otra carga o ninguna no hereda; la primera elección conserva lo leído', async () => {
  const { esOtraCarga } = await cargar();
  assert.equal(esOtraCarga('SM218|A', 'SM218|B'), true);
  assert.equal(esOtraCarga('SM218|A', ''), true);
  assert.equal(esOtraCarga('', 'SM218|A'), false, '017:RF-136: la carta llega antes que la carga');
  assert.equal(esOtraCarga('SM218|A', 'SM218|A'), false);
});

test('063:RF-51 la carta sustituye la potencia propuesta por la carga, no la escrita', async () => {
  const { esPotenciaPropuesta } = await cargar();
  assert.equal(esPotenciaPropuesta('1100', 1100), true);
  assert.equal(esPotenciaPropuesta('1500', 1100), false, 'la escribió el operador');
  assert.equal(esPotenciaPropuesta('1100', null), false);
});

test('063:RF-52 el incremento que no cuadra con la carga del modelo se dice', async () => {
  const { incrementoNoCuadra } = await cargar();
  assert.equal(incrementoNoCuadra(200, 1100), true);
  assert.equal(incrementoNoCuadra(1100, 1100), false);
  assert.equal(incrementoNoCuadra(1100.5, 1100), false);
  assert.equal(incrementoNoCuadra(null, 1100), false);
  assert.equal(incrementoNoCuadra(200, null), false);
});

test('017:RF-91 la carga elegida rellena cliente, ubicación, SET, tensión y UTM sin pisar lo escrito', async () => {
  const { propuestaDeCarga } = await cargar();
  const sol = { cliente: '', ubicacion: '', potencia_kw: '', set_nombre: 'SET escrita', tension_kv: '',
    fecha_solicitud: '' };
  const punto = { pcc_mva: '', utm_x: '', utm_y: '' };
  const carga = { kw: 1206, cliente: 'TierraLarga', utm_x: 388631, utm_y: 8503377, set_nombre: 'SET 21 El Carmen',
    tension_kv: 10 };
  const r = propuestaDeCarga(sol, punto, carga);
  assert.equal(r.cambia, true);
  assert.equal(r.sol.cliente, 'TierraLarga');
  assert.equal(r.sol.ubicacion, 'UTM 388631 E, 8503377 N');
  assert.equal(r.sol.tension_kv, '10');
  assert.equal(r.sol.potencia_kw, '1206');
  assert.equal(r.sol.set_nombre, 'SET escrita');           // lo del operador no se pisa
  assert.equal(r.sol.fecha_solicitud, '');                 // la fecha de la carta no se inventa
  assert.deepEqual([r.punto.utm_x, r.punto.utm_y], ['388631', '8503377']);
  // Sin datos de la carga, nada cambia; con todo ya lleno, tampoco.
  assert.equal(propuestaDeCarga(sol, punto, null).cambia, false);
  assert.equal(propuestaDeCarga(r.sol, r.punto, carga).cambia, false);
});
