import assert from 'node:assert/strict';
import test from 'node:test';
import { build } from 'esbuild';
import { createRequire } from 'node:module';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';

// Spec 111, T20 a T22 (RF-20 a RF-22): el espacio de ingeniería sin navegador. La selección enlazada entre el plano, la
// tabla, el inspector y los hallazgos; el hallazgo con su valor, umbral, norma (la del servidor), caso y motor; y el
// reparto de la pantalla, recordado por espacio y movido con el teclado. El recorrido en navegador real está en
// e2e/plano.spec.ts.
const FRONT = fileURLToPath(new URL('../', import.meta.url));
const PLANO = join(FRONT, 'src', 'features', 'plano');

let modulo;
async function cargar() {
  if (modulo) return modulo;
  const salida = await build({
    stdin: {
      contents: `
        import { createElement } from 'react';
        import { renderToStaticMarkup } from 'react-dom/server';
        import { InspectorElemento } from './src/features/plano/InspectorElemento';
        import { CapasResultados } from './src/features/plano/CapasResultados';
        export * as logica from './src/features/plano/logicaPlano';
        export { ENTRADA } from './src/features/plano/mensajesPlano';
        export const pintar = (c, props) => renderToStaticMarkup(createElement({ InspectorElemento, CapasResultados }[c], props));`,
      resolveDir: FRONT, loader: 'tsx',
    },
    bundle: true, write: false, format: 'cjs', platform: 'node', packages: 'external', jsx: 'automatic',
  });
  const m = { exports: {} };
  new Function('require', 'module', 'exports', salida.outputFiles[0].text)(createRequire(import.meta.url), m, m.exports);
  modulo = m.exports;
  return modulo;
}

const elementos = [
  { clase: 'tramo', codigo: 'T-1', alimentador: 'A1', detalle: 'N1 → N2',
    dato: { codigo: 'T-1', desde: 'N1', hasta: 'N2', tipo: 'AAAC', fases: 'ABC', longitud_m: 10, original: {}, deducido: [],
      calidad: 'ok', avisos: [], errores: [] } },
  { clase: 'barra', codigo: 'N1', alimentador: 'A1', detalle: '', dato: { codigo: 'N1', deducido: [], calidad: 'ok', avisos: [], errores: [] } },
  { clase: 'barra', codigo: 'N2', alimentador: 'A1', detalle: '', dato: { codigo: 'N2', deducido: [], calidad: 'ok', avisos: [], errores: [] } },
];

const NORMA = { clave: 'calidad.tension.tolerancia_ntcse', acto: 'DS 020-97-EM', articulo: 'num. 5.1.2 Tolerancias',
  cita: 'texto que da el servidor', estado: 'modificada', obligatoria: true };
const capas = () => ({
  pintable: true, motivo: '', mensajes: [], caso: 'Caso X', revision: 'r', motor: 'abierto', motor_texto: 'motor abierto (pandapower)',
  origen_umbral: 'por defecto', variacion: 'v'.repeat(16),
  capas: {
    tension: { leyenda: { magnitud: 'Tensión por barra', unidad: 'p.u.', umbral: { min: 0.95, max: 1.05 }, caso: 'Caso X',
      motor_texto: 'motor abierto (pandapower)', revision: 'r', motor: 'abierto', origen_umbral: 'por defecto' },
    elementos: [{ codigo: 'N2', valor: 0.9, banda: 'baja', motor: 'abierto',
      incumple: { texto: 'Tensión baja: 0,9 p.u.', icono: '!', valor: 0.9, umbral: 0.95, norma: NORMA } },
    { codigo: 'N1', valor: 1, banda: 'normal', motor: 'abierto', incumple: null }] },
    cargabilidad: { leyenda: { magnitud: 'Cargabilidad por tramo', unidad: '%', umbral: { max: 100 }, caso: 'Caso X',
      motor_texto: 'motor abierto (pandapower)', revision: 'r', motor: 'abierto', origen_umbral: 'por defecto' },
    elementos: [{ codigo: 'T-1', valor: 130, banda: 'sobrecarga', motor: 'abierto',
      incumple: { texto: 'Sobrecarga: 130 %', icono: '!', valor: 130, umbral: 100,
        norma: { criterio_empresa: 'perfil: estudios.cargabilidad_max_pct', origen: 'por defecto, 100 %' } } }] },
  },
});

