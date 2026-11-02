import assert from 'node:assert/strict';
import test from 'node:test';
import { build } from 'esbuild';

const entry = new URL('../src/solicitudLeida.ts', import.meta.url).pathname.replace(/^\/(.:\/)/, '$1');

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
