import assert from 'node:assert/strict';
import test from 'node:test';
import { build } from 'esbuild';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';

async function cargar() {
  const salida = await build({ stdin: { contents: `
    import { createElement } from 'react';
    import { renderToStaticMarkup } from 'react-dom/server';
    import { GemeloPIDE, VistaPideAnual, FormularioPideAnual, cuerpoPideAnual } from './src/components/GemeloPIDE';
    import { Ctx } from './src/context';
    export { api } from './src/api';
    export const panel = (jobs = {}) => renderToStaticMarkup(createElement(Ctx.Provider, { value: {
      ws:{id:'W'}, jobs, active:{}, health:{edicion:{producto:true,beta:[]}},
      run: async (f) => f(), startJob: async (f) => f() } },
      createElement(GemeloPIDE, {project:'P',feeders:['F1']})));
    export { cuerpoPideAnual };
    export const pintar = (r) => renderToStaticMarkup(createElement(VistaPideAnual, { r, ws: 'W' }));
    export const formulario = (busy) => renderToStaticMarkup(createElement(FormularioPideAnual, {
      ws: 'W', project: 'P', feeders: ['F1'], busy, planificar: async () => undefined }));`,
    resolveDir: fileURLToPath(new URL('..', import.meta.url)), loader: 'tsx' },
    bundle: true, write: false, format: 'cjs', platform: 'node', jsx: 'automatic' });
  const modulo = { exports: {} };
  new Function('require', 'module', 'exports', salida.outputFiles[0].text)(createRequire(import.meta.url), modulo, modulo.exports);
  return modulo.exports;
}

test('072:RF-18, 072:RF-24 formulario anual solicita fuentes y obras sin conceder aceptación', async () => {
  const { formulario } = await cargar();
  const html = formulario(false);
  for (const t of ['Perfil anual', 'Evaluación del modelo', 'Evidencia del corto plazo', 'Obras físicas por año', 'Identificador del estudio']) assert.ok(html.includes(t), t);
  assert.equal((html.match(/type="file"/g) ?? []).length, 3);
  assert.ok(!html.includes('type="checkbox"'));
  assert.ok(formulario(true).includes('<fieldset disabled=""'));
});

test('072:RF-25, 072:RF-28 solicitud conserva identidades y rechaza obras ambiguas', async () => {
  const { cuerpoPideAnual } = await cargar();
  const fuentes = { corto_plazo: { anio:4, anio_base:2030, caso:'P/C.IntCase', escenario:'P/C.IntScenario',
    variaciones:['P/O.IntScheme'], evidencia:{ruta:'R',sha256:'a'.repeat(64)} },
    proyeccion_anual:{ruta:'R',sha256:'b'.repeat(64)}, fuentes:{} };
  assert.throws(() => cuerpoPideAnual('P',['F1'],fuentes,'ensayo',5,'5 | Obra'), /identidad completa/);
  const b = cuerpoPideAnual('P',['F1'],fuentes,'ensayo',5,'5 | P/Obra.IntScheme');
  assert.equal(b.modo, 'anual');
  assert.deepEqual(b.anual.obras_por_anio,[{anio:5,variacion:'P/Obra.IntScheme'}]);
  assert.equal(b.anual.corto_plazo.caso, 'P/C.IntCase');
});

test('072:RF-27 vista distingue convergencia, cumplimiento, restitución y aceptación pendiente', async () => {
  const { pintar } = await cargar();
  const html = pintar({ modo:'anual',project:'P',feeders:['F1'],estado:'bloqueado_restitucion',report:'x.json',
    aceptacion_nativa:false,error:'falta obra <script>',fuentes:{perfil_sha256:'abc'},
    restitucion:{ok:false,diferencias:['escenario']},primer_anio_incumplimiento:5,
    anios:[{anio:5,anio_calendario:2035,casos:{con:'P/Con.IntCase'},obras_aplicadas:['P/O.IntScheme'],
      obras_acumuladas:['P/Corta.IntScheme','P/O.IntScheme'],antes:{converge:true,cumple:false,problemas:[{}]}}] });
  for (const t of ['Converge', 'Incumple', 'Sin confirmar', 'Aceptación nativa pendiente', 'P/Corta.IntScheme', 'abc', '2035']) assert.ok(html.includes(t),t);
  assert.ok(html.includes('&lt;script&gt;') && !html.includes('<script>'));
});

test('072:RF-18 cliente conserva POST histórico y sube solo los tres archivos PIDE', async () => {
  const { api } = await cargar();
  const previo = globalThis.fetch;
  const llamadas = [];
  globalThis.fetch = async (url, init) => { llamadas.push({url,init}); return new Response('{}'); };
  try {
    await api.pide('W',{project:'P',feeders:['F1'],implementar:false,capex:null,formato_01:null,anio_presentacion:2031});
    await api.pideFuentes('W',new File(['{}'],'p.json'),new File(['{}'],'e.json'),new File(['{}'],'c.json'));
    assert.equal(llamadas[0].url,'/api/workspaces/W/pide');
    assert.equal(JSON.parse(llamadas[0].init.body).implementar,false);
    assert.equal(llamadas[1].url,'/api/workspaces/W/pide/fuentes');
    assert.deepEqual([...llamadas[1].init.body.keys()],['perfil','evaluacion','corto_plazo']);
  } finally { globalThis.fetch = previo; }
});


test('072:RF-18 panel real conserva controles históricos y no hereda resultado de otro proyecto', async () => {
  const { panel } = await cargar();
  const html=panel({ajeno:{kind:'pide',result:{project:'Otro',modo:'anual',estado:'NO_HEREDAR'}}});
  for(const t of ['Diagnóstico y propuesta del horizonte','Continuación anual desde corto plazo aceptado',
    'Libro CAPEX','Año de presentación','Formato 01 de la empresa','Aplicar solas las obras que funcionan','Planificar']) assert.ok(html.includes(t),t);
  assert.ok(!html.includes('NO_HEREDAR'));
});
