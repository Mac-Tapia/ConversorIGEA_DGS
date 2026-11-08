import assert from 'node:assert/strict';
import test from 'node:test';
import {build} from 'esbuild';
import {createRequire} from 'node:module';
import {fileURLToPath} from 'node:url';

async function pintar(ocupado=false){
 const result=await build({stdin:{contents:`
 import {createElement} from 'react';
 import {renderToStaticMarkup} from 'react-dom/server';
 import {Ctx} from './src/shared/context';
 import {CargasTab} from './src/features/powerfactory/CargasTab';
 export const pintar=(ocupado)=>renderToStaticMarkup(createElement(Ctx.Provider,{value:{
  ws:{id:'Prueba',options:{},inputs:{}},health:{edicion:{producto:true,beta:[]}},
  active:ocupado?{powerfactory:{id:'activo'}}:{},run:async f=>f(),startJob:async()=>undefined,
  jobs:{proyectos:{kind:'pf_projects',status:'done',result:{exists:true,folder:'Empresa de prueba',projects:[
   {name:'SI213',path:'Empresa A/SI213',feeders:['F1']},
   {name:'SI213',path:'Empresa B/SI213',feeders:['F2']}]}}}}},createElement(CargasTab)));`,
 resolveDir:fileURLToPath(new URL('..',import.meta.url)),loader:'tsx'},bundle:true,write:false,format:'cjs',platform:'node',jsx:'automatic'});
 const mod={exports:{}};new Function('require','module','exports',result.outputFiles[0].text)(createRequire(import.meta.url),mod,mod.exports);
 return mod.exports.pintar(ocupado);
}

test('002:RF-18, 005:RF-16 render real conserva proyectos homónimos por ruta completa',async()=>{
 const html=await pintar();
 assert.ok(html.includes('value="Empresa A/SI213"')&&html.includes('value="Empresa B/SI213"'));
 for(const t of ['Buscar','Proyecto (2 de 2)','Volver a leer proyectos','Empresa de prueba'])assert.ok(html.includes(t),t);
});

test('002:RF-18 render conserva bloqueo del botón nativo durante trabajo PF',async()=>{
 const html=await pintar(true);
 assert.match(html,/<button[^>]*disabled=""[^>]*>Volver a leer proyectos/);
});