function almacen() {
  const datos = new Map();
  return { getItem: (k) => (datos.has(k) ? datos.get(k) : null), setItem: (k, v) => datos.set(k, String(v)), datos };
}

test('111:RF-20 — una selección de cualquier vista se selecciona en todas y el plano la encuadra; null la quita', async () => {
  const { logica, ENTRADA } = await cargar();
  for (const origen of ['plano', 'tabla', 'inspector', 'hallazgo']) {
    const s = logica.seleccionEnlazada('T-1', elementos);
    assert.deepEqual(s.alPlano, { tipo: 'seleccionar', codigo: 'T-1' }, origen);
    assert.equal(s.elegido, 'T-1');
  }
  const fuera = logica.seleccionEnlazada('NO-EXISTE', elementos);
  assert.equal(fuera.alPlano, null, 'un código que no está no cambia la selección');
  assert.match(fuera.anuncio, /no está en el plano/);
  const quitar = logica.seleccionEnlazada(null, elementos);
  assert.deepEqual(quitar, { elegido: null, alPlano: { tipo: 'deseleccionar' }, anuncio: 'Selección quitada.' });
  assert.ok(ENTRADA.includes('deseleccionar'), 'la página del plano entiende «deseleccionar»');
});

test('111:RF-20 — la pestaña manda al plano lo que da la regla, también la selección que viene del plano, y Escape la quita', () => {
  const fuente = readFileSync(join(PLANO, 'PlanoRed.tsx'), 'utf8');
  assert.match(fuente, /m\?\.tipo === 'seleccionado'\) seleccionarRef\.current\(m\.codigo\)/);
  assert.match(fuente, /e\.key === 'Escape' && elegido && !campo/);
  assert.match(fuente, /seleccionEnlazada\(codigo, elementos\)/);
});

test('111:RF-21 — cada hallazgo con su valor, umbral, norma del servidor (o lo que falta), caso y motor', async () => {
  const { logica, pintar } = await cargar();
  const h = logica.hallazgosDe(capas());
  assert.deepEqual(h.map((x) => [x.codigo, x.capa]), [['N2', 'tension'], ['T-1', 'cargabilidad']]);
  assert.equal(h[0].norma.acto, 'DS 020-97-EM');
  assert.equal(h[0].caso, 'Caso X');
  assert.equal(h[0].motor, 'motor abierto (pandapower)');
  assert.deepEqual(logica.hallazgosDe({ ...capas(), pintable: false }), []);

  const elemento = elementos[2];
  const html = pintar('InspectorElemento', { elemento, hallazgo: h[0], onElegir: () => {}, onQuitar: () => {} });
  for (const t of ['Hallazgo', 'Tensión baja: 0,9 p.u.', 'DS 020-97-EM', 'num. 5.1.2 Tolerancias', 'texto que da el servidor', 'Caso X',
    'motor abierto (pandapower)', 'Quitar la selección']) assert.ok(html.includes(t), `${t} en el inspector`);
  const criterio = pintar('InspectorElemento', { elemento: elementos[0], hallazgo: h[1] });
  assert.ok(criterio.includes('Criterio de la empresa, no norma') && criterio.includes('perfil: estudios.cargabilidad_max_pct')
    && criterio.includes('por defecto, 100 %'), 'la cargabilidad, como criterio de la empresa con su origen');
  const sinNorma = pintar('InspectorElemento', { elemento: elementos[0], hallazgo: { ...h[1], norma: { falta: 'La biblioteca no trae la regla.' } } });
  assert.ok(sinNorma.includes('La biblioteca no trae la regla.'), 'sin norma, el motivo que da el servidor');
  // Ninguna cita escrita en el frontend: el inspector no nombra ninguna norma por su cuenta.
  for (const f of ['InspectorElemento.tsx', 'CapasResultados.tsx', 'PlanoRed.tsx', 'logicaPlano.ts', 'textosPlano.ts']) {
    const texto = readFileSync(join(PLANO, f), 'utf8');
    assert.doesNotMatch(texto, /\b(DS|RM|RCD|NTCSE|CNE)\s?\d/, `${f} no escribe ninguna norma`);
  }
});

