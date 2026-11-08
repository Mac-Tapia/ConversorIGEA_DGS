/** 002:RF-18, 002:RF-19: fronteras del frontend, resueltas con TypeScript del lock local. */
import ts from 'typescript';
import {existsSync,readFileSync,readdirSync,realpathSync} from 'node:fs';
import {dirname,extname,isAbsolute,join,relative,resolve,sep} from 'node:path';
import {fileURLToPath} from 'node:url';

// RF-19 se aplica a todos los scripts admitidos por el frontend, también JS.
const TIPOS_SCRIPT = new Map([
  ['.ts',ts.ScriptKind.TS], ['.tsx',ts.ScriptKind.TSX],
  ['.mts',ts.ScriptKind.TS], ['.cts',ts.ScriptKind.TS],
  ['.js',ts.ScriptKind.JS], ['.jsx',ts.ScriptKind.JSX],
  ['.mjs',ts.ScriptKind.JS], ['.cjs',ts.ScriptKind.JS],
]);

function archivos(raiz){
  return readdirSync(raiz,{withFileTypes:true}).flatMap(e=>e.isDirectory()?archivos(join(raiz,e.name)):[join(raiz,e.name)]);
}
function dentro(raiz,ruta){
  const rel=relative(raiz,ruta);return rel!== '..' && !rel.startsWith(`..${sep}`) && !isAbsolute(rel);
}
function capa(src,ruta){
  const partes=relative(src,ruta).split(sep);
  if(!['api','shared','features','app'].includes(partes[0]) || partes.length<2 ||
    (partes[0]==='features' && partes.length<3)) return null;
  return {nombre:partes[0],feature:partes[0]==='features'?partes[1]:null};
}

export function comprobarFronteras(frontend){
  const raiz=resolve(frontend),src=realpathSync(join(raiz,'src')),errores=[];
  const configPath=ts.findConfigFile(raiz,ts.sys.fileExists,'tsconfig.json');
  const config=configPath?ts.readConfigFile(configPath,ts.sys.readFile):{config:{}};
  if(config.error)return ['Configuración TypeScript ilegible: '+ts.flattenDiagnosticMessageText(config.error.messageText,' ')];
  const parsed=ts.parseJsonConfigFileContent(config.config,ts.sys,raiz);
  const opciones={moduleResolution:ts.ModuleResolutionKind.Bundler,...parsed.options};
  for(const file of archivos(src)){
    const origen=capa(src,file),rel=relative(raiz,file).split(sep).join('/');
    if(!origen){errores.push(`${rel}: fuera de api/shared/features/app`);continue;}
    const extension=extname(file).toLowerCase(),tipo=TIPOS_SCRIPT.get(extension);
    if(tipo===undefined){
      if(/\.[cm]?[jt]sx?$/.test(extension))errores.push(`${rel}: formato de script no admitido: ${extension}`);
      continue;
    }
    const ast=ts.createSourceFile(file,readFileSync(file,'utf8'),ts.ScriptTarget.Latest,true,tipo);
    function revisar(spec,nodo){
      const linea=ast.getLineAndCharacterOfPosition(nodo.getStart(ast)).line+1;
      const fallo=texto=>errores.push(`${rel}:${linea}: ${texto}`);
      if(typeof spec!=='string'){fallo('dependencia dinámica opaca: use una ruta literal verificable');return;}
      let destino=ts.resolveModuleName(spec,file,opciones,ts.sys).resolvedModule?.resolvedFileName;
      if(!destino && spec.startsWith('.') && existsSync(resolve(dirname(file),spec))){
        const recurso=resolve(dirname(file),spec);
        if(extname(recurso)==='.css')destino=recurso;
      }
      if(!destino){fallo(`dependencia no resuelta: ${spec}`);return;}
      destino=realpathSync(destino);
      if(!dentro(src,destino) && destino.split(sep).includes('node_modules'))return;
      if(!dentro(src,destino)){fallo(`dependencia fuera de src: ${spec}`);return;}
      const objetivo=capa(src,destino);
      if(!objetivo){fallo(`destino sin capa canónica: ${spec}`);return;}
      if(origen.nombre==='features' && objetivo.nombre==='features' && origen.feature!==objetivo.feature){
        fallo(`importa otro feature (${origen.feature} → ${objetivo.feature}): ${spec}`);return;
      }
      const permitidas={api:['api'],shared:['api','shared'],features:['api','shared','features'],app:['api','shared','features','app']};
      if(!permitidas[origen.nombre].includes(objetivo.nombre))fallo(`dependencia de capa ilícita (${origen.nombre} → ${objetivo.nombre}): ${spec}`);
    }
    function visitar(n){
      if((ts.isImportDeclaration(n)||ts.isExportDeclaration(n))&&n.moduleSpecifier)revisar(n.moduleSpecifier.text,n);
      if(ts.isImportEqualsDeclaration(n)&&ts.isExternalModuleReference(n.moduleReference))revisar(n.moduleReference.expression?.text,n);
      if(ts.isImportTypeNode(n))revisar(ts.isLiteralTypeNode(n.argument)?n.argument.literal.text:undefined,n);
      if(ts.isCallExpression(n)&&(n.expression.kind===ts.SyntaxKind.ImportKeyword ||
        (ts.isIdentifier(n.expression)&&n.expression.text==='require'))){
        const literal=n.arguments[0];revisar(literal&&ts.isStringLiteralLike(literal)?literal.text:undefined,n);
      }
      ts.forEachChild(n,visitar);
    }
    for(const d of ast.parseDiagnostics)errores.push(`${rel}: TypeScript ilegible: ${ts.flattenDiagnosticMessageText(d.messageText,' ')}`);
    for(const ref of ast.referencedFiles)revisar(ref.fileName,ast);
    visitar(ast);
  }
  return [...new Set(errores)].sort();
}

if(process.argv[1]&&resolve(process.argv[1])===fileURLToPath(import.meta.url)){
 const indice=process.argv.indexOf('--raiz');
 const raiz=indice>=0?process.argv[indice+1]:fileURLToPath(new URL('..',import.meta.url));
 const errores=comprobarFronteras(raiz);
 if(errores.length){for(const e of errores)console.error(e);process.exitCode=1;}
 else console.log('Fronteras verificadas: api/shared/features/app, sin dependencias ilícitas.');
}
