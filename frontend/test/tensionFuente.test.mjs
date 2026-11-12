import assert from 'node:assert/strict';
import test from 'node:test';
import { build } from 'esbuild';
import { fileURLToPath } from 'node:url';

const entry = fileURLToPath(new URL('../src/features/powerfactory/tensionFuente.ts', import.meta.url));

async function cargar() {
  const salida = await build({
    entryPoints: [entry], bundle: true, write: false, format: 'esm', platform: 'node',
  });
  const codigo = Buffer.from(salida.outputFiles[0].contents).toString('base64');
  return import(`data:text/javascript;base64,${codigo}`);
}

const PA217 = {
  origen: 'medida', pu: 23.53627 / 22.9, kv: 23.53627, nominal_kv: 22.9,
  fecha: '2026-03-03 10:00:00', medidor: 'L-PA235', columna: 'Vll avg mean',
};

test('021:RF-79: el campo se rellena con la medida en pu y dice cuándo y dónde se midió', async () => {
  const { tensionInicial, notaDeLaMedida } = await cargar();
  assert.equal(tensionInicial(PA217), '1.0278');
  const nota = notaDeLaMedida(PA217);
  assert.match(nota, /^medida a las 2026-03-03 10:00:00 en L-PA235/);
  assert.match(nota, /23[,.]536 kV/);
  assert.equal(tensionInicial(null), '');
  assert.equal(notaDeLaMedida(null), '');
});

test('021:RF-85: con la barra de su SET, la nota nombra la barra', async () => {
  const { notaDeLaMedida } = await cargar();
  const nota = notaDeLaMedida({ ...PA217, barra: 'la barra SET PA 22,9 kV (B-PA2T2)' });
  assert.match(nota, /en la barra SET PA 22,9 kV \(B-PA2T2\)/);
});

test('021:RF-82: fuera de 0,90 a 1,10 pu no se rellena y se dice que se confirme', async () => {
  const { tensionInicial, notaDeLaMedida } = await cargar();
  const alta = { ...PA217, pu: 1.12 };
  assert.equal(tensionInicial(alta), '');
  assert.match(notaDeLaMedida(alta), /fuera de 0,90 a 1,10; no se aplica sola/);
});

test('021:RF-76: sin nominal, el campo queda vacío y dice que DIgSILENT la pasa a pu', async () => {
  const { tensionInicial, notaDeLaMedida } = await cargar();
  const sinNominal = { ...PA217, pu: null, nominal_kv: null };
  assert.equal(tensionInicial(sinNominal), '');
  assert.match(notaDeLaMedida(sinNominal), /DIgSILENT la pasa a pu con la de la barra de su fuente/);
});

test('021:RF-80: solo va a la API lo que tocó el operador; vacío es dejar la fuente como está', async () => {
  const { tensionesTocadas, tensionValida, puEscrito } = await cargar();
  assert.deepEqual(tensionesTocadas({ PA217: '1,05', AL209: '' }), { PA217: 1.05, AL209: null });
  assert.deepEqual(tensionesTocadas({}), {});
  assert.equal(puEscrito(' '), null);
  assert.equal(tensionValida('1,02'), true);
  assert.equal(tensionValida(''), true);
  assert.equal(tensionValida('1,2'), false);
  assert.equal(tensionValida('abc'), false);
});
