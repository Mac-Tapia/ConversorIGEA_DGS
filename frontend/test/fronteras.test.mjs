import assert from 'node:assert/strict';
import test from 'node:test';
import {mkdtempSync,mkdirSync,writeFileSync} from 'node:fs';
import {join} from 'node:path';
import {spawnSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {comprobarFronteras} from '../scripts/fronteras.mjs';

const base=process.env.CSG_P23_TEMP || 'D:/converter/auditorias/vtmp/pa23front';
mkdirSync(base,{recursive:true});
function fixture(files,config={}){
 const dir=mkdtempSync(join(base,'frontera-'));
 writeFileSync(join(dir,'tsconfig.json'),JSON.stringify({compilerOptions:{moduleResolution:'bundler',...config}}));
 for(const [name,text] of Object.entries(files)){
  const path=join(dir,'src',name);mkdirSync(join(path,'..'),{recursive:true});writeFileSync(path,text);
 }
 return dir;
}

test('002:RF-18 capas permitidas componen sin depender de otro feature',()=>{
 const dir=fixture({'api/types.ts':'export type Dato=number;',
  'shared/context.ts':"import type {Dato} from '../api/types'; export type Valor=Dato;",
  'features/uno/panel.ts':"import type {Valor} from '../../shared/context'; export const x:Valor=1;",
  'app/main.ts':"import {x} from '../features/uno/panel'; export {x};"});
 assert.deepEqual(comprobarFronteras(dir),[]);
});

for(const [nombre,codigo] of Object.entries({
 estatica:"import {x} from '../dos/panel';",
 reexportacion:"export {x} from '../dos/panel';",
 dinamica:"const x=import('../dos/panel');",
 tipos:"type X=import('../dos/panel').X;",
 require:"const x=require('../dos/panel');",
 alias:"import {x} from '@dos/panel';",
})) test(`002:RF-19 frontera ilícita ${nombre} falla incluso desde CLI`,()=>{
 const dir=fixture({'features/uno/panel.ts':codigo,'features/dos/panel.ts':'export const x=1;export type X=number;'},
  {baseUrl:'.',paths:{'@dos/*':['src/features/dos/*']}});
 assert.ok(comprobarFronteras(dir).some(e=>e.includes('otro feature')));
 const run=spawnSync(process.execPath,['scripts/fronteras.mjs','--raiz',dir],{encoding:'utf8'});
 assert.equal(run.status,1,run.stdout+run.stderr);
});

test('002:RF-18 shared/api no importan features, ni app desde una feature',()=>{
 for(const origen of ['shared/ui.ts','api/client.ts','features/uno/panel.ts']){
  const dest=origen.startsWith('features')?'../../app/main':'../features/dos/panel';
  const dir=fixture({[origen]:`import '${dest}';`,'features/dos/panel.ts':'export {};','app/main.ts':'export {};'});
  assert.ok(comprobarFronteras(dir).length);
 }
});

test('002:RF-19 dependencias no resolubles y dinámicas opacas fallan cerrado',()=>{
 for(const text of ["import '../dos/ausente';","const x=import(variable);","const x=require(variable);"]){
  const dir=fixture({'features/uno/panel.ts':text});assert.ok(comprobarFronteras(dir).length);
 }
});

test('002:RF-18 archivo fuera de la organización canónica falla',()=>{
 assert.ok(comprobarFronteras(fixture({'component.ts':'export {};'})).length);
});

test('002:RF-19 un directorio llamado node_modules dentro de otra feature no elude la frontera',()=>{
 const dir=fixture({'features/uno/panel.ts':"import '../dos/node_modules/trampa';",
  'features/dos/node_modules/trampa.ts':'export {};'});
 assert.ok(comprobarFronteras(dir).some(e=>e.includes('otro feature')));
});

test('002:RF-18, 002:RF-19 el árbol entregado usa las capas y carece de excepciones',()=>{
 const frontend=new URL('..',import.meta.url);
 assert.deepEqual(comprobarFronteras(fileURLToPath(frontend)),[]);
});
