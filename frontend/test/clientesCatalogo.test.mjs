import assert from 'node:assert/strict';
import test from 'node:test';
import { build } from 'esbuild';

const entry = new URL('../src/clientesCatalogo.ts', import.meta.url).pathname.replace(/^\/(.:\/)/, '$1');

async function cargar() {
  const salida = await build({
    entryPoints: [entry], bundle: true, write: false, format: 'esm', platform: 'node',
  });
  const codigo = Buffer.from(salida.outputFiles[0].contents).toString('base64');
  return import(`data:text/javascript;base64,${codigo}`);
}

test('un libro heredado sigue listo sin catálogo mensual', async () => {
  const { estadoCatalogoClientes } = await cargar();
  assert.deepEqual(estadoCatalogoClientes({
    name: 'clientes.xlsx', origin: 'upload', source_kind: 'file', vigente: true,
    catalogo: [{ nombre: 'clientes.xlsx', mes: null, origen_mes: 'sin_mes', activo: false, avisos: [] }],
  }), {
    esCatalogo: false, activos: 1, listoParaCruzar: true, motivo: '',
  });
});

test('una carpeta solo queda lista con índice vigente y un mes activo', async () => {
  const { estadoCatalogoClientes } = await cargar();
  const uno = { name: 'clientes', origin: 'server', source_kind: 'folder', vigente: true, catalogo: [
    { nombre: '0126.xlsx', mes: '2026-01', origen_mes: 'nombre', activo: true, avisos: [] },
  ] };
  assert.equal(estadoCatalogoClientes(uno).listoParaCruzar, true);

  const varios = { ...uno, catalogo: [...uno.catalogo, {
    nombre: '0226.xlsx', mes: '2026-02', origen_mes: 'nombre', activo: true, avisos: [],
  }] };
  assert.deepEqual(estadoCatalogoClientes(varios), {
    esCatalogo: true, activos: 2, listoParaCruzar: false,
    motivo: 'Hay 2 meses activos; elija un mes antes de cruzar.',
  });

  assert.deepEqual(estadoCatalogoClientes({ ...uno, vigente: false }), {
    esCatalogo: true, activos: 1, listoParaCruzar: false,
    motivo: 'Actualice el índice antes de cruzar.',
  });
});
