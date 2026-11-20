import assert from 'node:assert/strict';
import test from 'node:test';
import { build } from 'esbuild';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';

// 026:RF-49 — lo aprendido del operador llega al operador: el panel enseña su evaluación y sus puertas, el botón de
// ponerlo en uso solo aparece si las pasó (con su previa antes de confirmar), y la lista del proyecto entero enseña la
// propuesta aprendida con su motivo. Datos sintéticos.

async function cargar() {
  const salida = await build({ stdin: { contents: `
    import { createElement } from 'react';
    import { renderToStaticMarkup } from 'react-dom/server';
    import * as A from './src/features/asistente/Asistente';
    export const aprendido = (props) => A.VistaAprendido
      ? renderToStaticMarkup(createElement(A.VistaAprendido, { onPrevia() {}, onPromover() {}, previa: null, ...props }))
      : null;
    export const propuesta = (p) => A.VistaPropuestaAprendida
      ? renderToStaticMarkup(createElement(A.VistaPropuestaAprendida, { propuesta: p })) : null;`,
    resolveDir: fileURLToPath(new URL('..', import.meta.url)), loader: 'tsx' },
    bundle: true, write: false, format: 'cjs', platform: 'node', jsx: 'automatic' });
  const modulo = { exports: {} };
  new Function('require', 'module', 'exports', salida.outputFiles[0].text)(createRequire(import.meta.url), modulo, modulo.exports);
  return modulo.exports;
}

const candidato = (superadas) => ({
  tabla: [['txt', 'nada', 'convert'], ['txt', 'convert hecho', 'pf_calibrar']],
  evaluacion: { casos: superadas ? 12 : 2, aciertos: superadas ? 12 : 2, acierto: 1, aprendidas_de: 16 },
  puertas: { superadas, fallos: superadas ? [] : ['faltan casos de evaluación: 2 de 5'], acierto_minimo: 0.8, casos_minimos: 5 },
  huella: 'h'.repeat(64), promovido: false, intacto: true, promovido_por: null, promovido_en: null });

test('026:RF-49 el panel de lo aprendido enseña su evaluación y el botón solo con las puertas pasadas', async () => {
  const { aprendido } = await cargar();
  const pasa = aprendido({ estado: { candidato: candidato(true), en_uso: null, se_puede_promover: true, motivo: '' } });
  assert.ok(pasa, 'falta VistaAprendido en Asistente.tsx: lo aprendido no llega al operador');
  assert.ok(pasa.includes('Acierta 12 de 12 casos que no vio'), pasa);
  assert.ok(pasa.includes('pasa sus puertas') && pasa.includes('tras convert hecho: pf_calibrar'), pasa);
  assert.ok(pasa.includes('Revisar para ponerlo en uso'), 'con las puertas pasadas se ofrece revisar para promover');
  assert.ok(!pasa.includes('Confirmar y poner en uso'), 'sin la previa no se confirma');
  const motivo = 'No pasó sus puertas: faltan casos de evaluación: 2 de 5';
  const no = aprendido({ estado: { candidato: candidato(false), en_uso: null, se_puede_promover: false, motivo } });
  assert.ok(no.includes(motivo), 'sin puertas dice por qué');
  assert.ok(!no.includes('Revisar para ponerlo en uso') && !no.includes('Confirmar'), 'sin puertas no hay botón');
  const previa = { candidato: candidato(true), en_uso: null, se_puede_promover: true, motivo: '', confirmacion: 't' };
  const conPrevia = aprendido({ estado: previa, previa });
  assert.ok(conPrevia.includes('Confirmar y poner en uso') && conPrevia.includes('2 propuestas'), conPrevia);
  assert.ok(!/\(s\)|RF-/.test(pasa + no + conPrevia), 'texto sin «(s)» ni requisitos');
});

test('026:RF-49 la lista del proyecto enseña la propuesta aprendida con su motivo', async () => {
  const { propuesta } = await cargar();
  const html = propuesta({ accion: 'pf_calibrar', confirma_el_operador: true,
    motivo: 'el operador lo lanzó en este contexto; aprendido y evaluado con 12 casos que no vio (acierto 1.0)' });
  assert.ok(html, 'falta VistaPropuestaAprendida en Asistente.tsx: la lista no enseña lo aprendido');
  assert.ok(html.includes('pf_calibrar') && html.includes('evaluado con 12 casos'), html);
  assert.ok(html.includes('se confirma'), 'la propuesta aprendida no se lanza sola');
});