test('111:RF-21 — el hallazgo de los resultados se abre con su capa', async () => {
  const { pintar } = await cargar();
  const html = pintar('CapasResultados', { capas: capas(), onHallazgo: () => {} });
  assert.ok(html.includes('N2') && html.includes('T-1'));
  const fuente = readFileSync(join(PLANO, 'CapasResultados.tsx'), 'utf8');
  assert.match(fuente, /onHallazgo\(e\.codigo, clave\)/);
});

test('111:RF-22 — el reparto se recuerda por espacio, acotado, y los separadores se mueven con las flechas, Inicio y Fin', async () => {
  const { logica } = await cargar();
  const a = almacen();
  assert.deepEqual(logica.panelesRecordados(a, 'ws1'), logica.PANELES_POR_DEFECTO);
  logica.recordarPaneles(a, 'ws1', { plano: 95, tabla: 10 });
  assert.deepEqual(logica.panelesRecordados(a, 'ws1'), { plano: 80, tabla: 25 }, 'acotado entre 25 y 80');
  assert.deepEqual(logica.panelesRecordados(a, 'ws2'), logica.PANELES_POR_DEFECTO, 'cada espacio el suyo');
  a.setItem('convertersmartgrid.plano.paneles.ws3', 'no es json');
  assert.deepEqual(logica.panelesRecordados(a, 'ws3'), logica.PANELES_POR_DEFECTO);
  assert.deepEqual(logica.panelesRecordados(null, 'ws1'), logica.PANELES_POR_DEFECTO, 'sin almacenamiento');
  const lanza = { getItem: () => { throw new Error('privado'); }, setItem: () => { throw new Error('privado'); } };
  assert.deepEqual(logica.panelesRecordados(lanza, 'ws1'), logica.PANELES_POR_DEFECTO);
  logica.recordarPaneles(lanza, 'ws1', { plano: 50, tabla: 50 });
  assert.equal(logica.ajustarPanel(60, 'ArrowRight', 'vertical'), 65);
  assert.equal(logica.ajustarPanel(60, 'ArrowLeft', 'vertical'), 55);
  assert.equal(logica.ajustarPanel(60, 'ArrowDown', 'horizontal'), 65);
  assert.equal(logica.ajustarPanel(60, 'ArrowUp', 'horizontal'), 55);
  assert.equal(logica.ajustarPanel(60, 'Home', 'vertical'), 25);
  assert.equal(logica.ajustarPanel(60, 'End', 'horizontal'), 80);
  assert.equal(logica.ajustarPanel(80, 'ArrowRight', 'vertical'), 80);
  assert.equal(logica.ajustarPanel(60, 'ArrowDown', 'vertical'), null, 'en vertical, abajo no mueve');
});

test('111:RF-22 — una sola pantalla con el plano, la tabla y el inspector, con separadores accesibles y sin quitar ninguna vista', () => {
  const fuente = readFileSync(join(PLANO, 'PlanoRed.tsx'), 'utf8');
  for (const clase of ['plano-espacio', 'plano-espacio-mapa', 'plano-espacio-tabla', 'plano-espacio-inspector']) {
    assert.ok(fuente.includes(`className="${clase}"`), clase);
  }
  assert.equal((fuente.match(/role="separator"/g) ?? []).length, 2);
  assert.match(fuente, /aria-orientation="vertical"/);
  assert.match(fuente, /aria-orientation="horizontal"/);
  assert.match(fuente, /aria-valuenow=\{paneles\.plano\}/);
  for (const vista of ['<TablaElementos', '<InspectorElemento', 'className="map-frame"', '<CapasResultados', '<Comparacion',
    '<EdicionesPlano', '<FormulariosEdicion']) assert.ok(fuente.includes(vista), `${vista} sigue en la pestaña`);
  const css = readFileSync(join(FRONT, 'src', 'shared', 'styles.css'), 'utf8');
  assert.match(css, /\.plano-espacio \{ display: grid; grid-template-columns: var\(--ancho-plano/);
  assert.match(css, /@media \(max-width: 900px\)[\s\S]*\.plano-espacio \{ grid-template-columns: 1fr/);
});
