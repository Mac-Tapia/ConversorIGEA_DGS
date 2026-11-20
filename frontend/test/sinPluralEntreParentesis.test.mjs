import assert from 'node:assert/strict';
import test from 'node:test';
import { build } from 'esbuild';
import { createRequire } from 'node:module';
import { readdirSync, readFileSync } from 'node:fs';
import { join, relative } from 'node:path';
import { fileURLToPath } from 'node:url';
import ts from 'typescript';

// 086:RF-110 (revisión web W5, 2026-11-19): la vista inicial decía «Faltan 34 dato(s) que conviene dar» y había unos 78
// textos con «palabra(s)» o «palabra(es)» en 21 ficheros. La web concuerda con la cuenta («1 carga», «3 cargas») o
// usa el plural. Se leen los literales con el analizador de TypeScript: una llamada de código como `nombre(s)` o
// `new Set(s)` no es texto y no cuenta; los comentarios tampoco.
const SRC = fileURLToPath(new URL('../src/', import.meta.url));
const PLURAL_ENTRE_PARENTESIS = /\p{L}+\((?:s|es)\)/u;
const fuentes = (dir) => readdirSync(dir, { withFileTypes: true }).flatMap((e) => (e.isDirectory() ? fuentes(join(dir, e.name))
  : /\.tsx?$/.test(e.name) ? [join(dir, e.name)] : []));

const LITERALES = new Set([ts.SyntaxKind.StringLiteral, ts.SyntaxKind.NoSubstitutionTemplateLiteral, ts.SyntaxKind.TemplateHead,
  ts.SyntaxKind.TemplateMiddle, ts.SyntaxKind.TemplateTail, ts.SyntaxKind.JsxText]);

/** Los textos con «(s)»/«(es)» de un fuente: [línea, texto] de cada literal o texto JSX que lo lleva. */
function pluralesEntreParentesis(nombre, texto) {
  const sf = ts.createSourceFile(nombre, texto, ts.ScriptTarget.Latest, true,
    nombre.endsWith('.tsx') ? ts.ScriptKind.TSX : ts.ScriptKind.TS);
  const hallados = [];
  const visitar = (nodo) => {
    if (LITERALES.has(nodo.kind) && PLURAL_ENTRE_PARENTESIS.test(nodo.text)) {
      const { line } = sf.getLineAndCharacterOfPosition(nodo.getStart(sf));
      hallados.push([line + 1, nodo.text.trim().replace(/\s+/g, ' ').slice(0, 120)]);
    }
    ts.forEachChild(nodo, visitar);
  };
  visitar(sf);
  return hallados;
}

test('086:RF-110 el detector separa el texto de la web de las llamadas de código y de los comentarios', () => {
  const muestra = [
    "// un comentario con fichero(s) no cuenta",
    "const a = nombre(s) + f(s) + new Set(s).size + /x(s)/.test(s);",
    "const b = 'Faltan 3 dato(s)';",
    'const c = `${n} alimentador(es) y ${m} cliente(s)`;',
    'const d = <p>{n} carga(s) <span title="libro(s)">x</span></p>;',
  ].join('\n');
  const hallados = pluralesEntreParentesis('muestra.tsx', muestra).map(([linea]) => linea);
  assert.deepEqual(hallados, [3, 4, 4, 5, 5]);
});

test('086:RF-110 ningún texto de la web lleva «palabra(s)» ni «palabra(es)»', () => {
  const malos = [];
  for (const f of fuentes(SRC)) {
    const rel = relative(SRC, f).replaceAll('\\', '/');
    if (rel === 'api/esquema.ts') continue;
    for (const [linea, texto] of pluralesEntreParentesis(f, readFileSync(f, 'utf8'))) malos.push(`${rel}:${linea}: ${texto}`);
  }
  assert.deepEqual(malos, [], `${malos.length} texto(s) con el plural entre paréntesis:\n${malos.join('\n')}`);
});

async function formato() {
  const salida = await build({ entryPoints: ['src/shared/formato.ts'], bundle: true, write: false, format: 'cjs', platform: 'node' });
  const mod = { exports: {} };
  new Function('module', 'exports', 'require', salida.outputFiles[0].text)(mod, mod.exports, createRequire(import.meta.url));
  return mod.exports;
}

test('086:RF-110 cuenta y plural concuerdan con 1 y con varios, también con adjetivo', async () => {
  const { cuenta, plural } = await formato();
  assert.equal(cuenta(1, 'dato', 'datos'), '1 dato');
  assert.equal(cuenta(34, 'dato', 'datos'), '34 datos');
  assert.equal(cuenta(0, 'carga', 'cargas'), '0 cargas');
  assert.equal(cuenta(undefined, 'carga', 'cargas'), '— cargas');
  assert.equal(cuenta(1, 'libro nuevo', 'libros nuevos'), '1 libro nuevo');
  assert.equal(cuenta(3, 'libro nuevo', 'libros nuevos'), '3 libros nuevos');
  assert.equal(cuenta(1, 'alimentador', 'alimentadores'), '1 alimentador');
  assert.equal(cuenta(2, 'alimentador', 'alimentadores'), '2 alimentadores');
  assert.equal(plural(1, 'fallo', 'fallos'), 'fallo');
  assert.equal(plural(5, 'fallo', 'fallos'), 'fallos');
});
