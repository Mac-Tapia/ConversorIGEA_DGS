import assert from 'node:assert/strict';
import test from 'node:test';
import { build } from 'esbuild';
import { fileURLToPath } from 'node:url';

const entry = fileURLToPath(new URL('../src/features/powerfactory/ubicacionCarga.ts', import.meta.url));

async function cargar() {
  const salida = await build({
    entryPoints: [entry], bundle: true, write: false, format: 'esm', platform: 'node',
  });
  const codigo = Buffer.from(salida.outputFiles[0].contents).toString('base64');
  return import(`data:text/javascript;base64,${codigo}`);
}

// Como SE0001 de PA217 (2026-11-12): Y con un dígito de menos, propuesta la Y entera.
const PROPUESTA = { campo: 'CoordY', texto: 'Y = 8 476 517', cambios: { CoordY: 8476517 }, nodo: '18943', distancia_m: 0 };
const RECHAZO = {
  sed: 'SE0001', hoja: 'formulario', alimentador: 'PA217', nodo: '18680', distancia_m: 7990000, radio_m: 8745,
  tope_m: 8745, tope_del_perfil: false, fuente: 'red convertida de PA217', fuera: true,
  mensaje: 'SE0001: el punto (X 374 207,8; Y 476 517) queda a 7 990 km de PA217; ¿quiso decir Y = 8 476 517?',
  propuestas: [PROPUESTA],
};

test('004:RF-80: el rechazo de la carga del formulario va junto al formulario; el del libro, no', async () => {
  const { medidaDelFormulario } = await cargar();
  const conRechazo = medidaDelFormulario({ nuevas: [], ubicaciones_rechazadas: [RECHAZO] });
  assert.equal(conRechazo.rechazo.mensaje, RECHAZO.mensaje);
  assert.equal(conRechazo.ubicacion, null);
  const delLibro = medidaDelFormulario({ nuevas: [], ubicaciones_rechazadas: [{ ...RECHAZO, hoja: 'Hoja1' }] });
  assert.equal(delLibro.rechazo, null);
  const buena = { ...RECHAZO, fuera: false, distancia_m: 12, nodo: '18943' };
  const sinRechazo = medidaDelFormulario({ nuevas: [{ sed: 'SE0001', hoja: 'formulario', ubicacion: buena }] });
  assert.equal(sinRechazo.rechazo, null);
  assert.equal(sinRechazo.ubicacion.nodo, '18943');
});

test('004:RF-74; 004:RF-80: usar la propuesta copia solo sus campos, como texto', async () => {
  const { camposDePropuesta } = await cargar();
  assert.deepEqual(camposDePropuesta(PROPUESTA), { CoordY: '8476517' });
  assert.deepEqual(camposDePropuesta({ ...PROPUESTA, cambios: { CoordX: 8476517, CoordY: 374207.8 } }),
    { CoordX: '8476517', CoordY: '374207.8' });
});

test('004:RF-72; 004:RF-78; 004:RF-80: tras simular o aplicar, el nodo, la línea y lo que reemplaza', async () => {
  const { textoDeLaConexion, aDelNodo } = await cargar();
  assert.match(aDelNodo({ distancia_m: 12, nodo: '18943' }), /^a 12 m del nodo 18943$/);
  const texto = textoDeLaConexion({
    ubicacion: { ...RECHAZO, fuera: false, distancia_m: 12, nodo: '18943' }, longitud_linea_m: 40,
    reemplaza: { variaciones: ['Carga_SE0001_PA217_20261112_154934'], cambios: ['su ubicación'] },
  });
  assert.match(texto, /a 12 m del nodo 18943/);
  assert.match(texto, /línea de conexión de 40 m/);
  assert.match(texto, /reemplaza la carga anterior \(cambió su ubicación\)/);
  assert.equal(textoDeLaConexion({}), '');
});
