// 102:RF-31 (auditoría del 18-11, H06): un solo punto de entrada para los dos arneses de navegador. Corre los dos
// aunque el primero falle, para que la corrida diga el estado de los dos, y sale en rojo si falla cualquiera. Cada arnés
// conserva su reportero sin_omitidas: un recorrido omitido, en «fixme», inestable o sin correr ya deja el suyo en rojo.
// 086:RF-107 (086 T79): la evidencia queda junta en output/e2e/<sha>/ (la del plano, en plano/), con el resumen de los
// dos arneses, y solo una corrida en verde la sella con SHA256SUMS: un sello viejo de la misma revisión se borra al
// empezar, para que una corrida que cae no herede el sello de otra.
//   npm run e2e:todo
// CSG_E2E_PLAYWRIGHT (solo pruebas): un guion de Node que hace de Playwright, para comprobar este agregado sin navegador.
// CSG_E2E_RESULTADOS_PLANO (solo pruebas): dónde deja sus resultados el arnés del plano (por defecto e2e/resultados).
import { spawnSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { cpSync, existsSync, mkdirSync, readdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { join, relative } from 'node:path';
import { fileURLToPath } from 'node:url';
import { evidenciaDe, revision } from './entorno.mjs';

const FRONT = fileURLToPath(new URL('../../', import.meta.url));
const ARNESES = [
  ['recorridos de la web (test/e2e)', 'test/e2e/playwright.config.mjs'],
  ['plano de la red (e2e)', 'e2e/playwright.config.ts'],
];
const SELLO = 'SHA256SUMS';

function correr(config) {
  const falso = process.env.CSG_E2E_PLAYWRIGHT;
  const [orden, argumentos] = falso
    ? [process.execPath, [falso, 'test', '-c', config]]
    : ['npx', ['playwright', 'test', '-c', config]];
  const r = spawnSync(orden, argumentos, { cwd: FRONT, stdio: 'inherit', shell: !falso && process.platform === 'win32' });
  return r.status ?? 1;
}

function ficheros(carpeta) {
  return readdirSync(carpeta, { withFileTypes: true, recursive: true })
    .filter((e) => e.isFile())
    .map((e) => relative(carpeta, join(e.parentPath ?? e.path, e.name)).split('\\').join('/'))
    .filter((r) => r !== SELLO)
    .sort();
}

/** El formato de sha256sum: «<huella>  <ruta>», una línea por fichero, en orden; se comprueba con «sha256sum -c». */
function sellar(carpeta) {
  const lineas = ficheros(carpeta).map((r) => `${createHash('sha256').update(readFileSync(join(carpeta, r))).digest('hex')}  ${r}`);
  writeFileSync(join(carpeta, SELLO), lineas.join('\n') + '\n', 'utf8');
  return lineas.length;
}

const evidencia = evidenciaDe(FRONT);
mkdirSync(evidencia, { recursive: true });
rmSync(join(evidencia, SELLO), { force: true });

const resultados = ARNESES.map(([nombre, config]) => {
  console.log(`\n=== e2e: ${nombre} (${config}) ===`);
  return [nombre, correr(config)];
});

const plano = process.env.CSG_E2E_RESULTADOS_PLANO || join(FRONT, 'e2e', 'resultados');
rmSync(join(evidencia, 'plano'), { recursive: true, force: true });
if (existsSync(plano)) cpSync(plano, join(evidencia, 'plano'), { recursive: true });
const bien = resultados.every(([, rc]) => rc === 0);
writeFileSync(join(evidencia, 'resumen_e2e.json'), JSON.stringify({
  revision: revision(FRONT),
  fecha: new Date().toISOString(),
  arneses: resultados.map(([nombre, rc]) => ({ arnes: nombre, codigo: rc })),
  verde: bien,
}, null, 1) + '\n', 'utf8');

console.log('\n=== e2e: resumen ===');
for (const [nombre, rc] of resultados) console.log(`${rc === 0 ? 'bien ' : 'FALLO'} ${nombre} (código ${rc})`);
if (bien) console.log(`evidencia sellada: ${sellar(evidencia)} ficheros en ${join(evidencia, SELLO)}`);
else console.log(`evidencia sin sellar en ${evidencia}: algún arnés falló`);
process.exit(bien ? 0 : 1);
